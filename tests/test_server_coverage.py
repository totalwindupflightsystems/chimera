"""Coverage-focused tests for chimera.api.server — health probes, queue
overflow, error handlers, _check_providers, and the run() entrypoint.

External dependencies (uvicorn, litellm) are mocked where needed.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import patch

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from chimera.api.server import RequestQueue, _check_providers, create_app  # noqa: E402
from chimera.config import ChimeraConfig  # noqa: E402
from chimera.engine import Engine  # noqa: E402
from chimera.gateway import GatewayResponse  # noqa: E402
from tests.conftest import CONFIG_DICT, FakeGateway, dispatch_json  # noqa: E402

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _resp(text: str, model: str, ti: int = 10, to: int = 20) -> GatewayResponse:
    return GatewayResponse(text=text, model=model, tokens_input=ti, tokens_output=to)


def _client(config: ChimeraConfig) -> TestClient:
    def responder(model: str, messages: list, response_format=None, **kw: Any):
        if response_format is not None:
            return _resp(dispatch_json(), model, 100, 200)
        joined = json.dumps(messages)
        if "Upstream outputs" in joined:
            return _resp("FINAL ANSWER", model, 60, 90)
        return _resp(f"worker {model}", model, 20, 40)

    engine = Engine(config, FakeGateway(responder))
    app = create_app(config=config, engine=engine)
    return TestClient(app)


def _client_with_engine(config: ChimeraConfig, engine: Engine) -> TestClient:
    app = create_app(config=config, engine=engine)
    return TestClient(app)


# =========================================================================== #
# RequestQueue — properties and edge cases
# =========================================================================== #

class TestRequestQueueProperties:
    """Cover current_waiting and max_queue_depth properties."""

    def test_max_queue_depth_property(self) -> None:
        q = RequestQueue(max_concurrent=5, max_queue_depth=50)
        assert q.max_queue_depth == 50

    def test_current_waiting_starts_zero(self) -> None:
        q = RequestQueue(max_concurrent=5, max_queue_depth=50)
        assert q.current_waiting == 0

    @pytest.mark.asyncio
    async def test_acquire_and_release_increments_stats(self) -> None:
        q = RequestQueue(max_concurrent=2, max_queue_depth=10)
        assert await q.acquire() is True
        assert q.total_queued == 1
        q.release()
        assert q.total_completed == 1

    @pytest.mark.asyncio
    async def test_queue_full_rejects(self) -> None:
        """When waiting count exceeds max_queue_depth, acquire returns False.

        Flow with max_concurrent=1, max_queue_depth=1:
        1. First acquire takes the single concurrency slot (success).
        2. Second acquire starts waiting (current_waiting=1, blocks on semaphore).
        3. Third acquire: current_waiting(1) >= max_queue_depth(1) → reject.
        """
        q = RequestQueue(max_concurrent=1, max_queue_depth=1)

        # 1. First acquire — takes the slot
        assert await q.acquire() is True

        # 2. Second acquire — blocks on the semaphore (waiting)
        second_task = asyncio.create_task(q.acquire())

        # Let the second task enter the waiting state
        await asyncio.sleep(0.05)
        assert q.current_waiting == 1

        # 3. Third acquire — queue is full (1 waiting >= max_queue_depth=1)
        result = await q.acquire()
        assert result is False
        assert q.total_rejected == 1

        # Cleanup
        q.release()
        await second_task
        q.release()


# =========================================================================== #
# Health check endpoints
# =========================================================================== #

class TestHealthEndpoints:
    """Cover /v1/health, /v1/health/ready, /v1/health/live."""

    def test_health_live_returns_alive(self, config: ChimeraConfig) -> None:  # type: ignore[no-untyped-def]
        client = _client(config)
        r = client.get("/v1/health/live")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "alive"
        assert data["uptime_models"] == len(config.models)

    def test_health_ready_returns_ready(self, config: ChimeraConfig) -> None:  # type: ignore[no-untyped-def]
        """With FakeGateway always succeeding, readiness should return 200."""
        client = _client(config)
        r = client.get("/v1/health/ready")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ready"
        assert "providers" in data

    def test_health_ready_returns_503_when_no_provider_healthy(
        self, config: ChimeraConfig,  # type: ignore[no-untyped-def]
    ) -> None:
        """When gateway always fails, readiness should return 503.

        Note: providers without any configured models are always marked healthy
        (they never get tested). We remove the 'anthropic' provider (no models)
        to ensure ALL providers actually fail the connectivity check.
        """
        cfg_dict = dict(CONFIG_DICT)
        cfg_dict["providers"] = {
            "openrouter": {"base_url": "https://openrouter.ai/api/v1"},
            "zai": {"base_url": "https://api.z.ai/api/coding/paas/v4"},
        }
        config = ChimeraConfig.model_validate(cfg_dict)

        def failing(model: str, messages: list, **kw: Any):
            raise RuntimeError("provider down")

        engine = Engine(config, FakeGateway(failing))
        client = _client_with_engine(config, engine)
        r = client.get("/v1/health/ready")
        assert r.status_code == 503

    def test_health_returns_degraded_on_all_unhealthy(
        self, config: ChimeraConfig,  # type: ignore[no-untyped-def]
    ) -> None:
        """When all model-bearing providers fail, /v1/health returns degraded."""
        def failing(model: str, messages: list, **kw: Any):
            raise RuntimeError("provider down")

        engine = Engine(config, FakeGateway(failing))
        client = _client_with_engine(config, engine)
        r = client.get("/v1/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "degraded"

    def test_health_returns_healthy_when_all_ok(
        self, config: ChimeraConfig,  # type: ignore[no-untyped-def]
    ) -> None:
        """When all providers respond, /v1/health returns healthy."""
        client = _client(config)
        r = client.get("/v1/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "healthy"
        details = data["details"]
        assert details["config_loaded"] is True
        assert details["models_configured"] == len(config.models)
        assert details["providers_configured"] == len(config.providers)

    def test_health_handles_gateway_exception(
        self, config: ChimeraConfig,  # type: ignore[no-untyped-def]
    ) -> None:
        """If _check_providers raises unexpectedly, health returns degraded."""
        def exploding(model: str, messages: list, **kw: Any):
            raise ConnectionError("boom")

        engine = Engine(config, FakeGateway(exploding))
        client = _client_with_engine(config, engine)
        r = client.get("/v1/health")
        # Should not crash — returns degraded
        assert r.status_code == 200
        assert r.json()["status"] == "degraded"

    def test_readiness_handles_unexpected_exception(
        self, config: ChimeraConfig,  # type: ignore[no-untyped-def]
    ) -> None:
        """If _check_providers raises unexpectedly, readiness returns 503.

        Remove the 'anthropic' provider (no models → always healthy) so that
        every provider actually exercises the gateway path and fails.
        """
        cfg_dict = dict(CONFIG_DICT)
        cfg_dict["providers"] = {
            "openrouter": {"base_url": "https://openrouter.ai/api/v1"},
            "zai": {"base_url": "https://api.z.ai/api/coding/paas/v4"},
        }
        config = ChimeraConfig.model_validate(cfg_dict)

        def exploding(model: str, messages: list, **kw: Any):
            raise ValueError("unexpected")

        engine = Engine(config, FakeGateway(exploding))
        client = _client_with_engine(config, engine)
        r = client.get("/v1/health/ready")
        assert r.status_code == 503


# =========================================================================== #
# Queue overflow → 503
# =========================================================================== #

class TestQueueOverflow:
    """Cover the 503 path when the request queue is full."""

    def test_deliberate_returns_503_when_queue_full(
        self, config: ChimeraConfig,  # type: ignore[no-untyped-def]
    ) -> None:
        """When queue.acquire() returns False, /v1/deliberate returns 503."""
        client = _client(config)
        # Monkeypatch the app's request queue to always reject
        async def always_reject() -> bool:
            return False
        client.app.state.request_queue.acquire = always_reject  # type: ignore[attr-defined]

        r = client.post("/v1/deliberate",
                        json={"prompt": "overflow", "formation": "auto"})
        assert r.status_code == 503
        assert "Retry-After" in r.headers

    def test_chat_completions_returns_503_when_queue_full(
        self, config: ChimeraConfig,  # type: ignore[no-untyped-def]
    ) -> None:
        """When queue is full, /v1/chat/completions returns 503."""
        # Mock the queue to always reject
        cfg_dict = dict(CONFIG_DICT)
        config = ChimeraConfig.model_validate(cfg_dict)

        client = _client(config)
        # Monkeypatch the app's request queue to always reject
        async def always_reject() -> bool:
            return False
        client.app.state.request_queue.acquire = always_reject  # type: ignore[attr-defined]

        r = client.post(
            "/v1/chat/completions",
            json={"model": "auto", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert r.status_code == 503


# =========================================================================== #
# Chat completions DAG rejection + response_format extraction
# =========================================================================== #

class TestChatCompletionsEdgeCases:
    """Cover DAG rejection and response_format handling in chat completions."""

    def test_chat_completions_dag_rejected_without_opt_in(
        self, config: ChimeraConfig,  # type: ignore[no-untyped-def]
    ) -> None:
        """dag supplied without allow_custom_dag → HTTP 400."""
        client = _client(config)
        r = client.post(
            "/v1/chat/completions",
            json={
                "model": "auto",
                "messages": [{"role": "user", "content": "hi"}],
                "dag": {"stages": [], "edges": []},
                "allow_custom_dag": False,
            },
        )
        assert r.status_code == 400
        assert "allow_custom_dag" in r.json()["detail"]

    def test_chat_completions_json_schema_response_format(
        self, config: ChimeraConfig,  # type: ignore[no-untyped-def]
    ) -> None:
        """json_schema response_format is extracted and passed as output_schema."""
        captured: list[Any] = []

        def grab(model: str, messages: list, response_format=None, **kw: Any):
            if response_format is not None:
                captured.append(json.dumps(messages))
                return _resp(dispatch_json(), model, 10, 10)
            return _resp("FINAL ANSWER", model, 10, 10)

        engine = Engine(config, FakeGateway(grab))
        app = create_app(config=config, engine=engine)
        client = TestClient(app)

        r = client.post(
            "/v1/chat/completions",
            json={
                "model": "auto",
                "messages": [{"role": "user", "content": "hi"}],
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {"name": "test", "schema": {"type": "object"}},
                },
            },
        )
        assert r.status_code == 200, r.text

    def test_chat_completions_json_object_response_format(
        self, config: ChimeraConfig,  # type: ignore[no-untyped-def]
    ) -> None:
        """json_object response_format is extracted as generic object schema."""
        def grab(model: str, messages: list, response_format=None, **kw: Any):
            if response_format is not None:
                return _resp(dispatch_json(), model, 10, 10)
            return _resp("FINAL ANSWER", model, 10, 10)

        engine = Engine(config, FakeGateway(grab))
        app = create_app(config=config, engine=engine)
        client = TestClient(app)

        r = client.post(
            "/v1/chat/completions",
            json={
                "model": "auto",
                "messages": [{"role": "user", "content": "hi"}],
                "response_format": {"type": "json_object"},
            },
        )
        assert r.status_code == 200, r.text

    def test_deliberate_unknown_formation_returns_422(
        self, config: ChimeraConfig,  # type: ignore[no-untyped-def]
    ) -> None:
        """Unknown formation on /v1/deliberate → HTTP 422 (VALIDATION-001)."""
        def _unused(model: str, messages: list, **kw: Any) -> GatewayResponse:
            raise RuntimeError("not used")
        engine = Engine(config, FakeGateway(_unused))

        # Patch engine.deliberate to raise ValueError — should never be reached
        # now because the handler validates formations before calling the engine.
        async def raising_deliberate(*a: Any, **kw: Any) -> Any:
            raise ValueError("bad formation")

        engine.deliberate = raising_deliberate  # type: ignore[assignment]
        app = create_app(config=config, engine=engine)
        client = TestClient(app)

        r = client.post("/v1/deliberate", json={"prompt": "hi", "formation": "no-such"})
        assert r.status_code == 422
        assert "Unknown formation" in r.json()["detail"]


# =========================================================================== #
# _check_providers helper — direct unit tests
# =========================================================================== #

class TestCheckProviders:
    """Cover _check_providers directly: success, timeout, exception, empty."""

    @pytest.mark.asyncio
    async def test_all_providers_healthy(self, config: ChimeraConfig) -> None:  # type: ignore[no-untyped-def]
        class GoodGateway:
            async def complete(self, model: str, messages: list, **kw: Any):
                return _resp("ok", model)

        result = await _check_providers(config, GoodGateway())
        assert len(result) == len(config.providers)
        for _name, status in result.items():
            assert status["healthy"] is True

    @pytest.mark.asyncio
    async def test_provider_timeout_marked_unhealthy(
        self, config: ChimeraConfig,  # type: ignore[no-untyped-def]
    ) -> None:
        """Providers that time out are marked unhealthy.

        Only check providers that have models (openrouter, zai) — the
        'anthropic' provider has no models and is always healthy.
        """
        class TimeoutGateway:
            async def complete(self, model: str, messages: list, **kw: Any):
                await asyncio.sleep(100)  # will be cut by wait_for(timeout=5)

        result = await _check_providers(config, TimeoutGateway())
        for name in ("openrouter", "zai"):
            assert result[name]["healthy"] is False
            assert "timeout" in result[name].get("error", "")

    @pytest.mark.asyncio
    async def test_provider_exception_marked_unhealthy(
        self, config: ChimeraConfig,  # type: ignore[no-untyped-def]
    ) -> None:
        """Providers that raise are marked unhealthy.

        Only check providers that have models (openrouter, zai) — the
        'anthropic' provider has no models and is always healthy.
        """
        class ErrorGateway:
            async def complete(self, model: str, messages: list, **kw: Any):
                raise RuntimeError("connection refused")

        result = await _check_providers(config, ErrorGateway())
        for name in ("openrouter", "zai"):
            assert result[name]["healthy"] is False
            assert "connection refused" in result[name].get("error", "")

    @pytest.mark.asyncio
    async def test_provider_with_no_models_reports_note(
        self, config: ChimeraConfig,  # type: ignore[no-untyped-def]
    ) -> None:
        """Provider with no models → healthy with note."""
        # Add a provider with no associated models
        from chimera.config import Provider
        config.providers["orphan"] = Provider(base_url="https://orphan.test")
        config = config.model_copy()

        class GoodGateway:
            async def complete(self, model: str, messages: list, **kw: Any):
                return _resp("ok", model)

        result = await _check_providers(config, GoodGateway())
        assert result["orphan"]["healthy"] is True
        assert "note" in result["orphan"]

    @pytest.mark.asyncio
    async def test_empty_config_returns_none_marker(self) -> None:
        """Config with no providers → _none entry."""
        cfg_dict = dict(CONFIG_DICT)
        cfg_dict["providers"] = {}
        cfg_dict["models"] = {
            "test/model": {
                "categories": {"code": 0.5}, "cost_tier": "standard",
                "provider": "test",
            },
        }
        cfg_dict["defaults"] = {
            "dispatcher": "test/model",
            "default_worker": "test/model",
            "default_aggregator": "test/model",
        }
        config = ChimeraConfig.model_validate(cfg_dict)

        class GoodGateway:
            async def complete(self, model: str, messages: list, **kw: Any):
                return _resp("ok", model)

        result = await _check_providers(config, GoodGateway())
        assert "_none" in result
        assert result["_none"]["healthy"] is True


# =========================================================================== #
# run() entrypoint — mocked uvicorn
# =========================================================================== #

class TestRunEntrypoint:
    """Cover run() by mocking uvicorn.run and load_config."""

    def test_run_calls_uvicorn(self, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
        # Write a config file so load_config finds it
        import yaml
        config_path = tmp_path / "chimera.yaml"
        config_path.write_text(yaml.safe_dump(CONFIG_DICT), encoding="utf-8")
        monkeypatch.chdir(tmp_path)

        uvicorn_called: dict[str, Any] = {}

        def fake_uvicorn_run(app: Any, host: str, port: int) -> None:
            uvicorn_called["app"] = app
            uvicorn_called["host"] = host
            uvicorn_called["port"] = port

        with patch("uvicorn.run", side_effect=fake_uvicorn_run):
            from chimera.api.server import run
            run()

        assert "app" in uvicorn_called
        assert uvicorn_called["host"] == "127.0.0.1"
        assert uvicorn_called["port"] == 8000

    def test_run_with_explicit_host_port(self, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
        import yaml
        config_path = tmp_path / "chimera.yaml"
        config_path.write_text(yaml.safe_dump(CONFIG_DICT), encoding="utf-8")
        monkeypatch.chdir(tmp_path)

        uvicorn_called: dict[str, Any] = {}

        def fake_uvicorn_run(app: Any, host: str, port: int) -> None:
            uvicorn_called["host"] = host
            uvicorn_called["port"] = port

        with patch("uvicorn.run", side_effect=fake_uvicorn_run):
            from chimera.api.server import run
            run(host="0.0.0.0", port=9999)

        assert uvicorn_called["host"] == "0.0.0.0"
        assert uvicorn_called["port"] == 9999


# =========================================================================== #
# Extra coverage — app lifespan, web-router import, rate-limit, timeout,
# chat-completion errors, _check_providers outer except
# =========================================================================== #


class TestLifespanAndWebRouter:
    def test_lifespan_runs(self, config: ChimeraConfig) -> None:
        """TestClient triggers the lifespan, exercising the yield on line 111."""
        # If lifespan crashed or wasn't invoked, TestClient startup would raise.
        client = _client(config)
        r = client.get("/v1/health/live")
        assert r.status_code == 200

    def test_lifespan_context_invoked_directly(self, config: ChimeraConfig) -> None:
        """Invoke the lifespan via TestClient to ensure the bare ``yield``
        statement on line 111 is marked as hit by coverage.py.
        """
        engine = Engine(config, FakeGateway(lambda *a, **kw: _resp("ok", "x")))
        app = create_app(config=config, engine=engine)
        from fastapi.testclient import TestClient

        with TestClient(app):
            # Lifespan entered (yield reached) and exited cleanly.
            r = TestClient(app).get("/v1/health/live")
            assert r.status_code == 200

    def test_web_router_import_error_is_skipped(
        self, config: ChimeraConfig, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """If ``chimera.web.router`` import fails, create_app still builds."""
        # Remove any cached import of chimera.web and patch to make it raise.
        import sys
        monkeypatch.setitem(sys.modules, "chimera.web", None)  # forces ImportError
        engine = Engine(config, FakeGateway(lambda *a, **kw: _resp("ok", "x")))
        app = create_app(config=config, engine=engine)
        assert app.title == "Chimera"


class TestRateLimitedHTTPException:
    def test_deliberate_rate_limited_returns_429(
        self, config: ChimeraConfig,
    ) -> None:
        """When the rate limiter denies, /v1/deliberate returns HTTP 429."""
        client = _client(config)

        def always_deny(key: str):  # noqa: ARG001
            return (False, 30.0)

        client.app.state.rate_limiter.allow = always_deny  # type: ignore[attr-defined]

        r = client.post("/v1/deliberate", json={"prompt": "hi"})
        assert r.status_code == 429
        assert "Retry-After" in r.headers
        assert r.json()["detail"]["error"] == "rate_limited"

    def test_chat_completions_rate_limited_returns_429(
        self, config: ChimeraConfig,
    ) -> None:
        """Rate limiter denial on /v1/chat/completions → HTTP 429."""
        client = _client(config)

        def always_deny(key: str):  # noqa: ARG001
            return (False, 5.0)

        client.app.state.rate_limiter.allow = always_deny  # type: ignore[attr-defined]

        r = client.post(
            "/v1/chat/completions",
            json={"model": "auto", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert r.status_code == 429
        assert "Retry-After" in r.headers


class TestHealthDegradedFallbackPath:
    def test_health_unhealthy_exhausts_all_branches(
        self, config: ChimeraConfig,
    ) -> None:
        """A config with one model whose provider always fails → covers the
        fall-through ``return {"status": "degraded", ...}`` (line 259) and
        the outer except handler (lines 260-266) when the inner try raises.
        """
        cfg_dict = dict(CONFIG_DICT)
        cfg_dict["providers"] = {"broken": {"base_url": "https://broken.test"}}
        cfg_dict["models"] = {
            "broken/x": {
                "categories": {"code": 0.5}, "cost_tier": "standard",
                "provider": "broken",
            },
        }
        cfg_dict["defaults"] = {
            "dispatcher": "broken/x",
            "default_worker": "broken/x",
            "default_aggregator": "broken/x",
        }
        new_cfg = ChimeraConfig.model_validate(cfg_dict)

        class BrokenGateway:
            async def complete(self, model: str, messages: list, **kw: Any):
                raise RuntimeError("connection refused")

        engine = Engine(new_cfg, BrokenGateway())
        client = _client_with_engine(new_cfg, engine)
        r = client.get("/v1/health")
        assert r.status_code == 200
        assert r.json()["status"] == "degraded"

    def test_health_outer_except_when_gateway_attribute_missing(
        self, config: ChimeraConfig,
    ) -> None:
        """When ``request.app.state.engine.gateway`` itself raises on attribute
        access (e.g. a custom engine stub), the outer except (lines 260-266)
        catches it and returns degraded."""
        cfg_dict = dict(CONFIG_DICT)
        cfg_dict["providers"] = {"broken": {"base_url": "https://broken.test"}}
        cfg_dict["models"] = {
            "broken/x": {
                "categories": {"code": 0.5}, "cost_tier": "standard",
                "provider": "broken",
            },
        }
        cfg_dict["defaults"] = {
            "dispatcher": "broken/x",
            "default_worker": "broken/x",
            "default_aggregator": "broken/x",
        }
        new_cfg = ChimeraConfig.model_validate(cfg_dict)

        class ExplodingEngine:
            @property
            def gateway(self):
                raise RuntimeError("boom — gateway property exploded")

        engine = ExplodingEngine()
        client = _client_with_engine(new_cfg, engine)  # type: ignore[arg-type]
        r = client.get("/v1/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "degraded"
        assert "error" in data["details"]


class TestReadinessExceptionPath:
    def test_readiness_503_when_check_providers_raises(
        self, config: ChimeraConfig,
    ) -> None:
        """A non-HTTPException from _check_providers → 503 via lines 287-288."""
        cfg_dict = dict(CONFIG_DICT)
        cfg_dict["providers"] = {"x": {"base_url": "https://x"}}
        cfg_dict["models"] = {
            "x/y": {
                "categories": {"code": 0.5}, "cost_tier": "standard",
                "provider": "x",
            },
        }
        cfg_dict["defaults"] = {
            "dispatcher": "x/y",
            "default_worker": "x/y",
            "default_aggregator": "x/y",
        }
        new_cfg = ChimeraConfig.model_validate(cfg_dict)

        # Patch _check_providers to raise a non-HTTPException.
        from chimera.api import server as server_mod

        async def boom(config, gateway):  # noqa: ARG001
            raise RuntimeError("catastrophic")

        with patch.object(server_mod, "_check_providers", side_effect=boom):
            engine = Engine(new_cfg, FakeGateway(lambda *a, **kw: _resp("ok", "x")))
            client = _client_with_engine(new_cfg, engine)
            r = client.get("/v1/health/ready")
        assert r.status_code == 503
        assert "Not ready" in r.json()["detail"]


class TestDeliberateTimeoutHeader:
    def test_invalid_timeout_header_value_is_skipped(
        self, config: ChimeraConfig,
    ) -> None:
        """Unparseable timeout values in X-Chimera-Timeout are skipped (lines 374-377)."""
        client = _client(config)
        # "total=notanumber" → float() raises ValueError → continue
        r = client.post(
            "/v1/deliberate",
            json={"prompt": "hi"},
            headers={"X-Chimera-Timeout": "total=notanumber"},
        )
        assert r.status_code == 200

    def test_timeout_exceeds_ceiling_returns_400(
        self, config: ChimeraConfig,
    ) -> None:
        """total=10000 > admin ceiling (default 300) → 400."""
        client = _client(config)
        r = client.post(
            "/v1/deliberate",
            json={"prompt": "hi"},
            headers={"X-Chimera-Timeout": "total=10000, per_stage=99999"},
        )
        assert r.status_code == 400
        assert "exceeds admin ceiling" in r.json()["detail"]

    def test_per_stage_ceiling_exceeded(
        self, config: ChimeraConfig,
    ) -> None:
        """per_stage value exceeding admin ceiling → 400."""
        client = _client(config)
        r = client.post(
            "/v1/deliberate",
            json={"prompt": "hi"},
            headers={"X-Chimera-Timeout": "per_stage=9999"},
        )
        assert r.status_code == 400
        assert "per_stage" in r.json()["detail"]

    def test_timeout_zero_disables_overrides(
        self, config: ChimeraConfig,
    ) -> None:
        """total=0 sets timeout_total_s to None (disables override)."""
        client = _client(config)
        r = client.post(
            "/v1/deliberate",
            json={"prompt": "hi"},
            headers={"X-Chimera-Timeout": "total=0,per_stage=0"},
        )
        assert r.status_code == 200

    def test_timeout_header_garbage_part_skipped(
        self, config: ChimeraConfig,
    ) -> None:
        """Header parts without '=' are ignored — line 370-372."""
        client = _client(config)
        r = client.post(
            "/v1/deliberate",
            json={"prompt": "hi"},
            headers={"X-Chimera-Timeout": "garbage, total=120"},
        )
        assert r.status_code == 200


class TestChatCompletionUnknownModel:
    def test_chat_completion_keyerror_returns_400(
        self, config: ChimeraConfig,
    ) -> None:
        """engine.deliberate raising KeyError → HTTP 400 from /v1/chat/completions."""
        engine = Engine(config, FakeGateway(lambda *a, **kw: _resp("ok", "x")))

        async def raising_deliberate(*a: Any, **kw: Any):
            raise KeyError("unknown-model")

        engine.deliberate = raising_deliberate  # type: ignore[assignment]
        client = _client_with_engine(config, engine)
        r = client.post(
            "/v1/chat/completions",
            json={"model": "unknown-model",
                  "messages": [{"role": "user", "content": "hi"}]},
        )
        assert r.status_code == 400
        assert "Unknown model" in r.json()["detail"]


class TestCheckProvidersOuterExcept:
    @pytest.mark.asyncio
    async def test_outer_loop_exception_caught(self, config: ChimeraConfig) -> None:  # type: ignore[no-untyped-def]
        """Outer except at line 529 catches exceptions from the loop body.

        Inject a bad entry whose ``provider`` attribute is not a string —
        iteration via ``next((name for name, entry in ...) if entry.provider == provider_name)``
        raises AttributeError when ``entry.provider`` is missing.
        """
        from chimera.config import Provider
        cfg_dict = dict(CONFIG_DICT)
        # Add a provider with no matching model entry → loop hits next() which
        # iterates all entries; we mutate one model's provider attribute to be
        # an object that raises AttributeError on comparison.
        bad_cfg = ChimeraConfig.model_validate(cfg_dict)
        bad_cfg.providers["quirky"] = Provider(base_url="https://quirky.test")

        class RaisingProvider:
            def __eq__(self, other):
                raise AttributeError("provider comparison boom")

            def __hash__(self):
                raise TypeError("unhashable")

        # Mutate one existing model so ``entry.provider == provider_name``
        # raises AttributeError (caught at outer except).
        for entry in bad_cfg.models.values():
            object.__setattr__(entry, "provider", RaisingProvider())

        class GoodGateway:
            async def complete(self, model: str, messages: list, **kw: Any):
                return _resp("ok", model)

        result = await _check_providers(bad_cfg, GoodGateway())
        # The quirky provider has no matching model → loop hits ``next(...)``
        # which iterates all models; comparing raises AttributeError.
        assert "quirky" in result
        # Outer except catches AttributeError → entry marked unhealthy.
        assert result["quirky"]["healthy"] is False
        assert "boom" in result["quirky"].get("error", "")
