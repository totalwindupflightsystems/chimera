"""DF-CHIMERA-V2-25 — the SPA wires mid-run stage events into the DAG panel.

The server half (stage_started / stage_completed on the SSE wire) landed in
DF-CHIMERA-V2-18; this locks the user-visible consumer half: the shipped
``static/index.html`` must register listeners for both event names inside
``connectSSE``, drive the stat tiles from ``stage_completed``, and show /
hide the LIVE indicator around stage activity.

Hermetic by construction: reads the shipped HTML source and asserts on the
wiring strings themselves, so deleting the listener registration (or its
body) fails these tests — proven by the RED run in the task report.
"""

from __future__ import annotations

import pathlib
import re

import pytest

HTML_PATH = (
    pathlib.Path(__file__).resolve().parent.parent / "src" / "chimera" / "web" / "static" / "index.html"
)


@pytest.fixture(scope="module")
def spa_source() -> str:
    assert HTML_PATH.is_file(), f"shipped SPA missing: {HTML_PATH}"
    return HTML_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def connect_sse_body(spa_source: str) -> str:
    """The body of ``function connectSSE(...) { ... }`` — the listener home."""
    match = re.search(r"function connectSSE\([^)]*\) \{", spa_source)
    assert match, "connectSSE() not found in index.html"
    # Take everything from connectSSE to the next top-level function section
    # header; listener registrations all live inside this window.
    nxt = re.search(r"\n// ═+\n// Send Message", spa_source[match.start() :])
    end = match.start() + nxt.start() if nxt else len(spa_source)
    return spa_source[match.start() : end]


# ---------------------------------------------------------------------------
# AC1 — both stage-event listeners are registered inside connectSSE
# ---------------------------------------------------------------------------


def test_stage_started_listener_registered_in_connect_sse(connect_sse_body: str) -> None:
    assert "addEventListener('stage_started'" in connect_sse_body


def test_stage_completed_listener_registered_in_connect_sse(connect_sse_body: str) -> None:
    assert "addEventListener('stage_completed'" in connect_sse_body


def test_stage_listeners_use_the_wire_payload_field(connect_sse_body: str) -> None:
    """The SSE payloads carry the stage id under ``stage`` (web/routes.py);
    the SPA must consume that field (``stage_id`` is accepted defensively)."""
    started = connect_sse_body.split("addEventListener('stage_started'")[1]
    completed = connect_sse_body.split("addEventListener('stage_completed'")[1]
    for body in (started, completed):
        assert "data.stage" in body or "stageEventId(data)" in body


# ---------------------------------------------------------------------------
# AC2 (defensive-wiring) — the listeners must be non-throwing so a malformed
# payload can never break the SSE stream
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("event_name", ["stage_started", "stage_completed"])
def test_stage_listener_bodies_are_try_wrapped(connect_sse_body: str, event_name: str) -> None:
    body = connect_sse_body.split(f"addEventListener('{event_name}'")[1]
    assert "try {" in body, f"{event_name} listener body must be defensive (try/catch)"
    assert "catch" in body


# ---------------------------------------------------------------------------
# AC3 — tile updates driven by stage_completed, helpers reused
# ---------------------------------------------------------------------------


def test_stage_completed_updates_all_four_stat_tiles(connect_sse_body: str) -> None:
    body = connect_sse_body.split("addEventListener('stage_completed'")[1]
    assert "stat-tokens" in body
    assert "stat-cost" in body
    assert "stat-time" in body
    assert "stat-stages" in body


def test_stage_completed_uses_shared_tile_helpers(connect_sse_body: str) -> None:
    body = connect_sse_body.split("addEventListener('stage_completed'")[1]
    assert "animateValue(" in body, "tokens tile should animate via the shared helper"
    assert "fmtMs(" in body, "latency tile should format via the shared helper"


def test_stage_started_updates_status_line(connect_sse_body: str) -> None:
    body = connect_sse_body.split("addEventListener('stage_started'")[1]
    assert "setStatus(" in body
    assert "Running" in body


# ---------------------------------------------------------------------------
# LIVE indicator lifecycle: shown on stage activity, flipped off on completion
# ---------------------------------------------------------------------------


def test_stage_started_shows_live_indicator(connect_sse_body: str) -> None:
    body = connect_sse_body.split("addEventListener('stage_started'")[1]
    assert "'dag-live-indicator'" in body
    assert "style.display = 'flex'" in body


def test_deliberation_done_hides_live_indicator(connect_sse_body: str) -> None:
    body = connect_sse_body.split("addEventListener('deliberation_done'")[1]
    assert "'dag-live-indicator'" in body
    assert "style.display = 'none'" in body


# ---------------------------------------------------------------------------
# Node matching: in-flight and done classes land on the DAG node
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("event_name", "state", "css_class"),
    [("stage_started", "in-flight", "node-in-flight"), ("stage_completed", "done", "node-done")],
)
def test_stage_events_style_dag_nodes(
    connect_sse_body: str, spa_source: str, event_name: str, state: str, css_class: str
) -> None:
    """Each listener must flip the DAG node through markDagNode(sid, <state>),
    and the shared helper must translate that state into the real CSS class —
    otherwise the node styling is dead wiring."""
    body = connect_sse_body.split(f"addEventListener('{event_name}'")[1]
    assert f"markDagNode(sid, '{state}')" in body, (
        f"{event_name} must route the node through markDagNode('{state}')"
    )
    helper = spa_source.split("function markDagNode(")[1].split("\nfunction ")[0]
    assert f"'{css_class}'" in helper
    # The styled class must have CSS rules backing it.
    assert f".{css_class}" in spa_source


def test_dag_node_state_css_rules_exist(spa_source: str) -> None:
    """The styled classes must have CSS rules — otherwise the states are
    invisible and the node styling is dead wiring."""
    assert ".node-in-flight" in spa_source
    assert ".node-done" in spa_source


def test_dag_designed_replays_recorded_stage_states(spa_source: str) -> None:
    """Stage events precede the DAG render on a live run, so dag_designed's
    render callback must replay the recorded states (applyDagStates)."""
    dag_designed = spa_source.split("addEventListener('dag_designed'")[1]
    dag_designed = dag_designed.split("addEventListener(")[0]
    assert "applyDagStates()" in dag_designed
