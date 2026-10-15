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


def test_same_key_different_body_rejected_409(config, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """DF-CHIMERA-V2-83: reusing a key with a NEW body must never replay."""
    client, calls = _client_with_engine_counter(config, monkeypatch)

    r1 = client.post("/v1/deliberate", json={"prompt": "hello", "idempotency_key": "key-1"})
    r2 = client.post(
        "/v1/deliberate",
        json={"prompt": "a DIFFERENT prompt", "idempotency_key": "key-1"},
    )

    assert r1.status_code == 200
    assert r2.status_code == 409
    assert r2.headers["X-Idempotent-Body-Match"] == "false"
    assert r2.json()["detail"] != r1.json()["answer"]
    assert calls["n"] == 1  # mismatch is rejected, not re-executed


def test_same_key_same_body_still_replays(config, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """DF-CHIMERA-V2-83: the unchanged replay contract is intact."""
    client, calls = _client_with_engine_counter(config, monkeypatch)
    payload = {"prompt": "hello", "formation": "auto", "idempotency_key": "key-1"}

    r1 = client.post("/v1/deliberate", json=payload)
    r2 = client.post("/v1/deliberate", json=payload)

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r2.headers[REPLAY_HEADER] == "true"
    assert "X-Idempotent-Body-Match" not in r2.headers
    assert r1.json() == r2.json()
    assert calls["n"] == 1


def test_mismatched_key_field_does_not_break_fingerprint(config, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Bodies identical except the idempotency key value are the SAME request."""
    client, calls = _client_with_engine_counter(config, monkeypatch)

    r1 = client.post("/v1/deliberate", json={"prompt": "hello", "idempotency_key": "key-a"})
    r2 = client.post("/v1/deliberate", json={"prompt": "hello", "idempotency_key": "key-b"})

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert calls["n"] == 2  # different keys = different cache entries, no conflict


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


# ---------------------------------------------------------------------------
# DF-CHIMERA-V2-84: idempotency_key honored on POST /v1/chat/completions —
# same replay contract as /v1/deliberate, with keys namespaced `chat:` so the
# two surfaces never cross-replay.
# ---------------------------------------------------------------------------


def _chat_payload(key):  # type: ignore[no-untyped-def]
    payload = {
        "model": "auto",
        "messages": [{"role": "user", "content": "hello"}],
    }
    if key is not None:
        payload["idempotency_key"] = key
    return payload


def test_chat_same_key_replays_and_engine_runs_once(config, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    client, calls = _client_with_engine_counter(config, monkeypatch)

    r1 = client.post("/v1/chat/completions", json=_chat_payload("ck-1"))
    r2 = client.post("/v1/chat/completions", json=_chat_payload("ck-1"))

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json() == r2.json()  # SAME envelope, incl. completion id
    assert REPLAY_HEADER not in r1.headers
    assert r2.headers[REPLAY_HEADER] == "true"
    assert calls["n"] == 1  # engine ran once — the replay was not re-billed


def test_chat_different_key_executes_fresh(config, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    client, calls = _client_with_engine_counter(config, monkeypatch)

    r1 = client.post("/v1/chat/completions", json=_chat_payload("ck-a"))
    r2 = client.post("/v1/chat/completions", json=_chat_payload("ck-b"))

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert REPLAY_HEADER not in r1.headers
    assert REPLAY_HEADER not in r2.headers
    assert r1.json()["id"] != r2.json()["id"]
    assert calls["n"] == 2


def test_chat_no_key_executes_every_time(config, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    client, calls = _client_with_engine_counter(config, monkeypatch)

    r1 = client.post("/v1/chat/completions", json=_chat_payload(None))
    r2 = client.post("/v1/chat/completions", json=_chat_payload(None))

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert REPLAY_HEADER not in r1.headers
    assert REPLAY_HEADER not in r2.headers
    assert r1.json()["id"] != r2.json()["id"]
    assert calls["n"] == 2


def test_chat_key_never_cross_replays_with_deliberate(config, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """The same literal key on the two surfaces must not cross-replay."""
    client, calls = _client_with_engine_counter(config, monkeypatch)

    d1 = client.post(
        "/v1/deliberate",
        json={"prompt": "hello", "formation": "auto", "idempotency_key": "shared"},
    )
    c1 = client.post("/v1/chat/completions", json=_chat_payload("shared"))
    c2 = client.post("/v1/chat/completions", json=_chat_payload("shared"))

    assert d1.status_code == 200 and c1.status_code == 200 and c2.status_code == 200
    # chat first call with that key EXECUTED (not a replay of the deliberate
    # response — different wire shape entirely) and the second chat call
    # replayed the chat envelope.
    assert REPLAY_HEADER not in c1.headers
    assert c2.headers[REPLAY_HEADER] == "true"
    assert c2.json()["object"] == "chat.completion"
    assert calls["n"] == 2
