from __future__ import annotations

from dataclasses import dataclass
import re
import threading
import time
from typing import Any

import httpx

from app.config import settings
from app.usage_limits import record_gemini_server_call


_gemini_rate_lock = threading.Lock()
_last_gemini_request_at = 0.0


PROVIDER_LABELS = {
    "gemini": "Gemini (Google AI Studio)",
    "openai": "OpenAI / ChatGPT",
    "anthropic": "Anthropic / Claude",
    "xai": "xAI / Grok",
}

PROVIDER_ALIASES = {
    "gemini": "gemini",
    "google": "gemini",
    "google ai studio": "gemini",
    "openai": "openai",
    "chatgpt": "openai",
    "gpt": "openai",
    "anthropic": "anthropic",
    "claude": "anthropic",
    "xai": "xai",
    "x.ai": "xai",
    "grok": "xai",
}

PROVIDER_KEY_ENV_NAMES = {
    "gemini": "GEMINI_API_KEY or GOOGLE_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "xai": "XAI_API_KEY",
}


@dataclass(frozen=True)
class ProviderCredentials:
    provider: str
    api_key: str
    model: str
    uses_server_api_key: bool


def normalize_provider(provider: str | None) -> str:
    raw_provider = (provider or settings.llm_provider or "gemini").strip()
    lower_provider = raw_provider.lower()

    for provider_id, label in PROVIDER_LABELS.items():
        if lower_provider == label.lower():
            return provider_id

    if lower_provider in PROVIDER_ALIASES:
        return PROVIDER_ALIASES[lower_provider]

    supported = ", ".join(PROVIDER_LABELS.values())
    raise ValueError(f"Unsupported AI provider '{raw_provider}'. Choose one of: {supported}.")


def get_provider_choices() -> list[str]:
    return list(PROVIDER_LABELS.values())


def provider_to_label(provider: str | None) -> str:
    return PROVIDER_LABELS[normalize_provider(provider)]


def _unique_values(items: list[str]) -> list[str]:
    output = []
    for item in items:
        item = item.strip()
        if item and item not in output:
            output.append(item)
    return output


def get_model_choices(provider: str | None) -> list[str]:
    provider_id = normalize_provider(provider)
    if provider_id == "gemini":
        return _unique_values(
            [
                settings.gemini_model,
                settings.gemini_fallback_model,
                "gemini-3.1-flash-lite",
                "gemini-2.5-flash-lite",
                "gemini-2.5-flash",
                "gemini-2.5-pro",
            ]
        )
    if provider_id == "openai":
        return _unique_values([settings.openai_model])
    if provider_id == "anthropic":
        return _unique_values([settings.anthropic_model])
    if provider_id == "xai":
        return _unique_values([settings.xai_model])
    return []


def default_model_for_provider(provider: str | None) -> str:
    provider_id = normalize_provider(provider)
    choices = get_model_choices(provider_id)
    if choices:
        return choices[0]
    return _settings_model(provider_id)


def build_llm_config(
    provider: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
    demo_mode: bool = False,
) -> dict[str, Any]:
    config: dict[str, Any] = {"provider": normalize_provider(provider)}

    if api_key and api_key.strip():
        config["api_key"] = api_key.strip()

    if model and model.strip():
        config["model"] = model.strip()

    if demo_mode:
        config["demo_mode"] = True

    return config


def is_server_gemini_config(llm_config: dict[str, Any] | None = None) -> bool:
    llm_config = llm_config or {}
    provider = normalize_provider(llm_config.get("provider"))
    api_key = (llm_config.get("api_key") or "").strip()
    return provider == "gemini" and not api_key


def _settings_api_key(provider: str) -> str:
    if provider == "gemini":
        return settings.gemini_api_key
    if provider == "openai":
        return settings.openai_api_key
    if provider == "anthropic":
        return settings.anthropic_api_key
    if provider == "xai":
        return settings.xai_api_key
    return ""


def _settings_model(provider: str) -> str:
    if provider == "gemini":
        return settings.gemini_model
    if provider == "openai":
        return settings.openai_model
    if provider == "anthropic":
        return settings.anthropic_model
    if provider == "xai":
        return settings.xai_model
    return ""


