from typing import List
from duckduckgo_search import DDGS
from app.models.trip import WebEvidence


class SearchTool:
    def __init__(self) -> None:
        pass

    def search_destination(self, destination: str, travel_style: str | None = None) -> List[WebEvidence]:
        query_parts = [destination, "travel attractions neighborhoods food transport"]
        if travel_style:
            query_parts.append(travel_style)

        query = " ".join(query_parts)

        results = []
        with DDGS() as ddgs:
            raw = ddgs.text(query, max_results=3)
            results = list(raw)

        evidence: List[WebEvidence] = []
        for item in results:
            evidence.append(
                WebEvidence(
                    title=item.get("title", ""),
                    url=item.get("href", ""),
                    snippet=(item.get("body", "") or "")[:350],
                    category="travel_web",
                )
            )
        return evidence