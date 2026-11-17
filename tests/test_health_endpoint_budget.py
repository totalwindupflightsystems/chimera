"""PERF-1: the health endpoints are bounded, the probe is not.

The row: uncached ``/v1/health`` cost 2.6-11.0s because it was pinned to the
slowest provider probe (``health_timeout_s`` + grace ≈ 11s on the live
instance), and a 60s monitor poll always missed the 60s TTL — so every poll
paid the full probe wait. The fix bounds the ENDPOINT: an uncached call waits
at most ``server.health_endpoint_budget_s`` for a single-flight background
refresh, then serves last-known verdicts (``stale`` + ``age_s``) or
``error_class: "in_flight"`` markers for providers still being probed.

Acceptance criteria proven here (all with fake gateways, no real network):

1. one provider hanging past the probe budget → uncached ``/v1/health`` and
   ``/v1/health/ready`` answer well under 2s, and readiness is not
   PERMANENTLY unready: the cold-start 503 in-flight turns into 200 once the
   background refresh lands, and a warm (snapshot-backed) deployment stays
   ready on stale verdicts;
2. ``details.providers`` keeps per-provider ``error_class``/``latency_s``
   once the slow probe lands (served from the cache afterwards), while a
   never-answered provider is distinguishable (``in_flight``, no age) from
   one that answered ``age_s`` ago (``stale: true``);
3. cached ``/v1/health`` stays at millisecond scale; the refresh-failure
   path keeps the pre-PERF-1 probe-exception contract on both endpoints.
"""

from __future__ import annotations

import asyncio
import threading
import time
from typing import Any

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from chimera.api.server import (  # noqa: E402
    _check_providers,
    _degraded_provider_names,
    _ProviderHealthCache,
    create_app,
)
from chimera.config import ChimeraConfig, ServerConfig  # noqa: E402
from chimera.engine import Engine  # noqa: E402
from chimera.gateway import GatewayResponse  # noqa: E402

#: Endpoint budget under test — the ServerConfig default. The AC is "< 2s",
#: so the assertion leaves ~0.5s of scheduling/HTTP overhead on top of it.
ENDPOINT_BUDGET_S = 1.5
ENDPOINT_CEILING_S = 2.0


def _config(
    *,
    models: dict[str, str],
    health_timeout_s: float = 0.2,
    health_probe_grace_s: float = 0.1,
    health_endpoint_budget_s: float | None = None,
    api_keys: dict[str, str] | None = None,
) -> ChimeraConfig:
    """Minimal config: model name → provider name, health knobs explicit.

    The probe budget stays tiny so a hung probe self-terminates quickly;
    tests that prove the AC1 timing use the PRODUCTION probe defaults
    (``health_timeout_s=10, grace=1``) instead, because the point is that the
    ENDPOINT budget (default 1.5s) must hold while the probe outlives it.
    Every provider gets an api key so the probe actually runs (a keyless
    provider is reported ``missing_credentials`` without any live call).
    """
    first_model = next(iter(models))
    cfg_dict: dict[str, Any] = {
        "providers": {name: {"base_url": f"https://{name}.example/v1"} for name in set(models.values())},
        "models": {name: {"provider": provider, "cost_tier": "budget"} for name, provider in models.items()},
        "defaults": {
            "dispatcher": first_model,
            "default_worker": first_model,
            "default_aggregator": first_model,
        },
        "server": {
            "host": "127.0.0.1",
            "port": 8000,
            "health_timeout_s": health_timeout_s,
            "health_probe_grace_s": health_probe_grace_s,
        },
    }
    if health_endpoint_budget_s is not None:
        cfg_dict["server"]["health_endpoint_budget_s"] = health_endpoint_budget_s
    cfg = ChimeraConfig.model_validate(cfg_dict)
    for name in set(models.values()):
        cfg.api_keys.setdefault(name, "sk-test")
    return cfg


