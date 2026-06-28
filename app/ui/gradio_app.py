import json
import time
import gradio as gr

from app.config import settings
from app.llm import (
    build_llm_config,
    default_model_for_provider,
    get_model_choices,
    get_provider_choices,
    provider_to_label,
)


APP_CSS = """
.gradio-container .progress-text,
.gradio-container .meta-text,
.gradio-container .meta-text-center {
    display: none !important;
}

.planning-status {
    display: flex;
    align-items: center;
    gap: 12px;
    margin: 8px 0 12px;
    border: 1px solid var(--border-color-primary);
    border-radius: var(--block-radius);
    background: var(--block-background-fill);
    padding: 12px 14px;
}

.planning-status.done {
    border-color: var(--color-green-500);
}

.planning-status.error {
    border-color: var(--error-border-color);
}

.planning-spinner {
    flex: 0 0 auto;
    width: 22px;
    height: 22px;
    border: 3px solid var(--border-color-primary);
    border-top-color: var(--loader-color);
    border-radius: 999px;
    animation: planning-spin 0.9s linear infinite;
}

.planning-status.done .planning-spinner,
.planning-status.error .planning-spinner {
    animation: none;
    border-color: var(--loader-color);
}

.planning-copy {
    display: flex;
    flex: 1;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
}

.planning-title {
    font-weight: 600;
}

.planning-detail {
    color: var(--body-text-color-subdued);
    font-size: var(--text-sm);
}

.planning-elapsed {
    flex: 0 0 auto;
    border-radius: var(--radius-md);
    background: var(--background-fill-secondary);
    padding: 4px 8px;
    font-family: var(--font-mono);
    font-size: var(--text-sm);
}

@keyframes planning-spin {
    to {
        transform: rotate(360deg);
    }
}
"""


APP_JS = """
() => {
    if (window.__travelPlannerTimerInstalled) {
        return;
    }
    window.__travelPlannerTimerInstalled = true;

    const formatElapsed = (seconds) => {
        const mins = Math.floor(seconds / 60);
        const secs = seconds % 60;
        if (mins <= 0) {
            return `${secs}s`;
        }
        return `${mins}m ${String(secs).padStart(2, "0")}s`;
    };

    setInterval(() => {
        document.querySelectorAll(".planning-elapsed[data-start]").forEach((el) => {
            const startedAt = Number(el.dataset.start || "0");
            if (!startedAt) {
                return;
            }
            const elapsed = Math.max(0, Math.floor((Date.now() - startedAt) / 1000));
            el.textContent = formatElapsed(elapsed);
        });
    }, 250);
}
"""


def planning_status_html(demo_mode: bool = False) -> str:
    started_at = int(time.time() * 1000)
    title = "Running demo mode" if demo_mode else "Planning itinerary"
    detail = (
        "Using deterministic mock agents; no provider API calls will be made."
        if demo_mode
        else "Agents are negotiating through A2A. This can take a few minutes."
    )
    return f"""
<div class="planning-status">
    <div class="planning-spinner" aria-hidden="true"></div>
    <div class="planning-copy">
        <div class="planning-title">{title}</div>
        <div class="planning-detail">{detail}</div>
    </div>
    <div class="planning-elapsed" data-start="{started_at}">0s</div>
</div>
"""


def done_status_html() -> str:
    return """
<div class="planning-status done">
    <div class="planning-spinner" aria-hidden="true"></div>
    <div class="planning-copy">
        <div class="planning-title">Done</div>
        <div class="planning-detail">The planner finished this run.</div>
    </div>
</div>
"""


def error_status_html() -> str:
    return """
<div class="planning-status error">
    <div class="planning-spinner" aria-hidden="true"></div>
    <div class="planning-copy">
        <div class="planning-title">Planner stopped with an error</div>
        <div class="planning-detail">Check the diagnostics box for the provider message.</div>
    </div>
</div>
"""


def format_trace(trace: list[dict]) -> str:
    chunks: list[str] = []

    for round_data in trace:
        chunks.append(f"## Round {round_data['round_number']}")
        proposals = round_data.get("proposals", [])
        for p in proposals:
            chunks.append(f"### {p['agent_name']}")
            chunks.append(f"- Objective: {p.get('objective', '')}")
            chunks.append(f"- Confidence: {p.get('confidence', '')}")
            chunks.append(f"- Recommendations:")
            for rec in p.get("recommendations", []):
                chunks.append(f"  - {rec}")
            if p.get("objections"):
                chunks.append(f"- Objections:")
                for obj in p["objections"]:
                    chunks.append(f"  - {obj}")
            if p.get("pros"):
                chunks.append(f"- Notes:")
                for note in p["pros"]:
                    chunks.append(f"  - {note}")
        critic_notes = round_data.get("critic_notes", [])
        if critic_notes:
            chunks.append("### Critic")
            for note in critic_notes:
                chunks.append(f"- {note}")

    return "\n".join(chunks)


