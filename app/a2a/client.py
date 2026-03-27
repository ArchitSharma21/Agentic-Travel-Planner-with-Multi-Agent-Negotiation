import uuid
import json
import httpx


class A2AAgentClient:
    def __init__(self, endpoint: str):
        self.endpoint = endpoint.rstrip("/")

    async def call(self, payload: dict) -> dict:
        request_body = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "message/send",
            "params": {
                "message": {
                    "messageId": uuid.uuid4().hex,
                    "role": "user",
                    "parts": [
                        {
                            "kind": "text",
                            "text": json.dumps(payload, ensure_ascii=False),
                        }
                    ],
                }
            },
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(self.endpoint, json=request_body)
            resp.raise_for_status()
            data = resp.json()

        if "error" in data:
            raise Exception(data["error"].get("message", "Unknown A2A error"))

        if "result" not in data:
            raise Exception(f"A2A response missing result: {data}")

        return self._extract_result_payload(data["result"])

    def _extract_result_payload(self, result: dict) -> dict:
        # Case 1: Task-style response with artifacts
        artifacts = result.get("artifacts", []) or []
        for artifact in artifacts:
            parts = artifact.get("parts", []) or []
            for part in parts:
                text = part.get("text")
                if text:
                    return self._parse_text_payload(text)

        # Case 2: Message-style response
        message = result.get("message")
        if isinstance(message, dict):
            parts = message.get("parts", []) or []
            for part in parts:
                text = part.get("text")
                if text:
                    return self._parse_text_payload(text)

        # Case 3: direct parts on result
        parts = result.get("parts", []) or []
        for part in parts:
            text = part.get("text")
            if text:
                return self._parse_text_payload(text)

        raise Exception(f"Could not extract structured payload from A2A response: {result}")

    def _parse_text_payload(self, text: str) -> dict:
        text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                return json.loads(text[start:end + 1])
            raise Exception(f"Returned text was not valid JSON: {text[:500]}")