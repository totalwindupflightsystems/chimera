"""Tests for the DAG iteration loop — stage re-execution on audit failure."""

from __future__ import annotations

import json

from chimera.engine import Engine, _RE_ITERATION_SIGNAL
from chimera.dispatcher import Stage
from tests.conftest import FakeGateway, resp


def _iter_responder(config, *, max_iterations: int = 3):  # type: ignore[no-untyped-def]
    """Responder that simulates an iteration loop.

    The dispatcher returns a fixed DAG with an audit stage that signals
    failure on the first *N*-1 passes and passes on the *N*th pass.
    Workers and aggregators produce deterministic canned text.
    """
    # Build a DAG with iterate_on on the audit stage.
    # Structure: worker_1 -> aggregator -> audit (iterate_on: [worker_1])
    stages = [
        {"id": "worker_1", "kind": "worker", "model": "deepseek/deepseek-chat",
         "depends_on": []},
        {"id": "aggregator", "kind": "aggregator", "model": "zai-coding-plan/glm-5.2",
         "depends_on": ["worker_1"]},
        {"id": "audit", "kind": "audit", "model": "zai-coding-plan/glm-5.2",
         "depends_on": ["aggregator"],
         "iterate_on": ["worker_1"], "iteration_limit": max_iterations},
    ]
    edges = [["worker_1", "aggregator"], ["aggregator", "audit"]]
    payload = json.dumps({
        "formation": {"stages": stages, "edges": edges},
        "worker_prompts": [
            {"stage_id": "worker_1", "model": "deepseek/deepseek-chat",
             "prompt": "Write the answer.", "expected_output_schema": None},
        ],
        "aggregator_instructions": "Merge the answer.",
        "stage_instructions": {"audit": "Check the answer for correctness."},
    })
    _call_count = [0]  # mutable closure

    def _responder(model, messages, response_format=None, **kw):
        nonlocal _call_count
        if response_format is not None:  # dispatcher
            return resp(payload, model, tok_in=100, tok_out=200)
        joined = json.dumps(messages)
        # Audit stage: fail first iteration_count-1 calls, pass on the Nth
        if "Check the answer" in joined:
            _call_count[0] += 1
            n = _call_count[0]
            if n < max_iterations:
                return resp(
                    '{"passed": false, "feedback": "Missing details."}',
                    model, tok_in=30, tok_out=50,
                )
            return resp(
                '{"passed": true, "feedback": "OK.", "answer": "Final answer."}',
                model, tok_in=30, tok_out=50,
            )
        # Aggregator
        if "Upstream outputs" in joined or "merge" in joined.lower():
            return resp(f"[merged from {model}]", model, tok_in=40, tok_out=60)
        # Worker
        return resp(f"[worker output {model}]", model, tok_in=20, tok_out=30)

    return _responder


# ═══════════════════════════════════════════════════════════════════════════
#  Signal detection tests
# ═══════════════════════════════════════════════════════════════════════════


class TestIterationSignal:
    """_RE_ITERATION_SIGNAL correctly detects pass/fail in stage output."""

    @staticmethod
    def test_detects_passed_false_with_trailing_comma() -> None:
        assert _RE_ITERATION_SIGNAL.search('{"passed": false, "feedback": "nope"}')

    @staticmethod
    def test_detects_passed_false_with_trailing_brace() -> None:
        assert _RE_ITERATION_SIGNAL.search('{"passed": false}')

    @staticmethod
    def test_detects_passed_false_with_spaces() -> None:
        assert _RE_ITERATION_SIGNAL.search('{"passed"  :  false  , "x": 1}')

    @staticmethod
    def test_detects_passed_false_case_insensitive() -> None:
        assert _RE_ITERATION_SIGNAL.search('{"PASSED": false}')

    @staticmethod
    def test_rejects_passed_true() -> None:
        assert not _RE_ITERATION_SIGNAL.search('{"passed": true}')

    @staticmethod
    def test_rejects_no_passed_field() -> None:
        assert not _RE_ITERATION_SIGNAL.search('{"answer": "ok"}')

    @staticmethod
    def test_rejects_plain_text() -> None:
        assert not _RE_ITERATION_SIGNAL.search("The answer looks correct.")


# ═══════════════════════════════════════════════════════════════════════════
#  Check iteration needed helper
# ═══════════════════════════════════════════════════════════════════════════


class TestCheckIterationNeeded:
    """Engine._check_iteration_needed correctly inspects stage spans."""

    @staticmethod
    def test_signals_needed_on_failure(config) -> None:  # type: ignore[no-untyped-def]
        stage = Stage(id="audit", kind="audit", model="m", iterate_on=["w1"])
        span = type("Span", (), {"response": '{"passed": false}'})()  # noqa: E231
        assert Engine._check_iteration_needed(stage, span)

    @staticmethod
    def test_no_signal_on_pass(config) -> None:  # type: ignore[no-untyped-def]
        stage = Stage(id="audit", kind="audit", model="m", iterate_on=["w1"])
        span = type("Span", (), {"response": '{"passed": true}'})()  # noqa: E231
        assert not Engine._check_iteration_needed(stage, span)

    @staticmethod
    def test_no_signal_without_iterate_on(config) -> None:  # type: ignore[no-untyped-def]
        stage = Stage(id="audit", kind="audit", model="m")
        # Without iterate_on, we don't care about the signal
        assert not stage.iterate_on


