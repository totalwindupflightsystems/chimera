"""Idempotency-key support on POST /v1/deliberate (CHIMERA-V2-REVIEW-05).

A client retry after a timeout must not re-run (and re-bill) a full
deliberation. With an ``idempotency_key`` the endpoint caches the
successful response and replays it (HTTP 200 + ``X-Idempotent-Replay:
true``); without a key the behavior is byte-identical to before.
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from chimera.api.server import _IdempotencyCache, create_app  # noqa: E402
from chimera.engine import Engine  # noqa: E402
from chimera.gateway import GatewayResponse  # noqa: E402
from tests.conftest import FakeGateway, dispatch_json  # noqa: E402

REPLAY_HEADER = "X-Idempotent-Replay"


def _resp(text: str, model: str, ti: int, to: int) -> GatewayResponse:
    return GatewayResponse(text=text, model=model, tokens_input=ti, tokens_output=to)


def _responder(model, messages, response_format=None, **kw):  # type: ignore[no-untyped-def]
    if response_format is not None:
        return _resp(dispatch_json(), model, 100, 200)
    joined = json.dumps(messages)
    if "Upstream outputs" in joined:
        return _resp("FINAL ANSWER", model, 60, 90)
    return _resp(f"worker {model}", model, 20, 40)


def _client_with_engine_counter(config, monkeypatch):  # type: ignore[no-untyped-def]
    """TestClient whose engine.deliberate call count is recorded."""
    gateway = FakeGateway(_responder)
    engine = Engine(config, gateway)
    calls = {"n": 0}
    original = engine.deliberate

    async def counted(*args, **kwargs):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        return await original(*args, **kwargs)

    monkeypatch.setattr(engine, "deliberate", counted)
    app = create_app(config=config, engine=engine)
    return TestClient(app), calls


def test_same_key_replays_and_engine_runs_once(config, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    client, calls = _client_with_engine_counter(config, monkeypatch)
    payload = {"prompt": "hello", "formation": "auto", "idempotency_key": "key-1"}

    r1 = client.post("/v1/deliberate", json=payload)
    r2 = client.post("/v1/deliberate", json=payload)

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json() == r2.json()  # SAME DeliberateResponse, incl. request_id
    assert REPLAY_HEADER not in r1.headers
    assert r2.headers[REPLAY_HEADER] == "true"
    assert calls["n"] == 1  # engine ran once — the replay was not re-billed


def test_different_key_executes_fresh(config, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    client, calls = _client_with_engine_counter(config, monkeypatch)

    r1 = client.post("/v1/deliberate", json={"prompt": "hello", "idempotency_key": "key-a"})
    r2 = client.post("/v1/deliberate", json={"prompt": "hello", "idempotency_key": "key-b"})

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert REPLAY_HEADER not in r1.headers
    assert REPLAY_HEADER not in r2.headers
    assert r1.json()["request_id"] != r2.json()["request_id"]
    assert calls["n"] == 2


def test_no_key_executes_every_time(config, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    client, calls = _client_with_engine_counter(config, monkeypatch)

    r1 = client.post("/v1/deliberate", json={"prompt": "hello", "formation": "auto"})
    r2 = client.post("/v1/deliberate", json={"prompt": "hello", "formation": "auto"})

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert REPLAY_HEADER not in r1.headers
    assert REPLAY_HEADER not in r2.headers
    assert r1.json()["request_id"] != r2.json()["request_id"]
    assert calls["n"] == 2


def test_cache_default_capacity_is_512() -> None:
    cache = _IdempotencyCache()
    assert cache._capacity == 512


def test_lru_eviction_beyond_capacity() -> None:
    cache = _IdempotencyCache(capacity=3)

    def entry(i: int):  # type: ignore[no-untyped-def]
        from chimera.api.server import DeliberateResponse

        return DeliberateResponse(answer=f"a{i}", trace={}, request_id=f"r{i}")

    for i in range(4):
        cache.put(f"k{i}", entry(i))

    assert cache.get("k0") is None  # oldest evicted once capacity exceeded
    assert cache.get("k1") is not None
    assert cache.get("k2") is not None
    assert cache.get("k3") is not None

    # A get() refreshes recency: k1 survives the next insert, k2 evicts.
    cache.get("k1")
    cache.put("k4", entry(4))
    assert cache.get("k1") is not None
    assert cache.get("k2") is None
    assert cache.get("k3") is not None
    assert cache.get("k4") is not None
