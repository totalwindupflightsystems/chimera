"""Convert deliberation traces to Mermaid.js DAG visualizations.

The web UI uses Mermaid to render the dispatcher-designed DAG in real time.
Each stage becomes a node; edges show data flow.  Completed stages show
their model, token count, and latency inline.

The ``trace_to_mermaid`` function accepts the full trace dict (as returned
by the REST API) and produces a Mermaid flowchart string ready for rendering.
"""

from __future__ import annotations

from typing import Any

# Colour palette — distinct hues per stage kind
_KIND_COLOURS: dict[str, str] = {
    "dispatch": "#6C5CE7",   # purple
    "worker": "#00B894",     # green
    "aggregator": "#FDCB6E", # yellow
    "judge": "#E17055",      # coral
    "merge": "#74B9FF",      # blue
    "audit": "#FD79A8",      # pink
}

_FALLBACK_COLOUR = "#B2BEC3"  # grey


def trace_to_mermaid(trace: dict[str, Any]) -> str:
    """Generate a Mermaid flowchart from a deliberation trace.

    The trace is the ``trace`` field from a ``/v1/deliberate`` response.

    Returns a Mermaid ``flowchart TB`` string.  Wrap in a ``<pre
    class="mermaid">`` block for rendering.
    """
    lines: list[str] = ["flowchart TB"]
    stage_ids: set[str] = set()

    # Stages from the trace
    stages: list[dict] = trace.get("stages", [])
    for s in stages:
        sid = s.get("stage_id", "?")
        kind = s.get("kind", "worker")
        model_short = _short_model(s.get("model", ""))
        tokens = s.get("tokens_input", 0) + s.get("tokens_output", 0)
        latency = s.get("latency_ms", 0)
        colour = _KIND_COLOURS.get(kind, _FALLBACK_COLOUR)

        label = f"{kind}\\n{model_short}"
        if tokens:
            label += f"\\n{tokens} tok"
        if latency:
            label += f"\\n{latency}ms"

        lines.append(f"    {sid}[\"{label}\"]")
        lines.append(f"    style {sid} fill:{colour},stroke:#333,color:#fff")
        stage_ids.add(sid)

        # Edges from depends_on
        for dep in s.get("depends_on", []):
            lines.append(f"    {dep} --> {sid}")

    # Also include the dispatch stage if present
    dispatch = trace.get("dispatch")
    if dispatch:
        did = dispatch.get("stage_id", "dispatch")
        if did not in stage_ids:
            model_short = _short_model(dispatch.get("model", ""))
            tokens = dispatch.get("tokens_input", 0) + dispatch.get("tokens_output", 0)
            latency = dispatch.get("latency_ms", 0)
            label = f"dispatch\\n{model_short}\\n{tokens} tok\\n{latency}ms"
            lines.append(f"    {did}[\"{label}\"]")
            lines.append(f"    style {did} fill:{_KIND_COLOURS['dispatch']},stroke:#333,color:#fff")
            stage_ids.add(did)

    # Add a style legend
    lines.append("")
    lines.append("    subgraph Legend")
    for kind, colour in _KIND_COLOURS.items():
        lines.append(f"        {kind}[{kind}]")
        lines.append(f"        style {kind} fill:{colour},stroke:#333,color:#fff")
    lines.append("    end")

    return "\n".join(lines)


def _short_model(model: str) -> str:
    """Shorten a full model name for display in DAG nodes."""
    # Strip provider prefixes
    for prefix in ("openrouter/", "anthropic/", "deepseek/", "openai/",
                   "google/", "zai-coding-plan/", "moonshotai/"):
        if model.startswith(prefix):
            model = model[len(prefix):]
            break
    return model
