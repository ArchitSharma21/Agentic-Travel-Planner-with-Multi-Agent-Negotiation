from __future__ import annotations

from app.agents.budget_agent import BudgetAgent
from app.a2a.common import ProposalTaskPayload

budget_agent = BudgetAgent()


async def handle_budget_task(payload: dict) -> dict:
    task = ProposalTaskPayload(**payload)
    proposal = budget_agent.propose(
        trip_request=task.trip_request,
        evidence=task.evidence,
        prior_proposals=task.prior_proposals,
    )
    return proposal.model_dump()