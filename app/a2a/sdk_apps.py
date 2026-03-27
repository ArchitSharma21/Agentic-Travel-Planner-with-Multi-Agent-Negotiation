from __future__ import annotations

from fastapi import FastAPI

from a2a.server.apps.jsonrpc.fastapi_app import A2AFastAPIApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore

from app.a2a.cards import (
    make_budget_card,
    make_critic_card,
    make_experience_card,
    make_time_card,
)
from app.a2a.sdk_executors import ProposalExecutor
from app.agents.budget_agent import BudgetAgent
from app.agents.critic_agent import CriticAgent
from app.agents.experience_agent import ExperienceAgent
from app.agents.time_agent import TimeOptimizerAgent


budget_agent = BudgetAgent()
experience_agent = ExperienceAgent()
time_agent = TimeOptimizerAgent()
critic_agent = CriticAgent()


def _budget_handler(payload: dict) -> dict:
    proposal = budget_agent.propose(
        trip_request=payload.get("trip_request", {}),
        evidence=payload.get("evidence", []),
        prior_proposals=payload.get("prior_proposals", []),
    )
    return proposal.model_dump()


def _experience_handler(payload: dict) -> dict:
    proposal = experience_agent.propose(
        trip_request=payload.get("trip_request", {}),
        evidence=payload.get("evidence", []),
        prior_proposals=payload.get("prior_proposals", []),
    )
    return proposal.model_dump()


def _time_handler(payload: dict) -> dict:
    proposal = time_agent.propose(
        trip_request=payload.get("trip_request", {}),
        evidence=payload.get("evidence", []),
        prior_proposals=payload.get("prior_proposals", []),
    )
    return proposal.model_dump()


def _critic_handler(payload: dict) -> dict:
    return critic_agent.review(
        trip_request=payload.get("trip_request", {}),
        evidence=payload.get("evidence", []),
        proposals=payload.get("proposals", []),
    )


def register_official_a2a_apps(app: FastAPI) -> None:
    budget_server = A2AFastAPIApplication(
        agent_card=make_budget_card(),
        http_handler=DefaultRequestHandler(
            agent_executor=ProposalExecutor(_budget_handler, "Budget Agent"),
            task_store=InMemoryTaskStore(),
        ),
    )
    budget_server.add_routes_to_app(
        app,
        agent_card_url="/a2a/budget/.well-known/agent-card.json",
        rpc_url="/a2a/budget",
    )

    experience_server = A2AFastAPIApplication(
        agent_card=make_experience_card(),
        http_handler=DefaultRequestHandler(
            agent_executor=ProposalExecutor(_experience_handler, "Experience Agent"),
            task_store=InMemoryTaskStore(),
        ),
    )
    experience_server.add_routes_to_app(
        app,
        agent_card_url="/a2a/experience/.well-known/agent-card.json",
        rpc_url="/a2a/experience",
    )

    time_server = A2AFastAPIApplication(
        agent_card=make_time_card(),
        http_handler=DefaultRequestHandler(
            agent_executor=ProposalExecutor(_time_handler, "Time Agent"),
            task_store=InMemoryTaskStore(),
        ),
    )
    time_server.add_routes_to_app(
        app,
        agent_card_url="/a2a/time/.well-known/agent-card.json",
        rpc_url="/a2a/time",
    )

    critic_server = A2AFastAPIApplication(
        agent_card=make_critic_card(),
        http_handler=DefaultRequestHandler(
            agent_executor=ProposalExecutor(_critic_handler, "Critic Agent"),
            task_store=InMemoryTaskStore(),
        ),
    )
    critic_server.add_routes_to_app(
        app,
        agent_card_url="/a2a/critic/.well-known/agent-card.json",
        rpc_url="/a2a/critic",
    )