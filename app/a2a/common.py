from __future__ import annotations

from pydantic import BaseModel, Field


class ProposalTaskPayload(BaseModel):
    trip_request: dict
    evidence: list[dict] = Field(default_factory=list)
    pricing_context: dict = Field(default_factory=dict)
    prior_proposals: list[dict] = Field(default_factory=list)


class CriticTaskPayload(BaseModel):
    trip_request: dict
    evidence: list[dict] = Field(default_factory=list)
    pricing_context: dict = Field(default_factory=dict)
    proposals: list[dict] = Field(default_factory=list)