def build_gradio_app(planner):
    def run_planner(
        user_input: str,
        provider_label: str,
        model_name: str,
        api_key: str,
        demo_mode: bool,
    ):
        yield (
            planning_status_html(demo_mode=demo_mode),
            "",
            "",
            "",
            "",
            "",
        )

        try:
            llm_config = build_llm_config(
                provider=provider_label,
                api_key=api_key,
                model=model_name,
                demo_mode=demo_mode,
            )
            state = planner.run(user_input, llm_config=llm_config)
        except Exception as exc:
            error_payload = {
                "summary": "Planner could not complete this request.",
                "warnings": [str(exc)],
            }
            yield (
                error_status_html(),
                json.dumps(error_payload, indent=2),
                "",
                "",
                "",
                str(exc),
            )
            return

        data = state.to_public_dict()

        final_pretty = json.dumps(data.get("final_itinerary", {}), indent=2, ensure_ascii=False)
        trace_pretty = format_trace(data.get("debate_trace", []))
        rationale = "\n".join(data.get("final_rationale", []))
        rejected = "\n".join(data.get("rejected_alternatives", []))
        diagnostic_lines = list(data.get("errors", []))
        cost_breakdown = data.get("cost_breakdown") or {}
        if cost_breakdown:
            diagnostic_lines.append(
                "Pricing: "
                f"{cost_breakdown.get('total')} {cost_breakdown.get('currency')} "
                f"via {cost_breakdown.get('pricing_mode')}"
            )
        errors = "\n".join(diagnostic_lines)

        yield done_status_html(), final_pretty, trace_pretty, rationale, rejected, errors

    def update_model_choices(provider_label: str):
        choices = get_model_choices(provider_label)
        return gr.update(
            choices=choices,
            value=default_model_for_provider(provider_label),
        )

    default_provider = provider_to_label(settings.llm_provider)

    with gr.Blocks(title="Agentic Travel Planner", css=APP_CSS, js=APP_JS) as demo:
        gr.Markdown("# Agentic Travel Planner")
        gr.Markdown(
            "Budget, Experience, Time, and Critic agents negotiate toward a final itinerary. "
            "You can run it with the shared demo key; adding your own key is optional."
        )

        user_input = gr.Textbox(
            label="Trip Request",
            lines=8,
            placeholder=(
                "Plan a 4-day solo trip to Lisbon in May under 900 euros. "
                "I like museums, good food, and walkable neighborhoods."
            ),
        )

        with gr.Row():
            provider = gr.Dropdown(
                label="AI Provider",
                choices=get_provider_choices(),
                value=default_provider,
            )
            model = gr.Dropdown(
                label="Model",
                choices=get_model_choices(default_provider),
                value=default_model_for_provider(default_provider),
                allow_custom_value=True,
            )
            api_key = gr.Textbox(
                label="Optional API key",
                type="password",
                placeholder="Only needed for extra live runs",
            )
            demo_mode = gr.Checkbox(
                label="Demo mode",
                value=False,
                info="Use mocked agents without API calls.",
            )

        gr.Markdown(
            "No key is required for a quick live demo. The shared key is capped to a "
            "few live plans per day, so use Demo mode for quota-free walkthroughs or "
            "bring your own key if you want more live generations. Free and low-cost "
            "model tiers can occasionally return temporary quota, high-demand, or "
            "search-rate-limit errors; if an error says to retry in a specific number "
            "of seconds, wait that long before sending another request."
        )

        provider.change(
            fn=update_model_choices,
            inputs=[provider],
            outputs=[model],
        )

        run_btn = gr.Button("Generate Plan")
        status = gr.HTML()

        final_itinerary = gr.Code(label="Final Itinerary (JSON)", language="json")
        rationale = gr.Textbox(label="Final Rationale", lines=8)
        with gr.Accordion("How the AI made this decision", open=False):
            trace_view = gr.Markdown(label="Negotiation Trace")

        with gr.Accordion("System diagnostics", open=False):
            rejected = gr.Textbox(label="Rejected Alternatives", lines=8)
            errors = gr.Textbox(label="Errors / Warnings", lines=4)

        run_btn.click(
            fn=run_planner,
            inputs=[user_input, provider, model, api_key, demo_mode],
            outputs=[status, final_itinerary, trace_view, rationale, rejected, errors],
            api_name=False,
            show_api=False,
            show_progress="full",
        )

    return demo
