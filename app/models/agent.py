from typing import List, Optional
from pydantic import BaseModel, Field


class AgentProposal(BaseModel):
    agent_name: str
    objective: str
    assumptions: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)
    pros: List[str] = Field(default_factory=list)
    cons: List[str] = Field(default_factory=list)
    objections: List[str] = Field(default_factory=list)
    estimated_cost: Optional[float] = None
    confidence: float = 0.5


class DebateRound(BaseModel):
    round_number: int
    proposals: List[AgentProposal] = Field(default_factory=list)
    critic_notes: List[str] = Field(default_factory=list)


class PlannerResponse(BaseModel):
    parsed_request: dict
    evidence: List[dict]
    debate_trace: List[DebateRound]
    final_itinerary: dict
    final_rationale: List[str]
    rejected_alternatives: List[str]