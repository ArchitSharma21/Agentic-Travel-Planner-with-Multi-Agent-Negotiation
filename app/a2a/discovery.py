from __future__ import annotations

import httpx


class AgentDiscoveryError(Exception):
    pass


class AgentDirectory:
    def __init__(self, base_url: str = "http://127.0.0.1:7860"):
        self.base_url = base_url.rstrip("/")

    async def fetch_card(self, path: str) -> dict:
        url = f"{self.base_url}{path}"
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.json()

    async def discover_all(self) -> dict[str, dict]:
        cards = {
            "budget_agent": await self.fetch_card("/a2a/budget/.well-known/agent-card.json"),
            "experience_agent": await self.fetch_card("/a2a/experience/.well-known/agent-card.json"),
            "time_optimizer_agent": await self.fetch_card("/a2a/time/.well-known/agent-card.json"),
            "critic_agent": await self.fetch_card("/a2a/critic/.well-known/agent-card.json"),
        }
        return cards

    def extract_rpc_url(self, card: dict) -> str:
        # Prefer top-level URL
        url = card.get("url")
        if url:
            return url

        # Fallback to additionalInterfaces
        interfaces = card.get("additionalInterfaces", []) or []
        for interface in interfaces:
            if interface.get("transport") == "JSONRPC" and interface.get("url"):
                return interface["url"]

        raise AgentDiscoveryError(f"Could not find JSON-RPC URL in agent card: {card}")