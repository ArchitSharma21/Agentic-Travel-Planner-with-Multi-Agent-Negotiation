import os
from pydantic import BaseModel, Field


class Settings(BaseModel):
    app_env: str = Field(default=os.getenv("APP_ENV", "dev"))
    llm_provider: str = Field(default=os.getenv("LLM_PROVIDER", "gemini"))

    gemini_api_key: str = Field(
        default=os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY", "")
    )
    gemini_model: str = Field(default=os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite"))
    gemini_fallback_model: str = Field(
        default=os.getenv("GEMINI_FALLBACK_MODEL", "gemini-2.5-flash")
    )
    gemini_rate_limit_retries: int = Field(
        default=int(os.getenv("GEMINI_RATE_LIMIT_RETRIES", "1"))
    )
    gemini_max_retry_delay_seconds: float = Field(
        default=float(os.getenv("GEMINI_MAX_RETRY_DELAY_SECONDS", "75"))
    )
    gemini_min_seconds_between_requests: float = Field(
        default=float(os.getenv("GEMINI_MIN_SECONDS_BETWEEN_REQUESTS", "0"))
    )

    openai_api_key: str = Field(default=os.getenv("OPENAI_API_KEY", ""))
    openai_model: str = Field(default=os.getenv("OPENAI_MODEL", "gpt-4o-mini"))

    anthropic_api_key: str = Field(default=os.getenv("ANTHROPIC_API_KEY", ""))
    anthropic_model: str = Field(
        default=os.getenv("ANTHROPIC_MODEL", "claude-3-5-haiku-latest")
    )

    xai_api_key: str = Field(default=os.getenv("XAI_API_KEY", ""))
    xai_model: str = Field(default=os.getenv("XAI_MODEL", "grok-3-mini"))

    max_negotiation_rounds: int = Field(default=int(os.getenv("MAX_NEGOTIATION_ROUNDS", "1")))
    default_destination: str = Field(default=os.getenv("DEFAULT_DESTINATION", "Paris"))
    server_gemini_daily_call_limit: int = Field(
        default=int(os.getenv("SERVER_GEMINI_DAILY_CALL_LIMIT", "30"))
    )
    usage_state_path: str = Field(
        default=os.getenv(
            "USAGE_STATE_PATH",
            "/tmp/agentic_travel_planner_usage.json",
        )
    )
    travel_context_mode: str = Field(default=os.getenv("TRAVEL_CONTEXT_MODE", "mcp"))
    travel_context_mcp_url: str = Field(
        default=os.getenv("TRAVEL_CONTEXT_MCP_URL", "http://127.0.0.1:7860/mcp/protocol")
    )
    travel_context_mcp_timeout_seconds: float = Field(
        default=float(os.getenv("TRAVEL_CONTEXT_MCP_TIMEOUT_SECONDS", "4"))
    )
    search_provider: str = Field(default=os.getenv("SEARCH_PROVIDER", "auto"))
    brave_search_api_key: str = Field(default=os.getenv("BRAVE_SEARCH_API_KEY", ""))
    tavily_api_key: str = Field(default=os.getenv("TAVILY_API_KEY", ""))

    def validate_required(self) -> None:
        # API keys can be supplied per request from the UI, so startup should not
        # fail just because the server has no default provider key configured.
        return None


settings = Settings()