class _HangingGateway:
    """A gateway whose completions never answer inside any probe budget.

    The PERF-1 shape (the live hermes gateway): reachable in principle, but
    the probe cannot land, so the ENDPOINT must stop waiting on it.
    """

    def __init__(self) -> None:
        self.completion_calls = 0

    async def complete(self, model: str, messages: list, **kwargs: object) -> GatewayResponse:
        self.completion_calls += 1
        await asyncio.sleep(30)  # outlives every budget in this module
        raise AssertionError("unreachable — the probe is cancelled first")


class _ScriptedGateway:
    """Per-model latency, then a healthy answer — for refresh-landing tests."""

    def __init__(self, delays: dict[str, float]) -> None:
        self.delays = delays
        self.completion_calls = 0

    async def complete(self, model: str, messages: list, **kwargs: object) -> GatewayResponse:
        self.completion_calls += 1
        await asyncio.sleep(self.delays.get(model, 0.0))
        return GatewayResponse(text="pong", model=model, tokens_input=1, tokens_output=1)


def _expired_cache_with_snapshot(cfg: ChimeraConfig, snapshot: dict[str, dict[str, Any]]) -> TestClient:
    """An app whose cache holds an EXPIRED snapshot (the stale-serve premise).

    The config must carry a small ``health_endpoint_budget_s`` — the probe
    budget in these fixtures outlives it, which is the production shape.
    """
    app = create_app(config=cfg, engine=Engine(cfg, _HangingGateway()))
    app.state.provider_health_cache = _ProviderHealthCache(ttl_s=0.05)
    app.state.provider_health_cache.store(snapshot)
    time.sleep(0.08)  # > ttl → get() misses, get_stale() still returns it
    return TestClient(app)


# --------------------------------------------------------------------------- #
# AC1: the endpoint is bounded even when a provider hangs past the probe budget
# --------------------------------------------------------------------------- #


def test_uncached_health_with_hanging_provider_returns_under_2s() -> None:
    """One hanging provider at PRODUCTION probe budgets → /v1/health < 2s.

    ``health_timeout_s=10 + grace=1`` is the measured live shape (11.0s per
    call before the fix); the endpoint must answer inside its own 1.5s
    budget with the probe still running in the background.
    """
    cfg = _config(
        models={"hermes/glm-5.3-flash": "hermes"},
        health_timeout_s=10.0,
        health_probe_grace_s=1.0,
    )
    with _hanging_client(cfg) as client:
        started = time.perf_counter()
        r = client.get("/v1/health")
        elapsed = time.perf_counter() - started

    assert r.status_code == 200
    assert elapsed < ENDPOINT_CEILING_S, f"uncached /v1/health took {elapsed:.2f}s"
    assert elapsed >= ENDPOINT_BUDGET_S * 0.9, "endpoint must actually wait its budget, not skip probing"
    data = r.json()
    # The probe is still running: the provider is unmeasured, not broken.
    assert data["in_flight_providers"] == ["hermes"]
    entry = data["details"]["providers"]["hermes"]
    assert entry["error_class"] == "in_flight"
    assert entry["healthy"] is False
    # No snapshot backs this payload, so there is no honest age to report.
    assert "age_s" not in data["details"]
    # Unmeasured does not degrade (same convention as slow/probe_skipped).
    assert data["status"] == "healthy"
    assert data["unhealthy_providers"] == []


def _hanging_client(cfg: ChimeraConfig) -> TestClient:
    """TestClient over a hanging-probe app, WITH the lifespan.

    The ``with`` block matters: shutdown cancels any refresh task still
    outstanding, and the probe's own cancellation guard tears down its
    per-provider subtasks — a hung probe never leaks past the test.
    """
    return TestClient(create_app(config=cfg, engine=Engine(cfg, _HangingGateway())))


def test_ready_503_names_in_flight_when_nothing_ever_answered() -> None:
    """A cold service where every probe is still running is 503 — with the cause."""
    cfg = _config(
        models={"slow/one": "slowp", "slow/two": "slowq"},
        health_timeout_s=10.0,
        health_probe_grace_s=1.0,
    )
    with _hanging_client(cfg) as client:
        started = time.perf_counter()
        r = client.get("/v1/health/ready")
        elapsed = time.perf_counter() - started

    assert r.status_code == 503
    assert elapsed < ENDPOINT_CEILING_S
    detail = r.json()["detail"]
    assert "Not ready" in detail
    assert "in_flight" in detail
    assert "slowp" in detail and "slowq" in detail


