from __future__ import annotations

from app.agents.time_agent import TimeOptimizerAgent
from app.a2a.common import ProposalTaskPayload

time_agent = TimeOptimizerAgent()


async def handle_time_task(payload: dict) -> dict:
    task = ProposalTaskPayload(**payload)
    proposal = time_agent.propose(
        trip_request=task.trip_request,
        evidence=task.evidence,
        prior_proposals=task.prior_proposals,
    )
    return proposal.model_dump()