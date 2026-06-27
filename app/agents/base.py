import json
from typing import Any

from app.llm import get_llm


class BaseAgent:
    def __init__(self, name: str, system_prompt: str, temperature: float = 0.2):
        self.name = name
        self.system_prompt = system_prompt
        self.temperature = temperature

    def invoke_json(self, payload: dict, llm_config: dict | None = None) -> dict:
        llm = get_llm(
            temperature=self.temperature,
            max_new_tokens=900,
            llm_config=llm_config,
        )
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False, indent=2)},
        ]

        text = llm.invoke(
            messages=messages,
            temperature=self.temperature,
            max_tokens=900,
            response_format={"type": "json_object"},
        ).strip()

        parsed = self._try_parse_json(text)
        if parsed is not None:
            return parsed

        if getattr(llm, "provider", None) == "gemini":
            return self._fallback_json(text)

        repair_messages = [
            {
                "role": "system",
                "content": (
                    "Convert the user's text into valid JSON only. "
                    "Do not include markdown fences. "
                    "Do not include commentary."
                ),
            },
            {"role": "user", "content": text},
        ]

        repaired = llm.invoke(
            messages=repair_messages,
            temperature=0.0,
            max_tokens=900,
        ).strip()

        parsed = self._try_parse_json(repaired)
        if parsed is not None:
            return parsed

        return self._fallback_json(text)

    def _fallback_json(self, text: str) -> dict:
        return {
            "agent_name": self.name,
            "objective": "fallback",
            "assumptions": ["Model output was not valid JSON."],
            "recommendations": [text[:1200]],
            "pros": [],
            "cons": [],
            "objections": [],
            "estimated_cost": None,
            "cost_currency": None,
            "confidence": 0.2,
        }

    def normalize_proposal(self, data: dict, default_objective: str) -> dict:
        if not isinstance(data, dict):
            data = {}

        recommendations = self._normalize_string_list(data.get("recommendations"))
        if not recommendations:
            fallback_text = data.get("recommendation") or data.get("summary") or data.get("objective")
            if fallback_text:
                recommendations = [str(fallback_text)]

        assumptions = self._normalize_string_list(data.get("assumptions"))
        if "agent_name" not in data:
            assumptions.append("Model response omitted agent_name; normalized by the app.")

        return {
            "agent_name": str(data.get("agent_name") or self.name),
            "objective": str(data.get("objective") or default_objective),
            "assumptions": assumptions,
            "recommendations": recommendations,
            "pros": self._normalize_string_list(data.get("pros")),
            "cons": self._normalize_string_list(data.get("cons")),
            "objections": self._normalize_string_list(data.get("objections")),
            "estimated_cost": self._coerce_optional_float(data.get("estimated_cost")),
            "cost_currency": self._normalize_currency(data.get("cost_currency")),
            "confidence": self._coerce_confidence(data.get("confidence")),
        }

    def normalize_critic_result(self, data: dict) -> dict:
        if not isinstance(data, dict):
            return {"critic_notes": ["Critic returned malformed output."]}

        notes = self._normalize_string_list(data.get("critic_notes"))
        if not notes:
            notes = self._normalize_string_list(data.get("notes"))
        if not notes and data:
            notes = [json.dumps(data, ensure_ascii=False)[:800]]

        return {"critic_notes": notes or ["Critic returned no notes."]}

    def _normalize_string_list(self, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = value.strip()
            return [value] if value else []
        if not isinstance(value, list):
            return [str(value).strip()] if str(value).strip() else []

        output = []
        for item in value:
            if isinstance(item, str):
                text = item.strip()
            elif isinstance(item, dict):
                text = (
                    item.get("value")
                    or item.get("name")
                    or item.get("label")
                    or item.get("text")
                    or item.get("description")
                    or ""
                )
                text = str(text).strip()
            else:
                text = str(item).strip()

            if text:
                output.append(text)
        return output

    def _coerce_optional_float(self, value) -> float | None:
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _normalize_currency(self, value) -> str | None:
        if value is None:
            return None
        currency = str(value).strip().upper()
        if not currency:
            return None
        aliases = {
            "$": "USD",
            "US$": "USD",
            "DOLLAR": "USD",
            "DOLLARS": "USD",
            "€": "EUR",
            "EURO": "EUR",
            "EUROS": "EUR",
            "£": "GBP",
            "POUND": "GBP",
            "POUNDS": "GBP",
            "₹": "INR",
            "RUPEE": "INR",
            "RUPEES": "INR",
        }
        return aliases.get(currency, currency[:8])

    def _coerce_confidence(self, value) -> float:
        try:
            confidence = float(value)
        except (TypeError, ValueError):
            confidence = 0.4
        return max(0.0, min(1.0, confidence))

    def _try_parse_json(self, text: str):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                return None
        return None
