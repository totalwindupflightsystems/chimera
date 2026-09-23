"""A failed worker must never render as a healthy node in the live DAG.

DF-CHIMERA-V2-42.  ``trace_to_mermaid`` coloured nodes ONLY by stage kind
(``_KIND_COLOURS``) and printed a metric block for every node, so a stage that
degraded upstream — a timeout, a 402, a gateway drop — rendered in the very
same green as a success, printed a completion-shaped latency, and carried no
marker at all: a degraded run looked like a healthy one.  The trace already
carried the truth (``DeliberationTrace.worker_failures``, ``stage_id`` /
``model`` / ``error``) and the API hands it to the web layer; the DAG simply
never read it.

These tests pin the three properties that make the DAG honest:

* a stage named in ``worker_failures`` renders in the failure colour with the
  literal ``FAILED`` marker and its upstream error, whatever its stage kind —
  and that failure styling drops the success metrics (a degraded stage reports
  zero tokens and a latency that reads as a completed call);
* a trace with no failures renders byte-for-byte what it rendered before the
  change (pinned golden captured from the pre-change implementation);
* hostile error text (double quotes, newlines, backslashes) cannot break the
  mermaid definition.
"""

from __future__ import annotations

import json
import re
from typing import Any

import pytest

from chimera.engine import Engine
from chimera.gateway import GatewayError
from chimera.web.trace_viz import trace_to_mermaid
from tests.conftest import FakeGateway, dispatch_json, resp

# The failure fill, kept as a literal on purpose: the tests assert what the DAG
# actually prints, so renaming or shadowing the constant cannot satisfy them.
_FAILURE_HEX = "#B71C1C"

# A node definition is ONE line, one quoted label, nothing else.
_NODE_LINE_RE = re.compile(r'^ {4}(?P<sid>[A-Za-z0-9_]+)\["(?P<label>[^"]*)"\]$')
_STYLE_LINE_RE = re.compile(r"^ {4}style (?P<sid>[A-Za-z0-9_]+) fill:#[0-9A-Fa-f]{6},stroke:#333,color:#fff$")

# ``trace_to_mermaid(_healthy_trace())`` as produced by the implementation at
# the base commit (0fc54d5) BEFORE this change — the A2 byte-identical guard.
_HEALTHY_RENDER_PINNED = r"""flowchart TB
    worker_1["worker\nqwen/qwen3-coder\nvia openrouter\n5 tok\n12ms"]
    style worker_1 fill:#00B894,stroke:#333,color:#fff
    dispatcher --> worker_1
    worker_2["worker\ndeepseek-chat\n9 tok\n30ms"]
    style worker_2 fill:#00B894,stroke:#333,color:#fff
    dispatcher --> worker_2
    aggregator_1["aggregator\nglm-5.2\nvia zai\n13 tok\n40ms"]
    style aggregator_1 fill:#FDCB6E,stroke:#333,color:#fff
    worker_1 --> aggregator_1
    worker_2 --> aggregator_1
    custom_1["custom\nlocal-model"]
    style custom_1 fill:#B2BEC3,stroke:#333,color:#fff
    dispatcher["dispatch\ngpt-5\n30 tok\n15ms"]
    style dispatcher fill:#6C5CE7,stroke:#333,color:#fff

    subgraph Legend
        dispatch[dispatch]
        style dispatch fill:#6C5CE7,stroke:#333,color:#fff
        worker[worker]
        style worker fill:#00B894,stroke:#333,color:#fff
        aggregator[aggregator]
        style aggregator fill:#FDCB6E,stroke:#333,color:#fff
        judge[judge]
        style judge fill:#E17055,stroke:#333,color:#fff
        merge[merge]
        style merge fill:#74B9FF,stroke:#333,color:#fff
        audit[audit]
        style audit fill:#FD79A8,stroke:#333,color:#fff
    end"""


