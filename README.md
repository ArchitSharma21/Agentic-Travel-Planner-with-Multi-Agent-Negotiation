---
title: Agentic Travel Planner with Multiple Agents and A2A Protocol
emoji: ✈️
colorFrom: gray
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# Agentic Travel Planner with Multiple Agents and A2A Protocol

A multi-agent travel planning system where specialist agents negotiate under user constraints, critique one another, and produce an explainable final itinerary. The system is deployed on Hugging Face Spaces and uses official A2A SDK-backed agent routes plus agent-card discovery. It also includes an MCP travel-context server for reusable search and deterministic pricing tools.

## Why this project exists

Most travel planners act like a single assistant. This project explores a stronger architecture where different agents optimize for different goals and a coordinator merges them into one final plan.

The system includes:
- a **Budget Agent** that minimizes spend
- an **Experience Agent** that maximizes quality and novelty
- a **Time Optimizer Agent** that improves schedule feasibility
- a **Critic Agent** that detects contradictions and weak assumptions
- an **Intent Agent** that converts user input into structured trip constraints
- a **Travel Context tool layer** that retrieves no-account web evidence and computes deterministic trip cost estimates

The final output is not just an itinerary. It also includes:
- a debate trace
- rejected alternatives
- final decision rationale
- estimated total cost with explicit currency
- warnings when assumptions are necessary

## Core ideas demonstrated

- multi-agent planning under constraints
- agent specialization and disagreement
- explainable reasoning traces
- web-grounded travel planning
- structured JSON generation for final itineraries
- official A2A SDK-backed server routing
- agent-card discovery
- MCP-exposed travel context tools
- deterministic pricing with provenance
- Hugging Face Spaces deployment with secrets

## Architecture

```text
User Request
   ↓
Intent Agent
   ↓
MCP Travel Context
  ├── Destination Evidence
  └── Deterministic Pricing Context
   ↓
A2A Agent Discovery
   ↓
Specialist Agents
  ├── Budget Agent
  ├── Experience Agent
  ├── Time Optimizer Agent
  └── Critic Agent
   ↓
Scoring + Final Merge
   ↓
Final Itinerary + Debate Trace + Rejected Alternatives
```

## How the planner works

1. The user submits a natural-language travel request.
2. The Intent Agent converts that request into structured travel constraints.
3. The planner calls the MCP travel-context layer for destination evidence and deterministic pricing.
4. The travel-context layer computes a cost breakdown for lodging, meals, local transport, and activities.
5. The planner discovers specialist agents through A2A agent cards.
6. The specialist agents produce competing proposals:

   * Budget Agent
   * Experience Agent
   * Time Optimizer Agent
7. The Critic Agent reviews the specialist outputs and identifies conflicts or weak assumptions.
8. The planner scores the proposals and performs a final merge.
9. The app recomputes the final total from the deterministic pricing engine before returning the itinerary.

## Features

* multi-agent travel planning
* official A2A SDK-backed routes
* MCP travel-context tool server
* agent-card discovery
* structured final itinerary generation
* explainable reasoning trace
* proposal scoring
* critic feedback loop
* no-account search fallbacks through DuckDuckGo, Wikivoyage, Wikipedia, cache, and local fallback evidence
* deterministic dynamic price estimates with optional no-account Frankfurter FX conversion
* Hugging Face Spaces deployment
* Gradio UI for quick interaction
* FastAPI backend for API usage

## Tech stack

* Python
* FastAPI
* Gradio
* Pydantic
* Gemini API by default, with optional OpenAI, Anthropic, and xAI provider support
* official A2A Python SDK
* MCP Python SDK
* DuckDuckGo / web search based evidence retrieval
* Wikivoyage/Wikipedia MediaWiki APIs for no-account destination fallback
* Frankfurter exchange-rate API for no-account currency conversion, with bundled static fallback rates
* Hugging Face Docker Spaces

## Project structure

```text
app/
├── main.py
├── config.py
├── llm.py
├── prompts.py
├── agents/
│   ├── intent_agent.py
│   ├── budget_agent.py
│   ├── experience_agent.py
│   ├── time_agent.py
│   └── critic_agent.py
├── a2a/
│   ├── cards.py
│   ├── discovery.py
│   ├── sdk_apps.py
│   └── sdk_executors.py
├── services/
│   ├── budget_service.py
│   ├── critic_service.py
│   ├── experience_service.py
│   └── time_service.py
├── graph/
│   └── planner.py
├── tools/
│   ├── estimation.py
│   ├── search.py
│   └── travel_context.py
├── mcp/
│   └── travel_context_server.py
├── models/
│   ├── agent.py
│   ├── state.py
│   └── trip.py
└── ui/
    └── gradio_app.py
```