def test_cold_ready_is_not_permanently_unready_once_refresh_lands() -> None:
    """The readiness honesty clause, both halves.

    First poll (cold, probe outstanding): 503 ``in_flight`` — nothing has
    answered, and a never-answered provider must not be dressed up as ready.
    The background refresh then lands (fast provider healthy, hanging one
    slow), and the NEXT poll is 200 ready: transiently unready, never
    permanently, for a service whose providers actually work.
    """
    cfg = _config(
        models={"fast/one": "fastp", "hermes/glm-5.3-flash": "hermes"},
        health_endpoint_budget_s=0.15,  # probe budget (0.2+0.1) outlives it
    )
    gateway = _ScriptedGateway({"fast/one": 0.0, "hermes/glm-5.3-flash": 30.0})
    app = create_app(config=cfg, engine=Engine(cfg, gateway))
    with TestClient(app) as client:
        started = time.perf_counter()
        first = client.get("/v1/health/ready")
        elapsed = time.perf_counter() - started

        assert first.status_code == 503
        assert elapsed < ENDPOINT_CEILING_S
        detail = first.json()["detail"]
        assert "in_flight" in detail
        assert "fastp" in detail  # nothing answered YET — honest, not a lie

        time.sleep(0.5)  # refresh lands: fastp healthy, hermes slow
        second = client.get("/v1/health/ready")

    assert second.status_code == 200
    data = second.json()
    assert data["status"] == "ready"
    assert data["providers"]["fastp"]["healthy"] is True
    assert data["providers"]["hermes"]["error_class"] == "slow"
    assert data["in_flight_providers"] == []


def test_warm_ready_with_hanging_provider_stays_ready_on_stale_verdicts() -> None:
    """The measured live shape, warm: hanging hermes, snapshot-backed verdicts.

    Readiness serves the last-known verdicts within the endpoint budget —
    the healthy one (stale + aged) still satisfies readiness, the hanging
    one keeps its cached ``slow`` class + ``latency_s`` so it stays
    identifiable — and the whole answer arrives in well under 2s.
    """
    cfg = _config(
        models={"fast/one": "fastp", "hermes/glm-5.3-flash": "hermes"},
        health_endpoint_budget_s=0.15,
    )
    snapshot: dict[str, dict[str, Any]] = {
        "fastp": {"healthy": True, "model_tested": "fast/one"},
        "hermes": {
            "healthy": False,
            "error": "slow: no response within 10.0s (probe waited 11.01s)",
            "error_class": "slow",
            "latency_s": 11.007,
        },
    }
    client = _expired_cache_with_snapshot(cfg, snapshot)
    with client:
        started = time.perf_counter()
        r = client.get("/v1/health/ready")
        elapsed = time.perf_counter() - started

    assert r.status_code == 200
    assert elapsed < ENDPOINT_CEILING_S, f"stale-ready took {elapsed:.2f}s"
    data = r.json()
    assert data["status"] == "ready"
    assert data["slow_providers"] == ["hermes"]
    assert data["in_flight_providers"] == []
    providers = data["providers"]
    assert providers["fastp"]["healthy"] is True
    assert providers["fastp"]["stale"] is True
    assert providers["fastp"]["age_s"] > 0
    assert providers["hermes"]["error_class"] == "slow"
    assert providers["hermes"]["latency_s"] == 11.007
    assert providers["hermes"]["stale"] is True


