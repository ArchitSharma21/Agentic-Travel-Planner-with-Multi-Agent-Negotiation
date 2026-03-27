import asyncio
import json
import time
import httpx

from app.agents.intent_agent import IntentAgent
from app.config import settings
from app.llm import get_llm
from app.models.agent import AgentProposal, DebateRound
from app.models.state import PlannerState
from app.models.trip import FinalItinerary
from app.prompts import FINAL_MERGE_PROMPT
from app.tools.estimation import estimate_base_trip_cost
from app.tools.search import SearchTool
from app.a2a.discovery import AgentDirectory

from a2a.client import A2AClient
from a2a.types import AgentCard, SendMessageRequest, MessageSendParams


class TravelPlanner:
    def __init__(self) -> None:
        self.intent_agent = IntentAgent()
        self.search_tool = SearchTool()
        self.final_llm = get_llm(temperature=0.2, max_new_tokens=1100)

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

    def run(self, raw_user_input: str) -> PlannerState:
        return asyncio.run(self._run_async(raw_user_input))

    def _trip_value(self, trip_request, key: str, default=None):
        if isinstance(trip_request, dict):
            return trip_request.get(key, default)
        return getattr(trip_request, key, default)

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
        merged.setdefault("transport_notes", [])
        merged.setdefault("activities", [])
        merged.setdefault("daily_plan", [])
        merged.setdefault("warnings", [])

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

    async def _run_async(self, raw_user_input: str) -> PlannerState:
        await self._ensure_discovered_clients()
        state = PlannerState(raw_user_input=raw_user_input)

        t0 = time.time()
        trip_request = self.intent_agent.parse_request(raw_user_input)
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
        )
        print(f"[timing] specialists_parallel: {time.time() - t0:.2f}s")

        t0 = time.time()
        critic_result = await self._critic_review_async(
            trip_request=trip_payload,
            evidence=compact_evidence,
            proposals=[p.model_dump() for p in proposals],
        )
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
        try:
            merged = self._merge_final(
                trip_request=trip_payload,
                evidence=compact_evidence,
                proposals=[p.model_dump() for p in scored_proposals],
                debate_trace=[r.model_dump() for r in state.debate_trace],
            )
        except Exception as exc:
            state.errors.append(f"Final merge failed: {str(exc)}")
            merged = {
                "summary": "Could not fully merge the final itinerary.",
                "hotel_area": None,
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

    def _extract_a2a_json_result(self, result: dict) -> dict:
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
    ) -> list[AgentProposal]:
        payload = {
            "trip_request": trip_request,
            "evidence": evidence,
            "prior_proposals": prior_proposals,
        }

        budget_task = self._call_agent(self.budget_client, payload)
        exp_task = self._call_agent(self.experience_client, payload)
        time_task = self._call_agent(self.time_client, payload)

        budget_p, exp_p, time_p = await asyncio.gather(
            budget_task, exp_task, time_task
        )

        return [
            AgentProposal(**budget_p),
            AgentProposal(**exp_p),
            AgentProposal(**time_p),
        ]

    async def _critic_review_async(self, trip_request, evidence, proposals):
        payload = {
            "trip_request": trip_request,
            "evidence": evidence,
            "proposals": proposals,
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
    ) -> dict:
        num_days = trip_request.get("num_days") or 3

        merge_payload = {
            "trip_request": {
                "destination": trip_request.get("destination"),
                "num_days": num_days,
                "budget_total": trip_request.get("budget_total"),
                "travelers": trip_request.get("travelers", 1),
                "travel_style": trip_request.get("travel_style"),
                "hard_constraints": trip_request.get("hard_constraints", []),
                "soft_preferences": trip_request.get("soft_preferences", []),
                "notes": trip_request.get("notes"),
            },
            "evidence": evidence[:3],
            "proposals": proposals,
            "debate_trace": debate_trace,
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

        text = self.final_llm.invoke(
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

        repaired = self.final_llm.invoke(
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