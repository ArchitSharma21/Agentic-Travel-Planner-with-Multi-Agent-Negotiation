import json
import gradio as gr


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
    def run_planner(user_input: str):
        state = planner.run(user_input)
        data = state.to_public_dict()

        final_pretty = json.dumps(data.get("final_itinerary", {}), indent=2, ensure_ascii=False)
        trace_pretty = format_trace(data.get("debate_trace", []))
        rationale = "\n".join(data.get("final_rationale", []))
        rejected = "\n".join(data.get("rejected_alternatives", []))
        errors = "\n".join(data.get("errors", []))

        return final_pretty, trace_pretty, rationale, rejected, errors

    with gr.Blocks(title="Agentic Travel Planner") as demo:
        gr.Markdown("# Agentic Travel Planner")
        gr.Markdown(
            "Budget, Experience, Time, and Critic agents negotiate toward a final itinerary."
        )

        user_input = gr.Textbox(
            label="Trip Request",
            lines=8,
            placeholder=(
                "Plan a 4-day solo trip to Lisbon in May under 900 euros. "
                "I like museums, good food, and walkable neighborhoods."
            ),
        )
        run_btn = gr.Button("Generate Plan")

        final_itinerary = gr.Code(label="Final Itinerary (JSON)", language="json")
        rationale = gr.Textbox(label="Final Rationale", lines=8)
        with gr.Accordion("How the AI made this decision", open=False):
            trace_view = gr.Markdown(label="Negotiation Trace")
        
        with gr.Accordion("System diagnostics", open=False):
            rejected = gr.Textbox(label="Rejected Alternatives", lines=8)
            errors = gr.Textbox(label="Errors / Warnings", lines=4)

        run_btn.click(
            fn=run_planner,
            inputs=[user_input],
            outputs=[final_itinerary, trace_view, rationale, rejected, errors],
        )

    return demo