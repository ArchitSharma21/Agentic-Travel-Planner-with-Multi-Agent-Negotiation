from __future__ import annotations

from app.agents.experience_agent import ExperienceAgent
from app.a2a.common import ProposalTaskPayload

experience_agent = ExperienceAgent()


async def handle_experience_task(payload: dict) -> dict:
    task = ProposalTaskPayload(**payload)
    proposal = experience_agent.propose(
        trip_request=task.trip_request,
        evidence=task.evidence,
        prior_proposals=task.prior_proposals,
    )
    return proposal.model_dump()