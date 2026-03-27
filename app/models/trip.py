from typing import List, Optional
from pydantic import BaseModel, Field


class TripRequest(BaseModel):
    origin: Optional[str] = None
    destination: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    num_days: Optional[int] = None
    budget_total: Optional[float] = None
    travelers: Optional[int] = 1
    travel_style: Optional[str] = None
    hard_constraints: List[str] = Field(default_factory=list)
    soft_preferences: List[str] = Field(default_factory=list)
    notes: Optional[str] = None


class WebEvidence(BaseModel):
    title: str
    url: str
    snippet: str
    category: str


class ActivityOption(BaseModel):
    name: str
    estimated_cost: Optional[float] = None
    duration_hours: Optional[float] = None
    area: Optional[str] = None
    reason: Optional[str] = None


class DayPlan(BaseModel):
    day: int
    morning: List[str] = Field(default_factory=list)
    afternoon: List[str] = Field(default_factory=list)
    evening: List[str] = Field(default_factory=list)
    estimated_day_cost: Optional[float] = None


class FinalItinerary(BaseModel):
    summary: str
    hotel_area: Optional[str] = None
    transport_notes: List[str] = Field(default_factory=list)
    activities: List[ActivityOption] = Field(default_factory=list)
    daily_plan: List[DayPlan] = Field(default_factory=list)
    estimated_total_cost: Optional[float] = None
    warnings: List[str] = Field(default_factory=list)