def test_background_refresh_lands_for_the_next_call() -> None:
    """A provider that answers after the budget gets its verdict cached.

    The first call answers partial (in_flight); the refresh keeps running,
    the probe lands HEALTHY, and the second call serves it from the cache at
    ms scale with no new probe call — in_flight was a delay, not a verdict.
    """
    cfg = _config(
        models={"slowish/one": "slowish"},
        health_endpoint_budget_s=0.02,  # returns before the probe can land
        health_timeout_s=1.0,  # the probe IS allowed to finish (healthy at 0.2s)
        health_probe_grace_s=0.0,
    )
    gateway = _ScriptedGateway({"slowish/one": 0.2})
    app = create_app(config=cfg, engine=Engine(cfg, gateway))
    with TestClient(app) as client:
        first = client.get("/v1/health").json()
        assert first["in_flight_providers"] == ["slowish"]
        calls_after_first = gateway.completion_calls

        time.sleep(0.5)  # the background refresh lands here (healthy)
        started = time.perf_counter()
        second = client.get("/v1/health").json()
        elapsed = time.perf_counter() - started

    # second call: cached fresh verdict, ms scale, no new probes
    assert elapsed < 0.05, f"cached call took {elapsed:.3f}s"
    assert gateway.completion_calls == calls_after_first  # single-flight: one round
    assert second["in_flight_providers"] == []
    assert second["details"]["providers"]["slowish"] == {"healthy": True, "model_tested": "slowish/one"}


# --------------------------------------------------------------------------- #
# AC2: per-provider error_class/latency_s survive; never-answered vs answered
# --------------------------------------------------------------------------- #


def test_slow_verdict_lands_in_cache_once_probe_finishes() -> None:
    """AC2: the slow provider stays identifiable with its measured latency."""
    cfg = _config(
        models={"hermes/glm-5.3-flash": "hermes"},
        health_endpoint_budget_s=0.05,  # first call is partial
        health_probe_grace_s=0.1,  # probe gives up at 0.3s → slow verdict lands
    )
    with _hanging_client(cfg) as client:
        first = client.get("/v1/health").json()
        assert first["in_flight_providers"] == ["hermes"]

        time.sleep(0.6)  # budget + grace elapse; the slow verdict is stored
        second = client.get("/v1/health").json()

    entry = second["details"]["providers"]["hermes"]
    assert entry["error_class"] == "slow"
    assert entry["latency_s"] >= 0.2
    assert entry["error"].startswith("slow:")
    assert second["slow_providers"] == ["hermes"]
    assert second["in_flight_providers"] == []


def test_partial_serve_labels_last_known_verdicts_stale() -> None:
    """While the refresh runs, snapshot verdicts come back stale + aged."""
    cfg = _config(models={"p/one": "p"}, health_endpoint_budget_s=0.15)
    snapshot: dict[str, dict[str, Any]] = {"p": {"healthy": True, "model_tested": "p/one"}}
    client = _expired_cache_with_snapshot(cfg, snapshot)
    with client:
        data = client.get("/v1/health").json()

    entry = data["details"]["providers"]["p"]
    assert entry["healthy"] is True
    assert entry["stale"] is True
    assert entry["age_s"] > 0
    # The stale decoration is per-serve: the cached verdict keeps its plain
    # shape for the next fresh store.
    cached, _age = client.app.state.provider_health_cache.get_stale()  # type: ignore[attr-defined]
    assert cached is not None and "stale" not in cached["p"]
    assert data["details"]["age_s"] > 0
    assert data["in_flight_providers"] == []


def test_never_answered_is_distinguishable_from_answered_30s_ago() -> None:
    """in_flight (no age) vs stale (age_s) — the readiness honesty clause."""
    cfg = _config(
        models={"a/one": "a", "b/one": "b"},
        health_endpoint_budget_s=0.15,
    )
    snapshot: dict[str, dict[str, Any]] = {"a": {"healthy": True, "model_tested": "a/one"}}
    client = _expired_cache_with_snapshot(cfg, snapshot)
    with client:
        data = client.get("/v1/health").json()

    providers = data["details"]["providers"]
    assert providers["a"]["stale"] is True
    assert providers["a"]["age_s"] > 0
    assert providers["b"]["error_class"] == "in_flight"
    assert "age_s" not in providers["b"]
    assert "stale" not in providers["b"]
    assert data["in_flight_providers"] == ["b"]


