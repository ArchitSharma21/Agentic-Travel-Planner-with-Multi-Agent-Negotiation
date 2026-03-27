from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.agents.budget_agent import BudgetAgent

router = APIRouter(prefix="/agents/budget", tags=["budget"])
agent = BudgetAgent()


class ProposalRequest(BaseModel):
    trip_request: dict
    evidence: list[dict] = Field(default_factory=list)
    prior_proposals: list[dict] = Field(default_factory=list)


@router.post("/propose")
async def propose(payload: ProposalRequest) -> dict:
    proposal = agent.propose(
        trip_request=payload.trip_request,
        evidence=payload.evidence,
        prior_proposals=payload.prior_proposals,
    )
    return proposal.model_dump()