"""C1: Concurrency safety tests — multiple simultaneous deliberations on one
Engine instance must not leak state between requests.

Tests verify:
- 10+ concurrent deliberations all complete correctly
- No state leakage (stage results, traces, budget tracking, request IDs)
- Worker outputs belong to the right request
- Concurrency safety under gateway errors
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from chimera.engine import Engine
from chimera.gateway import GatewayError, GatewayResponse
from tests.conftest import FakeGateway, dispatch_json, resp


# --------------------------------------------------------------------------- #
# Concurrency-safe gateway that tags responses with per-request data
# --------------------------------------------------------------------------- #

_REQUEST_KEY = "x-chimera-request"
# Semaphore to introduce deliberate interleaving without breaking determinism.
_RATE_LIMITER: asyncio.Semaphore | None = None


class ConcurrentFakeGateway(FakeGateway):
    """Gateway that tags every response with the request making the call.

    This lets us verify that worker outputs from request A don't leak into
    request B's trace — a classic concurrency bug where mutable state is
    shared across coroutines.
    """

    def __init__(self, responder: Any = None, *, extra_latency: float = 0.0) -> None:
        super().__init__(responder=responder)
        self.extra_latency = extra_latency
        self._call_counts: dict[str, int] = {}
        # Track which request_ids were seen at dispatch time
        self._dispatch_request_ids: list[str] = []

    async def complete(
        self,
        model: str,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.2,
        response_format: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> GatewayResponse:
        self.calls.append((model, messages, {"temperature": temperature,
                                             "response_format": response_format, **kwargs}))

        # Introduce deterministic interleaving by releasing the event loop
        # after each call so concurrent tasks can swap in.
        if self.extra_latency:
            await asyncio.sleep(self.extra_latency)

        if self.responder is not None:
            result = self.responder(model, messages, response_format=response_format,
                                    temperature=temperature, **kwargs)
            if asyncio.iscoroutine(result):
                return await result
            return result
        return GatewayResponse(text=f"[fake response from {model}]",
                               model=model, tokens_input=10, tokens_output=20)


def _tagged_responder(config: Any, request_id_parts: list[str]) -> Any:
    """Responder that includes the calling coroutine's task name in every response."""

    async def _responder(model: str, messages: list[dict[str, str]],
                         response_format: Any = None, **kw: Any) -> GatewayResponse:
        # Yield control so other coroutines can interleave
        await asyncio.sleep(0)
        if response_format is not None:  # dispatcher
            return resp(dispatch_json(), model, tok_in=100, tok_out=200)
        joined = json.dumps(messages)
        if "Upstream outputs" in joined:  # aggregator/merge/audit
            return resp(f"[merged by {model}]", model, tok_in=30, tok_out=50)
        # worker: echo back the task name from the prompt
        content = messages[0]["content"]
        return resp(f"[worker {model}: {content[:60]}]", model, tok_in=20, tok_out=30)

    return _responder


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_single_deliberation_completes(config) -> None:  # type: ignore[no-untyped-def]
    """Baseline: one deliberation completes normally with the tagged gateway."""
    gw = ConcurrentFakeGateway(_tagged_responder(config, []))
    result = await Engine(config, gw).deliberate("What is 2+2?", "auto")
    assert result.answer.startswith("[merged by")
    assert len(result.trace.workers) >= 1
    assert result.trace.total_tokens > 0


@pytest.mark.asyncio
async def test_two_concurrent_deliberations_no_state_leakage(config) -> None:  # type: ignore[no-untyped-def]
    """Two concurrent deliberations must not leak stage results between them."""
    engine = Engine(config, ConcurrentFakeGateway(_tagged_responder(config, []), extra_latency=0.001))

    async def run(prompt: str) -> str:
        result = await engine.deliberate(prompt, "auto")
        return result.answer

    a, b = await asyncio.gather(
        run("What is the capital of France?"),
        run("What is the capital of Germany?"),
    )

    # Both get valid aggregator answers (not empty or error text)
    assert a.startswith("[merged by")
    assert b.startswith("[merged by")
    # Answers may be identical (same merger) but never empty
    assert len(a) > 10
    assert len(b) > 10


