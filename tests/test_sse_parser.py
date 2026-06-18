"""Unit tests for `_parse_sse_events` — the SSE parser whose regression
caused 15/30 integration tests to fail (events split on blank ``data:`` lines).

These run WITHOUT ``--run-integration`` — they're pure string parsing tests.
"""

from __future__ import annotations

import json

from tests.integration.test_web_sse import _parse_sse_events


# ═══════════════════════════════════════════════════════════════════════════
#  Golden path
# ═══════════════════════════════════════════════════════════════════════════


def test_parse_three_simple_events() -> None:
    """All three event types parse correctly with single-line data."""
    raw = """event: deliberation_started
data: {"prompt": "hello"}

event: dag_designed
data: {"mermaid": "simple graph", "stage_count": 2}

event: deliberation_done
data: {"answer": "42", "total_tokens": 100}"""

    events = _parse_sse_events(raw)
    assert len(events) == 3, f"Expected 3 events, got {len(events)}: {events}"

    assert events[0]["event"] == "deliberation_started"
    assert json.loads(events[0]["data"])["prompt"] == "hello"

    assert events[1]["event"] == "dag_designed"
    data1 = json.loads(events[1]["data"])
    assert data1["mermaid"] == "simple graph"
    assert data1["stage_count"] == 2

    assert events[2]["event"] == "deliberation_done"
    data2 = json.loads(events[2]["data"])
    assert data2["answer"] == "42"


# ═══════════════════════════════════════════════════════════════════════════
#  REGRESSION: multi-line ``data:`` values with blank lines
#  (the bug that caused the 15-test failure cascade)
# ═══════════════════════════════════════════════════════════════════════════


def test_parse_multiline_data_with_blank_lines() -> None:
    """Multi-line data values containing blank lines must NOT split events.

    This is THE regression test.  ``SSEEvent.format()`` splits
    ``json.dumps(data)`` on newlines, producing one ``data:`` line per
    line of JSON.  When the JSON value contains blank lines (e.g. a
    mermaid diagram with ``\\n\\n`` between sections), the corresponding
    ``data:`` line is empty.  The old parser treated empty lines as
    event boundaries, silently dropping the first two events.
    """
    raw = """event: deliberation_started
data: {"prompt": "test"}

event: dag_designed
data: {"mermaid": "flowchart TB\\n    worker_1\\n\\n    subgraph Legend\\n    end", "stage_count": 2}

event: deliberation_done
data: {"answer": "ok"}"""

    events = _parse_sse_events(raw)
    event_types = [e["event"] for e in events]
    assert event_types == [
        "deliberation_started",
        "dag_designed",
        "deliberation_done",
    ], f"Parser dropped events! Got: {event_types}"

    # Verify the mermaid data is intact (joined back with newlines)
    dag_data = json.loads(events[1]["data"])
    assert "flowchart TB" in dag_data["mermaid"]
    assert "subgraph Legend" in dag_data["mermaid"]
    assert dag_data["stage_count"] == 2


def test_parse_multiline_data_consecutive_blank_lines() -> None:
    """Consecutive blank ``data:`` lines don't create phantom events."""
    raw = """event: test
data: line1\\n\\nline2

event: done
data: {}"""

    events = _parse_sse_events(raw)
    assert len(events) == 2, f"Expected 2 events, got {len(events)}: {events}"
    assert events[0]["event"] == "test"
    assert events[1]["event"] == "done"


def test_parse_real_mermaid_output() -> None:
    """Parse a realistic mermaid DAG — the exact format that broke the parser."""
    # Single-line JSON with \\n inside — this is what json.dumps() produces
    mermaid_json = (
        '{"mermaid": "flowchart TB\\n    worker_1\\n\\n    '
        'subgraph Legend\\n    end", "formation": "simple", "stage_count": 3}'
    )
    raw = 'event: dag_designed\n' + 'data: ' + mermaid_json + '\n'

    events = _parse_sse_events(raw)
    assert len(events) == 1, f"Should be 1 event, got {len(events)}: {events}"
    assert events[0]["event"] == "dag_designed"

    data = json.loads(events[0]["data"])
    assert "subgraph Legend" in data["mermaid"]
    assert data["stage_count"] == 3
    assert data["formation"] == "simple"


# ═══════════════════════════════════════════════════════════════════════════
#  Edge cases
# ═══════════════════════════════════════════════════════════════════════════


def test_parse_empty_input() -> None:
    """Empty input produces no events."""
    assert _parse_sse_events("") == []


def test_parse_whitespace_only() -> None:
    """Whitespace-only input produces no events."""
    assert _parse_sse_events("\n\n   \n") == []


def test_parse_single_event_no_data() -> None:
    """An ``event:`` line without ``data:`` still produces a valid event."""
    raw = "event: heartbeat\n"
    events = _parse_sse_events(raw)
    assert len(events) == 1
    assert events[0]["event"] == "heartbeat"
    assert "data" not in events[0]


def test_parse_event_with_id() -> None:
    """``id:`` field attaches to the following event."""
    raw = """id: 42
event: update
data: {"x": 1}"""
    events = _parse_sse_events(raw)
    assert len(events) == 1
    assert events[0]["event"] == "update"
    assert events[0]["id"] == "42"
    assert json.loads(events[0]["data"]) == {"x": 1}


def test_parse_retry_field_ignored() -> None:
    """``retry:`` field is silently ignored (not a parse error)."""
    raw = """retry: 3000
event: test
data: {}"""
    events = _parse_sse_events(raw)
    assert len(events) == 1
    assert events[0]["event"] == "test"


def test_parse_data_only_no_event() -> None:
    """A ``data:`` line without a preceding ``event:`` still creates an entry.

    This is SSE-spec-legal for unnamed events.
    """
    raw = "data: {\"silent\": true}\n"
    events = _parse_sse_events(raw)
    assert len(events) == 1
    assert "event" not in events[0]
    assert json.loads(events[0]["data"]) == {"silent": True}


def test_parse_events_separated_by_blank_lines() -> None:
    """Blank lines between events are ignored (event: triggers new events)."""
    raw = """event: first
data: {}



event: second
data: {}"""
    events = _parse_sse_events(raw)
    assert len(events) == 2
    assert events[0]["event"] == "first"
    assert events[1]["event"] == "second"


def test_parse_is_idempotent() -> None:
    """Parsing the same input twice gives identical results."""
    raw = """event: a
data: {"x": 1}

event: b
data: {"y": 2}"""
    first = _parse_sse_events(raw)
    second = _parse_sse_events(raw)
    assert first == second