The `services/` folder contains earlier internal service wrappers kept for compatibility and reference, while the current agent communication path uses the official A2A SDK-backed routes in `app/a2a/`.

## A2A and MCP roles

This project uses A2A and MCP for different jobs:

* **A2A** handles agent-to-agent collaboration: Budget, Experience, Time, and Critic agents negotiate through official A2A SDK routes.
* **MCP** exposes reusable tools and context: destination search, deterministic trip-cost estimation, and combined travel context.

At runtime, the planner uses `TravelContextClient` before agent negotiation. By default it tries the mounted MCP protocol endpoint at `/mcp/protocol` and calls `build_travel_context`; if the MCP endpoint is unavailable, it falls back to the same local Python tool layer and records that fallback in diagnostics. Set `TRAVEL_CONTEXT_MODE=direct` to bypass MCP for local scripts, or keep `TRAVEL_CONTEXT_MODE=mcp` to exercise the MCP boundary.

The FastAPI app exposes a human-readable MCP status endpoint at `/mcp` and mounts the MCP streamable HTTP protocol at `/mcp/protocol`. The same tools can also be run as a standalone stdio MCP server:

```bash
python -m app.mcp.travel_context_server
```

Available MCP tools:

* `search_destination(destination, travel_style=None)`
* `estimate_trip_cost(trip_request)`
* `build_travel_context(trip_request)`

## Agent roles

### Intent Agent

Parses the user’s request into structured trip constraints.

### Budget Agent

Optimizes for affordability and flags overspending.

### Experience Agent

Optimizes for memorable, high-value experiences.

### Time Optimizer Agent

Optimizes routing, pacing, and realistic day plans.

### Critic Agent

Finds contradictions, weak assumptions, and poor trade-offs.

## Example query

Plan a 4-day solo trip to Barcelona in May under 900 euros. I like museums, food markets, and walkable neighborhoods.

## Example output

* final itinerary
* estimated total cost with explicit currency
* day-by-day plan
* debate trace
* rejected alternatives
* rationale
* warnings

## Running locally

Install dependencies:

```bash
pip install -r requirements.txt
```

Set environment variables in a `.env` file:

```bash
LLM_PROVIDER=gemini
GEMINI_API_KEY=your_google_ai_studio_key
GEMINI_MODEL=gemini-3.1-flash-lite
GEMINI_FALLBACK_MODEL=gemini-2.5-flash
GEMINI_RATE_LIMIT_RETRIES=1
GEMINI_MAX_RETRY_DELAY_SECONDS=75
GEMINI_MIN_SECONDS_BETWEEN_REQUESTS=0
APP_ENV=dev
MAX_NEGOTIATION_ROUNDS=1
DEFAULT_DESTINATION=Paris
SERVER_GEMINI_DAILY_CALL_LIMIT=30
TRAVEL_CONTEXT_MODE=mcp
TRAVEL_CONTEXT_MCP_URL=http://127.0.0.1:7860/mcp/protocol
TRAVEL_CONTEXT_MCP_TIMEOUT_SECONDS=4
SEARCH_PROVIDER=auto
BRAVE_SEARCH_API_KEY=
TAVILY_API_KEY=
```

The Gradio UI also lets users pick a provider/model and enter a per-run API key without saving it. Supported provider values and default model environment variables are:

```bash
gemini      # GEMINI_API_KEY or GOOGLE_API_KEY, GEMINI_MODEL
openai      # OPENAI_API_KEY, OPENAI_MODEL
anthropic   # ANTHROPIC_API_KEY, ANTHROPIC_MODEL
xai         # XAI_API_KEY, XAI_MODEL
```

Default model names:

```bash
GEMINI_MODEL=gemini-3.1-flash-lite
GEMINI_FALLBACK_MODEL=gemini-2.5-flash
GEMINI_RATE_LIMIT_RETRIES=1
GEMINI_MAX_RETRY_DELAY_SECONDS=75
GEMINI_MIN_SECONDS_BETWEEN_REQUESTS=0
OPENAI_MODEL=gpt-4o-mini
ANTHROPIC_MODEL=claude-3-5-haiku-latest
XAI_MODEL=grok-3-mini
```

When users leave the API key field blank and the app uses the shared Gemini key, this project is limited to 30 Gemini API calls per day by default. A normal plan uses about 6 LLM calls before retries or fallback calls, so the public demo should be treated as roughly 3 full live plans per day before users are asked to bring their own key. User-supplied API keys are not limited by the project counter.

