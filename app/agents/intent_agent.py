from app.agents.base import BaseAgent
from app.prompts import INTENT_PROMPT
from app.models.trip import TripRequest


class IntentAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="intent_agent",
            system_prompt=INTENT_PROMPT,
            temperature=0.0,
        )

    def parse_request(self, raw_user_input: str) -> TripRequest:
        data = self.invoke_json({"user_request": raw_user_input})
        normalized = self._normalize_trip_request(data)
        return TripRequest(**normalized)

    def _normalize_trip_request(self, data: dict) -> dict:
        if not isinstance(data, dict):
            data = {}

        # travelers
        travelers = data.get("travelers", 1)
        if travelers is None:
            travelers = 1
        try:
            travelers = int(travelers)
        except (TypeError, ValueError):
            travelers = 1
        data["travelers"] = travelers

        # num_days
        if data.get("num_days") is not None:
            try:
                data["num_days"] = int(data["num_days"])
            except (TypeError, ValueError):
                data["num_days"] = None

        # budget_total
        if data.get("budget_total") is not None:
            try:
                data["budget_total"] = float(data["budget_total"])
            except (TypeError, ValueError):
                data["budget_total"] = None

        # hard constraints
        data["hard_constraints"] = self._normalize_string_list(
            data.get("hard_constraints", [])
        )

        # soft preferences
        data["soft_preferences"] = self._normalize_preferences(
            data.get("soft_preferences", [])
        )

        # normalize scalar text fields
        for key in [
            "origin",
            "destination",
            "start_date",
            "end_date",
            "travel_style",
            "notes",
        ]:
            value = data.get(key)
            if value is not None and not isinstance(value, str):
                data[key] = str(value)

        return data

    def _normalize_string_list(self, items) -> list[str]:
        if not isinstance(items, list):
            return []

        output = []
        for item in items:
            if isinstance(item, str):
                item = item.strip()
                if item:
                    output.append(item)
            elif isinstance(item, dict):
                value = (
                    item.get("value")
                    or item.get("name")
                    or item.get("constraint")
                    or item.get("label")
                )
                if value:
                    output.append(str(value).strip())
        return output

    def _normalize_preferences(self, items) -> list[str]:
        if not isinstance(items, list):
            return []

        output = []
        for item in items:
            if isinstance(item, str):
                item = item.strip()
                if item:
                    output.append(item)
            elif isinstance(item, dict):
                value = item.get("value") or item.get("name") or item.get("label")
                category = item.get("category")

                if value and category:
                    output.append(f"{category}: {value}")
                elif value:
                    output.append(str(value).strip())

        return output