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

    def test_deliberate_value_error_returns_400(
        self, config: ChimeraConfig,  # type: ignore[no-untyped-def]
    ) -> None:
        """engine.deliberate raising ValueError → HTTP 400."""
        def exploding(model: str, messages: list, **kw: Any):
            raise RuntimeError("not used")

        engine = Engine(config, FakeGateway(exploding))

        # Patch engine.deliberate to raise ValueError
        async def raising_deliberate(*a: Any, **kw: Any) -> Any:
            raise ValueError("bad formation")

        engine.deliberate = raising_deliberate  # type: ignore[assignment]
        app = create_app(config=config, engine=engine)
        client = TestClient(app)

        r = client.post("/v1/deliberate", json={"prompt": "hi", "formation": "bad"})
        assert r.status_code == 400
        assert "bad formation" in r.json()["detail"]


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
