from contextlib import asynccontextmanager

import gradio as gr
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.config import settings
from app.graph.planner import TravelPlanner
from app.ui.gradio_app import build_gradio_app
from app.a2a.sdk_apps import register_official_a2a_apps
from app.usage_limits import UsageLimitExceeded


class PlanRequest(BaseModel):
    user_input: str = Field(..., min_length=5)
    llm_provider: str | None = None
    api_key: str | None = None
    model: str | None = None
    demo_mode: bool = False


planner = TravelPlanner()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.validate_required()
    yield
    await planner.aclose()


app = FastAPI(
    title="Agentic Travel Planner",
    version="1.0.0",
    lifespan=lifespan,
)

register_official_a2a_apps(app)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/plan")
async def plan_trip(request: PlanRequest):
    try:
        llm_config = {
            "provider": request.llm_provider,
            "api_key": request.api_key,
            "model": request.model,
            "demo_mode": request.demo_mode,
        }
        state = await planner.arun(request.user_input, llm_config=llm_config)
        return state.to_public_dict()
    except UsageLimitExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Planning failed: {str(exc)}") from exc


gradio_app = build_gradio_app(planner)
app = gr.mount_gradio_app(app, gradio_app, path="/")