def _resolve_credentials(
    provider: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
    llm_config: dict[str, Any] | None = None,
) -> ProviderCredentials:
    llm_config = llm_config or {}
    resolved_provider = normalize_provider(provider or llm_config.get("provider"))
    explicit_api_key = (api_key or llm_config.get("api_key") or "").strip()
    resolved_api_key = explicit_api_key
    resolved_model = (model or llm_config.get("model") or "").strip()

    if not resolved_api_key:
        resolved_api_key = _settings_api_key(resolved_provider).strip()

    if not resolved_model:
        resolved_model = _settings_model(resolved_provider).strip()

    if not resolved_api_key:
        env_names = PROVIDER_KEY_ENV_NAMES[resolved_provider]
        label = PROVIDER_LABELS[resolved_provider]
        raise RuntimeError(
            f"No API key found for {label}. Add one in the UI or set {env_names}."
        )

    if not resolved_model:
        label = PROVIDER_LABELS[resolved_provider]
        raise RuntimeError(f"No model configured for {label}.")

    return ProviderCredentials(
        provider=resolved_provider,
        api_key=resolved_api_key,
        model=resolved_model,
        uses_server_api_key=not explicit_api_key,
    )


def _message_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks = []
        for item in content:
            if isinstance(item, dict) and "text" in item:
                chunks.append(str(item["text"]))
            else:
                chunks.append(str(item))
        return "\n".join(chunks)
    return str(content)


def _raise_provider_error(
    response: httpx.Response,
    provider_label: str,
    uses_server_api_key: bool = False,
) -> None:
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = response.text[:1000]
        if response.status_code == 429 and uses_server_api_key:
            raise RuntimeError(
                f"{provider_label} shared project key hit a provider quota/rate limit. "
                "Please paste your own API key in the API Key field to continue, "
                "or try again later. Provider details: "
                f"{detail}"
            ) from None

        raise RuntimeError(
            f"{provider_label} API request failed ({response.status_code}): {detail}"
        ) from None


def _is_gemini_overloaded(response: httpx.Response) -> bool:
    if response.status_code != 503:
        return False

    try:
        data = response.json()
    except ValueError:
        return True

    error = data.get("error", {}) if isinstance(data, dict) else {}
    return error.get("status") == "UNAVAILABLE" or response.status_code == 503


def _gemini_retry_delay_seconds(response: httpx.Response) -> float | None:
    if response.status_code != 429:
        return None

    retry_after = response.headers.get("retry-after")
    if retry_after:
        try:
            return max(0.0, float(retry_after))
        except ValueError:
            pass

    try:
        data = response.json()
    except ValueError:
        return None

    error = data.get("error", {}) if isinstance(data, dict) else {}
    if error.get("status") != "RESOURCE_EXHAUSTED":
        return None

    message = str(error.get("message") or "")
    match = re.search(r"retry in ([0-9]+(?:\.[0-9]+)?)s", message, re.IGNORECASE)
    if not match:
        return None

    return max(0.0, float(match.group(1)))


def _pace_gemini_request() -> None:
    global _last_gemini_request_at

    min_delay = max(0.0, settings.gemini_min_seconds_between_requests)
    if min_delay <= 0:
        return

    with _gemini_rate_lock:
        now = time.monotonic()
        wait_seconds = (_last_gemini_request_at + min_delay) - now
        if wait_seconds > 0:
            time.sleep(wait_seconds)

        _last_gemini_request_at = time.monotonic()


