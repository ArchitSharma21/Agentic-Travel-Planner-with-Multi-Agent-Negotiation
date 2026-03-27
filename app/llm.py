from huggingface_hub import InferenceClient
from app.config import settings


class HFChatLLM:
    def __init__(self, temperature: float = 0.2, max_tokens: int = 700):
        self.client = InferenceClient(api_key=settings.hf_token)
        self.model = settings.hf_model
        self.temperature = temperature
        self.max_tokens = max_tokens

    def invoke(
        self,
        messages,
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: dict | None = None,
    ) -> str:
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature if temperature is None else temperature,
            "max_tokens": self.max_tokens if max_tokens is None else max_tokens,
        }

        if response_format is not None:
            kwargs["response_format"] = response_format

        response = self.client.chat.completions.create(**kwargs)
        return response.choices[0].message.content or ""


def get_llm(temperature: float = 0.2, max_new_tokens: int = 700) -> HFChatLLM:
    return HFChatLLM(
        temperature=temperature,
        max_tokens=max_new_tokens,
    )