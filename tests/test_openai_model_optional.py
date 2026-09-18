"""INT-API-003: `model` is optional on ``POST /v1/chat/completions``.

docs/OPENAI_API.md documented ``model`` as optional with the ``"auto"``
default and showed a minimal request. The live schema REQUIRED it: the field
was ``Field(..., min_length=1)``, so the documented request answered **422**
with FastAPI's raw ``detail`` array while the doc promised the OpenAI-style
error object for the same endpoint.

The fix is one default (``Field("auto", min_length=1)``), and this file pins
the whole contract around it:

* omitting ``model`` is accepted and deliberates with the AUTO dispatcher;
* ``messages`` stays required and non-empty;
* OpenAPI no longer lists ``model`` as required and shows the ``auto`` default;
* an explicitly empty string is STILL a 422 — and its body is FastAPI's
  ``{"detail": [...]}`` validation shape, not an OpenAI ``error`` object;
* an explicitly unknown non-empty value is STILL a 404 ``model_not_found`` —
  the new default is never a silent substitution for a named model (CH-GAP-027).

The engine is faked in the established style (``tests/conftest.FakeGateway``)
so nothing here touches a live provider.
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from chimera.api.server import ChatCompletionRequest, create_app  # noqa: E402
from chimera.engine import Engine  # noqa: E402
from chimera.gateway import GatewayResponse  # noqa: E402
from tests.conftest import FakeGateway, dispatch_json  # noqa: E402

_MESSAGES = [{"role": "user", "content": "what is 2+2?"}]


def _resp(text: str, model: str, ti: int, to: int) -> GatewayResponse:
    return GatewayResponse(text=text, model=model, tokens_input=ti, tokens_output=to)


def _auto_responder(model, messages, response_format=None, **kw):  # type: ignore[no-untyped-def]
    """Dispatcher JSON for the design call, "FINAL ANSWER" for the aggregator."""
    if response_format is not None:
        return _resp(dispatch_json(), model, 100, 200)
    if "Upstream outputs" in json.dumps(messages):
        return _resp("FINAL ANSWER", model, 60, 90)
    return _resp(f"worker {model}", model, 20, 40)


def _client_with_gateway(config):  # type: ignore[no-untyped-def]
    gateway = FakeGateway(_auto_responder)
    app = create_app(config=config, engine=Engine(config, gateway))
    return TestClient(app), gateway


# --------------------------------------------------------------------------- #
# The request model itself
# --------------------------------------------------------------------------- #


def test_request_model_defaults_to_auto() -> None:
    """The Pydantic model defaults ``model`` to the auto formation."""
    req = ChatCompletionRequest.model_validate({"messages": _MESSAGES})
    assert req.model == "auto"


def test_request_model_still_rejects_empty_string() -> None:
    """An explicitly supplied empty model is a validation error, not a default."""
    with pytest.raises(ValidationError) as excinfo:
        ChatCompletionRequest.model_validate({"model": "", "messages": _MESSAGES})
    assert [e["loc"] for e in excinfo.value.errors()] == [("model",)]


# --------------------------------------------------------------------------- #
# Live HTTP behaviour
# --------------------------------------------------------------------------- #


def test_omitted_model_is_accepted_and_routes_as_auto(config) -> None:  # type: ignore[no-untyped-def]
    """The documented minimal request (messages only) deliberates as ``auto``."""
    client, gateway = _client_with_gateway(config)

    r = client.post("/v1/chat/completions", json={"messages": _MESSAGES})

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["object"] == "chat.completion"
    assert body["model"] == "auto"
    assert body["choices"][0]["message"]["content"] == "FINAL ANSWER"
    assert body["usage"]["total_tokens"] > 0
    # AUTO means the dispatcher designs the DAG, and only that path issues a
    # response_format (JSON-mode) design call. A preset formation such as
    # "simple" skips it entirely — so a recorded design call proves the request
    # was routed to the auto formation, not substituted with something else.
    assert any(kw.get("response_format") is not None for _, _, kw in gateway.calls)


def test_omitted_model_matches_explicit_auto(config) -> None:  # type: ignore[no-untyped-def]
    """Omitting ``model`` and sending ``"auto"`` produce the same response shape."""
    client, _gateway = _client_with_gateway(config)
    common = {"messages": _MESSAGES}

    omitted = client.post("/v1/chat/completions", json=common)
    explicit = client.post("/v1/chat/completions", json={"model": "auto", **common})

    assert omitted.status_code == explicit.status_code == 200
    assert omitted.json()["model"] == explicit.json()["model"] == "auto"
    assert (
        omitted.json()["choices"][0]["message"]["content"]
        == explicit.json()["choices"][0]["message"]["content"]
    )


def test_omitted_model_without_messages_is_422(config) -> None:  # type: ignore[no-untyped-def]
    """``messages`` is still required and non-empty — the default shares nothing with it."""
    client, gateway = _client_with_gateway(config)

    r = client.post("/v1/chat/completions", json={})

    assert r.status_code == 422
    assert [e["loc"] for e in r.json()["detail"]] == [["body", "messages"]]
    assert gateway.calls == []


def test_explicit_empty_model_is_422_with_fastapi_detail_array(config) -> None:  # type: ignore[no-untyped-def]
    """Empty model stays a 422, and the body is the raw validation array.

    This is the error surface the endpoint ACTUALLY emits for a bad request
    body: FastAPI's ``{"detail": [...]}``, NOT the OpenAI-style ``error``
    object the same doc promises for the model/stream/upstream errors.
    """
    client, gateway = _client_with_gateway(config)

    r = client.post("/v1/chat/completions", json={"model": "", "messages": _MESSAGES})

    assert r.status_code == 422
    body = r.json()
    assert set(body) == {"detail"}
    assert "error" not in body
    assert isinstance(body["detail"], list) and body["detail"]
    assert [e["loc"] for e in body["detail"]] == [["body", "model"]]
    assert body["detail"][0]["type"] == "string_too_short"
    assert gateway.calls == []  # rejected before any dispatch / billing


def test_explicit_unknown_model_still_404_not_substituted(config) -> None:  # type: ignore[no-untyped-def]
    """A named non-formation model keeps the hard 404 — no fall back to auto."""
    client, gateway = _client_with_gateway(config)
    unknown = "bogus/nonexistent-model-xyz"

    r = client.post("/v1/chat/completions", json={"model": unknown, "messages": _MESSAGES})

    assert r.status_code == 404, r.text
    body = r.json()
    assert body["error"]["code"] == "model_not_found"
    assert body["error"]["param"] == "model"
    assert body["error"]["type"] == "invalid_request_error"
    assert unknown in body["error"]["message"]
    assert gateway.calls == []  # nothing dispatched / billed


# --------------------------------------------------------------------------- #
# OpenAPI contract
# --------------------------------------------------------------------------- #


def test_openapi_chat_request_no_longer_requires_model(config) -> None:  # type: ignore[no-untyped-def]
    """``model`` is optional in the published schema; ``messages`` is not."""
    client, _gateway = _client_with_gateway(config)

    schema = client.get("/openapi.json").json()["components"]["schemas"]["ChatCompletionRequest"]

    assert schema["required"] == ["messages"]
    assert "model" not in schema["required"]
    assert schema["properties"]["model"]["default"] == "auto"
    # The default does not relax the empty-string rule.
    assert schema["properties"]["model"]["minLength"] == 1
    # messages stays a required, non-empty list.
    assert schema["properties"]["messages"]["minItems"] == 1
