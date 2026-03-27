from __future__ import annotations

from fastapi import FastAPI

from app.a2a.cards import (
    make_budget_card,
    make_critic_card,
    make_experience_card,
    make_time_card,
)


def register_agent_cards(app: FastAPI) -> None:
    budget_card = make_budget_card()
    experience_card = make_experience_card()
    time_card = make_time_card()
    critic_card = make_critic_card()

    @app.get("/a2a/budget/.well-known/agent-card.json")
    async def budget_agent_card():
        return budget_card.model_dump(mode="json", exclude_none=True)

    @app.get("/a2a/experience/.well-known/agent-card.json")
    async def experience_agent_card():
        return experience_card.model_dump(mode="json", exclude_none=True)

    @app.get("/a2a/time/.well-known/agent-card.json")
    async def time_agent_card():
        return time_card.model_dump(mode="json", exclude_none=True)

    @app.get("/a2a/critic/.well-known/agent-card.json")
    async def critic_agent_card():
        return critic_card.model_dump(mode="json", exclude_none=True)