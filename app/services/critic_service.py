from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.agents.critic_agent import CriticAgent

router = APIRouter(prefix="/agents/critic", tags=["critic"])
agent = CriticAgent()


class CriticRequest(BaseModel):
    trip_request: dict
    evidence: list[dict] = Field(default_factory=list)
    proposals: list[dict] = Field(default_factory=list)


@router.post("/review")
async def review(payload: CriticRequest) -> dict:
    return agent.review(
        trip_request=payload.trip_request,
        evidence=payload.evidence,
        proposals=payload.proposals,
    )