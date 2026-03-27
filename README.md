# Agentic Travel Planner with Multiple Agents and A2A Protocol

A multi-agent travel planning system where specialist agents negotiate under user constraints, critique one another, and produce an explainable final itinerary. The system is deployed on Hugging Face Spaces and uses official A2A SDK-backed agent routes plus agent-card discovery.

## Why this project exists

Most travel planners act like a single assistant. This project explores a stronger architecture where different agents optimize for different goals and a coordinator merges them into one final plan.

The system includes:
- a **Budget Agent** that minimizes spend
- an **Experience Agent** that maximizes quality and novelty
- a **Time Optimizer Agent** that improves schedule feasibility
- a **Critic Agent** that detects contradictions and weak assumptions
- an **Intent Agent** that converts user input into structured trip constraints

The final output is not just an itinerary. It also includes:
- a debate trace
- rejected alternatives
- final decision rationale
- estimated total cost
- warnings when assumptions are necessary

## Core ideas demonstrated

- multi-agent planning under constraints
- agent specialization and disagreement
- explainable reasoning traces
- web-grounded travel planning
- structured JSON generation for final itineraries
- official A2A SDK-backed server routing
- agent-card discovery
- Hugging Face Spaces deployment with secrets

## Architecture

```text
User Request
   ↓
Intent Agent
   ↓
Web Evidence Retrieval
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
````

## How the planner works

1. The user submits a natural-language travel request.
2. The Intent Agent converts that request into structured travel constraints.
3. The planner retrieves lightweight web evidence for the destination.
4. The planner discovers specialist agents through A2A agent cards.
5. The specialist agents produce competing proposals:

   * Budget Agent
   * Experience Agent
   * Time Optimizer Agent
6. The Critic Agent reviews the specialist outputs and identifies conflicts or weak assumptions.
7. The planner scores the proposals and performs a final merge.
8. The final itinerary is returned together with rationale and rejected alternatives.

## Features

* multi-agent travel planning
* official A2A SDK-backed routes
* agent-card discovery
* structured final itinerary generation
* explainable reasoning trace
* proposal scoring
* critic feedback loop
* Hugging Face Spaces deployment
* Gradio UI for quick interaction
* FastAPI backend for API usage

## Tech stack

* Python
* FastAPI
* Gradio
* Pydantic
* Hugging Face Inference API / Inference Providers
* official A2A Python SDK
* DuckDuckGo / web search based evidence retrieval
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
│   └── search.py
├── models/
│   ├── agent.py
│   ├── state.py
│   └── trip.py
└── ui/
    └── gradio_app.py
```

The `services/` folder contains earlier internal service wrappers kept for compatibility and reference, while the current agent communication path uses the official A2A SDK-backed routes in `app/a2a/`.

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
* estimated total cost
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
HF_TOKEN=your_huggingface_token
HF_MODEL=your_model_id
APP_ENV=dev
MAX_NEGOTIATION_ROUNDS=1
DEFAULT_DESTINATION=Paris
```

Start the app:

```bash
uvicorn space_entry:app --host 0.0.0.0 --port 7860
```

## Hugging Face Spaces deployment

Use a Docker Space.

Set these Space secrets:

```bash
HF_TOKEN
HF_MODEL
```

Make sure the app serves on port `7860`.