def _healthy_trace() -> dict[str, Any]:
    """Two healthy workers, an aggregator, a fallback-kind stage and a dispatch span."""
    return {
        "dispatch": {
            "stage_id": "dispatcher",
            "model": "openai/gpt-5",
            "tokens_input": 10,
            "tokens_output": 20,
            "latency_ms": 15,
        },
        "stages": [
            {
                "stage_id": "worker_1",
                "kind": "worker",
                "model": "openrouter/qwen/qwen3-coder",
                "provider": "openrouter",
                "tokens_input": 2,
                "tokens_output": 3,
                "latency_ms": 12,
                "depends_on": ["dispatcher"],
            },
            {
                "stage_id": "worker_2",
                "kind": "worker",
                "model": "deepseek/deepseek-chat",
                "tokens_input": 4,
                "tokens_output": 5,
                "latency_ms": 30,
                "depends_on": ["dispatcher"],
            },
            {
                "stage_id": "aggregator_1",
                "kind": "aggregator",
                "model": "zai-coding-plan/glm-5.2",
                "provider": "zai",
                "tokens_input": 6,
                "tokens_output": 7,
                "latency_ms": 40,
                "depends_on": ["worker_1", "worker_2"],
            },
            {
                "stage_id": "custom_1",
                "kind": "custom",
                "model": "local-model",
                "depends_on": [],
            },
        ],
        "worker_failures": [],
    }


def _degraded_trace(stage_id: str, error: str, **stage_overrides: Any) -> dict[str, Any]:
    """The healthy DAG with ``stage_id`` reported failed by the trace."""
    trace = _healthy_trace()
    for stage in trace["stages"]:
        if stage["stage_id"] == stage_id:
            stage.update(stage_overrides)
    model = next(s["model"] for s in trace["stages"] if s["stage_id"] == stage_id)
    trace["worker_failures"] = [{"stage_id": stage_id, "model": model, "error": error}]
    return trace


def _labels(mermaid: str) -> dict[str, str]:
    """Node labels keyed by stage id, with the mermaid line separators made explicit."""
    return {
        m.group("sid"): m.group("label").replace("\\n", "\n")
        for line in mermaid.splitlines()
        if (m := _NODE_LINE_RE.match(line))
    }


def _style_of(mermaid: str, sid: str) -> str:
    for line in mermaid.splitlines():
        if line.startswith(f"    style {sid} "):
            return line
    raise AssertionError(f"no style line for {sid!r} in:\n{mermaid}")


def _error_line(mermaid: str, sid: str) -> str:
    """The error text rendered after the FAILED marker (index-independent)."""
    lines = _labels(mermaid)[sid].split("\n")
    assert "FAILED" in lines, f"{sid!r} carries no FAILED marker: {lines}"
    return " ".join(lines[lines.index("FAILED") + 1 :])


def _assert_mermaid_parses(mermaid: str) -> None:
    """Every node definition is a single well-formed quoted-label line.

    The reference side for the hostile-error tests: a label that swallowed a
    quote, a backslash escape or a raw newline stops matching here.
    """
    assert mermaid.startswith("flowchart TB\n")
    assert "\r" not in mermaid
    for line in mermaid.splitlines():
        if '["' in line:
            assert _NODE_LINE_RE.match(line), f"unparseable node definition: {line!r}"
        if line.startswith("    style "):
            assert _STYLE_LINE_RE.match(line), f"unparseable style line: {line!r}"


# --------------------------------------------------------------------------- #
# A1 — a failed stage renders as FAILED
# --------------------------------------------------------------------------- #


def test_failed_worker_renders_failure_colour_marker_and_error() -> None:
    error = "gateway dropped the connection after 3 retries"
    mermaid = trace_to_mermaid(_degraded_trace("worker_2", error))

    style = _style_of(mermaid, "worker_2")
    assert style == f"    style worker_2 fill:{_FAILURE_HEX},stroke:#333,color:#fff"
    assert "#00B894" not in style  # ...and not the worker-kind green

    label = _labels(mermaid)["worker_2"]
    assert label.split("\n")[:3] == ["worker", "deepseek-chat", "FAILED"]
    assert error in label
    _assert_mermaid_parses(mermaid)


