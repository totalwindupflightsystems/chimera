"""Tests for the FastAPI REST API (OpenAI-compatible endpoints)."""

from __future__ import annotations

import json

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from chimera.api.server import aggregate_usage, create_app  # noqa: E402
from chimera.engine import DeliberationTrace, Engine, StageSpan  # noqa: E402
from tests.conftest import FakeGateway, dispatch_json  # noqa: E402


def _client(config):  # type: ignore[no-untyped-def]
    def responder(model, messages, response_format=None, **kw):
        if response_format is not None:
            return _resp(dispatch_json(), model, 100, 200)
        joined = json.dumps(messages)
        if "Upstream outputs" in joined:
            return _resp("FINAL ANSWER", model, 60, 90)
        return _resp(f"worker {model}", model, 20, 40)

    client, _gateway = _client_with_gateway(config, responder)
    return client


def _client_with_gateway(config, responder):  # type: ignore[no-untyped-def]
    """TestClient + FakeGateway pair so tests can assert on recorded calls."""
    gateway = FakeGateway(responder)
    engine = Engine(config, gateway)
    app = create_app(config=config, engine=engine)
    return TestClient(app), gateway


def _resp(text, model, ti, to):  # type: ignore[no-untyped-def]
    from chimera.gateway import GatewayResponse
    return GatewayResponse(text=text, model=model, tokens_input=ti, tokens_output=to)


