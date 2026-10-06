"""TTL cache for /v1/health provider probes (REV-CHIMERA-V2-20261005-1).

AC1 first call probes all providers (age_s=0); AC2 second call within the
window is served from cache with age_s > 0 and NO new probe; AC3
``?refresh=1`` bypasses the cache and re-probes (age_s resets); AC4 an
expired entry re-probes. AC6 is this file; AC5 is the pre-existing suite.
"""

from __future__ import annotations

from typing import Any

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from chimera.api.server import _ProviderHealthCache  # noqa: E402
from chimera.config import ChimeraConfig  # noqa: E402
from chimera.engine import Engine  # noqa: E402
from chimera.gateway import GatewayResponse  # noqa: E402
from tests.conftest import FakeGateway  # noqa: E402

REV = "REV-CHIMERA-V2-20261005-1"


@pytest.fixture(autouse=True)
def _isolate_health_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """Zero the cache before AND after every test in this module.

    The cache is per-app-instance, but a module-level default would leak a
    computed timestamp across tests if the implementation ever moved it there
    — and the timestamps these tests assert on (age_s > 0) are exactly the
    kind that silently survive. Belt and braces, both directions.
    """
    # created fresh per app; nothing ambient to clear today — keep the seam
    # so a later module-level cache lands inside this isolation automatically.
    yield
    import chimera.api.server as server_mod

    # If a module-level singleton ever appears, this clears it between tests.
    singleton = getattr(server_mod, "_provider_health_cache_singleton", None)
    if singleton is not None:
        singleton.clear()


@pytest.fixture(autouse=True)
def _provider_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hermetic keys so the credentials gate in _check_providers passes."""
    for env_var in ("OPENROUTER_API_KEY", "ZAI_API_KEY", "DEEPSEEK_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.setenv(env_var, "test-key")


def _resp(text: str, model: str) -> GatewayResponse:
    return GatewayResponse(text=text, model=model, tokens_input=10, tokens_output=20)


class CountingGateway:
    """FakeGateway that counts probe completions — the AC2 oracle."""

    def __init__(self) -> None:
        self.complete_calls = 0

    def __call__(self, model: str, messages: list, response_format=None, **kw: Any):
        self.complete_calls += 1
        return _resp(f"worker {model}", model)


def _client_with_counter(config: ChimeraConfig) -> tuple[TestClient, CountingGateway]:
    gw = CountingGateway()
    engine = Engine(config, FakeGateway(gw))
    from chimera.api.server import create_app

    app = create_app(config=config, engine=engine)
    return TestClient(app), gw


# Cache-class unit behavior: the seam the route reads through.


class TestProviderHealthCache:
    def test_miss_then_hit_then_refresh(self) -> None:
        c = _ProviderHealthCache(ttl_s=60.0)
        assert c.get() == (None, None)  # empty miss
        c.store({"p": {"healthy": True}})
        results, age_s = c.get()
        assert results == {"p": {"healthy": True}}
        assert age_s is not None and 0 <= age_s < 1
        c.clear()
        assert c.get() == (None, None)

    def test_expiry_after_ttl(self) -> None:
        c = _ProviderHealthCache(ttl_s=0.05)
        c.store({"p": {"healthy": True}})
        import time as _time

        _time.sleep(0.08)
        assert c.get() == (None, None)  # expired → miss

    def test_store_copies_input_dict(self) -> None:
        """store() must not alias the caller's dict (later mutation safety)."""
        c = _ProviderHealthCache()
        src = {"p": {"healthy": True}}
        c.store(src)
        src["p"]["healthy"] = False
        assert c.get()[0]["p"]["healthy"] is True


# Endpoint behavior: the acceptance criteria, proven on the live route.


class TestHealthCacheEndpoints:
    def test_first_call_probes_and_age_zero(self, config: ChimeraConfig) -> None:
        """AC1: first call probes providers and reports age_s = 0."""
        client, gw = _client_with_counter(config)
        data = client.get("/v1/health").json()
        assert data["details"]["age_s"] == 0
        assert gw.complete_calls > 0  # probes actually ran
        assert data["status"] in {"healthy", "degraded"}

    def test_second_call_within_ttl_is_cached(self, config: ChimeraConfig) -> None:
        """AC2: second call within 60s serves the cache — no new probes."""
        client, gw = _client_with_counter(config)
        first = client.get("/v1/health").json()
        calls_after_first = gw.complete_calls
        assert calls_after_first > 0

        second = client.get("/v1/health").json()
        assert gw.complete_calls == calls_after_first  # NO new probes
        assert second["details"]["providers"] == first["details"]["providers"]
        assert second["details"]["age_s"] > 0  # cached age
        assert second["details"]["age_s"] < 60  # inside the TTL window

    def test_refresh_bypasses_cache(self, config: ChimeraConfig) -> None:
        """AC3: ?refresh=1 forces a fresh probe — age_s resets to 0."""
        client, gw = _client_with_counter(config)
        client.get("/v1/health")
        calls_after_first = gw.complete_calls

        refreshed = client.get("/v1/health?refresh=1").json()
        assert gw.complete_calls > calls_after_first  # probes ran again
        assert refreshed["details"]["age_s"] == 0  # fresh, not cached age

    def test_refresh_stores_new_result_for_later_hits(self, config: ChimeraConfig) -> None:
        """refresh=1 re-arms the cache: the NEXT plain call hits it again."""
        client, gw = _client_with_counter(config)
        client.get("/v1/health")
        n1 = gw.complete_calls
        client.get("/v1/health?refresh=1")
        n2 = gw.complete_calls
        assert n2 > n1

        third = client.get("/v1/health").json()  # plain call after refresh
        assert gw.complete_calls == n2  # served from the refreshed cache
        assert third["details"]["age_s"] > 0

    def test_expired_cache_reprobes(self, config: ChimeraConfig) -> None:
        """AC4: after the TTL the next call probes again (age resets to 0)."""
        client, gw = _client_with_counter(config)

        # Rebuild with a near-zero TTL by pre-populating a short-TTL cache.
        app = client.app
        app.state.provider_health_cache = _ProviderHealthCache(ttl_s=0.05)

        client.get("/v1/health")
        n1 = gw.complete_calls
        import time as _time

        _time.sleep(0.08)  # > ttl → entry expires
        data = client.get("/v1/health").json()
        assert gw.complete_calls > n1  # re-probed
        assert data["details"]["age_s"] == 0

    def test_liveness_accepts_refresh_noop(self, config: ChimeraConfig) -> None:
        """/v1/health/live?refresh=1 stays 200 alive (no probe, no cache)."""
        client, gw = _client_with_counter(config)
        r = client.get("/v1/health/live?refresh=1")
        assert r.status_code == 200
        assert r.json()["status"] == "alive"
        assert gw.complete_calls == 0  # liveness never probes