class ProviderChatLLM:
    def __init__(
        self,
        provider: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 700,
        llm_config: dict[str, Any] | None = None,
    ):
        credentials = _resolve_credentials(
            provider=provider,
            api_key=api_key,
            model=model,
            llm_config=llm_config,
        )
        self.provider = credentials.provider
        self.api_key = credentials.api_key
        self.model = credentials.model
        self.uses_server_api_key = credentials.uses_server_api_key
        self.temperature = temperature
        self.max_tokens = max_tokens

    def invoke(
        self,
        messages,
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: dict | None = None,
    ) -> str:
        resolved_temperature = self.temperature if temperature is None else temperature
        resolved_max_tokens = self.max_tokens if max_tokens is None else max_tokens

        if self.provider == "gemini":
            return self._invoke_gemini(
                messages,
                resolved_temperature,
                resolved_max_tokens,
                response_format,
            )
        if self.provider == "openai":
            return self._invoke_openai(
                messages,
                resolved_temperature,
                resolved_max_tokens,
                response_format,
            )
        if self.provider == "anthropic":
            return self._invoke_anthropic(messages, resolved_temperature, resolved_max_tokens)
        if self.provider == "xai":
            return self._invoke_xai(
                messages,
                resolved_temperature,
                resolved_max_tokens,
                response_format,
            )

        raise ValueError(f"Unsupported AI provider '{self.provider}'.")

    def _invoke_gemini(
        self,
        messages,
        temperature: float,
        max_tokens: int,
        response_format: dict | None,
    ) -> str:
        system_messages = []
        contents = []

        for message in messages:
            role = message.get("role", "user")
            text = _message_text(message.get("content", ""))

            if role == "system":
                system_messages.append(text)
                continue

            contents.append(
                {
                    "role": "model" if role == "assistant" else "user",
                    "parts": [{"text": text}],
                }
            )

        generation_config: dict[str, Any] = {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
        }
        if response_format is not None:
            generation_config["responseMimeType"] = "application/json"

        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": generation_config,
        }
        if system_messages:
            payload["systemInstruction"] = {
                "parts": [{"text": "\n\n".join(system_messages)}]
            }

        data = self._post_gemini_generate(
            model=self.model,
            payload=payload,
        )

        candidates = data.get("candidates") or []
        if not candidates:
            return ""

        parts = candidates[0].get("content", {}).get("parts", []) or []
        return "".join(part.get("text", "") for part in parts)

    def _post_gemini_generate(self, model: str, payload: dict[str, Any]) -> dict:
        response = self._send_gemini_request(model=model, payload=payload)

        fallback_model = settings.gemini_fallback_model.strip()
        should_try_fallback = (
            not self.uses_server_api_key
            and fallback_model
            and fallback_model != model
            and _is_gemini_overloaded(response)
        )

        if should_try_fallback:
            response = self._send_gemini_request(
                model=fallback_model,
                payload=payload,
            )

        _raise_provider_error(
            response,
            PROVIDER_LABELS["gemini"],
            uses_server_api_key=self.uses_server_api_key,
        )
        return response.json()

    def _send_gemini_request(self, model: str, payload: dict[str, Any]) -> httpx.Response:
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent"
        )

        retries = max(0, settings.gemini_rate_limit_retries)
        max_delay = max(0.0, settings.gemini_max_retry_delay_seconds)

        with httpx.Client(timeout=120.0) as client:
            for attempt in range(retries + 1):
                _pace_gemini_request()

                if self.uses_server_api_key:
                    record_gemini_server_call()

                response = client.post(
                    url,
                    headers={"x-goog-api-key": self.api_key},
                    json=payload,
                )

                retry_delay = _gemini_retry_delay_seconds(response)
                should_retry = (
                    retry_delay is not None
                    and attempt < retries
                    and retry_delay <= max_delay
                )
                if not should_retry:
                    return response

                time.sleep(retry_delay + 0.5)

        return response

    def _invoke_openai(
        self,
        messages,
        temperature: float,
        max_tokens: int,
        response_format: dict | None,
    ) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_completion_tokens": max_tokens,
        }
        if response_format is not None:
            payload["response_format"] = response_format

        return self._invoke_openai_compatible(
            url="https://api.openai.com/v1/chat/completions",
            payload=payload,
        )

    def _invoke_xai(
        self,
        messages,
        temperature: float,
        max_tokens: int,
        response_format: dict | None,
    ) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format is not None:
            payload["response_format"] = {"type": "json_object"}

        return self._invoke_openai_compatible(
            url="https://api.x.ai/v1/chat/completions",
            payload=payload,
        )

    def _invoke_openai_compatible(self, url: str, payload: dict[str, Any]) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        with httpx.Client(timeout=120.0) as client:
            response = client.post(url, headers=headers, json=payload)
            _raise_provider_error(response, PROVIDER_LABELS[self.provider])
            data = response.json()

        return data["choices"][0]["message"].get("content") or ""

    def _invoke_anthropic(self, messages, temperature: float, max_tokens: int) -> str:
        system_messages = []
        anthropic_messages = []

        for message in messages:
            role = message.get("role", "user")
            text = _message_text(message.get("content", ""))

            if role == "system":
                system_messages.append(text)
            elif role == "assistant":
                anthropic_messages.append({"role": "assistant", "content": text})
            else:
                anthropic_messages.append({"role": "user", "content": text})

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": anthropic_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if system_messages:
            payload["system"] = "\n\n".join(system_messages)

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

        with httpx.Client(timeout=120.0) as client:
            response = client.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=payload,
            )
            _raise_provider_error(response, PROVIDER_LABELS["anthropic"])
            data = response.json()

        return "".join(
            block.get("text", "")
            for block in data.get("content", [])
            if block.get("type") == "text"
        )

def get_llm(
    temperature: float = 0.2,
    max_new_tokens: int = 700,
    provider: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
    llm_config: dict[str, Any] | None = None,
) -> ProviderChatLLM:
    return ProviderChatLLM(
        provider=provider,
        api_key=api_key,
        model=model,
        temperature=temperature,
        max_tokens=max_new_tokens,
        llm_config=llm_config,
    )
