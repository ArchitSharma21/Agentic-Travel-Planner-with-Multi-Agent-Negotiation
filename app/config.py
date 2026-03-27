import os
from pydantic import BaseModel, Field


class Settings(BaseModel):
    app_env: str = Field(default=os.getenv("APP_ENV", "dev"))
    hf_token: str = Field(default=os.getenv("HF_TOKEN", ""))
    hf_model: str = Field(default=os.getenv("HF_MODEL", "microsoft/phi-4-mini-instruct"))
    max_negotiation_rounds: int = Field(default=int(os.getenv("MAX_NEGOTIATION_ROUNDS", "1")))
    default_destination: str = Field(default=os.getenv("DEFAULT_DESTINATION", "Paris"))

    def validate_required(self) -> None:
        missing = []
        if not self.hf_token:
            missing.append("HF_TOKEN")
        if missing:
            raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")


settings = Settings()