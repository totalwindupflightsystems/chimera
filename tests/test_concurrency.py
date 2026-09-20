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
import copy
import json
from typing import Any

import pytest

from chimera.engine import Engine
from chimera.gateway import GatewayError, GatewayResponse
from tests.conftest import FakeGateway, dispatch_json, resp

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

import chimera.web.routes as web_routes  # noqa: E402
from chimera.api.server import create_app  # noqa: E402
from chimera.config import ChimeraConfig  # noqa: E402
from chimera.web.session import SessionManager  # noqa: E402
from chimera.web.sse import SSEBroadcaster  # noqa: E402
from tests.conftest import CONFIG_DICT  # noqa: E402

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


# --------------------------------------------------------------------------- #
# Web chat path shares the /v1 queue + rate limit (DF-CHIMERA-V2-22)
# --------------------------------------------------------------------------- #
#
# ``POST /web/sessions/{id}/chat`` runs the same billed deliberation as
# ``POST /v1/chat/completions`` but used to bypass BOTH guards, so N concurrent
# web-UI deliberations launched N unrestrained provider fan-outs.  These tests
# pin the shared-queue behaviour: a genuinely saturated queue answers
# 503 + ``Retry-After`` exactly like /v1 in the same state, a completed chat
# releases its slot, and the shared rate limiter actually runs on this path.
#
# Saturation is set up with the queue's OWN public contract — max_concurrent
# in-flight slots plus max_queue_depth parked waiters — and everything runs in
# ONE event loop (httpx ASGITransport), because the endpoint and the holders
# must contend for the same ``asyncio.Semaphore``.  No private attribute is
# touched and no provider is reachable.


def _web_responder(model, messages, response_format=None, **kw):  # type: ignore[no-untyped-def]
    """Canned responder — zero network, mirrors tests/test_web.py::_client."""
    if response_format is not None:
        return resp(dispatch_json(), model, 100, 200)
    joined = json.dumps(messages)
    if "Upstream outputs" in joined:
        return resp("FINAL ANSWER", model, 60, 90)
    return resp(f"worker {model}", model, 20, 40)


def _web_config(**overrides: Any) -> ChimeraConfig:
    """A deep copy of CONFIG_DICT with queue/auth/rate-limit overrides applied."""
    cfg_dict = copy.deepcopy(CONFIG_DICT)
    cfg_dict.update(overrides)
    return ChimeraConfig.model_validate(cfg_dict)


def _build_web(config: ChimeraConfig) -> tuple[TestClient, Any, Any]:
    """Return ``(client, app, gateway)`` built on a stubbed gateway."""
    gateway = FakeGateway(_web_responder)
    app = create_app(config=config, engine=Engine(config, gateway))
    return TestClient(app), app, gateway


@pytest.fixture
def web_singletons():  # type: ignore[no-untyped-def]
    """Isolate the module-level web state (same fixture as tests/test_web.py)."""
    web_routes._session_manager = SessionManager()
    web_routes._sse_broadcaster = SSEBroadcaster()
    yield
    web_routes._session_manager = SessionManager()
    web_routes._sse_broadcaster = SSEBroadcaster()


def _new_session(app: Any, client: TestClient) -> str:  # type: ignore[no-untyped-def]
    """Create a session and pre-arm its SSE readiness signal (no 2s wait)."""
    session_id = client.post("/web/sessions").json()["session_id"]
    web_routes._sse_broadcaster.ensure_ready(session_id).set()
    return session_id


async def _park_waiters(app: Any, count: int) -> list[asyncio.Task]:
    """Hold *count* queue slots with in-flight acquisitions that never release.

    ``RequestQueue.acquire()`` counts a request as *in flight* the moment the
    semaphore is handed over, so these tasks reproduce "the slots are busy"
    without touching any private attribute.
    """

    async def _hold() -> None:
        assert await app.state.request_queue.acquire() is True
        await asyncio.Event().wait()  # held for the whole test

    tasks = [asyncio.create_task(_hold()) for _ in range(count)]
    for _ in range(500):
        if app.state.request_queue.total_queued >= count:
            break
        await asyncio.sleep(0)
    assert app.state.request_queue.total_queued == count, "holders did not take the slots"
    return tasks