For a portfolio deployment on a shared free API key, keep the default Gemini model on `gemini-3.1-flash-lite`. When a user provides their own Gemini key, the app automatically falls back to `gemini-2.5-flash` if Flash-Lite returns a temporary 503 high-demand response. Set `GEMINI_FALLBACK_MODEL=` to disable that fallback.

Gemini specialist-agent calls use the same A2A orchestration as the other providers. Specialist agents run in parallel through A2A, while the app-level daily cap protects the shared demo key from being exhausted too quickly.

The UI includes a Demo mode checkbox for portfolio walkthroughs. Demo mode uses deterministic mock agent proposals, critic notes, evidence, and final itinerary generation without calling search or any LLM provider. It preserves the same public response shape and negotiation trace so viewers can understand the multi-agent workflow even when provider quotas are exhausted.

The app retrieves travel context before the LLM agents run. In MCP mode, the planner calls the MCP travel-context endpoint for destination evidence and deterministic pricing; in direct mode or fallback mode, it calls the same local tool layer directly. Gemini does not need native web browsing/search grounding for the planner to work.

Cost estimates are planning estimates, not guaranteed quotes. The app computes a deterministic cost breakdown from trip length, travelers, travel style, currency, and a dynamic no-account destination cost index. The cost index uses Nominatim to resolve the destination country and World Bank GDP per capita PPP as a transparent rough cost signal, with a generic fallback if live lookup fails. Agents receive this `pricing_context` and are prompted to use it as the authority for numeric estimates. The final `estimated_total_cost` is recomputed by code after the LLM merge, so model-generated prices cannot silently overwrite the deterministic total.

The app prefers free/no-account data sources:

* DuckDuckGo search when available
* optional Brave Search or Tavily Search API when keys are configured
* Wikivoyage and Wikipedia MediaWiki APIs as no-account search fallbacks
* a 24-hour local search cache
* deterministic local fallback evidence when live search is blocked
* Frankfurter exchange rates when available
* bundled fallback FX rates when exchange-rate lookup fails
* a generic deterministic fallback when destination cost-index lookups are unavailable

Optional free-tier API upgrades can improve quality, but are not required:

* **Search quality:** Brave Search or Tavily can reduce DDG bot/rate-limit failures and usually return cleaner snippets. Configure `BRAVE_SEARCH_API_KEY` or `TAVILY_API_KEY`; with `SEARCH_PROVIDER=auto`, the app tries configured signed providers before DDG and no-account fallbacks.
* **Live lodging/flight quotes:** Amadeus can provide more realistic hotel and flight pricing, but it requires account setup, OAuth, quota handling, and a clearer UX for quote freshness. It is best treated as a future optional enhancement rather than a dependency for the portfolio demo.
* **Places quality:** Google Places can improve attraction/place discovery, but it does not reliably provide exact ticket prices and adds key management overhead.

The live planner is designed around 6 planned LLM calls per full run: intent parsing, 3 specialist proposals, critic review, and final merge. Search, pricing, FX lookup, caching, and deterministic cost validation use 0 LLM calls. Malformed model output can trigger repair calls, and provider-level retries/fallbacks may add transport attempts, but the normal agent plan is 6 calls.

Free and low-cost model tiers can occasionally return temporary high-demand, quota, or rate-limit errors. Consecutive requests can hit per-minute Gemini quota even with a user-provided key. If the error says "Please retry in 18s" or similar, wait at least that long before sending another request. The app automatically retries Gemini 429 delays up to `GEMINI_MAX_RETRY_DELAY_SECONDS`, but persistent quota errors still need a cooldown. DuckDuckGo search can also rate-limit automated requests. The planner degrades gracefully when this happens, but users can improve reliability by choosing a stronger model, waiting for the indicated cooldown, bringing their own API key, or using Demo mode.

If every specialist agent falls back because the provider is rate-limiting, the planner skips the critic and final merge calls to avoid wasting additional quota on a result that cannot improve. The diagnostics panel names the specialist, critic, or final-merge stage that hit the failure.

Start the app:

```bash
uvicorn space_entry:app --host 0.0.0.0 --port 7860
```

## Hugging Face Spaces deployment

Use a Docker Space.

Set these Space secrets:

```bash
LLM_PROVIDER
GEMINI_API_KEY
GEMINI_MODEL
GEMINI_FALLBACK_MODEL
SERVER_GEMINI_DAILY_CALL_LIMIT
```

If you want to use another provider as the Space default, set the matching API key and model secrets from the provider list above. Users can still override the default provider/key from the UI for a single run.

Make sure the app serves on port `7860`.
