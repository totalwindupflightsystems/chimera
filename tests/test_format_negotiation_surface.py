"""Format negotiation surfaced to OpenAI-compatible clients.

DF-CHIMERA-V2-53.  ``negotiate_response_format`` already downgrades/removes
``response_format`` per provider capability and logs the loss internally
(``gateway_format_downgrade`` / ``gateway_format_removed``), but the
OpenAI-compatible response carried no trace of it: a drop-in SDK client that
sent ``json_schema`` got ``200`` + ``finish_reason=stop`` and believed it had
validated data even when the provider answered as plain text (hit for real in
dogfood run 15 — a severity enum [P0, P1, P2] came back as high/medium/low).

These tests pin the full surfacing path:

1. gateway call → ``GatewayResponse.metadata["format_negotiation"]``
   (``{"requested": ..., "served": ...}``, present ONLY on a lossy outcome);
2. metadata → ``StageSpan.negotiated_format`` on the trace span;
3. the answer span's outcome → the compat response's
   ``chimera_format_negotiation`` field (absent when nothing was weakened).

The internal auto-fallback itself is intentional and stays (DF-CHIMERA-V2-7);
these tests cover making it VISIBLE at the user-facing edge, not removing it.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from chimera.api import server as api_server  # noqa: E402
from chimera.config import ChimeraConfig  # noqa: E402
from chimera.engine import Engine  # noqa: E402
from chimera.gateway import GatewayResponse, LiteLLMGateway  # noqa: E402
from tests.conftest import CONFIG_DICT, FakeGateway, dispatch_json  # noqa: E402

# =========================================================================== #
# 1. Gateway: the negotiated outcome rides the metadata side-band
# =========================================================================== #


def _gateway_config_with(provider: str, model_id: str) -> ChimeraConfig:
    """Conftest config plus one model whose provider is *provider*."""
    cfg_dict = dict(CONFIG_DICT)
    cfg_dict["models"] = dict(CONFIG_DICT["models"])
    from chimera.config import ModelEntry  # noqa: PLC0415 — local import keeps the RED run legible

    cfg_dict["models"][model_id] = ModelEntry(
        categories={"code": 0.9},
        cost_tier="budget",
        provider=provider,
    )
    return ChimeraConfig.model_validate(cfg_dict)


_SCHEMA_REQUEST: dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "findings",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "severity": {"type": "string", "enum": ["P0", "P1", "P2"]},
            },
            "required": ["severity"],
        },
    },
}


@pytest.mark.asyncio
async def test_gateway_response_carries_downgrade_outcome() -> None:
    """json_schema → json_object provider: metadata records requested+served."""
    config = _gateway_config_with("moonshot", "moonshot/test-chat")
    gw = LiteLLMGateway(config)
    fake_result = _litellm_result()

    with patch_litellm(fake_result):
        resp = await gw.complete(
            "moonshot/test-chat",
            [{"role": "user", "content": "hi"}],
            response_format=dict(_SCHEMA_REQUEST),
        )

    assert resp.metadata["format_negotiation"] == {
        "requested": "json_schema",
        "served": "json_object",
    }


@pytest.mark.asyncio
async def test_gateway_response_carries_removal_outcome() -> None:
    """Format stripped for a text-only provider: served is explicitly None."""
    config = _gateway_config_with("deepseek", "deepseek/test-chat")
    gw = LiteLLMGateway(config)
    fake_result = _litellm_result()

    with patch_litellm(fake_result):
        resp = await gw.complete(
            "deepseek/test-chat",
            [{"role": "user", "content": "hi"}],
            response_format=dict(_SCHEMA_REQUEST),
        )

    assert resp.metadata["format_negotiation"] == {
        "requested": "json_schema",
        "served": None,
    }


@pytest.mark.asyncio
async def test_gateway_response_schema_pass_through_has_no_negotiation() -> None:
    """A schema-capable provider honors the request — no report is stamped.

    The metadata entry marks a LOSSY outcome only; a pass-through must not
    look like a downgrade.
    """
    config = _gateway_config_with("zai", "zai/test-chat")
    gw = LiteLLMGateway(config)
    fake_result = _litellm_result()

    with patch_litellm(fake_result):
        resp = await gw.complete(
            "zai/test-chat",
            [{"role": "user", "content": "hi"}],
            response_format=dict(_SCHEMA_REQUEST),
        )

    assert "format_negotiation" not in resp.metadata


@pytest.mark.asyncio
async def test_gateway_response_text_call_has_no_negotiation() -> None:
    """No response_format requested → no negotiation happened → no entry."""
    config = _gateway_config_with("deepseek", "deepseek/test-chat")
    gw = LiteLLMGateway(config)
    fake_result = _litellm_result()

    with patch_litellm(fake_result):
        resp = await gw.complete(
            "deepseek/test-chat",
            [{"role": "user", "content": "hi"}],
        )

    assert "format_negotiation" not in resp.metadata


@pytest.mark.asyncio
async def test_gateway_call_immune_to_stale_negotiation_outcome() -> None:
    """A call with no response_format must not report ANOTHER call's outcome.

    ``negotiate_response_format`` records its outcome on a ContextVar that
    ``complete()`` drains; a direct caller (a unit test, another module)
    leaves a stale value behind. Every ``complete()`` resets before it
    negotiates, so a plain text call after a lossy one carries no
    ``format_negotiation`` at all — not someone else's downgrade.
    """
    from chimera.gateway import negotiate_response_format

    config = _gateway_config_with("deepseek", "deepseek/test-chat")
    gw = LiteLLMGateway(config)
    fake_result = _litellm_result()

    # Simulate a direct caller leaving a stale outcome on the ContextVar.
    negotiate_response_format({"type": "json_schema"}, "deepseek")

    with patch_litellm(fake_result):
        resp = await gw.complete(
            "deepseek/test-chat",
            [{"role": "user", "content": "hi"}],
        )

    assert "format_negotiation" not in resp.metadata


def _litellm_result(text: str = '{"ok": true}') -> Any:
    """Minimal namespace quacking like a LiteLLM completion result."""
    from types import SimpleNamespace

    return SimpleNamespace(
        choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content=text))],
        usage=SimpleNamespace(prompt_tokens=5, completion_tokens=7),
    )


def patch_litellm(fake_result: Any):  # type: ignore[no-untyped-def]
    """Patch litellm.acompletion for one gateway call."""
    from unittest.mock import patch

    return patch("litellm.acompletion", return_value=fake_result)


# =========================================================================== #
# 2. Engine: the trace span carries its call's negotiation outcome
# =========================================================================== #


@pytest.mark.asyncio
async def test_answer_span_carries_negotiated_format(config) -> None:  # type: ignore[no-untyped-def]
    """The aggregator span carries ITS call's negotiated outcome.

    The FakeGateway stands in for the real gateway's side-band stamping: the
    aggregator's schema request went to an openrouter-facing model (capability
    table: none), so the real gateway removes the format and reports
    ``{"requested": "json_schema", "served": None}``.
    """

    def responder(model, messages, response_format=None, **kw):  # type: ignore[no-untyped-def]
        joined = json.dumps(messages)
        if "Upstream outputs" in joined:  # aggregator (its schema request carries response_format too)
            return GatewayResponse(
                text='{"findings": []}',
                model=model,
                tokens_input=60,
                tokens_output=90,
                metadata={
                    "provider": "openrouter",
                    "format_negotiation": {
                        "requested": "json_schema",
                        "served": None,
                    },
                },
            )
        if response_format is not None:  # dispatcher design call
            return GatewayResponse(
                text=dispatch_json(),
                model=model,
                tokens_input=100,
                tokens_output=200,
            )
        return GatewayResponse(  # workers
            text=f"[worker {model}]",
            model=model,
            tokens_input=25,
            tokens_output=35,
        )

    result = await Engine(config, FakeGateway(responder)).deliberate(
        "task",
        "auto",
        output_schema={"type": "object", "properties": {"findings": {"type": "array"}}},
    )
    agg_spans = [s for s in result.trace.stages if s.kind in {"aggregator", "merge", "audit"}]
    assert agg_spans
    assert result.trace.answer_stage_id
    assert all(s.negotiated_format == {"requested": "json_schema", "served": None} for s in agg_spans)


@pytest.mark.asyncio
async def test_answer_span_without_negotiation_metadata_leaves_default(config) -> None:  # type: ignore[no-untyped-def]
    """A span whose gateway carried no report stays ``None`` — never guessed.

    Test doubles (and pass-through routes) carry no ``format_negotiation``
    metadata; the engine must not fabricate an outcome for them.
    """
    result = await Engine(config, FakeGateway()).deliberate("task", "auto")
    assert all(s.negotiated_format is None for s in result.trace.stages)


# =========================================================================== #
# 3. Compat response: the answer stage's outcome is surfaced
# =========================================================================== #


def _compat_format_negotiation_of(trace):  # type: ignore[no-untyped-def]
    """Direct call of the helper the route uses (unit-level pins)."""
    return api_server._compat_format_negotiation(trace)


def test_negotiation_outcome_removed_when_provider_strips_format(config) -> None:  # type: ignore[no-untyped-def]
    """json_schema + NONE-capability answer provider ⇒ served: null is surfaced."""
    from chimera.engine import DeliberationTrace, StageSpan

    trace = DeliberationTrace(
        request_id="req-neg",
        formation="simple",
        source="preset",
        answer_stage_id="aggregator",
        dispatch=StageSpan(
            stage_id="dispatch",
            kind="dispatch",
            model="zai-coding-plan/glm-5.2",
            prompt="d",
            response="{}",
        ),
        stages=[
            StageSpan(
                stage_id="aggregator",
                kind="aggregator",
                model="deepseek/deepseek-v4-flash",
                provider="deepseek",
                prompt="merge",
                response="plain text",
                negotiated_format={"requested": "json_schema", "served": None},
            ),
        ],
    )
    assert _compat_format_negotiation_of(trace) == {
        "requested": "json_schema",
        "served": None,
    }


def test_negotiation_outcome_pass_through_is_omitted(config) -> None:  # type: ignore[no-untyped-def]
    """A pass-through (served == requested) is NOT a downgrade — omit it."""
    from chimera.engine import DeliberationTrace, StageSpan

    trace = DeliberationTrace(
        request_id="req-neg",
        formation="simple",
        source="preset",
        answer_stage_id="aggregator",
        dispatch=StageSpan(
            stage_id="dispatch",
            kind="dispatch",
            model="zai-coding-plan/glm-5.2",
            prompt="d",
            response="{}",
        ),
        stages=[
            StageSpan(
                stage_id="aggregator",
                kind="aggregator",
                model="zai-coding-plan/glm-5.2",
                provider="zai",
                prompt="merge",
                response="{}",
                negotiated_format={"requested": "json_schema", "served": "json_schema"},
            ),
        ],
    )
    assert _compat_format_negotiation_of(trace) is None


def test_negotiation_outcome_ignores_non_answer_spans(config) -> None:  # type: ignore[no-untyped-def]
    """A downgrade on a NON-answer stage must not be attributed to the answer."""
    from chimera.engine import DeliberationTrace, StageSpan

    trace = DeliberationTrace(
        request_id="req-neg",
        formation="simple",
        source="preset",
        answer_stage_id="aggregator",
        dispatch=StageSpan(
            stage_id="dispatch",
            kind="dispatch",
            model="zai-coding-plan/glm-5.2",
            prompt="d",
            response="{}",
            negotiated_format={"requested": "json_object", "served": None},
        ),
        stages=[
            StageSpan(
                stage_id="worker_1",
                kind="worker",
                model="deepseek/deepseek-v4-flash",
                provider="deepseek",
                prompt="w",
                response="r",
                negotiated_format={"requested": "json_schema", "served": None},
            ),
            StageSpan(
                stage_id="aggregator",
                kind="aggregator",
                model="zai-coding-plan/glm-5.2",
                provider="zai",
                prompt="merge",
                response="{}",
            ),
        ],
    )
    assert _compat_format_negotiation_of(trace) is None


def test_chat_completions_surfaces_downgrade(config) -> None:  # type: ignore[no-untyped-def]
    """Route-level: a downgraded aggregator request surfaces the outcome."""
    gateway = FakeGateway(_downgrade_responder)
    engine = Engine(config, gateway)
    app = api_server.create_app(config=config, engine=engine)
    client = TestClient(app)
    r = client.post(
        "/v1/chat/completions",
        json={
            "model": "auto",
            "messages": [{"role": "user", "content": "hi"}],
            "response_format": _SCHEMA_REQUEST,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["chimera_format_negotiation"] == {
        "requested": "json_schema",
        "served": "json_object",
    }


def _downgrade_responder(model, messages, response_format=None, **kw):  # type: ignore[no-untyped-def]
    """Aggregator resolves to a moonshot-backed model: schema downgraded."""
    joined = json.dumps(messages)
    if "Upstream outputs" in joined:  # aggregator — the answer stage
        return GatewayResponse(
            text='{"severity": "P1"}',
            model=model,
            tokens_input=60,
            tokens_output=90,
            metadata={
                "provider": "moonshot",
                "format_negotiation": {
                    "requested": "json_schema",
                    "served": "json_object",
                },
            },
        )
    if response_format is not None:  # dispatcher design call
        return GatewayResponse(
            text=dispatch_json(),
            model=model,
            tokens_input=100,
            tokens_output=200,
        )
    return GatewayResponse(  # workers
        text=f"worker {model}",
        model=model,
        tokens_input=20,
        tokens_output=40,
    )


def test_chat_completions_no_field_when_format_supported(config) -> None:  # type: ignore[no-untyped-def]
    """No loss anywhere ⇒ the field is ABSENT (not null, not pass-through)."""
    gateway = FakeGateway(_standard_responder)
    engine = Engine(config, gateway)
    app = api_server.create_app(config=config, engine=engine)
    client = TestClient(app)
    r = client.post(
        "/v1/chat/completions",
        json={
            "model": "auto",
            "messages": [{"role": "user", "content": "hi"}],
            "response_format": _SCHEMA_REQUEST,
        },
    )
    assert r.status_code == 200, r.text
    assert "chimera_format_negotiation" not in r.json()


def test_chat_completions_no_field_without_response_format(config) -> None:  # type: ignore[no-untyped-def]
    """Plain request (no response_format) ⇒ field absent — shape unchanged."""
    gateway = FakeGateway(_standard_responder)
    engine = Engine(config, gateway)
    app = api_server.create_app(config=config, engine=engine)
    client = TestClient(app)
    r = client.post(
        "/v1/chat/completions",
        json={"model": "auto", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.status_code == 200, r.text
    assert "chimera_format_negotiation" not in r.json()


def _standard_responder(model, messages, response_format=None, **kw):  # type: ignore[no-untyped-def]
    """Every call normal, no negotiation metadata anywhere."""
    if response_format is not None:
        return GatewayResponse(
            text=dispatch_json(),
            model=model,
            tokens_input=100,
            tokens_output=200,
        )
    joined = json.dumps(messages)
    if "Upstream outputs" in joined:
        return GatewayResponse(
            text="FINAL ANSWER",
            model=model,
            tokens_input=60,
            tokens_output=90,
        )
    return GatewayResponse(
        text=f"worker {model}",
        model=model,
        tokens_input=20,
        tokens_output=40,
    )


def test_chat_completions_negotiation_uses_answer_span_not_workers(config) -> None:  # type: ignore[no-untyped-def]
    """A worker-stage downgrade does not surface as the ANSWER's constraint.

    Only the stage whose call produced the merged answer constrains it; the
    schema never rides worker calls on the wire, so their outcomes are noise
    for the compat field.
    """

    def responder(model, messages, response_format=None, **kw):  # type: ignore[no-untyped-def]
        if response_format is not None:
            return GatewayResponse(
                text=dispatch_json(),
                model=model,
                tokens_input=100,
                tokens_output=200,
            )
        joined = json.dumps(messages)
        if "Upstream outputs" in joined:  # aggregator: schema honored
            return GatewayResponse(
                text="FINAL ANSWER",
                model=model,
                tokens_input=60,
                tokens_output=90,
            )
        return GatewayResponse(  # workers: pretend a downgrade happened
            text=f"worker {model}",
            model=model,
            tokens_input=20,
            tokens_output=40,
            metadata={
                "provider": "moonshot",
                "format_negotiation": {
                    "requested": "json_schema",
                    "served": "json_object",
                },
            },
        )

    gateway = FakeGateway(responder)
    engine = Engine(config, gateway)
    app = api_server.create_app(config=config, engine=engine)
    client = TestClient(app)
    r = client.post(
        "/v1/chat/completions",
        json={
            "model": "auto",
            "messages": [{"role": "user", "content": "hi"}],
            "response_format": _SCHEMA_REQUEST,
        },
    )
    assert r.status_code == 200, r.text
    assert "chimera_format_negotiation" not in r.json()


# Keep the import used even if the asyncio helpers above are reordered.
_ = asyncio