def test_refresh_partial_never_serves_the_stale_snapshot() -> None:
    """``?refresh=1`` asked for fresh data: while it probes, everything is in_flight."""
    cfg = _config(models={"p/one": "p"}, health_endpoint_budget_s=0.15)
    snapshot: dict[str, dict[str, Any]] = {"p": {"healthy": True, "model_tested": "p/one"}}
    client = _expired_cache_with_snapshot(cfg, snapshot)
    with client:
        data = client.get("/v1/health?refresh=1").json()

    entry = data["details"]["providers"]["p"]
    assert entry["error_class"] == "in_flight"
    assert "stale" not in entry
    assert data["in_flight_providers"] == ["p"]


def test_stale_serve_reflects_a_provider_that_reappeared_in_config() -> None:
    """A provider added after the last snapshot reads in_flight, not stale."""
    cfg = _config(models={"a/one": "a"}, health_endpoint_budget_s=0.15)
    snapshot: dict[str, dict[str, Any]] = {"a": {"healthy": True, "model_tested": "a/one"}}
    client = _expired_cache_with_snapshot(cfg, snapshot)
    with client:
        # The config grew since the snapshot: register provider b with a model.
        cfg.models["b/one"] = cfg.models["a/one"].model_copy(update={"provider": "b"})
        cfg.providers["b"] = cfg.providers["a"].model_copy(update={"base_url": "https://b.example/v1"})
        data = client.get("/v1/health").json()

    providers = data["details"]["providers"]
    assert providers["a"]["stale"] is True
    assert providers["b"]["error_class"] == "in_flight"
    assert data["in_flight_providers"] == ["b"]


def test_in_flight_class_does_not_degrade_status() -> None:
    """The degraded aggregation treats in_flight as unmeasured, like slow."""
    status = {
        "p1": {"healthy": False, "error_class": "in_flight"},
        "p2": {"healthy": False, "error": "api: boom", "error_class": "api"},
        "p3": {"healthy": True},
    }
    assert _degraded_provider_names(status) == ["p2"]


# --------------------------------------------------------------------------- #
# AC3: cached stays ms-scale; config knob; failure contract preserved
# --------------------------------------------------------------------------- #


def test_cached_health_stays_ms_scale() -> None:
    """Second call inside the TTL: millisecond scale, no probes."""
    cfg = _config(models={"p/one": "p"})
    gateway = _ScriptedGateway({})
    with TestClient(create_app(config=cfg, engine=Engine(cfg, gateway))) as client:
        client.get("/v1/health")
        calls_after_first = gateway.completion_calls
        started = time.perf_counter()
        r = client.get("/v1/health")
        elapsed = time.perf_counter() - started

    assert r.status_code == 200
    assert elapsed < 0.05, f"cached /v1/health took {elapsed * 1000:.1f}ms"
    assert gateway.completion_calls == calls_after_first
    assert r.json()["details"]["age_s"] > 0


def test_server_config_health_endpoint_budget_default_and_validation() -> None:
    """The knob defaults to 1.5s and refuses non-positive budgets."""
    assert ServerConfig().health_endpoint_budget_s == 1.5
    assert ServerConfig(health_endpoint_budget_s=0.4).health_endpoint_budget_s == 0.4
    with pytest.raises(Exception):  # noqa: B017 — pydantic ValidationError
        ServerConfig(health_endpoint_budget_s=0.0)


