import asyncio
import json
import re
import time
import httpx

from app.agents.intent_agent import IntentAgent
from app.config import settings
from app.llm import get_llm, is_server_gemini_config
from app.models.agent import AgentProposal, DebateRound
from app.models.state import PlannerState
from app.models.trip import FinalItinerary, TripRequest, WebEvidence
from app.prompts import FINAL_MERGE_PROMPT
from app.tools.estimation import estimate_base_trip_cost
from app.tools.search import SearchTool
from app.a2a.discovery import AgentDirectory
from app.usage_limits import ensure_gemini_server_budget

from a2a.client import A2AClient
from a2a.types import AgentCard, SendMessageRequest, MessageSendParams


class TravelPlanner:
    def __init__(self) -> None:
        self.intent_agent = IntentAgent()
        self.search_tool = SearchTool()

        self.agent_directory = AgentDirectory()
        self._a2a_httpx_client: httpx.AsyncClient | None = None

        self.budget_client: A2AClient | None = None
        self.experience_client: A2AClient | None = None
        self.time_client: A2AClient | None = None
        self.critic_client: A2AClient | None = None

    async def _ensure_discovered_clients(self) -> None:
        if all(
            [
                self.budget_client,
                self.experience_client,
                self.time_client,
                self.critic_client,
            ]
        ):
            return

        cards = await self.agent_directory.discover_all()

        if self._a2a_httpx_client is None:
            self._a2a_httpx_client = httpx.AsyncClient(timeout=60.0)

        budget_card = AgentCard.model_validate(cards["budget_agent"])
        experience_card = AgentCard.model_validate(cards["experience_agent"])
        time_card = AgentCard.model_validate(cards["time_optimizer_agent"])
        critic_card = AgentCard.model_validate(cards["critic_agent"])

        self.budget_client = A2AClient(
            httpx_client=self._a2a_httpx_client,
            agent_card=budget_card,
        )
        self.experience_client = A2AClient(
            httpx_client=self._a2a_httpx_client,
            agent_card=experience_card,
        )
        self.time_client = A2AClient(
            httpx_client=self._a2a_httpx_client,
            agent_card=time_card,
        )
        self.critic_client = A2AClient(
            httpx_client=self._a2a_httpx_client,
            agent_card=critic_card,
        )

    async def aclose(self) -> None:
        if self._a2a_httpx_client is not None:
            await self._a2a_httpx_client.aclose()
            self._a2a_httpx_client = None

    def run(
        self,
        raw_user_input: str,
        llm_config: dict | None = None,
    ) -> PlannerState:
        return asyncio.run(self._run_async(raw_user_input, llm_config=llm_config))

    async def arun(
        self,
        raw_user_input: str,
        llm_config: dict | None = None,
    ) -> PlannerState:
        return await self._run_async(raw_user_input, llm_config=llm_config)

    def _trip_value(self, trip_request, key: str, default=None):
        if isinstance(trip_request, dict):
            return trip_request.get(key, default)
        return getattr(trip_request, key, default)

    def _infer_currency(self, raw_text: str = "", trip_request=None) -> str:
        explicit = self._trip_value(trip_request, "budget_currency") if trip_request else None
        if explicit:
            return str(explicit).strip().upper()

        text = (raw_text or "").lower()
        if "€" in raw_text or "euro" in text or "eur" in text:
            return "EUR"
        if "$" in raw_text or "usd" in text or "dollar" in text:
            return "USD"
        if "£" in raw_text or "gbp" in text or "pound" in text:
            return "GBP"
        if "₹" in raw_text or "inr" in text or "rupee" in text:
            return "INR"
        if "yen" in text or "jpy" in text:
            return "JPY"
        return "EUR"

    def _expected_llm_calls_per_plan(self) -> int:
        # Intent + 3 specialist agents + critic + final merge. Repair calls are
        # still metered individually if malformed model output forces them.
        return 6

    def _run_demo(self, raw_user_input: str) -> PlannerState:
        trip_request = self._demo_trip_request(raw_user_input)
        evidence = self._demo_evidence(trip_request.destination or settings.default_destination)
        proposals = self._demo_proposals(trip_request)
        critic_notes = [
            "Budget, experience, and time proposals are consistent with the stated constraints.",
            "Keep the plan walkable and cluster activities by neighborhood to reduce transit friction.",
            "Leave one flexible evening so the itinerary feels realistic rather than overpacked.",
        ]

        state = PlannerState(
            raw_user_input=raw_user_input,
            trip_request=trip_request,
            evidence=evidence,
            proposals=proposals,
            debate_trace=[
                DebateRound(
                    round_number=1,
                    proposals=proposals,
                    critic_notes=critic_notes,
                )
            ],
            errors=[
                "Demo mode used deterministic mock agent responses; no provider API calls were made."
            ],
        )

        merged = self._demo_final_itinerary(trip_request)
        merged = self._normalize_final_itinerary_output(merged, trip_request)
        merged = self._fill_empty_days(merged, trip_request)
        state.final_itinerary = FinalItinerary(**merged)
        state.final_rationale = self._build_rationale(state)
        state.rejected_alternatives = self._build_rejections(state)
        return state

    def _demo_trip_request(self, raw_user_input: str) -> TripRequest:
        text = raw_user_input.strip()
        lower = text.lower()

        destination = settings.default_destination
        destination_match = re.search(
            r"\bto\s+([A-Za-z][A-Za-z\s'-]{1,40}?)(?:\s+(?:in|under|within|for|with|on)\b|[,.]|$)",
            text,
            re.IGNORECASE,
        )
        if destination_match:
            destination = destination_match.group(1).strip()

        days = 3
        days_match = re.search(r"\b(\d{1,2})\s*[- ]?\s*day", lower)
        if days_match:
            days = max(1, min(10, int(days_match.group(1))))

        budget_total = None
        budget_match = re.search(
            r"(?:under|within|budget(?:\s+of)?|less than)\s*(?:[$€£]?\s*)?(\d{2,6})",
            lower,
        )
        if budget_match:
            budget_total = float(budget_match.group(1))

        preferences = []
        preference_keywords = [
            "museums",
            "food",
            "architecture",
            "walkable neighborhoods",
            "cafes",
            "markets",
            "history",
            "nightlife",
            "nature",
        ]
        for keyword in preference_keywords:
            if keyword in lower:
                preferences.append(keyword)
        if not preferences:
            preferences = ["local food", "walkable neighborhoods", "cultural highlights"]

        style = "budget" if budget_total or "budget" in lower or "under" in lower else "mid-range"

        return TripRequest(
            destination=destination,
            num_days=days,
            budget_total=budget_total,
            budget_currency=self._infer_currency(raw_user_input),
            travelers=1,
            travel_style=style,
            hard_constraints=["Stay within the stated budget"] if budget_total else [],
            soft_preferences=preferences,
            notes="Demo mode inferred this request locally without calling an LLM.",
        )

    def _demo_evidence(self, destination: str) -> list[WebEvidence]:
        return [
            WebEvidence(
                title=f"{destination} neighborhood guide",
                url="demo://local-neighborhood-guide",
                snippet=(
                    f"Cluster sightseeing in central {destination} neighborhoods to keep the trip walkable."
                ),
                category="planning",
            ),
            WebEvidence(
                title=f"{destination} food and market notes",
                url="demo://local-food-markets",
                snippet="Food halls, markets, and casual cafes keep costs predictable while showing local character.",
                category="food",
            ),
            WebEvidence(
                title=f"{destination} transit overview",
                url="demo://local-transit",
                snippet="Use public transit for longer hops and reserve evenings for nearby districts.",
                category="transport",
            ),
        ]

    def _demo_proposals(self, trip_request: TripRequest) -> list[AgentProposal]:
        base_estimate = estimate_base_trip_cost(trip_request)
        budget = (
            min(base_estimate, round(trip_request.budget_total * 0.85, 2))
            if trip_request.budget_total
            else base_estimate
        )
        currency = self._infer_currency(trip_request=trip_request)
        return [
            AgentProposal(
                agent_name="budget_agent",
                objective="minimize cost",
                assumptions=["Demo proposal generated without provider API calls."],
                recommendations=[
                    "Use cafes, markets, and public transit to keep daily costs predictable.",
                    "Stay in a central but not premium hotel area to reduce transport costs.",
                ],
                pros=["Keeps the plan comfortably under the target budget.", "planner_score=0.86"],
                cons=["Avoid stacking too many paid attractions on the same day."],
                estimated_cost=round(budget * 0.88, 2),
                cost_currency=currency,
                confidence=0.86,
            ),
            AgentProposal(
                agent_name="experience_agent",
                objective="maximize experience quality",
                assumptions=["Demo proposal generated without provider API calls."],
                recommendations=[
                    "Balance one anchor attraction per day with open neighborhood time.",
                    "Prioritize food, markets, and cultural stops that match the user's interests.",
                ],
                pros=["Good variety across culture, food, and wandering time.", "planner_score=0.9"],
                cons=["A few premium experiences may need to be skipped if budget is strict."],
                estimated_cost=round(budget * 0.95, 2),
                cost_currency=currency,
                confidence=0.9,
            ),
            AgentProposal(
                agent_name="time_optimizer_agent",
                objective="maximize time efficiency",
                assumptions=["Demo proposal generated without provider API calls."],
                recommendations=[
                    "Cluster each day around one area to avoid zig-zagging across the city.",
                    "Keep evenings near the final afternoon stop.",
                ],
                pros=["Low transit overhead and realistic pacing.", "planner_score=0.88"],
                cons=["Some cross-city attractions are intentionally deferred."],
                estimated_cost=round(budget * 0.9, 2),
                cost_currency=currency,
                confidence=0.88,
            ),
        ]

    def _demo_final_itinerary(self, trip_request: TripRequest) -> dict:
        destination = trip_request.destination or settings.default_destination
        interests = trip_request.soft_preferences or ["local food", "culture"]
        base_estimate = estimate_base_trip_cost(trip_request)
        total = (
            min(base_estimate, round(trip_request.budget_total * 0.85, 2))
            if trip_request.budget_total
            else base_estimate
        )
        currency = self._infer_currency(trip_request=trip_request)
        day_budget = round(total / max(1, trip_request.num_days or 3), 2)

        day_templates = [
            (
                f"Arrive and walk a central {destination} neighborhood",
                "Visit a market or food hall for a relaxed lunch",
                "Dinner near the hotel area followed by an easy evening walk",
            ),
            (
                f"Visit a museum or cultural anchor connected to {interests[0]}",
                "Explore nearby streets, cafes, and viewpoints",
                "Casual dinner in a lively local district",
            ),
            (
                "Take a slow morning in a residential neighborhood",
                "Mix one paid attraction with free outdoor time",
                "Flexible final evening for a favorite area or low-key food stop",
            ),
        ]

        daily_plan = []
        for day in range(1, (trip_request.num_days or 3) + 1):
            morning, afternoon, evening = day_templates[(day - 1) % len(day_templates)]
            daily_plan.append(
                {
                    "day": day,
                    "morning": [morning],
                    "afternoon": [afternoon],
                    "evening": [evening],
                    "estimated_day_cost": day_budget,
                }
            )

        return {
            "summary": (
                f"Demo itinerary for {destination}: a walkable, budget-aware plan balancing "
                "culture, food, and realistic pacing."
            ),
            "hotel_area": f"Central {destination}, close to transit but outside the priciest core",
            "cost_currency": currency,
            "transport_notes": [
                "Use public transit for long hops and walk within each daily cluster.",
                "Keep evenings near the afternoon area to avoid late cross-city transfers.",
            ],
            "activities": [
                {
                    "name": "Neighborhood food walk",
                    "estimated_cost": 25.0,
                    "duration_hours": 2.5,
                    "area": "Central district",
                    "reason": "Matches food and walkability preferences without overspending.",
                },
                {
                    "name": "Museum or cultural anchor",
                    "estimated_cost": 15.0,
                    "duration_hours": 2.0,
                    "area": "Museum quarter",
                    "reason": "Adds a clear daily highlight while preserving flexible time.",
                },
            ],
            "daily_plan": daily_plan,
            "estimated_total_cost": round(total, 2),
            "warnings": ["Demo mode: itinerary uses mocked agent outputs and local heuristics."],
        }

    def _compact_proposal(self, proposal) -> dict:
        if isinstance(proposal, AgentProposal):
            proposal = proposal.model_dump()

        pros = proposal.get("pros", []) or []
        score = next((item for item in pros if str(item).startswith("planner_score=")), None)

        compact = {
            "agent_name": proposal.get("agent_name"),
            "objective": proposal.get("objective"),
            "recommendations": (proposal.get("recommendations", []) or [])[:4],
            "cons": (proposal.get("cons", []) or [])[:3],
            "objections": (proposal.get("objections", []) or [])[:3],
            "estimated_cost": proposal.get("estimated_cost"),
            "confidence": proposal.get("confidence"),
        }

        if score:
            compact["planner_score"] = score.split("=", 1)[1]

        return compact

    def _fallback_agent_proposal(
        self,
        agent_name: str,
        objective: str,
        error: str,
    ) -> AgentProposal:
        return AgentProposal(
            agent_name=agent_name,
            objective=objective,
            assumptions=[f"{agent_name} failed and was replaced with a fallback."],
            recommendations=[
                "Use the other specialist proposals and hard user constraints for this run."
            ],
            pros=[f"fallback_reason={error[:300]}"],
            cons=[error[:500]],
            objections=[],
            estimated_cost=None,
            confidence=0.15,
        )

    def _critic_notes_from_trace(self, debate_trace: list[dict]) -> list[str]:
        notes: list[str] = []
        for round_data in debate_trace:
            notes.extend(round_data.get("critic_notes", []) or [])
        return notes[:6]

    def _should_parallelize_specialists(self, llm_config: dict | None) -> bool:
        return True

    def _try_parse_json(self, text: str):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                return None
        return None

    def _normalize_final_itinerary_output(self, merged: dict, trip_request) -> dict:
        if not isinstance(merged, dict):
            return {
                "summary": "Could not generate a structured itinerary.",
                "hotel_area": None,
                "cost_currency": self._infer_currency(trip_request=trip_request),
                "transport_notes": [],
                "activities": [],
                "daily_plan": [],
                "estimated_total_cost": estimate_base_trip_cost(trip_request),
                "warnings": ["Final merge output was not a valid dictionary."],
            }

        if "final_itinerary" in merged and isinstance(merged["final_itinerary"], dict):
            nested = merged["final_itinerary"]

            if "estimated_total_cost" not in nested and "estimated_total_cost" in merged:
                nested["estimated_total_cost"] = merged["estimated_total_cost"]

            if "warnings" not in nested and "warnings" in merged:
                nested["warnings"] = merged["warnings"]

            merged = nested

        if "summary" not in merged or not merged.get("summary"):
            merged["summary"] = "Generated itinerary based on the agent discussion."

        merged.setdefault("hotel_area", None)
        inferred_currency = self._infer_currency(trip_request=trip_request)
        if not merged.get("cost_currency"):
            merged["cost_currency"] = inferred_currency
        merged.setdefault("transport_notes", [])
        merged.setdefault("activities", [])
        merged.setdefault("daily_plan", [])
        merged.setdefault("warnings", [])
        if merged["cost_currency"] != inferred_currency:
            merged["warnings"].append(
                f"Cost currency reported as {merged['cost_currency']}; requested/inferred currency was {inferred_currency}."
            )

        if merged.get("estimated_total_cost") is None:
            merged["estimated_total_cost"] = estimate_base_trip_cost(trip_request)

        return merged

    def _fill_empty_days(self, merged: dict, trip_request) -> dict:
        num_days = self._trip_value(trip_request, "num_days", 3) or 3
        soft_preferences = self._trip_value(trip_request, "soft_preferences", []) or []
        interests = " / ".join(soft_preferences[:2]) or "architecture and food"

        daily_plan = merged.get("daily_plan", [])
        existing_days = {day.get("day"): day for day in daily_plan if isinstance(day, dict)}

        filled = []
        for day_num in range(1, num_days + 1):
            day_entry = existing_days.get(day_num)

            if not day_entry:
                day_entry = {
                    "day": day_num,
                    "morning": [],
                    "afternoon": [],
                    "evening": [],
                    "estimated_day_cost": 0.0,
                }

            if (
                not day_entry.get("morning")
                and not day_entry.get("afternoon")
                and not day_entry.get("evening")
            ):
                day_entry["morning"] = [
                    f"Explore a local neighborhood on foot with a focus on {interests}"
                ]
                day_entry["afternoon"] = [
                    "Visit a cafe, food hall, or market for a relaxed local meal"
                ]
                day_entry["evening"] = [
                    "Take an evening walk in a scenic district and enjoy dinner nearby"
                ]
                day_entry["estimated_day_cost"] = max(
                    day_entry.get("estimated_day_cost") or 0.0, 25.0
                )

            filled.append(day_entry)

        merged["daily_plan"] = filled
        return merged

    async def _run_async(
        self,
        raw_user_input: str,
        llm_config: dict | None = None,
    ) -> PlannerState:
        llm_config = llm_config or {}
        if llm_config.get("demo_mode"):
            return self._run_demo(raw_user_input)

        if is_server_gemini_config(llm_config):
            ensure_gemini_server_budget(self._expected_llm_calls_per_plan())

        await self._ensure_discovered_clients()
        state = PlannerState(raw_user_input=raw_user_input)

        t0 = time.time()
        trip_request = self.intent_agent.parse_request(
            raw_user_input,
            llm_config=llm_config,
        )
        if not trip_request.destination:
            trip_request.destination = settings.default_destination
            trip_request.soft_preferences.append(
                f"No destination supplied. Defaulted to {settings.default_destination}."
            )
        if not trip_request.num_days:
            trip_request.num_days = 3
        state.trip_request = trip_request
        print(f"[timing] intent_agent: {time.time() - t0:.2f}s")

        t0 = time.time()
        try:
            evidence = self.search_tool.search_destination(
                destination=trip_request.destination,
                travel_style=trip_request.travel_style,
            )
        except Exception as exc:
            evidence = []
            state.errors.append(f"Search failed: {str(exc)}")
        state.evidence = evidence
        print(f"[timing] search: {time.time() - t0:.2f}s")

        compact_evidence = [
            {"title": e.title, "snippet": e.snippet, "url": e.url}
            for e in evidence[:3]
        ]
        trip_payload = trip_request.model_dump()

        t0 = time.time()
        proposals = await self._generate_round_proposals_async(
            trip_request=trip_payload,
            evidence=compact_evidence,
            prior_proposals=[],
            llm_config=llm_config,
        )
        specialist_fallbacks = []
        for proposal in proposals:
            if any("failed and was replaced with a fallback" in item for item in proposal.assumptions):
                specialist_fallbacks.append(proposal.agent_name)
                detail = proposal.cons[0] if proposal.cons else "Unknown fallback reason."
                state.errors.append(f"{proposal.agent_name} fallback used: {detail}")
        all_specialists_fallback = (
            bool(proposals) and len(specialist_fallbacks) == len(proposals)
        )
        print(f"[timing] specialists: {time.time() - t0:.2f}s")

        t0 = time.time()
        if all_specialists_fallback:
            note = (
                "Skipped critic because all specialist agents used fallbacks; "
                "avoiding extra provider calls."
            )
            critic_result = {"critic_notes": [note]}
            state.errors.append(note)
        else:
            critic_result = await self._critic_review_async(
                trip_request=trip_payload,
                evidence=compact_evidence,
                proposals=[self._compact_proposal(p) for p in proposals],
                llm_config=llm_config,
            )
            for note in critic_result.get("critic_notes", []):
                if str(note).startswith("Critic failed:"):
                    state.errors.append(str(note))
        print(f"[timing] critic: {time.time() - t0:.2f}s")

        scored_proposals = self._score_proposals(
            trip_request=trip_payload,
            proposals=proposals,
            critic_result=critic_result,
        )

        state.proposals = scored_proposals
        state.debate_trace.append(
            DebateRound(
                round_number=1,
                proposals=scored_proposals,
                critic_notes=critic_result.get("critic_notes", []),
            )
        )

        t0 = time.time()
        if all_specialists_fallback:
            merge_skip_reason = (
                "Skipped final merge because all specialist agents used fallbacks; "
                "avoiding another provider call while quota/rate limits appear active."
            )
            state.errors.append(merge_skip_reason)
            merged = {
                "summary": "Could not fully merge the final itinerary.",
                "hotel_area": None,
                "cost_currency": self._infer_currency(trip_request=trip_request),
                "transport_notes": [],
                "activities": [],
                "daily_plan": [],
                "estimated_total_cost": estimate_base_trip_cost(trip_request),
                "warnings": [merge_skip_reason],
            }
        else:
            try:
                merged = self._merge_final(
                    trip_request=trip_payload,
                    evidence=compact_evidence,
                    proposals=[self._compact_proposal(p) for p in scored_proposals],
                    debate_trace=[r.model_dump() for r in state.debate_trace],
                    llm_config=llm_config,
                )
            except Exception as exc:
                state.errors.append(f"Final merge failed: {str(exc)}")
                merged = {
                    "summary": "Could not fully merge the final itinerary.",
                    "hotel_area": None,
                    "cost_currency": self._infer_currency(trip_request=trip_request),
                    "transport_notes": [],
                    "activities": [],
                    "daily_plan": [],
                    "estimated_total_cost": estimate_base_trip_cost(trip_request),
                    "warnings": [f"Final merge failed: {str(exc)}"],
                }
        print(f"[timing] final_merge: {time.time() - t0:.2f}s")

        if merged.get("estimated_total_cost") is None:
            merged["estimated_total_cost"] = estimate_base_trip_cost(trip_request)

        merged = self._normalize_final_itinerary_output(merged, trip_request)
        merged = self._fill_empty_days(merged, trip_request)

        state.final_itinerary = FinalItinerary(**merged)
        state.final_rationale = self._build_rationale(state)
        state.rejected_alternatives = self._build_rejections(state)
        return state

    async def _call_agent(self, client: A2AClient, payload: dict) -> dict:
        send_message_payload = {
            "message": {
                "role": "user",
                "parts": [
                    {
                        "kind": "text",
                        "text": json.dumps(payload, ensure_ascii=False),
                    }
                ],
                "messageId": str(time.time_ns()),
            }
        }

        request = SendMessageRequest(
            id=str(time.time_ns()),
            params=MessageSendParams(**send_message_payload),
        )

        response = await client.send_message(request)
        return self._extract_a2a_json_result(response.model_dump())

    async def _call_agent_or_fallback(
        self,
        client: A2AClient,
        payload: dict,
        agent_name: str,
        objective: str,
    ) -> AgentProposal:
        try:
            result = await self._call_agent(client, payload)
            return AgentProposal(**result)
        except Exception as exc:
            return self._fallback_agent_proposal(
                agent_name=agent_name,
                objective=objective,
                error=str(exc),
            )

    def _extract_a2a_json_result(self, result: dict) -> dict:
        if result.get("error"):
            error = result["error"]
            message = error.get("message") if isinstance(error, dict) else str(error)
            raise Exception(message or f"A2A agent failed: {result}")

        artifacts = (
            result.get("result", {}).get("artifacts", [])
            or result.get("artifacts", [])
            or []
        )
        for artifact in artifacts:
            for part in artifact.get("parts", []):
                text = part.get("text")
                if text:
                    parsed = self._try_parse_json(text)
                    if parsed is not None:
                        return parsed

        message = result.get("result", {}).get("message") or result.get("message")
        if isinstance(message, dict):
            for part in message.get("parts", []):
                text = part.get("text")
                if text:
                    parsed = self._try_parse_json(text)
                    if parsed is not None:
                        return parsed

        raise Exception(f"Could not parse A2A response: {result}")

    async def _generate_round_proposals_async(
        self,
        trip_request: dict,
        evidence: list[dict],
        prior_proposals: list[dict],
        llm_config: dict | None = None,
    ) -> list[AgentProposal]:
        payload = {
            "trip_request": trip_request,
            "evidence": evidence,
            "prior_proposals": prior_proposals,
            "llm_config": llm_config or {},
        }

        if not self._should_parallelize_specialists(llm_config):
            budget_p = await self._call_agent_or_fallback(
                self.budget_client,
                payload,
                agent_name="budget_agent",
                objective="minimize cost",
            )
            exp_p = await self._call_agent_or_fallback(
                self.experience_client,
                payload,
                agent_name="experience_agent",
                objective="maximize experience quality",
            )
            time_p = await self._call_agent_or_fallback(
                self.time_client,
                payload,
                agent_name="time_optimizer_agent",
                objective="maximize time efficiency",
            )
            return [
                budget_p,
                exp_p,
                time_p,
            ]

        budget_task = self._call_agent_or_fallback(
            self.budget_client,
            payload,
            agent_name="budget_agent",
            objective="minimize cost",
        )
        exp_task = self._call_agent_or_fallback(
            self.experience_client,
            payload,
            agent_name="experience_agent",
            objective="maximize experience quality",
        )
        time_task = self._call_agent_or_fallback(
            self.time_client,
            payload,
            agent_name="time_optimizer_agent",
            objective="maximize time efficiency",
        )
        budget_p, exp_p, time_p = await asyncio.gather(
            budget_task, exp_task, time_task
        )

        return [
            budget_p,
            exp_p,
            time_p,
        ]

    async def _critic_review_async(self, trip_request, evidence, proposals, llm_config=None):
        payload = {
            "trip_request": trip_request,
            "evidence": evidence,
            "proposals": proposals,
            "llm_config": llm_config or {},
        }

        try:
            return await self._call_agent(self.critic_client, payload)
        except Exception as exc:
            return {"critic_notes": [f"Critic failed: {str(exc)}"]}

    def _score_proposals(
        self,
        trip_request: dict,
        proposals: list[AgentProposal],
        critic_result: dict,
    ) -> list[AgentProposal]:
        budget_total = trip_request.get("budget_total")
        critic_notes = " ".join(critic_result.get("critic_notes", [])).lower()

        for proposal in proposals:
            cost_score = 1.0
            if budget_total and proposal.estimated_cost:
                if proposal.estimated_cost <= budget_total:
                    cost_score = 1.0
                elif proposal.estimated_cost <= budget_total * 1.15:
                    cost_score = 0.6
                else:
                    cost_score = 0.2

            evidence_score = 0.8 if proposal.recommendations else 0.4
            confidence_score = max(0.0, min(1.0, proposal.confidence))

            penalty = 0.0
            if proposal.agent_name.replace("_", " ") in critic_notes:
                penalty += 0.15
            if any("constraint" in c.lower() for c in proposal.cons):
                penalty += 0.10

            final_score = max(
                0.0,
                min(
                    1.0,
                    (0.35 * cost_score)
                    + (0.30 * evidence_score)
                    + (0.35 * confidence_score)
                    - penalty,
                ),
            )

            proposal.pros.append(f"planner_score={round(final_score, 3)}")

        return proposals

    def _final_itinerary_response_format(self, num_days: int) -> dict:
        return {
            "type": "json_schema",
            "json_schema": {
                "name": "final_itinerary",
                "strict": True,
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "summary": {"type": "string"},
                        "hotel_area": {"type": ["string", "null"]},
                        "cost_currency": {"type": "string"},
                        "transport_notes": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "activities": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "name": {"type": "string"},
                                    "estimated_cost": {"type": ["number", "null"]},
                                    "duration_hours": {"type": ["number", "null"]},
                                    "area": {"type": ["string", "null"]},
                                    "reason": {"type": ["string", "null"]},
                                },
                                "required": [
                                    "name",
                                    "estimated_cost",
                                    "duration_hours",
                                    "area",
                                    "reason",
                                ],
                            },
                        },
                        "daily_plan": {
                            "type": "array",
                            "minItems": num_days,
                            "maxItems": num_days,
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "day": {"type": "integer"},
                                    "morning": {"type": "array", "items": {"type": "string"}},
                                    "afternoon": {"type": "array", "items": {"type": "string"}},
                                    "evening": {"type": "array", "items": {"type": "string"}},
                                    "estimated_day_cost": {"type": ["number", "null"]},
                                },
                                "required": [
                                    "day",
                                    "morning",
                                    "afternoon",
                                    "evening",
                                    "estimated_day_cost",
                                ],
                            },
                        },
                        "estimated_total_cost": {"type": ["number", "null"]},
                        "warnings": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "required": [
                        "summary",
                        "hotel_area",
                        "cost_currency",
                        "transport_notes",
                        "activities",
                        "daily_plan",
                        "estimated_total_cost",
                        "warnings",
                    ],
                },
            },
        }

    def _merge_final(
        self,
        trip_request: dict,
        evidence: list[dict],
        proposals: list[dict],
        debate_trace: list[dict],
        llm_config: dict | None = None,
    ) -> dict:
        num_days = trip_request.get("num_days") or 3

        merge_payload = {
            "trip_request": {
                "destination": trip_request.get("destination"),
                "num_days": num_days,
                "budget_total": trip_request.get("budget_total"),
                "budget_currency": self._infer_currency(trip_request=trip_request),
                "travelers": trip_request.get("travelers", 1),
                "travel_style": trip_request.get("travel_style"),
                "hard_constraints": trip_request.get("hard_constraints", []),
                "soft_preferences": trip_request.get("soft_preferences", []),
                "notes": trip_request.get("notes"),
            },
            "evidence": evidence[:3],
            "proposals": proposals,
            "critic_notes": self._critic_notes_from_trace(debate_trace),
        }

        messages = [
            {"role": "system", "content": FINAL_MERGE_PROMPT},
            {
                "role": "user",
                "content": (
                    "Merge the specialist proposals into one final itinerary.\n"
                    "Return JSON matching the provided schema exactly.\n\n"
                    f"INPUT:\n{json.dumps(merge_payload, ensure_ascii=False, indent=2)}"
                ),
            },
        ]

        final_llm = get_llm(
            temperature=0.2,
            max_new_tokens=1100,
            llm_config=llm_config,
        )

        text = final_llm.invoke(
            messages=messages,
            temperature=0.1,
            max_tokens=1400,
            response_format=self._final_itinerary_response_format(num_days),
        ).strip()

        parsed = self._try_parse_json(text)
        if parsed is not None:
            return parsed

        repair_messages = [
            {
                "role": "system",
                "content": (
                    "Convert the user's text into valid JSON only. "
                    "Do not include markdown fences or commentary."
                ),
            },
            {"role": "user", "content": text},
        ]

        repaired = final_llm.invoke(
            messages=repair_messages,
            temperature=0.0,
            max_tokens=1400,
        ).strip()

        parsed = self._try_parse_json(repaired)
        if parsed is not None:
            return parsed

        return {
            "summary": "Generated a fallback itinerary because the final merge output was malformed.",
            "hotel_area": None,
            "cost_currency": self._infer_currency(trip_request=trip_request),
            "transport_notes": [],
            "activities": [],
            "daily_plan": [],
            "estimated_total_cost": estimate_base_trip_cost(trip_request),
            "warnings": [
                "Final merge output was not valid JSON.",
                "A fallback itinerary was generated.",
            ],
        }

    def _build_rationale(self, state: PlannerState) -> list[str]:
        lines = []
        for proposal in state.proposals:
            score_str = next(
                (p for p in proposal.pros if p.startswith("planner_score=")),
                "planner_score=unknown",
            )
            lines.append(
                f"{proposal.agent_name} emphasized {proposal.objective}; {score_str}."
            )
        lines.append("Final itinerary balances cost, experience quality, and scheduling realism.")
        lines.append("Critic feedback was incorporated before final merge.")
        return lines

    def _build_rejections(self, state: PlannerState) -> list[str]:
        rejected = []
        for proposal in state.proposals:
            for objection in proposal.objections:
                rejected.append(f"{proposal.agent_name}: {objection}")
        return rejected[:10]