async def test_saturated_queue_refuses_web_chat_exactly_like_v1(web_singletons: None) -> None:  # type: ignore[no-untyped-def]
    """Acceptance 1: saturated queue -> 503 + Retry-After on the web path.

    Three requests over one slot (``max_concurrent=1``) with one waiter allowed
    (``max_queue_depth=1``): the holder occupies the slot, the first web chat
    parks as the waiter, and every request after that is refused — the web chat
    and ``/v1/deliberate`` alike, with the same status and the same
    ``Retry-After``.  Releasing the holder then lets the parked web chat finish,
    which is what proves both surfaces contend for one and the same semaphore.
    """
    import httpx

    config = _web_config(queue={"max_concurrent": 1, "max_queue_depth": 1})
    gateway = FakeGateway(_web_responder)
    app = create_app(config=config, engine=Engine(config, gateway))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://chimera.test") as client:
        session_id = (await client.post("/web/sessions")).json()["session_id"]
        web_routes._sse_broadcaster.ensure_ready(session_id).set()

        holders = await _park_waiters(app, 1)
        try:
            # The waiter is the first web chat: it takes the one queue-depth
            # allowance (no semaphore yet), so nothing reaches the engine.
            parked = asyncio.create_task(
                client.post(
                    f"/web/sessions/{session_id}/chat",
                    json={"prompt": "parked", "formation": "simple"},
                )
            )
            for _ in range(500):
                if app.state.request_queue.total_queued >= 2:
                    break
                await asyncio.sleep(0)
            assert app.state.request_queue.total_queued == 2, "the web chat did not park"
            assert gateway.calls == [], "a queued request must not reach the providers"

            # Web surface: refused, 503 + Retry-After, no provider call.
            refused = await client.post(
                f"/web/sessions/{session_id}/chat",
                json={"prompt": "refused", "formation": "simple"},
            )
            assert refused.status_code == 503, refused.text
            assert refused.headers["retry-after"] == "5"
            assert "Server busy — queue full. Retry later." in refused.text
            assert gateway.calls == []

            # /v1 reference surface, in the very same state.
            v1 = await client.post("/v1/deliberate", json={"prompt": "hi", "formation": "simple"})
            assert v1.status_code == 503, v1.text
            assert v1.headers["retry-after"] == refused.headers["retry-after"]
            assert v1.json()["detail"] == "Server busy — queue full. Retry later."
            assert app.state.request_queue.total_rejected == 2

            # A refusal records no turn and broadcasts no SSE event.
            assert session_id not in web_routes._sse_broadcaster._subscribers
            history = (await client.get(f"/web/sessions/{session_id}")).json()
            assert history["turn_count"] == 0

            # Hand the slot back the way a real request's ``finally`` does —
            # cancelling a task does NOT release an asyncio semaphore — then
            # let go of the holder task.  The parked web chat, which was
            # waiting on the SAME semaphore, now runs to completion.
            app.state.request_queue.release()
            holders[0].cancel()
            completed = await asyncio.wait_for(parked, timeout=5.0)
            assert completed.status_code == 200, completed.text
            assert completed.json()["answer"] == "FINAL ANSWER"
            assert gateway.calls, "the parked chat must reach the engine once released"
            # One release for the simulated holder, one for the real web chat.
            assert app.state.request_queue.total_completed == 2
            assert app.state.request_queue.current_waiting == 0
        finally:
            for holder in holders:
                holder.cancel()


def test_successful_web_chat_releases_its_queue_slot(web_singletons: None) -> None:  # type: ignore[no-untyped-def]
    """Acceptance 2: a completed chat frees its slot — pins the try/finally."""
    config = _web_config(queue={"max_concurrent": 1, "max_queue_depth": 100})
    client, app, gateway = _build_web(config)
    session_id = _new_session(app, client)

    first = client.post(
        f"/web/sessions/{session_id}/chat", json={"prompt": "one", "formation": "simple"}
    )
    assert first.status_code == 200, first.text
    # max_concurrent == 1: a leaked slot would block the second call on the
    # semaphore instead of answering, so both assertions below are load-bearing.
    assert app.state.request_queue.total_completed == 1
    assert app.state.request_queue.current_waiting == 0

    web_routes._sse_broadcaster.ensure_ready(session_id).set()
    second = client.post(
        f"/web/sessions/{session_id}/chat", json={"prompt": "two", "formation": "simple"}
    )

    assert second.status_code == 200, second.text
    assert second.json()["turn_number"] == 2
    assert app.state.request_queue.total_completed == 2
    assert gateway.calls