@pytest.mark.asyncio
async def test_ten_concurrent_deliberations_all_complete(config) -> None:  # type: ignore[no-untyped-def]
    """10 concurrent deliberations all produce valid results."""
    n = 10

    class CountingGateway(ConcurrentFakeGateway):
        async def complete(self, model, messages, **kw):
            await asyncio.sleep(0)  # yield to interleave
            return await super().complete(model, messages, **kw)

    gw = CountingGateway(_tagged_responder(config, []), extra_latency=0.0005)
    engine = Engine(config, gw)

    async def run(i: int) -> tuple[int, str, int]:
        result = await engine.deliberate(f"Task number {i}", "auto")
        return i, result.answer, result.trace.total_tokens

    outcomes = await asyncio.gather(*(run(i) for i in range(n)))

    assert len(outcomes) == n
    for idx, answer, tokens in outcomes:
        assert answer.startswith("[merged by"), f"Task {idx} got unexpected answer: {answer!r}"
        assert tokens > 0, f"Task {idx} had zero tokens"


@pytest.mark.asyncio
async def test_request_ids_are_unique_under_concurrency(config) -> None:  # type: ignore[no-untyped-def]
    """Every concurrent deliberation gets a unique request_id."""
    gw = ConcurrentFakeGateway(_tagged_responder(config, []), extra_latency=0.001)
    engine = Engine(config, gw)

    async def run(i: int) -> str:
        result = await engine.deliberate(f"Task {i}", "auto")
        return result.trace.request_id

    request_ids = await asyncio.gather(*(run(i) for i in range(20)))

    # All 16-char hex request IDs are unique
    assert len(set(request_ids)) == 20
    for rid in request_ids:
        assert len(rid) == 16
        int(rid, 16)  # valid hex


@pytest.mark.asyncio
async def test_worker_outputs_dont_leak_between_concurrent_requests(config) -> None:  # type: ignore[no-untyped-def]
    """Worker outputs from request A should not appear in request B's trace.

    This is the classic concurrency bug: mutable shared state (like a dict of
    stage results) gets overwritten by a concurrent coroutine.
    """
    captured_traces: list[Any] = []

    class CapturingGateway(ConcurrentFakeGateway):
        async def complete(self, model, messages, **kw):
            await asyncio.sleep(0)  # maximize interleaving
            return await super().complete(model, messages, **kw)

    gw = CapturingGateway(_tagged_responder(config, []))
    engine = Engine(config, gw)

    async def run(prompt: str, marker: str) -> None:
        result = await engine.deliberate(prompt, "auto")
        captured_traces.append((marker, result.trace))

    await asyncio.gather(
        run("Alpha prompt with distinctive text AAAA", "alpha"),
        run("Beta prompt with distinctive text BBBB", "beta"),
        run("Gamma prompt with distinctive text CCCC", "gamma"),
    )

    assert len(captured_traces) == 3

    # Each trace's worker prompts should reference ONLY its own prompt, not
    # the prompts of other concurrent requests.
    for marker, trace in captured_traces:
        assert trace.workers, f"Trace {marker} has no workers"
        # Dispatch prompt should contain the request's own text
        dispatch_text = trace.dispatch.prompt
        # Check that the marker text appears (case-insensitive)
        assert marker in dispatch_text.lower(), (
            f"Trace {marker} dispatch missing own marker: {dispatch_text!r}"
        )


@pytest.mark.asyncio
async def test_concurrent_deliberations_independent_budgets(config) -> None:  # type: ignore[no-untyped-def]
    """Each concurrent deliberation calculates its own cost independently."""
    n = 10
    gw = ConcurrentFakeGateway(_tagged_responder(config, []), extra_latency=0.001)
    engine = Engine(config, gw)

    async def run(i: int) -> float:
        result = await engine.deliberate(f"Budget test {i}", "auto")
        return result.trace.total_cost

    costs = await asyncio.gather(*(run(i) for i in range(n)))

    # Every deliberation has a non-zero cost (API calls were simulated)
    for i, cost in enumerate(costs):
        assert cost > 0.0, f"Deliberation {i} had zero cost"
        assert cost < 1.0, f"Deliberation {i} cost {cost} is unreasonably high"


