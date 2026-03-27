import json
from app.llm import get_llm


class BaseAgent:
    def __init__(self, name: str, system_prompt: str, temperature: float = 0.2):
        self.name = name
        self.system_prompt = system_prompt
        self.temperature = temperature
        self.llm = get_llm(temperature=temperature, max_new_tokens=900)

    def invoke_json(self, payload: dict) -> dict:
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False, indent=2)},
        ]

        text = self.llm.invoke(
            messages=messages,
            temperature=self.temperature,
            max_tokens=900,
        ).strip()

        parsed = self._try_parse_json(text)
        if parsed is not None:
            return parsed

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

        repaired = self.llm.invoke(
            messages=repair_messages,
            temperature=0.0,
            max_tokens=900,
        ).strip()

        parsed = self._try_parse_json(repaired)
        if parsed is not None:
            return parsed

        return {
            "agent_name": self.name,
            "objective": "fallback",
            "assumptions": ["Model output was not valid JSON."],
            "recommendations": [text[:1200]],
            "pros": [],
            "cons": [],
            "objections": [],
            "estimated_cost": None,
            "confidence": 0.2,
        }

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