def test_refresh_failure_keeps_the_pre_perf1_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A probe that raises (not a hung provider) still degrades honestly."""
    cfg = _config(models={"solo/one": "solo"})

    async def exploding(config: ChimeraConfig, gateway: Any) -> dict[str, Any]:
        raise RuntimeError("probe exploded")

    monkeypatch.setattr("chimera.api.server._check_providers", exploding)
    app = create_app(config=cfg, engine=Engine(cfg, _HangingGateway()))
    with TestClient(app) as client:
        r = client.get("/v1/health")
        ready = client.get("/v1/health/ready")

    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "degraded"
    assert data["unhealthy_providers"] == sorted(cfg.providers)
    assert "probe exploded" in data["details"]["error"]
    assert ready.status_code == 503
    assert "Not ready" in ready.json()["detail"]


# --------------------------------------------------------------------------- #
# Refresh machinery: single-flight, loop guard, shutdown hygiene
# --------------------------------------------------------------------------- #


def test_cache_single_flight_starts_one_probe_round() -> None:
    """A second caller joins the in-flight refresh; the probe runs once."""

    async def scenario() -> None:
        cache = _ProviderHealthCache(ttl_s=60.0)
        calls = {"n": 0}

        async def probe() -> dict[str, dict[str, Any]]:
            calls["n"] += 1
            await asyncio.sleep(0.05)
            return {"p": {"healthy": True}}

        task = cache.begin_refresh(probe)  # factory: built only if the wrapper starts
        assert cache.in_flight_refresh() is task
        await asyncio.wait({task})
        assert cache.in_flight_refresh() is None  # done → nobody joins it
        assert calls["n"] == 1
        results, age = cache.get()
        assert results == {"p": {"healthy": True}}
        assert age is not None and age >= 0

    asyncio.run(scenario())


def test_in_flight_refresh_ignores_a_foreign_loop_task() -> None:
    """A refresh task belonging to another loop must never be awaited cross-loop.

    Test clients run one event loop per request; the guard is what keeps a
    stale loop's task from being joined by the next request's loop.
    """
    cache = _ProviderHealthCache()
    gate = threading.Event()
    started = threading.Event()
    task: asyncio.Task[None] | None = None

    async def probe() -> dict[str, dict[str, Any]]:
        started.set()
        # Park until the main thread releases us — pending on `loop` the whole time.
        await asyncio.get_running_loop().run_in_executor(None, gate.wait, 5.0)
        return {"p": {"healthy": True}}

    loop = asyncio.new_event_loop()
    try:

        async def start_refresh() -> asyncio.Task[None]:
            return cache.begin_refresh(probe)

        task = loop.run_until_complete(start_refresh())
        assert started.wait(timeout=2.0)

        async def check_from_another_loop() -> Any:
            return cache.in_flight_refresh()

        # From a DIFFERENT loop the foreign task is not in flight.
        assert asyncio.run(check_from_another_loop()) is None
    finally:
        gate.set()
        if task is not None:
            task.cancel()
            loop.run_until_complete(asyncio.gather(task, return_exceptions=True))
        loop.close()


def test_lifespan_shutdown_cancels_outstanding_refresh() -> None:
    """The lifespan's shutdown path cancels a refresh that outlived requests."""
    cfg = _config(models={"hermes/glm-5.3-flash": "hermes"}, health_endpoint_budget_s=0.05)

    async def scenario() -> None:
        app = create_app(config=cfg, engine=Engine(cfg, _HangingGateway()))
        cache = app.state.provider_health_cache

        async def probe() -> dict[str, dict[str, Any]]:
            await asyncio.sleep(30)
            return {}

        cache.begin_refresh(probe)
        task = cache.in_flight_refresh()
        assert task is not None

        async with app.router.lifespan_context(app):
            pass  # startup + shutdown; the shutdown hook runs cancel_refresh()

        await asyncio.sleep(0)  # let the cancellation land
        assert task.done()
        assert task.cancelled()

    asyncio.run(scenario())


def test_probe_cancellation_guard_tears_down_subtasks() -> None:
    """Cancelling the probe mid-wait cancels the per-provider subtasks too.

    PERF-1 moved the probe into a background task, so the probe coroutine can
    now be cancelled while its subtasks are still outstanding — and a hung
    subtask must not outlive the loop.
    """

    async def scenario() -> None:
        cfg = _config(models={"hermes/glm-5.3-flash": "hermes"})
        gateway = _HangingGateway()
        task = asyncio.create_task(_check_providers(cfg, gateway))
        await asyncio.sleep(0.05)  # subtasks are up and hanging
        assert gateway.completion_calls > 0
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        # The guard gathered the cancelled subtask before re-raising, so we
        # get control back with nothing still sleeping on the loop.
        assert task.cancelled()

    asyncio.run(scenario())
