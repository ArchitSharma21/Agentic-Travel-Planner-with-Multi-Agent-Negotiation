from __future__ import annotations

from a2a.types import AgentCard, AgentCapabilities, AgentInterface, AgentSkill

BASE_URL = "http://127.0.0.1:7860"


def make_budget_card() -> AgentCard:
    return AgentCard(
        name="Budget Agent",
        description="Specialist travel-planning agent focused on minimizing trip cost.",
        url=f"{BASE_URL}/a2a/budget",
        preferredTransport="JSONRPC",
        version="1.0.0",
        defaultInputModes=["text"],
        defaultOutputModes=["text"],
        capabilities=AgentCapabilities(
            streaming=False,
            pushNotifications=False,
            stateTransitionHistory=False,
        ),
        additionalInterfaces=[
            AgentInterface(
                url=f"{BASE_URL}/a2a/budget",
                transport="JSONRPC",
            )
        ],
        skills=[
            AgentSkill(
                id="budget_planning",
                name="Budget trip optimization",
                description="Optimizes travel plans for affordability and lower-cost transport/accommodation choices.",
                tags=["budget", "travel", "cost", "itinerary"],
                examples=[
                    "Plan a budget-friendly 4-day trip to Hamburg.",
                    "Suggest an affordable city itinerary.",
                ],
            )
        ],
    )


def make_experience_card() -> AgentCard:
    return AgentCard(
        name="Experience Agent",
        description="Specialist travel-planning agent focused on quality, food, architecture, and memorable experiences.",
        url=f"{BASE_URL}/a2a/experience",
        preferredTransport="JSONRPC",
        version="1.0.0",
        defaultInputModes=["text"],
        defaultOutputModes=["text"],
        capabilities=AgentCapabilities(
            streaming=False,
            pushNotifications=False,
            stateTransitionHistory=False,
        ),
        additionalInterfaces=[
            AgentInterface(
                url=f"{BASE_URL}/a2a/experience",
                transport="JSONRPC",
            )
        ],
        skills=[
            AgentSkill(
                id="experience_planning",
                name="Experience optimization",
                description="Optimizes travel plans for memorable experiences, food, culture, and architecture.",
                tags=["experience", "travel", "food", "architecture", "culture"],
                examples=[
                    "Plan a memorable architecture and food trip.",
                    "Recommend high-quality cultural experiences.",
                ],
            )
        ],
    )


def make_time_card() -> AgentCard:
    return AgentCard(
        name="Time Optimizer Agent",
        description="Specialist travel-planning agent focused on pacing, feasibility, and efficient routing.",
        url=f"{BASE_URL}/a2a/time",
        preferredTransport="JSONRPC",
        version="1.0.0",
        defaultInputModes=["text"],
        defaultOutputModes=["text"],
        capabilities=AgentCapabilities(
            streaming=False,
            pushNotifications=False,
            stateTransitionHistory=False,
        ),
        additionalInterfaces=[
            AgentInterface(
                url=f"{BASE_URL}/a2a/time",
                transport="JSONRPC",
            )
        ],
        skills=[
            AgentSkill(
                id="time_optimization",
                name="Time-efficient trip planning",
                description="Optimizes pacing, feasibility, and low-backtracking itineraries.",
                tags=["time", "routing", "feasibility", "itinerary", "travel"],
                examples=[
                    "Make this itinerary more efficient.",
                    "Group nearby places into realistic days.",
                ],
            )
        ],
    )


def make_critic_card() -> AgentCard:
    return AgentCard(
        name="Critic Agent",
        description="Specialist travel-planning agent focused on contradictions, weak grounding, and feasibility problems.",
        url=f"{BASE_URL}/a2a/critic",
        preferredTransport="JSONRPC",
        version="1.0.0",
        defaultInputModes=["text"],
        defaultOutputModes=["text"],
        capabilities=AgentCapabilities(
            streaming=False,
            pushNotifications=False,
            stateTransitionHistory=False,
        ),
        additionalInterfaces=[
            AgentInterface(
                url=f"{BASE_URL}/a2a/critic",
                transport="JSONRPC",
            )
        ],
        skills=[
            AgentSkill(
                id="proposal_critique",
                name="Travel plan critique",
                description="Reviews travel proposals for contradictions, cost issues, weak grounding, and feasibility problems.",
                tags=["critic", "validation", "review", "travel", "feasibility"],
                examples=[
                    "Review this itinerary for contradictions.",
                    "Check whether this trip plan is realistic.",
                ],
            )
        ],
    )