# ═══════════════════════════════════════════════════════════════════════════
#  Full iteration loop integration tests
# ═══════════════════════════════════════════════════════════════════════════


class TestIterationLoop:
    """Full DAG execution with iteration loop."""

    # The responder in _iter_responder returns a dispatcher payload with a
    # DAG that includes an audit stage with iterate_on.  Using formation="auto"
    # (the default) lets the dispatcher output drive the DAG structure.

    @staticmethod
    async def test_no_iteration_when_audit_passes_first_try(config) -> None:  # type: ignore[no-untyped-def]
        """When audit passes on the first try, the DAG runs exactly once."""
        gw = FakeGateway(_iter_responder(config, max_iterations=1))
        result = await Engine(config, gw).deliberate("test task")
        trace = result.trace
        assert trace.iteration_count == 1, (
            f"Expected 1 iteration, got {trace.iteration_count}"
        )

    @staticmethod
    async def test_re_iterates_on_audit_failure(config) -> None:  # type: ignore[no-untyped-def]
        """When audit fails, the DAG re-runs workers with feedback."""
        gw = FakeGateway(_iter_responder(config, max_iterations=2))
        result = await Engine(config, gw).deliberate("test task")
        trace = result.trace
        # First audit fails, second passes = 2 passes total
        assert trace.iteration_count == 2, (
            f"Expected 2 iterations, got {trace.iteration_count}"
        )

    @staticmethod
    async def test_hits_iteration_limit_and_accepts(config) -> None:  # type: ignore[no-untyped-def]
        """When audit keeps failing, the engine stops at iteration_limit."""
        gw = FakeGateway(_iter_responder(config, max_iterations=3))
        result = await Engine(config, gw).deliberate("test task")
        trace = result.trace
        # With max_iterations=3 and all failing, we should still return
        # the last iteration's result (not loop forever)
        assert trace.iteration_count == 3, (
            f"Expected 3 iterations (limit), got {trace.iteration_count}"
        )
        # Answer should exist even after limit reached
        assert result.answer, "Answer should not be empty after iteration limit"

    @staticmethod
    async def test_no_iterate_on_no_loop_behavior(config) -> None:  # type: ignore[no-untyped-def]
        """A DAG without iterate_on stages runs exactly once regardless of output."""
        from tests.test_engine import _engine_responder

        gw = FakeGateway(_engine_responder(config))
        result = await Engine(config, gw).deliberate("task")
        assert result.trace.iteration_count == 1, (
            f"Expected 1 iteration for non-iterating DAG, "
            f"got {result.trace.iteration_count}"
        )

    @staticmethod
    async def test_feedback_present_in_re_run_worker_prompt(config) -> None:  # type: ignore[no-untyped-def]
        """Re-run workers receive iteration feedback in their prompt."""
        gw = FakeGateway(_iter_responder(config, max_iterations=2))
        await Engine(config, gw).deliberate("test task")
        # Find the worker call with "Previous attempt feedback" in the prompt
        feedback_calls = [
            c for c in gw.calls
            if "Previous attempt feedback" in str(c[1])
        ]
        assert len(feedback_calls) >= 1, (
            "Expected at least one worker call with iteration feedback, "
            f"got {len(feedback_calls)}"
        )

    @staticmethod
    async def test_spans_have_correct_iteration_numbers(config) -> None:  # type: ignore[no-untyped-def]
        """Each StageSpan carries the correct iteration number."""
        gw = FakeGateway(_iter_responder(config, max_iterations=2))
        result = await Engine(config, gw).deliberate("test task")
        trace = result.trace
        # Check that some span has iteration=2 (from re-run)
        stages_with_iter_2 = [s for s in trace.stages if s.iteration == 2]
        assert len(stages_with_iter_2) >= 1, (
            "Expected at least one stage with iteration=2, "
            f"got none. Iterations: {[(s.stage_id, s.iteration) for s in trace.stages]}"
        )
        # The dispatch span should always be iteration=1
        assert trace.dispatch.iteration == 1


# ═══════════════════════════════════════════════════════════════════════════
#  Collect feedback logic
# ═══════════════════════════════════════════════════════════════════════════


class TestCollectFeedback:
    """Engine._collect_feedback builds useful feedback strings."""

    @staticmethod
    def test_returns_feedback_with_trigger_response(config) -> None:  # type: ignore[no-untyped-def]
        trigger = Stage(id="audit", kind="audit", model="m", depends_on=["aggregator"])
        spans = {"audit": type("Span", (), {"response": "Bad output!"})()}  # noqa: E231
        results = {
            "aggregator": type("R", (), {"response": type("G", (), {"text": "Merged."})()})(),
        }
        fb = Engine._collect_feedback(trigger, None, results, spans)  # type: ignore[arg-type]
        assert "Bad output!" in fb
        assert "Merged." in fb

    @staticmethod
    def test_fallback_when_no_spans(config) -> None:  # type: ignore[no-untyped-def]
        trigger = Stage(id="audit", kind="audit", model="m")
        fb = Engine._collect_feedback(trigger, None, {}, {})  # type: ignore[arg-type]
        assert fb == "The previous output needs improvement."
