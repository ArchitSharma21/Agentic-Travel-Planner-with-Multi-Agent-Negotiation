from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from app.models.trip import TripRequest, WebEvidence, FinalItinerary
from app.models.agent import AgentProposal, DebateRound


class PlannerState(BaseModel):
    raw_user_input: str
    trip_request: Optional[TripRequest] = None
    evidence: List[WebEvidence] = Field(default_factory=list)
    current_round: int = 0
    proposals: List[AgentProposal] = Field(default_factory=list)
    debate_trace: List[DebateRound] = Field(default_factory=list)
    final_itinerary: Optional[FinalItinerary] = None
    final_rationale: List[str] = Field(default_factory=list)
    rejected_alternatives: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)

    def to_public_dict(self) -> Dict[str, Any]:
        return {
            "trip_request": self.trip_request.model_dump() if self.trip_request else None,
            "evidence": [e.model_dump() for e in self.evidence],
            "debate_trace": [r.model_dump() for r in self.debate_trace],
            "final_itinerary": self.final_itinerary.model_dump() if self.final_itinerary else None,
            "final_rationale": self.final_rationale,
            "rejected_alternatives": self.rejected_alternatives,
            "errors": self.errors,
        }