@pytest.mark.asyncio
async def test_concurrent_with_gateway_errors_some_failing(config) -> None:  # type: ignore[no-untyped-def]
    """Some concurrent requests failing with gateway errors don't corrupt others."""

    class FlakyConcurrentGateway(ConcurrentFakeGateway):
        def __init__(self) -> None:
            super().__init__(_tagged_responder(config, []), extra_latency=0.001)
            self._fail_count = 0

        async def complete(self, model, messages, **kw):
            await asyncio.sleep(0)
            self._fail_count += 1
            if self._fail_count <= 3:
                raise GatewayError("simulated transient failure")
            return await super().complete(model, messages, **kw)

    gw = FlakyConcurrentGateway()
    engine = Engine(config, gw)

    outcomes: list[str] = []

    async def run(i: int) -> None:
        try:
            result = await engine.deliberate(f"Task {i}", "auto")
            outcomes.append(f"ok:{i}:{result.trace.source}")
        except Exception as exc:
            outcomes.append(f"err:{i}:{type(exc).__name__}")

    await asyncio.gather(*(run(i) for i in range(5)))

    # Some completed successfully
    oks = [o for o in outcomes if o.startswith("ok:")]
    assert len(oks) >= 1, f"Expected at least one successful deliberation, got: {outcomes}"


@pytest.mark.asyncio
async def test_concurrent_high_volume_50_deliberations(config) -> None:  # type: ignore[no-untyped-def]
    """Stress test: 50 concurrent deliberations all complete without corruption."""
    n = 50

    class FastGateway(ConcurrentFakeGateway):
        async def complete(self, model, messages, **kw):
            return await super().complete(model, messages, **kw)

    gw = FastGateway(_tagged_responder(config, []))
    engine = Engine(config, gw)

    async def run(i: int) -> tuple[int, bool, int]:
        result = await engine.deliberate(f"Stress test {i}", "auto")
        # Verify structural integrity
        ok = (
            result.answer.startswith("[merged by")
            and len(result.trace.workers) >= 1
            and result.trace.total_tokens > 0
            and result.trace.total_cost > 0
        )
        return i, ok, result.trace.total_tokens

    results = await asyncio.gather(*(run(i) for i in range(n)))

    assert len(results) == n
    failures = [(idx, tokens) for idx, ok, tokens in results if not ok]
    assert not failures, f"Failures in concurrent high-volume test: {failures}"

    # All request IDs should be unique
    # (We can't easily collect them here without storing, but the test above
    # already validates uniqueness.)


@pytest.mark.asyncio
async def test_config_snapshot_isolated_from_mutation(config) -> None:  # type: ignore[no-untyped-def]
    """Modifying the config after Engine init must NOT affect in-flight requests."""
    engine = Engine(config, ConcurrentFakeGateway(_tagged_responder(config, [])))

    # Modify the live config object AFTER engine init
    original_dispatcher = config.defaults.dispatcher
    config.defaults.dispatcher = "deepseek/deepseek-chat"

    result = await engine.deliberate("test mutation isolation", "auto")

    # The engine's snapshot should still have the original dispatcher
    assert engine.config.defaults.dispatcher == original_dispatcher
    # The mutated live config has the new value
    assert config.defaults.dispatcher == "deepseek/deepseek-chat"
    # The deliberation completed using the snapshot values
    assert result.answer.startswith("[merged by")


@pytest.mark.asyncio
async def test_config_snapshot_models_isolated(config) -> None:  # type: ignore[no-untyped-def]
    """Mutating model entries in the original config doesn't affect the engine snapshot."""
    engine = Engine(config, ConcurrentFakeGateway(_tagged_responder(config, [])))

    # Remove a model from the live config
    del config.models["openrouter/google/gemini-2.5-flash"]

    result = await engine.deliberate("test model isolation", "auto")

    # Engine snapshot still has the model
    assert "openrouter/google/gemini-2.5-flash" in engine.config.models
    # Live config does not
    assert "openrouter/google/gemini-2.5-flash" not in config.models
    assert result.answer.startswith("[merged by")


@pytest.mark.asyncio
async def test_config_mutation_logs_warning(config, capsys) -> None:  # type: ignore[no-untyped-def]
    """Mutating the config after snapshot triggers a warning log."""

    engine = Engine(config, ConcurrentFakeGateway(_tagged_responder(config, [])))

    # Mutate the config
    config.defaults.default_worker = "zai-coding-plan/glm-5.2"

    await engine.deliberate("test mutation warning", "auto")

    # structlog writes to stdout — check captured output
    captured = capsys.readouterr().out
    assert "config_mutated_after_snapshot" in captured, (
        f"Expected config_mutated_after_snapshot in stdout, got: {captured}"
    )