def test_failure_colour_overrides_the_stage_kind_colour() -> None:
    """A failed aggregator (yellow) and a failed judge (coral) go red too."""
    trace = _healthy_trace()
    trace["stages"].append({"stage_id": "judge_1", "kind": "judge", "model": "moonshotai/kimi-k3"})
    trace["worker_failures"] = [
        {"stage_id": "aggregator_1", "model": "zai-coding-plan/glm-5.2", "error": "timeout"},
        {"stage_id": "judge_1", "model": "moonshotai/kimi-k3", "error": "timeout"},
    ]

    mermaid = trace_to_mermaid(trace)

    for sid, kind_colour in (("aggregator_1", "#FDCB6E"), ("judge_1", "#E17055")):
        assert f"fill:{_FAILURE_HEX}," in _style_of(mermaid, sid)
        assert kind_colour not in _style_of(mermaid, sid)
        assert "FAILED" in _labels(mermaid)[sid]
    # The healthy stages keep their kind colours.
    assert "#00B894" in _style_of(mermaid, "worker_1")
    assert "#6C5CE7" in _style_of(mermaid, "dispatcher")


def test_a_failure_changes_only_its_own_node_lines() -> None:
    """A1: surgical — the node definition and its style line, nothing else."""
    before = trace_to_mermaid(_healthy_trace()).splitlines()
    after = trace_to_mermaid(_degraded_trace("worker_2", "502 from upstream")).splitlines()

    assert len(before) == len(after)  # same DAG shape: one node re-coloured
    own = [i for i, line in enumerate(before) if line.startswith(('    worker_2["', "    style worker_2 "))]
    assert len(own) == 2
    differing = [i for i, (b, a) in enumerate(zip(before, after, strict=True)) if b != a]
    assert differing == own
    for i, (b, a) in enumerate(zip(before, after, strict=True)):
        if i not in own:
            assert a == b, f"line {i} should be untouched: {a!r}"


# --------------------------------------------------------------------------- #
# A2 — the success path is untouched
# --------------------------------------------------------------------------- #


def test_healthy_trace_renders_the_pinned_pre_change_output() -> None:
    assert trace_to_mermaid(_healthy_trace()) == _HEALTHY_RENDER_PINNED


def test_traces_without_a_worker_failures_key_render_like_an_empty_list() -> None:
    """Older traces (and the empty-trace fallback) predate the field entirely."""
    trace = _healthy_trace()
    del trace["worker_failures"]

    assert trace_to_mermaid(trace) == _HEALTHY_RENDER_PINNED
    assert trace_to_mermaid({}) == trace_to_mermaid({"worker_failures": []})


# --------------------------------------------------------------------------- #
# Truncation and metric suppression on a failed node
# --------------------------------------------------------------------------- #


def test_long_error_is_truncated_and_the_full_text_stays_out_of_the_dag() -> None:
    big = "D" * 200
    mermaid = trace_to_mermaid(_degraded_trace("worker_1", big))

    error_line = _error_line(mermaid, "worker_1")
    assert error_line.startswith(big[:50])
    assert error_line.endswith("...")
    assert len(error_line) <= 70
    assert big not in mermaid


def test_failed_node_drops_success_metrics() -> None:
    """A degraded stage reports 0 tokens and an elapsed-until-failure latency;
    printed as a completion block that reads as a healthy call."""
    mermaid = trace_to_mermaid(_degraded_trace("worker_1", "402 credits exhausted"))

    label = _labels(mermaid)["worker_1"]
    assert "tok" not in label
    assert "ms" not in label
    assert label.split("\n")[2] == "via openrouter"  # the real attribution survives
    assert label.split("\n")[3] == "FAILED"
    # The same node on the healthy path still carries its metrics.
    assert "5 tok" in _labels(trace_to_mermaid(_healthy_trace()))["worker_1"]


def test_failure_on_the_dispatch_node_is_marked_too() -> None:
    """The same rule for the dispatch span (today the engine keys failures by
    DAG stage id only — the renderer must not depend on that)."""
    trace = _healthy_trace()
    trace["worker_failures"] = [{"stage_id": "dispatcher", "model": "openai/gpt-5", "error": "timeout"}]

    mermaid = trace_to_mermaid(trace)

    assert f"fill:{_FAILURE_HEX}," in _style_of(mermaid, "dispatcher")
    assert _labels(mermaid)["dispatcher"].split("\n")[2] == "FAILED"


