"""Tests for the FastAPI REST API (OpenAI-compatible endpoints)."""

from __future__ import annotations

import json

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from chimera.api.server import create_app  # noqa: E402
from chimera.engine import Engine  # noqa: E402
from tests.conftest import FakeGateway, dispatch_json  # noqa: E402


def _client(config):  # type: ignore[no-untyped-def]
    def responder(model, messages, response_format=None, **kw):
        if response_format is not None:
            return _resp(dispatch_json(), model, 100, 200)
        joined = json.dumps(messages)
        if "Upstream outputs" in joined:
            return _resp("FINAL ANSWER", model, 60, 90)
        return _resp(f"worker {model}", model, 20, 40)

    engine = Engine(config, FakeGateway(responder))
    app = create_app(config=config, engine=engine)
    return TestClient(app)


def _resp(text, model, ti, to):  # type: ignore[no-untyped-def]
    from chimera.gateway import GatewayResponse
    return GatewayResponse(text=text, model=model, tokens_input=ti, tokens_output=to)


def test_health(config) -> None:  # type: ignore[no-untyped-def]
    client = _client(config)
    r = client.get("/v1/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_list_formations(config) -> None:  # type: ignore[no-untyped-def]
    client = _client(config)
    r = client.get("/v1/formations")
    assert r.status_code == 200
    data = r.json()
    assert set(data) == {"auto", "simple", "debate", "audit"}
    assert data["simple"]["workers"] == 2


def test_list_models(config) -> None:  # type: ignore[no-untyped-def]
    client = _client(config)
    r = client.get("/v1/models")
    assert r.status_code == 200
    data = r.json()
    assert "deepseek/deepseek-chat" in data
    assert data["deepseek/deepseek-chat"]["cost_tier"] == "budget"


def test_deliberate(config) -> None:  # type: ignore[no-untyped-def]
    client = _client(config)
    r = client.post("/v1/deliberate", json={"prompt": "hello", "formation": "auto"})
    assert r.status_code == 200
    data = r.json()
    assert data["answer"] == "FINAL ANSWER"
    assert "trace" in data
    assert data["trace"]["formation"] == "auto"
    assert len(data["request_id"]) > 0


def test_chat_completions_openai_shape(config) -> None:  # type: ignore[no-untyped-def]
    client = _client(config)
    r = client.post(
        "/v1/chat/completions",
        json={
            "model": "auto",
            "messages": [{"role": "user", "content": "what is 2+2?"}],
        },
    )
    assert r.status_code == 200
    data = r.json()
    # OpenAI-compatible response fields
    assert data["object"] == "chat.completion"
    assert data["id"].startswith("chatcmpl-")
    assert data["choices"][0]["message"]["content"] == "FINAL ANSWER"
    assert data["choices"][0]["finish_reason"] == "stop"
    assert data["usage"]["total_tokens"] > 0
    assert data["model"] == "auto"


def test_chat_completions_strips_system_messages(config) -> None:  # type: ignore[no-untyped-def]
    client = _client(config)
    captured: list[str] = []

    def grab(model, messages, response_format=None, **kw):
        if response_format is not None:
            captured.append(json.dumps(messages))
            return _resp(dispatch_json(), model, 10, 10)
        return _resp("FINAL ANSWER", model, 10, 10)

    engine = Engine(config, FakeGateway(grab))
    app = create_app(config=config, engine=engine)
    client = TestClient(app)
    client.post(
        "/v1/chat/completions",
        json={
            "model": "auto",
            "messages": [
                {"role": "system", "content": "be helpful"},
                {"role": "user", "content": "the real prompt"},
            ],
        },
    )
    assert "the real prompt" in captured[0]
    assert "be helpful" not in captured[0]
