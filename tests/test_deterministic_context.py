import unittest
from unittest.mock import patch

from app.config import settings
from app.graph.planner import TravelPlanner
from app.models.trip import TripCostBreakdown, TripRequest, WebEvidence
from app.tools.estimation import estimate_trip_cost_breakdown
from app.tools.search import SearchTool
from app.tools.travel_context import TravelContext, TravelContextClient


class DeterministicContextTests(unittest.TestCase):
    def test_dynamic_cost_index_changes_destination_costs_without_saved_city_table(self):
        def fake_country(destination):
            return ("PH", "mock Philippines") if destination == "Manila" else ("DK", "mock Denmark")

        def fake_gdp(country_code):
            return (12000, "mock low PPP") if country_code == "PH" else (76000, "mock high PPP")

        with (
            patch("app.tools.estimation._destination_country_code", fake_country),
            patch("app.tools.estimation._world_bank_gdp_ppp", fake_gdp),
        ):
            manila = estimate_trip_cost_breakdown(
                TripRequest(
                    destination="Manila",
                    num_days=6,
                    travelers=1,
                    travel_style="mid-range",
                    budget_currency="EUR",
                )
            )
            copenhagen = estimate_trip_cost_breakdown(
                TripRequest(
                    destination="Copenhagen",
                    num_days=4,
                    travelers=1,
                    travel_style="mid-range",
                    budget_currency="EUR",
                )
            )

        self.assertEqual(manila.pricing_mode, "dynamic_cost_index+live_fx")
        self.assertEqual(copenhagen.pricing_mode, "dynamic_cost_index+live_fx")
        self.assertLess(manila.total, copenhagen.total)

    def test_day_costs_vary_and_sum_to_total(self):
        planner = TravelPlanner()
        trip = TripRequest(
            destination="Test City",
            num_days=4,
            travelers=1,
            travel_style="mid-range",
            budget_currency="EUR",
        )
        breakdown = TripCostBreakdown(
            lodging=300,
            meals=160,
            local_transport=40,
            activities=100,
            total=600,
            currency="EUR",
            pricing_mode="test",
        )
        merged = {
            "warnings": [],
            "daily_plan": [
                {"day": 1, "morning": ["arrival walk"], "afternoon": ["market"], "evening": ["dinner"]},
                {"day": 2, "morning": ["museum"], "afternoon": ["castle tour"], "evening": ["food tour"]},
                {"day": 3, "morning": ["park"], "afternoon": ["library"], "evening": ["cafe"]},
                {"day": 4, "morning": ["canal tour"], "afternoon": ["departure"], "evening": ["departure"]},
            ],
        }

        output = planner._apply_deterministic_costs(merged, trip, breakdown)
        costs = [day["estimated_day_cost"] for day in output["daily_plan"]]

        self.assertEqual(round(sum(costs), 2), 600)
        self.assertGreater(len(set(costs)), 1)

    def test_mcp_failure_falls_back_to_direct_context(self):
        fallback = TravelContext(
            evidence=[
                WebEvidence(
                    title="Fallback",
                    url="app://fallback",
                    snippet="fallback",
                    category="test",
                )
            ],
            cost_breakdown=TripCostBreakdown(total=123, currency="EUR"),
            diagnostics=["direct fallback used"],
            source="direct_fallback",
        )

        async def failing_mcp(_trip_request):
            raise RuntimeError("mock MCP failure")

        client = TravelContextClient(mode="mcp")
        with (
            patch.object(client, "_build_mcp", failing_mcp),
            patch.object(client, "_build_direct", return_value=fallback),
        ):
            context = __import__("asyncio").run(
                client.build(TripRequest(destination="Anywhere", num_days=2))
            )

        self.assertEqual(context.source, "direct_fallback")
        self.assertIn("MCP travel context failed", context.diagnostics[0])

    def test_signed_search_providers_are_preferred_when_keys_exist(self):
        original_provider = settings.search_provider
        original_brave = settings.brave_search_api_key
        original_tavily = settings.tavily_api_key
        try:
            settings.search_provider = "auto"
            settings.brave_search_api_key = "brave-key"
            settings.tavily_api_key = "tavily-key"
            names = [provider.__name__ for provider in SearchTool()._provider_chain()]
        finally:
            settings.search_provider = original_provider
            settings.brave_search_api_key = original_brave
            settings.tavily_api_key = original_tavily

        self.assertLess(names.index("_brave_search"), names.index("_duckduckgo_search"))
        self.assertLess(names.index("_tavily_search"), names.index("_duckduckgo_search"))


if __name__ == "__main__":
    unittest.main()