# --------------------------------------------------------------------------- #
# A3 — hostile error text cannot break the definition
# --------------------------------------------------------------------------- #


def test_hostile_error_text_cannot_break_the_mermaid_definition() -> None:
    hostile = 'upstream said "no"\\nthen dropped\nretry \\ exhausted \\"final\\"'
    trace = _degraded_trace("worker_2", hostile)

    mermaid = trace_to_mermaid(trace)

    assert isinstance(mermaid, str)
    _assert_mermaid_parses(mermaid)  # the parse oracle accepts the real render
    assert "    style worker_2 fill:" in mermaid
    label = _labels(mermaid)["worker_2"]
    assert "FAILED" in label
    assert '"' not in label
    assert "upstream said" in label
    assert hostile not in mermaid
    # The error line is one line: FAILED plus exactly one error line.
    assert label.split("\n")[2] == "FAILED"
    assert len(label.split("\n")) == 4


def test_the_parse_checker_rejects_a_broken_definition() -> None:
    """The oracle above is not vacuous: it fails on a label that ate a quote."""
    with pytest.raises(AssertionError):
        _assert_mermaid_parses('flowchart TB\n    w1["broken "label""]')


def test_failure_colour_is_a_distinct_palette_entry() -> None:
    from chimera.web.trace_viz import _FAILURE_COLOUR, _KIND_COLOURS

    assert _FAILURE_COLOUR == _FAILURE_HEX
    assert _FAILURE_COLOUR not in set(_KIND_COLOURS.values())
    assert _FAILURE_COLOUR != "#B2BEC3"  # not the grey fallback either

    mermaid = trace_to_mermaid(_degraded_trace("worker_2", "boom"))
    assert f"style worker_2 fill:{_FAILURE_COLOUR}" in mermaid


# --------------------------------------------------------------------------- #
# The real trace shape — a degraded run through the engine
# --------------------------------------------------------------------------- #


async def test_degraded_run_from_the_engine_renders_the_dropped_worker_as_failed(config) -> None:  # type: ignore[no-untyped-def]
    """End to end: the engine's own trace dict (worker_failures + stages) drives
    the DAG, so the stage ids really line up and the dropped worker goes red."""
    payload = dispatch_json(
        workers=[
            ("w_ok", "deepseek/deepseek-v4-flash"),
            ("w_down", "deepseek/deepseek-chat"),
        ]
    )
    dropped = "upstream gateway dropped the connection (timeout after 120s)"

    def responder(model, messages, response_format=None, **kw):  # type: ignore[no-untyped-def]
        if response_format is not None:  # dispatcher design pass
            return resp(payload, model, 100, 200)
        if "Upstream outputs" in json.dumps(messages):  # aggregator
            return resp("MERGED ANSWER", model, 10, 10)
        if model == "deepseek/deepseek-chat":
            raise GatewayError(dropped)  # transient: never recorded as a block
        return resp("WORKER OUTPUT", model, 10, 10)

    result = await Engine(config, FakeGateway(responder)).deliberate("task", "auto")
    trace = result.trace.model_dump(mode="json")

    # The engine's own failure list, keyed by the stage ids the DAG renders.
    assert [f["stage_id"] for f in trace["worker_failures"]] == ["w_down"]
    assert "w_down" in {s["stage_id"] for s in trace["stages"]}

    mermaid = trace_to_mermaid(trace)

    _assert_mermaid_parses(mermaid)
    assert f"fill:{_FAILURE_HEX}," in _style_of(mermaid, "w_down")
    assert "FAILED" in _labels(mermaid)["w_down"]
    assert "timeout after 120s" in _labels(mermaid)["w_down"]
    # The healthy sibling and the aggregator that merged anyway stay untouched.
    assert "#00B894" in _style_of(mermaid, "w_ok")
    assert "#FDCB6E" in _style_of(mermaid, "aggregator")
