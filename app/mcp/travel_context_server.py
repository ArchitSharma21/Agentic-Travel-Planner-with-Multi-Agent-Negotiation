from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from app.models.trip import TripRequest
from app.tools.estimation import estimate_trip_cost_breakdown
from app.tools.search import SearchTool


mcp = FastMCP("agentic-travel-context", streamable_http_path="/mcp/protocol")


@mcp.tool()
def search_destination(destination: str, travel_style: str | None = None) -> dict:
    """Return no-account destination evidence from DDG, Wikivoyage/Wikipedia, cache, or local fallback."""
    search_tool = SearchTool()
    evidence = search_tool.search_destination(destination, travel_style)
    return {
        "evidence": [item.model_dump() for item in evidence],
        "diagnostics": search_tool.last_diagnostics,
    }


@mcp.tool()
def estimate_trip_cost(trip_request: dict) -> dict:
    """Return deterministic lodging, meal, local transport, and activity cost estimates."""
    trip = TripRequest(**trip_request)
    return estimate_trip_cost_breakdown(trip).model_dump()


@mcp.tool()
def build_travel_context(trip_request: dict) -> dict:
    """Return combined destination evidence and deterministic pricing context for a trip request."""
    trip = TripRequest(**trip_request)
    search_tool = SearchTool()
    evidence = search_tool.search_destination(
        destination=trip.destination or "",
        travel_style=trip.travel_style,
    )
    cost_breakdown = estimate_trip_cost_breakdown(trip)
    return {
        "evidence": [item.model_dump() for item in evidence],
        "search_diagnostics": search_tool.last_diagnostics,
        "cost_breakdown": cost_breakdown.model_dump(),
    }


if __name__ == "__main__":
    mcp.run()
