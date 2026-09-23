"""Convert deliberation traces to Mermaid.js DAG visualizations.

The web UI uses Mermaid to render the dispatcher-designed DAG in real time.
Each stage becomes a node; edges show data flow.  Completed stages show
their model, the provider that actually served the call (when the trace
carries the resolved-route attribution, QA-CHIMERA-V2-16), token count, and
latency inline.

A stage the trace reports as failed (``worker_failures``) is rendered as a
failure — the failure colour, the literal ``FAILED`` marker and the upstream
error — instead of a healthy node (DF-CHIMERA-V2-42).  Before that, node
colour came from the stage kind alone and every node printed its metric block,
so a worker dropped upstream (timeout, 402, gateway drop) was indistinguish-
able from a success in the DAG.

The ``trace_to_mermaid`` function accepts the full trace dict (as returned
by the REST API) and produces a Mermaid flowchart string ready for rendering.
"""

from __future__ import annotations

from typing import Any

# Colour palette — distinct hues per stage kind
_KIND_COLOURS: dict[str, str] = {
    "dispatch": "#6C5CE7",  # purple
    "worker": "#00B894",  # green
    "aggregator": "#FDCB6E",  # yellow
    "judge": "#E17055",  # coral
    "merge": "#74B9FF",  # blue
    "audit": "#FD79A8",  # pink
}

_FALLBACK_COLOUR = "#B2BEC3"  # grey

# A failed stage overrides every kind colour: red, never a success hue.
_FAILURE_COLOUR = "#B71C1C"  # dark red

# How much of the upstream error reaches the node label (the full text stays
# in the trace/API payload and the CLI warning).
_ERROR_MAX_CHARS = 60


def trace_to_mermaid(trace: dict[str, Any]) -> str:
    """Generate a Mermaid flowchart from a deliberation trace.

    The trace is the ``trace`` field from a ``/v1/deliberate`` response.

    Returns a Mermaid ``flowchart TB`` string.  Wrap in a ``<pre
    class="mermaid">`` block for rendering.

    A stage whose ``stage_id`` appears in ``trace["worker_failures"]`` renders
    as a failed node: the failure colour, the ``FAILED`` marker and the
    truncated upstream error.  Its success metrics (tokens, latency) are
    dropped — a degraded stage reports zero tokens and an elapsed-until-failure
    latency, which as a completion block reads exactly like a healthy call.
    """
    lines: list[str] = ["flowchart TB"]
    stage_ids: set[str] = set()
    failures = _failure_index(trace)

    # Stages from the trace
    stages: list[dict] = trace.get("stages", [])
    for s in stages:
        sid = s.get("stage_id", "?")
        kind = s.get("kind", "worker")
        model_short = _short_model(s.get("model", ""))
        tokens = s.get("tokens_input", 0) + s.get("tokens_output", 0)
        latency = s.get("latency_ms", 0)
        # QA-CHIMERA-V2-16: the resolved serving provider, when the trace
        # carries one (absent on internal/degraded spans and older traces).
        provider = s.get("provider", "")
        failure = failures.get(str(sid))
        colour = _FAILURE_COLOUR if failure else _KIND_COLOURS.get(kind, _FALLBACK_COLOUR)

        label = f"{kind}\\n{model_short}"
        if provider:
            label += f"\\nvia {provider}"
        if failure is not None:
            label += _failure_marker(failure)
        else:
            if tokens:
                label += f"\\n{tokens} tok"
            if latency:
                label += f"\\n{latency}ms"

        lines.append(f'    {sid}["{label}"]')
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
            failure = failures.get(str(did))
            label = f"dispatch\\n{model_short}"
            if failure is not None:
                # The same rule as any other node: a failed dispatch is red and
                # marked, never a healthy purple node — the engine keys
                # failures by DAG stage id today, but this is not relied upon.
                colour = _FAILURE_COLOUR
                label += _failure_marker(failure)
            else:
                colour = _KIND_COLOURS["dispatch"]
                label += f"\\n{tokens} tok\\n{latency}ms"
            lines.append(f'    {did}["{label}"]')
            lines.append(f"    style {did} fill:{colour},stroke:#333,color:#fff")
            stage_ids.add(did)

    # Add a style legend
    lines.append("")
    lines.append("    subgraph Legend")
    for kind, colour in _KIND_COLOURS.items():
        lines.append(f"        {kind}[{kind}]")
        lines.append(f"        style {kind} fill:{colour},stroke:#333,color:#fff")
    lines.append("    end")

    return "\n".join(lines)


def _failure_index(trace: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Map stage id → its ``worker_failures`` entry.

    The trace payload carries ``worker_failures`` as a list of dicts with
    ``stage_id`` / ``model`` / ``error`` (``DeliberationTrace`` serialized by
    the API).  Anything malformed is skipped rather than rendered as a node.
    """
    index: dict[str, dict[str, Any]] = {}
    for entry in trace.get("worker_failures") or []:
        if not isinstance(entry, dict):
            continue
        stage_id = entry.get("stage_id")
        if stage_id and str(stage_id) not in index:
            index[str(stage_id)] = entry
    return index


def _failure_marker(failure: dict[str, Any]) -> str:
    """The ``FAILED`` marker plus the escaped, truncated upstream error."""
    marker = "\\nFAILED"
    error = _escape_error(failure.get("error"))
    if error:
        marker += f"\\n{error}"
    return marker


def _escape_error(error: Any, limit: int = _ERROR_MAX_CHARS) -> str:
    """Make an upstream error safe inside a quoted mermaid node label.

    A double quote would close the label early, a backslash is mermaid's own
    escape introducer inside a label, and CR/LF/TAB would split the node
    definition across lines — none of them may survive into the DAG source.
    The text is then collapsed to a single line and truncated: the full error
    stays in the trace payload.
    """
    text = str(error or "")
    text = text.replace("\\", "/").replace('"', "'")
    text = " ".join(text.split())  # collapses newlines, tabs and runs of spaces
    if len(text) > limit:
        text = text[:limit].rstrip() + "..."
    return text


def _short_model(model: str) -> str:
    """Shorten a full model name for display in DAG nodes."""
    # Strip provider prefixes
    for prefix in (
        "openrouter/",
        "anthropic/",
        "deepseek/",
        "openai/",
        "google/",
        "zai-coding-plan/",
        "moonshotai/",
    ):
        if model.startswith(prefix):
            model = model[len(prefix) :]
            break
    return model
