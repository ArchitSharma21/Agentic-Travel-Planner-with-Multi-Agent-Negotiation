from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from app.config import settings
from app.models.trip import TripCostBreakdown, TripRequest, WebEvidence
from app.tools.estimation import estimate_trip_cost_breakdown
from app.tools.search import SearchTool


@dataclass
class TravelContext:
    evidence: list[WebEvidence]
    cost_breakdown: TripCostBreakdown
    diagnostics: list[str] = field(default_factory=list)
    source: str = "direct"


class TravelContextClient:
    def __init__(
        self,
        mode: str | None = None,
        mcp_url: str | None = None,
        search_tool: SearchTool | None = None,
    ) -> None:
        self.mode = (mode or settings.travel_context_mode or "mcp").strip().lower()
        self.mcp_url = (mcp_url or settings.travel_context_mcp_url).strip()
        self.timeout_seconds = settings.travel_context_mcp_timeout_seconds
        self.search_tool = search_tool or SearchTool()

    async def build(self, trip_request: TripRequest) -> TravelContext:
        if self.mode == "direct":
            return self._build_direct(trip_request, source="direct")

        if self.mode != "mcp":
            context = self._build_direct(trip_request, source="direct")
            context.diagnostics.insert(
                0,
                f"Unknown TRAVEL_CONTEXT_MODE '{self.mode}'; used direct travel context.",
            )
            return context

        try:
            return await self._build_mcp(trip_request)
        except Exception as exc:
            context = self._build_direct(trip_request, source="direct_fallback")
            context.diagnostics.insert(
                0,
                "MCP travel context failed; used direct fallback: "
                f"{self._format_exception(exc)[:240]}",
            )
            return context

    def _build_direct(self, trip_request: TripRequest, source: str) -> TravelContext:
        evidence = self.search_tool.search_destination(
            destination=trip_request.destination or "",
            travel_style=trip_request.travel_style,
        )
        return TravelContext(
            evidence=evidence,
            cost_breakdown=estimate_trip_cost_breakdown(trip_request),
            diagnostics=list(self.search_tool.last_diagnostics),
            source=source,
        )

    async def _build_mcp(self, trip_request: TripRequest) -> TravelContext:
        async with streamablehttp_client(
            self.mcp_url,
            timeout=self.timeout_seconds,
            sse_read_timeout=timedelta(seconds=self.timeout_seconds),
        ) as (read, write, _session_id_callback):
            async with ClientSession(
                read,
                write,
                read_timeout_seconds=timedelta(seconds=self.timeout_seconds),
            ) as session:
                await session.initialize()
                result = await session.call_tool(
                    "build_travel_context",
                    {"trip_request": trip_request.model_dump()},
                )

        payload = self._extract_tool_payload(result)
        evidence = [
            WebEvidence(**item)
            for item in payload.get("evidence", [])
            if isinstance(item, dict)
        ]
        cost_breakdown = TripCostBreakdown(**payload.get("cost_breakdown", {}))
        diagnostics = list(payload.get("search_diagnostics", []) or [])
        diagnostics.insert(0, f"Travel context retrieved through MCP: {self.mcp_url}")
        return TravelContext(
            evidence=evidence,
            cost_breakdown=cost_breakdown,
            diagnostics=diagnostics,
            source="mcp",
        )

    def _extract_tool_payload(self, result: Any) -> dict:
        structured = getattr(result, "structuredContent", None)
        if isinstance(structured, dict):
            return structured

        for item in getattr(result, "content", []) or []:
            text = getattr(item, "text", None)
            if not text and isinstance(item, dict):
                text = item.get("text")
            if not text:
                continue
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed

        raise ValueError("MCP build_travel_context returned no structured payload.")

    def _format_exception(self, exc: BaseException) -> str:
        if isinstance(exc, BaseExceptionGroup):
            messages = [
                self._format_exception(item)
                for item in exc.exceptions
                if not isinstance(item, (GeneratorExit, KeyboardInterrupt))
            ]
            messages = [message for message in messages if message]
            return "; ".join(messages) or str(exc)

        cause = exc.__cause__ or exc.__context__
        if cause and cause is not exc:
            cause_message = self._format_exception(cause)
            if cause_message and cause_message != str(exc):
                return f"{exc.__class__.__name__}: {exc}; caused by {cause_message}"

        message = str(exc).strip()
        if message:
            return f"{exc.__class__.__name__}: {message}"
        return exc.__class__.__name__
