from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import List

import httpx
from duckduckgo_search import DDGS

from app.config import settings
from app.models.trip import WebEvidence


class SearchTool:
    def __init__(self, cache_path: str = "/tmp/travel_planner_search_cache.json") -> None:
        self.cache_path = Path(cache_path)
        self.last_diagnostics: list[str] = []

    def search_destination(
        self,
        destination: str,
        travel_style: str | None = None,
    ) -> List[WebEvidence]:
        self.last_diagnostics = []
        cache_key = self._cache_key(destination, travel_style)
        cached = self._read_cache(cache_key)
        if cached:
            self.last_diagnostics.append("Search used cached destination evidence.")
            return cached

        evidence: list[WebEvidence] = []

        for provider in self._provider_chain():
            try:
                evidence.extend(provider(destination, travel_style))
            except Exception as exc:
                self.last_diagnostics.append(
                    f"{provider.__name__.replace('_', ' ').strip()} failed: {str(exc)[:220]}"
                )

            evidence = self._dedupe(evidence)
            if len(evidence) >= 3:
                break

        if not evidence:
            evidence = self._local_fallback(destination, travel_style)
            self.last_diagnostics.append(
                "Search used deterministic local fallback evidence because live providers returned nothing."
            )

        evidence = evidence[:5]
        self._write_cache(cache_key, evidence)
        return evidence

    def _provider_chain(self):
        provider = (settings.search_provider or "auto").strip().lower()
        providers = {
            "brave": self._brave_search,
            "tavily": self._tavily_search,
            "duckduckgo": self._duckduckgo_search,
            "ddg": self._duckduckgo_search,
            "wikivoyage": self._wikivoyage_search,
            "wikipedia": self._wikipedia_search,
        }

        if provider in providers:
            return [
                providers[provider],
                self._duckduckgo_search,
                self._wikivoyage_search,
                self._wikipedia_search,
            ]

        chain = []
        if settings.brave_search_api_key:
            chain.append(self._brave_search)
        if settings.tavily_api_key:
            chain.append(self._tavily_search)
        chain.extend(
            [
                self._duckduckgo_search,
                self._wikivoyage_search,
                self._wikipedia_search,
            ]
        )
        return chain

    def _cache_key(self, destination: str, travel_style: str | None) -> str:
        return "|".join(
            [
                (destination or "").strip().lower(),
                (travel_style or "").strip().lower(),
            ]
        )

    def _read_cache(self, cache_key: str) -> list[WebEvidence]:
        try:
            data = json.loads(self.cache_path.read_text())
        except Exception:
            return []

        item = data.get(cache_key)
        if not item:
            return []

        if time.time() - item.get("created_at", 0) > 60 * 60 * 24:
            return []

        try:
            return [WebEvidence(**entry) for entry in item.get("evidence", [])]
        except Exception:
            return []

    def _write_cache(self, cache_key: str, evidence: list[WebEvidence]) -> None:
        try:
            data = json.loads(self.cache_path.read_text())
        except Exception:
            data = {}

        data[cache_key] = {
            "created_at": time.time(),
            "evidence": [item.model_dump() for item in evidence],
        }

        try:
            self.cache_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        except Exception:
            return

    def _duckduckgo_search(
        self,
        destination: str,
        travel_style: str | None,
    ) -> list[WebEvidence]:
        query = self._destination_query(destination, travel_style)

        with DDGS(timeout=8) as ddgs:
            results = list(ddgs.text(query, max_results=3))

        evidence: list[WebEvidence] = []
        for item in results:
            evidence.append(
                WebEvidence(
                    title=item.get("title", ""),
                    url=item.get("href", ""),
                    snippet=(item.get("body", "") or "")[:350],
                    category="travel_web:duckduckgo",
                )
            )
        return evidence

    def _brave_search(
        self,
        destination: str,
        travel_style: str | None,
    ) -> list[WebEvidence]:
        if not settings.brave_search_api_key:
            raise RuntimeError("BRAVE_SEARCH_API_KEY is not configured.")

        response = httpx.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={
                "q": self._destination_query(destination, travel_style),
                "count": 5,
                "safesearch": "moderate",
            },
            headers={
                "Accept": "application/json",
                "X-Subscription-Token": settings.brave_search_api_key,
            },
            timeout=8.0,
        )
        response.raise_for_status()
        data = response.json()

        evidence = []
        for item in data.get("web", {}).get("results", [])[:5]:
            evidence.append(
                WebEvidence(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    snippet=(item.get("description", "") or "")[:350],
                    category="travel_web:brave",
                )
            )
        return evidence

    def _tavily_search(
        self,
        destination: str,
        travel_style: str | None,
    ) -> list[WebEvidence]:
        if not settings.tavily_api_key:
            raise RuntimeError("TAVILY_API_KEY is not configured.")

        response = httpx.post(
            "https://api.tavily.com/search",
            headers={
                "Authorization": f"Bearer {settings.tavily_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "query": self._destination_query(destination, travel_style),
                "search_depth": "basic",
                "max_results": 5,
                "include_answer": False,
            },
            timeout=8.0,
        )
        response.raise_for_status()
        data = response.json()

        evidence = []
        for item in data.get("results", [])[:5]:
            evidence.append(
                WebEvidence(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    snippet=(item.get("content", "") or "")[:350],
                    category="travel_web:tavily",
                )
            )
        return evidence

    def _destination_query(self, destination: str, travel_style: str | None) -> str:
        query_parts = [destination, "travel attractions neighborhoods food transport"]
        if travel_style:
            query_parts.append(travel_style)
        return " ".join(query_parts)

    def _wikivoyage_search(
        self,
        destination: str,
        travel_style: str | None,
    ) -> list[WebEvidence]:
        return self._mediawiki_search(
            base_url="https://en.wikivoyage.org/w/api.php",
            site_url="https://en.wikivoyage.org/wiki/",
            query=f"{destination} travel guide",
            category="travel_web:wikivoyage",
        )

    def _wikipedia_search(
        self,
        destination: str,
        travel_style: str | None,
    ) -> list[WebEvidence]:
        return self._mediawiki_search(
            base_url="https://en.wikipedia.org/w/api.php",
            site_url="https://en.wikipedia.org/wiki/",
            query=f"{destination} tourism attractions neighborhoods food transport",
            category="travel_web:wikipedia",
        )

    def _mediawiki_search(
        self,
        base_url: str,
        site_url: str,
        query: str,
        category: str,
    ) -> list[WebEvidence]:
        response = httpx.get(
            base_url,
            params={
                "action": "query",
                "list": "search",
                "srsearch": query,
                "srlimit": 3,
                "format": "json",
                "utf8": 1,
            },
            headers={"User-Agent": "agentic-travel-planner/1.0"},
            timeout=8.0,
        )
        response.raise_for_status()
        data = response.json()

        evidence: list[WebEvidence] = []
        for item in data.get("query", {}).get("search", []):
            title = item.get("title", "")
            snippet = self._clean_snippet(item.get("snippet", ""))
            if not title:
                continue
            evidence.append(
                WebEvidence(
                    title=title,
                    url=f"{site_url}{title.replace(' ', '_')}",
                    snippet=snippet[:350],
                    category=category,
                )
            )
        return evidence

    def _clean_snippet(self, snippet: str) -> str:
        text = re.sub(r"<[^>]+>", "", snippet or "")
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _dedupe(self, evidence: list[WebEvidence]) -> list[WebEvidence]:
        output: list[WebEvidence] = []
        seen: set[str] = set()
        for item in evidence:
            key = (item.url or item.title).strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            output.append(item)
        return output

    def _local_fallback(
        self,
        destination: str,
        travel_style: str | None,
    ) -> list[WebEvidence]:
        style_text = f" for a {travel_style} trip" if travel_style else ""
        return [
            WebEvidence(
                title=f"{destination} planning baseline",
                url="app://local-travel-baseline",
                snippet=(
                    f"Plan {destination}{style_text} by clustering each day around one "
                    "neighborhood, mixing one anchor activity with nearby food, walking, "
                    "and transit-light options."
                ),
                category="travel_web:local_fallback",
            ),
            WebEvidence(
                title=f"{destination} cost-aware itinerary fallback",
                url="app://local-cost-aware-itinerary",
                snippet=(
                    "Use public transport, markets, casual restaurants, and free outdoor "
                    "or neighborhood time when live destination search is unavailable."
                ),
                category="travel_web:local_fallback",
            ),
        ]
