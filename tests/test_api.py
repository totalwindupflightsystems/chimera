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


# --------------------------------------------------------------------------- #
# Client-defined DAG + stage_models over the HTTP API (Features 1 & 2)
# --------------------------------------------------------------------------- #


def _client_dag_dict() -> dict[str, object]:
    return {
        "stages": [
            {"id": "researcher", "kind": "worker", "model": "deepseek/deepseek-chat"},
            {"id": "finalizer", "kind": "aggregator",
             "model": "zai-coding-plan/glm-5.2", "depends_on": ["researcher"]},
        ],
        "edges": [["researcher", "finalizer"]],
    }


def test_client_dag_rejected_without_opt_in(config) -> None:  # type: ignore[no-untyped-def]
    """dag supplied without allow_custom_dag → HTTP 400."""
    client = _client(config)
    r = client.post(
        "/v1/deliberate",
        json={"prompt": "hi", "dag": _client_dag_dict(), "allow_custom_dag": False},
    )
    assert r.status_code == 400
    assert "allow_custom_dag" in r.json()["detail"]


def test_client_dag_accepted_with_opt_in(config) -> None:  # type: ignore[no-untyped-def]
    """dag + allow_custom_dag=true → 200, trace source is 'custom'."""
    client = _client(config)
    r = client.post(
        "/v1/deliberate",
        json={"prompt": "hi", "dag": _client_dag_dict(), "allow_custom_dag": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["trace"]["source"] == "custom"
    stage_ids = {s["stage_id"] for s in data["trace"]["stages"]}
    assert stage_ids == {"researcher", "finalizer"}


def test_client_dag_invalid_model_returns_400(config) -> None:  # type: ignore[no-untyped-def]
    """Invalid model in a client DAG surfaces as HTTP 400."""
    client = _client(config)
    bad_dag = {
        "stages": [
            {"id": "w", "kind": "worker", "model": "no/such/model"},
            {"id": "a", "kind": "aggregator", "model": "zai-coding-plan/glm-5.2",
             "depends_on": ["w"]},
        ],
        "edges": [["w", "a"]],
    }
    r = client.post(
        "/v1/deliberate",
        json={"prompt": "hi", "dag": bad_dag, "allow_custom_dag": True},
    )
    assert r.status_code == 400


def test_stage_models_via_api(config) -> None:  # type: ignore[no-untyped-def]
    """stage_models passes through the API and forces a stage's model."""
    client = _client(config)
    r = client.post(
        "/v1/deliberate",
        json={"prompt": "hi", "stage_models": {"worker_1": "zai-coding-plan/glm-5.2"}},
    )
    assert r.status_code == 200, r.text
    workers = {s["stage_id"]: s["model"] for s in r.json()["trace"]["stages"]
               if s["kind"] == "worker"}
    assert workers["worker_1"] == "zai-coding-plan/glm-5.2"


def test_chat_completions_accepts_custom_dag(config) -> None:  # type: ignore[no-untyped-def]
    """The OpenAI-compatible endpoint also honors allow_custom_dag."""
    client = _client(config)
    r = client.post(
        "/v1/chat/completions",
        json={
            "model": "auto",
            "messages": [{"role": "user", "content": "hi"}],
            "dag": _client_dag_dict(),
            "allow_custom_dag": True,
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["choices"][0]["message"]["content"] == "FINAL ANSWER"
