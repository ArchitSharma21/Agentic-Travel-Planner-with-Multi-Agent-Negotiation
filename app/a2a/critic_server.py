from __future__ import annotations

from app.agents.critic_agent import CriticAgent
from app.a2a.common import CriticTaskPayload

critic_agent = CriticAgent()


async def handle_critic_task(payload: dict) -> dict:
    task = CriticTaskPayload(**payload)
    result = critic_agent.review(
        trip_request=task.trip_request,
        evidence=task.evidence,
        proposals=task.proposals,
    )
    return result