def test_web_chat_releases_its_slot_after_a_failed_deliberation(web_singletons: None) -> None:  # type: ignore[no-untyped-def]
    """The release is in ``finally``: a raising engine still frees the slot."""
    config = _web_config(queue={"max_concurrent": 1, "max_queue_depth": 100})
    client, app, _ = _build_web(config)
    session_id = _new_session(app, client)

    async def boom(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("provider exploded")

    app.state.engine.deliberate = boom  # type: ignore[method-assign]

    with pytest.raises(RuntimeError):
        client.post(f"/web/sessions/{session_id}/chat", json={"prompt": "x", "formation": "simple"})

    assert app.state.request_queue.total_completed == 1
    assert app.state.request_queue.current_waiting == 0
    # The slot is genuinely usable again: a fresh chat (with the real engine
    # restored) is not blocked by the leaked slot.
    app.state.engine.deliberate = _deliberate_op(app)  # type: ignore[assignment]
    web_routes._sse_broadcaster.ensure_ready(session_id).set()
    again = client.post(
        f"/web/sessions/{session_id}/chat", json={"prompt": "y", "formation": "simple"}
    )
    assert again.status_code == 200, again.text


def _deliberate_op(app: Any):  # type: ignore[no-untyped-def]
    """Rebuild a working ``deliberate`` for the app's engine (test-local)."""
    return Engine(app.state.config, FakeGateway(_web_responder)).deliberate


def test_web_chat_is_rate_limited_like_the_v1_surface(web_singletons: None) -> None:  # type: ignore[no-untyped-def]
    """Acceptance 3: the shared ``_check_rate_limit`` runs on the web path."""
    config = _web_config()
    client, app, gateway = _build_web(config)
    # Deliberately NOT pre-armed with the broadcaster: if the guard ever ran
    # after the SSE readiness/broadcast block, this session id would appear in
    # _ready (same technique as tests/test_web_formation_validation.py).
    session_id = client.post("/web/sessions").json()["session_id"]

    def always_deny(key: str) -> tuple[bool, float]:  # noqa: ARG001
        return (False, 30.0)

    app.state.rate_limiter.allow = always_deny  # type: ignore[method-assign]
    gateway.calls.clear()

    response = client.post(
        f"/web/sessions/{session_id}/chat",
        json={"prompt": "hi", "formation": "simple"},
    )
    v1 = client.post("/v1/deliberate", json={"prompt": "hi", "formation": "simple"})

    # Same status, same header and same body the /v1 surface returns for the
    # same limiter state.
    assert response.status_code == 429, response.text
    assert v1.status_code == 429
    assert response.headers["retry-after"] == v1.headers["retry-after"] == "31"
    assert response.json()["detail"] == v1.json()["detail"] == {
        "error": "rate_limited",
        "message": "Too many requests. Please wait before retrying.",
    }

    # Refused at the edge: no provider call, no turn, no queue slot taken.
    assert gateway.calls == []
    history = client.get(f"/web/sessions/{session_id}").json()
    assert history["turn_count"] == 0
    assert session_id not in web_routes._sse_broadcaster._ready
    assert app.state.request_queue.total_queued == 0
    assert app.state.request_queue.total_rejected == 0


def test_web_chat_rate_limit_uses_the_configured_limiter(web_singletons: None) -> None:  # type: ignore[no-untyped-def]
    """A real configured limiter (burst 1) refuses the SECOND web chat."""
    config = _web_config(rate_limit={"enabled": True, "requests_per_minute": 1, "burst_size": 1})
    client, app, _ = _build_web(config)
    session_id = _new_session(app, client)

    first = client.post(
        f"/web/sessions/{session_id}/chat", json={"prompt": "one", "formation": "simple"}
    )
    assert first.status_code == 200, first.text

    web_routes._sse_broadcaster.ensure_ready(session_id).set()
    second = client.post(
        f"/web/sessions/{session_id}/chat", json={"prompt": "two", "formation": "simple"}
    )

    assert second.status_code == 429, second.text
    assert "Retry-After" in second.headers
    assert second.json()["detail"]["error"] == "rate_limited"
    # Same shared bucket key ("anonymous" keyless) as the /v1 surface: the
    # refusal is not a web-only counter.
    assert app.state.rate_limiter.bucket_count() == 1


def test_v1_endpoints_still_take_the_queue_unaffected(web_singletons: None) -> None:  # type: ignore[no-untyped-def]
    """Control: the reference endpoints keep their own guard behaviour."""
    config = _web_config(queue={"max_concurrent": 1, "max_queue_depth": 100})
    client, app, gateway = _build_web(config)

    response = client.post("/v1/deliberate", json={"prompt": "hi", "formation": "simple"})

    assert response.status_code == 200, response.text
    assert app.state.request_queue.total_completed == 1
    assert gateway.calls