def test_health(config) -> None:  # type: ignore[no-untyped-def]
    client = _client(config)
    r = client.get("/v1/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] in {"healthy", "degraded", "unhealthy"}
    assert "details" in data
    assert data["details"]["config_loaded"] is True


def test_list_formations(config) -> None:  # type: ignore[no-untyped-def]
    client = _client(config)
    r = client.get("/v1/formations")
    assert r.status_code == 200
    data = r.json()
    assert set(data) == {"auto", "simple", "debate", "audit", "speed"}
    assert data["simple"]["workers"] == 2


def test_list_models(config) -> None:  # type: ignore[no-untyped-def]
    client = _client(config)
    r = client.get("/v1/models")
    assert r.status_code == 200
    body = r.json()
    # INT-API-004: an OpenAI ListModelsResponse envelope. The pre-envelope
    # keyed map is still served, additively, under `catalog`.
    assert body["object"] == "list"
    assert "deepseek/deepseek-chat" in body["catalog"]
    assert body["catalog"]["deepseek/deepseek-chat"]["cost_tier"] == "budget"
    assert "deepseek/deepseek-chat" in {e["id"] for e in body["data"]}


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


def test_aggregate_usage_sums_dispatch_and_every_stage() -> None:
    """``aggregate_usage`` totals the dispatch span plus every stage span.

    DF-CHIMERA-V2-10: the OpenAI-compatible ``usage`` block is the
    deliberation-wide aggregate, so the dispatch span and each worker /
    aggregator span each contribute their own inputs and outputs.
    """
    trace = DeliberationTrace(
        request_id="req-usage",
        formation="simple",
        source="preset",
        dispatch=StageSpan(
            stage_id="dispatch",
            kind="dispatch",
            model="zai-coding-plan/glm-5.2",
            prompt="design the deliberation",
            response="{}",
            tokens_input=100,
            tokens_output=10,
        ),
        stages=[
            StageSpan(
                stage_id="worker_1",
                kind="worker",
                model="deepseek/deepseek-chat",
                prompt="worker one",
                response="a",
                tokens_input=7,
                tokens_output=3,
            ),
            StageSpan(
                stage_id="aggregator",
                kind="aggregator",
                model="zai-coding-plan/glm-5.2",
                prompt="merge",
                response="b",
                tokens_input=5,
                tokens_output=2,
            ),
        ],
        total_tokens=127,
    )

    prompt_tokens, completion_tokens, total_tokens = aggregate_usage(trace)

    assert (prompt_tokens, completion_tokens, total_tokens) == (112, 15, 127)
    assert prompt_tokens + completion_tokens == total_tokens
    # The engine computes total_tokens over the identical span set.
    assert total_tokens == trace.total_tokens


def test_chat_completions_usage_is_deliberation_wide(config) -> None:  # type: ignore[no-untyped-def]
    """Regression: ``usage`` aggregates every span, not one stage (DF-CHIMERA-V2-10).

    Pre-fix the route reported ``prompt_tokens`` = the DISPATCHER stage's input
    alone and buried every other stage's INPUT tokens inside
    ``completion_tokens`` (``total_tokens - dispatch input``), so a client doing
    usage accounting got a wrong input/output split.
    """
    worker_calls = {"n": 0}

    def responder(model, messages, response_format=None, **kw):  # type: ignore[no-untyped-def]
        if response_format is not None:
            # Dispatcher design call — the large catalog-carrying input.
            return _resp(dispatch_json(), model, 100, 10)
        joined = json.dumps(messages)
        if "Upstream outputs" in joined:
            # Aggregator merges the worker outputs.
            return _resp("FINAL ANSWER", model, 50, 80)
        worker_calls["n"] += 1
        if worker_calls["n"] == 1:
            return _resp("worker one", model, 7, 3)
        return _resp("worker two", model, 5, 2)

    client, _gateway = _client_with_gateway(config, responder)
    r = client.post(
        "/v1/chat/completions",
        json={"model": "simple", "messages": [{"role": "user", "content": "hello"}]},
    )
    assert r.status_code == 200
    usage = r.json()["usage"]

    # dispatch 100/10 + worker_1 7/3 + worker_2 5/2 + aggregator 50/80
    assert usage["prompt_tokens"] == 162
    assert usage["completion_tokens"] == 95
    assert usage["total_tokens"] == 257
    assert usage["prompt_tokens"] + usage["completion_tokens"] == usage["total_tokens"]
    # The pre-fix split (dispatch input only, everything else folded into
    # completion) must not come back.
    assert (usage["prompt_tokens"], usage["completion_tokens"]) != (100, 257 - 100)


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


# --------------------------------------------------------------------------- #
# VALIDATION-001: Input validation for DeliberateRequest + ChatCompletionRequest
# --------------------------------------------------------------------------- #


def test_deliberate_empty_prompt_returns_422(config) -> None:  # type: ignore[no-untyped-def]
    """Empty prompt on /v1/deliberate → 422."""
    client = _client(config)
    r = client.post("/v1/deliberate", json={"prompt": "", "formation": "auto"})
    assert r.status_code == 422
    assert "prompt" in r.text


def test_deliberate_empty_formation_returns_422(config) -> None:  # type: ignore[no-untyped-def]
    """Empty formation on /v1/deliberate → 422."""
    client = _client(config)
    r = client.post("/v1/deliberate", json={"prompt": "hi", "formation": ""})
    assert r.status_code == 422
    assert "formation" in r.text


def test_deliberate_unknown_formation_returns_422(config) -> None:  # type: ignore[no-untyped-def]
    """Formation not in cfg.formations → 422."""
    client = _client(config)
    r = client.post("/v1/deliberate", json={"prompt": "hi", "formation": "no-such"})
    assert r.status_code == 422
    assert "Unknown formation" in r.json()["detail"]


def test_deliberate_valid_formation_returns_200(config) -> None:  # type: ignore[no-untyped-def]
    """A configured formation on /v1/deliberate → 200."""
    client = _client(config)
    r = client.post("/v1/deliberate", json={"prompt": "hi", "formation": "simple"})
    assert r.status_code == 200, r.text
    assert r.json()["answer"] == "FINAL ANSWER"


def test_chat_completions_empty_messages_returns_422(config) -> None:  # type: ignore[no-untyped-def]
    """Empty messages list on /v1/chat/completions → 422."""
    client = _client(config)
    r = client.post(
        "/v1/chat/completions",
        json={"model": "auto", "messages": []},
    )
    assert r.status_code == 422
    assert "messages" in r.text


def test_chat_completions_empty_model_returns_422(config) -> None:  # type: ignore[no-untyped-def]
    """Empty model string on /v1/chat/completions → 422."""
    client = _client(config)
    r = client.post(
        "/v1/chat/completions",
        json={"model": "", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.status_code == 422
    assert "model" in r.text


def test_chat_completions_valid_request_returns_200(config) -> None:  # type: ignore[no-untyped-def]
    """A valid /v1/chat/completions request → 200."""
    client = _client(config)
    r = client.post(
        "/v1/chat/completions",
        json={
            "model": "auto",
            "messages": [{"role": "user", "content": "what is 2+2?"}],
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["choices"][0]["message"]["content"] == "FINAL ANSWER"


# --------------------------------------------------------------------------- #
# Dogfood P0 (error-200-as-success): no usable answer → HTTP 502
# --------------------------------------------------------------------------- #
#
# When a deliberation produces no usable answer (the answer stage degraded),
# /v1/deliberate and /v1/chat/completions must return HTTP 502 with an
# OpenAI-compatible structured error body instead of 200 with a placeholder
# string.  Partial degradation (real merged answer exists) must stay 200.

from chimera.gateway import GatewayError  # noqa: E402


def _all_stages_fail(model, messages, response_format=None, **kw):  # type: ignore[no-untyped-def]
    """Dispatcher succeeds; every DAG stage (workers + aggregator) fails."""
    if response_format is not None:
        return _resp(dispatch_json(), model, 10, 10)
    raise GatewayError("upstream exploded")


def _partial_degradation(model, messages, response_format=None, **kw):  # type: ignore[no-untyped-def]
    """Workers fail but the aggregator succeeds with a real merged answer."""
    if response_format is not None:
        return _resp(dispatch_json(), model, 10, 10)
    joined = json.dumps(messages)
    if "Upstream outputs" in joined:
        return _resp("REAL MERGED ANSWER", model, 60, 90)
    raise GatewayError("worker down")


def _client_with(config, responder):  # type: ignore[no-untyped-def]
    engine = Engine(config, FakeGateway(responder))
    app = create_app(config=config, engine=engine)
    return TestClient(app)


def test_deliberate_no_answer_returns_502(config) -> None:  # type: ignore[no-untyped-def]
    """Fully degraded answer stage → 502 + structured error (type, request_id, message)."""
    client = _client_with(config, _all_stages_fail)
    r = client.post("/v1/deliberate", json={"prompt": "hello", "formation": "auto"})
    assert r.status_code == 502, r.text
    err = r.json()["error"]
    assert err["type"] == "upstream_error"
    assert "upstream exploded" in err["message"]
    assert len(err["request_id"]) > 0


def test_chat_completions_no_answer_returns_502(config) -> None:  # type: ignore[no-untyped-def]
    """Fully degraded answer stage → 502 + structured error (type, request_id, message)."""
    client = _client_with(config, _all_stages_fail)
    r = client.post(
        "/v1/chat/completions",
        json={"model": "auto", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.status_code == 502, r.text
    err = r.json()["error"]
    assert err["type"] == "upstream_error"
    assert "upstream exploded" in err["message"]
    assert len(err["request_id"]) > 0


def test_deliberate_partial_degradation_still_200(config) -> None:  # type: ignore[no-untyped-def]
    """Workers fail but a real merged answer exists → /v1/deliberate stays 200."""
    client = _client_with(config, _partial_degradation)
    r = client.post("/v1/deliberate", json={"prompt": "hello", "formation": "auto"})
    assert r.status_code == 200, r.text
    assert r.json()["answer"] == "REAL MERGED ANSWER"


def test_chat_completions_partial_degradation_still_200(config) -> None:  # type: ignore[no-untyped-def]
    """Workers fail but a real merged answer exists → /v1/chat/completions stays 200."""
    client = _client_with(config, _partial_degradation)
    r = client.post(
        "/v1/chat/completions",
        json={"model": "auto", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["choices"][0]["message"]["content"] == "REAL MERGED ANSWER"


def test_deliberate_trace_serializes_worker_failures(config) -> None:  # type: ignore[no-untyped-def]
    """C2: dropped workers appear in the API trace JSON (machine-readable)."""
    client = _client_with(config, _partial_degradation)
    r = client.post("/v1/deliberate", json={"prompt": "hello", "formation": "auto"})
    assert r.status_code == 200, r.text
    failures = r.json()["trace"]["worker_failures"]
    assert len(failures) == 2  # both workers dropped in _partial_degradation
    for failure in failures:
        assert failure["stage_id"] in {"worker_1", "worker_2"}
        assert failure["model"]
        assert "worker down" in failure["error"]


def test_deliberate_trace_worker_failures_empty_when_healthy(config) -> None:  # type: ignore[no-untyped-def]
    client = _client(config)
    r = client.post("/v1/deliberate", json={"prompt": "hello", "formation": "auto"})
    assert r.status_code == 200, r.text
    assert r.json()["trace"]["worker_failures"] == []


def test_chat_completions_unknown_model_returns_404(config) -> None:  # type: ignore[no-untyped-def]
    """OpenAI-compat contract: unknown model is a hard error (CH-GAP-027).

    Regression: model='bogus/nonexistent-model-xyz' used to silently
    substitute the auto formation, billing a real deliberation and returning
    HTTP 200 with a wrong-model answer.
    """
    client = _client(config)
    r = client.post(
        "/v1/chat/completions",
        json={
            "model": "bogus/nonexistent-model-xyz",
            "messages": [{"role": "user", "content": "hi"}],
        },
    )
    assert r.status_code == 404
    data = r.json()
    assert data["error"]["code"] == "model_not_found"
    assert data["error"]["param"] == "model"
    assert "choices" not in data


def test_chat_completions_custom_without_dag_returns_404(config) -> None:  # type: ignore[no-untyped-def]
    """model='custom' is only valid with a DAG — otherwise hard 404."""
    client = _client(config)
    r = client.post(
        "/v1/chat/completions",
        json={"model": "custom", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "model_not_found"


# --------------------------------------------------------------------------- #
# DF-CHIMERA-0911-3: `model` selects a FORMATION — the 404 must be actionable
# --------------------------------------------------------------------------- #
#
# Regression: a valid GET /v1/models key (e.g. "deepseek/deepseek-v4-flash")
# sent as the top-level `model` returned 404 model_not_found whose message
# named only formations/'custom' — it never said `model` is a formation
# selector, and never named the override fields that DO force a specific
# catalog model. An OpenAI-SDK caller had no in-band path from the error to
# the fix.

#: Override fields the 404 must name as the supported specific-model controls.
_MODEL_404_OVERRIDE_FIELDS = ("worker_model", "stage_models", "allowed_models")


def _assert_actionable_model_404(response, model_value: str) -> dict:  # type: ignore[no-untyped-def]
    """Assert the full formation-selector 404 contract + actionable guidance."""
    assert response.status_code == 404
    data = response.json()
    err = data["error"]
    assert err["code"] == "model_not_found"
    assert err["param"] == "model"
    assert err["type"] == "invalid_request_error"
    assert "choices" not in data  # never a 200 with a substituted model
    message = err["message"]
    assert f"`{model_value}`" in message
    assert "FORMATION" in message  # says what `model` actually selects
    for field in _MODEL_404_OVERRIDE_FIELDS:
        assert f"`{field}`" in message, message
    assert "extra_body" in message  # how OpenAI SDK callers pass the overrides
    assert "OPENAI_API.md" in message  # pointer to the documented contract
    return data


def test_chat_completions_catalog_model_id_returns_actionable_404(config) -> None:  # type: ignore[no-untyped-def]
    """A GET /v1/models key is NOT a valid top-level `model` (DF-CHIMERA-0911-3).

    The premise is asserted against the same client: the value IS a catalog
    entry, so the 404 (not a 200) is the real contract, and the message must
    hand the caller the override fields that force that model.
    """
    client, gateway = _client_with_gateway(config, _standard_responder)
    model_id = "deepseek/deepseek-v4-flash"
    assert model_id in client.get("/v1/models").json()["catalog"]  # premise: a catalog key

    r = client.post(
        "/v1/chat/completions",
        json={"model": model_id, "messages": [{"role": "user", "content": "hi"}]},
    )
    _assert_actionable_model_404(r, model_id)
    assert gateway.calls == []  # rejected before any engine work / billing


def test_chat_completions_unknown_formation_returns_actionable_404(config) -> None:  # type: ignore[no-untyped-def]
    """A completely unknown `model` keeps the same shape AND the same guidance."""
    client, gateway = _client_with_gateway(config, _standard_responder)
    common = {"messages": [{"role": "user", "content": "hi"}]}

    catalog_id = "deepseek/deepseek-v4-flash"
    catalog_case = client.post("/v1/chat/completions", json={"model": catalog_id, **common})
    unknown = "bogus/nonexistent-model-xyz"
    unknown_case = client.post("/v1/chat/completions", json={"model": unknown, **common})

    _assert_actionable_model_404(unknown_case, unknown)
    unknown_data = unknown_case.json()
    catalog_data = _assert_actionable_model_404(catalog_case, catalog_id)
    # One message template for both cases — only the quoted model name differs.
    assert unknown_data["error"]["message"].replace(unknown, "MODEL") == (
        catalog_data["error"]["message"].replace(catalog_id, "MODEL")
    )
    assert gateway.calls == []


@pytest.mark.parametrize("formation", ["auto", "simple", "debate", "audit", "speed"])
def test_chat_completions_valid_formations_unaffected(config, formation) -> None:  # type: ignore[no-untyped-def]
    """Every configured formation still deliberates normally (no 404 regression)."""
    client, gateway = _client_with_gateway(config, _standard_responder)
    r = client.post(
        "/v1/chat/completions",
        json={"model": formation, "messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["choices"][0]["message"]["content"] == "FINAL ANSWER"
    assert gateway.calls


@pytest.mark.parametrize(
    ("override_payload", "field"),  # type: ignore[no-untyped-def]
    [
        ({"worker_model": "bogus/nonexistent-model-xyz"}, "worker_model"),
        ({"aggregator_model": "bogus/nonexistent-model-xyz"}, "aggregator_model"),
        ({"stage_models": {"worker_1": "bogus/nonexistent-model-xyz"}}, "stage_models"),
    ],
)
def test_chat_completions_unknown_override_model_returns_400(  # type: ignore[no-untyped-def]
    config, override_payload, field,
) -> None:
    """Unknown model INSIDE an override field is a 400 — a different contract.

    Pins the split the docs now state: the top-level `model` is a formation
    selector (404 model_not_found, OpenAI-style body), while override model
    names are catalog-validated by the engine → HTTP 400 with FastAPI's
    ``detail`` body (never the OpenAI-style ``error`` object).
    """
    client = _client(config)
    r = client.post(
        "/v1/chat/completions",
        json={
            "model": "auto",
            "messages": [{"role": "user", "content": "hi"}],
            **override_payload,
        },
    )
    assert r.status_code == 400, r.text
    body = r.json()
    assert "error" not in body, body
    assert field in body["detail"], body
    assert "unknown model" in body["detail"], body


def test_chat_completions_unknown_stage_id_warns_but_succeeds(config) -> None:  # type: ignore[no-untyped-def]
    """An unknown stage_models STAGE id is non-fatal (documented warn) — 200.

    Distinguishes the two halves of `stage_models` for docs accuracy: unknown
    stage id → warn + normal deliberation; unknown model name → 400.
    """
    client = _client(config)
    r = client.post(
        "/v1/chat/completions",
        json={
            "model": "auto",
            "messages": [{"role": "user", "content": "hi"}],
            "stage_models": {"no_such_stage": "deepseek/deepseek-chat"},
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["choices"][0]["message"]["content"] == "FINAL ANSWER"


def test_chat_completions_stream_true_returns_400(config) -> None:  # type: ignore[no-untyped-def]
    """OpenAI-compat contract: stream:true is a hard 400 (CH-GAP-030).

    Regression: stream used to be silently dropped by pydantic, so an
    OpenAI-SDK client sending stream=True received a single JSON object
    where it expected text/event-stream chunks and failed client-side.
    Now it must get an explicit 400 naming the field — never a silent
    non-stream 200.
    """
    client = _client(config)
    r = client.post(
        "/v1/chat/completions",
        json={
            "model": "auto",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": True,
        },
    )
    assert r.status_code == 400
    data = r.json()
    assert data["error"]["code"] == "stream_not_supported"
    assert data["error"]["param"] == "stream"
    assert "choices" not in data


def test_chat_completions_stream_false_still_200(config) -> None:  # type: ignore[no-untyped-def]
    """stream:false and omitted stream keep the synchronous 200 contract."""
    client = _client(config)
    for payload in (
        {"model": "auto", "messages": [{"role": "user", "content": "hi"}], "stream": False},
        {"model": "auto", "messages": [{"role": "user", "content": "hi"}]},
    ):
        r = client.post("/v1/chat/completions", json=payload)
        assert r.status_code == 200, r.text
        assert r.json()["object"] == "chat.completion"
        assert r.json()["choices"][0]["message"]["content"]


def _standard_responder(model, messages, response_format=None, **kw):  # type: ignore[no-untyped-def]
    """Canonical scripted responder: valid dispatcher JSON, then worker/aggregator text."""
    if response_format is not None:
        return _resp(dispatch_json(), model, 100, 200)
    joined = json.dumps(messages)
    if "Upstream outputs" in joined:
        return _resp("FINAL ANSWER", model, 60, 90)
    return _resp(f"worker {model}", model, 20, 40)


def test_chat_completions_max_tokens_honored(config) -> None:  # type: ignore[no-untyped-def]
    """CH-GAP-031: max_tokens caps every worker/aggregator gateway call.

    Regression: max_tokens used to be absent from ChatCompletionRequest, so a
    drop-in client bounding cost believed the limit was applied while the
    deliberation ran unbounded. Now the cap must reach the gateway on all
    answer-producing calls (2 workers + 1 aggregator for the auto formation).
    """
    client, gateway = _client_with_gateway(config, _standard_responder)
    r = client.post(
        "/v1/chat/completions",
        json={
            "model": "auto",
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 1,
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["object"] == "chat.completion"
    # 4 calls total: 1 dispatcher + 2 workers + 1 aggregator.
    assert len(gateway.calls) == 4, gateway.calls
    capped = [c for c in gateway.calls if c[2].get("max_tokens") == 1]
    assert len(capped) == 3, f"expected 2 workers + 1 aggregator capped, got {gateway.calls}"
    # The dispatcher design call stays uncapped (small structured output).
    uncapped = [c for c in gateway.calls if "max_tokens" not in c[2]]
    assert len(uncapped) == 1, gateway.calls
    assert uncapped[0][2]["temperature"] == 0.1  # dispatcher signature


def test_chat_completions_max_completion_tokens_alias(config) -> None:  # type: ignore[no-untyped-def]
    """CH-GAP-031: max_completion_tokens accepted; wins over max_tokens."""
    client, gateway = _client_with_gateway(config, _standard_responder)
    r = client.post(
        "/v1/chat/completions",
        json={
            "model": "auto",
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 999,
            "max_completion_tokens": 5,
        },
    )
    assert r.status_code == 200, r.text
    capped = [c for c in gateway.calls if c[2].get("max_tokens") == 5]
    assert len(capped) == 3, gateway.calls


def test_chat_completions_n_and_top_p_accepted(config) -> None:  # type: ignore[no-untyped-def]
    """CH-GAP-031: n and top_p accepted for drop-in compat (documented no-ops).

    They must not 422 (pydantic) and must not leak into gateway kwargs — the
    OpenAI docs table names them as accepted-but-ignored.
    """
    client, gateway = _client_with_gateway(config, _standard_responder)
    r = client.post(
        "/v1/chat/completions",
        json={
            "model": "auto",
            "messages": [{"role": "user", "content": "hi"}],
            "n": 2,
            "top_p": 0.5,
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["object"] == "chat.completion"
    assert len(r.json()["choices"]) == 1  # n>1 unsupported — single choice
    assert all("n" not in c[2] and "top_p" not in c[2] for c in gateway.calls), gateway.calls
