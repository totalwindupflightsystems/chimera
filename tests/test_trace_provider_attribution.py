"""Resolved provider / wire model / api_base on deliberation-trace stage spans.

QA-CHIMERA-V2-16.  A trace used to expose only ``model`` (the response-reported
catalog id), so attributing a stage to a provider meant eyeballing the model-id
prefix and LiteLLM's stderr.  For a catalog with native prefixes AND generic
``base_url`` gateways AND credential fallbacks that is not a verification: a
route can serve a model on a provider other than the one its id names (F8
anthropic → openrouter) and the trace could not say so.

The attribution flows one way only:

``LiteLLMGateway.complete`` → ``resolve_litellm_model`` / ``effective_provider``
→ ``metadata["provider"|"wire_model"|"api_base"]`` on the ``GatewayResponse``
→ ``Engine._build_stage_result`` (worker/aggregator stages) and
``Engine._build_dispatch_span`` (the dispatcher's own call, CH-GAP-056)
→ ``StageSpan`` fields → the API trace payload.

Nothing derives a provider from the model id, and nothing invents one for a
stage with no resolved route (a degraded stage, or a gateway stub that carries
no metadata).  CH-GAP-056 added the dispatch span to the attributed set: the
dispatcher model call is a real gateway completion, so it carries the route the
gateway resolved for it — and stays empty exactly when no route was resolved
(the dispatcher's own ``{}`` fallback after a ``GatewayError``).  It also
carries the dispatcher's real ``time.monotonic()`` bracket, so the most
expensive stage of a run can be placed on the timeline.
"""

from __future__ import annotations

import copy
import json
from typing import Any
from unittest.mock import patch

import pytest

from chimera.config import ChimeraConfig
from chimera.engine import Engine, StageSpan, _route_attribution
from chimera.gateway import GatewayError, GatewayResponse, LiteLLMGateway
from chimera.web.trace_viz import trace_to_mermaid
from tests.conftest import CONFIG_DICT, FakeGateway, dispatch_json, resp

# --------------------------------------------------------------------------- #
# Fixtures: a catalog with a native route, a generic base_url route and an
# anthropic model that can only be served through the OpenRouter fallback.
# --------------------------------------------------------------------------- #

ROUTER9_PROVIDER = "router9"
ROUTER9_MODEL = "router9/ds/deepseek-v4-flash"
ROUTER9_BASE_URL = "http://master001:20128/v1"
ROUTER9_WIRE_MODEL = "openai/ds/deepseek-v4-flash"
FAKE_ROUTER9_KEY = "fake-router9-key-for-attribution-tests"

OPENROUTER_MODEL = "openrouter/qwen/qwen3-coder"
FAKE_OPENROUTER_KEY = "sk-or-v1-fake-key-for-attribution-tests"

ANTHROPIC_MODEL = "anthropic/claude-sonnet-4"
ANTHROPIC_WIRE_MODEL = "openrouter/anthropic/claude-sonnet-4"

_FAST_RETRY = {"max_attempts": 1, "base_delay_ms": 1, "max_delay_ms": 5}


def _config_dict(
    *,
    api_keys: dict[str, str] | None = None,
    circuit_breakers: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """The shared test catalog plus a generic gateway and an anthropic entry.

    ``api_keys`` deliberately carries only an OpenRouter credential: the
    anthropic model has no Anthropic key, which is what makes the gateway route
    it through OpenRouter (F8).
    """
    config = copy.deepcopy(CONFIG_DICT)
    config["retry"] = dict(_FAST_RETRY)
    config["api_keys"] = (
        api_keys if api_keys is not None else {"openrouter": FAKE_OPENROUTER_KEY}
    )
    if circuit_breakers is not None:
        config["circuit_breakers"] = circuit_breakers
    config["providers"][ROUTER9_PROVIDER] = {
        "base_url": ROUTER9_BASE_URL,
        "api_key": FAKE_ROUTER9_KEY,
    }
    config["models"][ROUTER9_MODEL] = {
        "categories": {"code": 0.8, "analysis": 0.7},
        "cost_tier": "budget",
        "provider": ROUTER9_PROVIDER,
    }
    config["models"][ANTHROPIC_MODEL] = {
        "categories": {"code": 0.9, "analysis": 0.9},
        "cost_tier": "premium",
        "provider": "anthropic",
    }
    config["defaults"] = {
        "dispatcher": OPENROUTER_MODEL,
        "default_worker": ROUTER9_MODEL,
        "default_aggregator": OPENROUTER_MODEL,
    }
    return config


def _config(**kwargs: Any) -> ChimeraConfig:
    return ChimeraConfig.model_validate(_config_dict(**kwargs))


def _dag(worker_model: str, aggregator_model: str = OPENROUTER_MODEL) -> dict[str, Any]:
    """A client DAG with one worker and one aggregator."""
    return {
        "stages": [
            {"id": "researcher", "kind": "worker", "model": worker_model},
            {"id": "finalizer", "kind": "aggregator", "model": aggregator_model,
             "depends_on": ["researcher"]},
        ],
        "edges": [["researcher", "finalizer"]],
    }


def _payload(worker_model: str, aggregator_model: str = OPENROUTER_MODEL) -> str:
    return dispatch_json(workers=[("researcher", worker_model)],
                         aggregator=aggregator_model)


class _StubResult:
    """Minimal LiteLLM-shaped result so ``_build_response`` works."""

    class _Message:
        def __init__(self, content: str) -> None:
            self.content = content

    class _Choice:
        finish_reason = "stop"

        def __init__(self, content: str) -> None:
            self.message = _StubResult._Message(content)

    class _Usage:
        prompt_tokens = 5
        completion_tokens = 2

    def __init__(self, content: str) -> None:
        self.choices = [_StubResult._Choice(content)]
        self.usage = _StubResult._Usage()


def _scripted_acompletion(payload: str):  # type: ignore[no-untyped-def]
    """A ``litellm.acompletion`` stand-in that answers like a healthy provider.

    The dispatcher pass is always the first gateway call of a deliberation (the
    engine designs/fills the DAG before any stage runs), so it answers with
    ``payload``; the aggregator prompt is the one that carries the upstream
    worker outputs.  Everything else is a worker call.
    """
    calls = {"n": 0}

    async def _complete(**kwargs: Any) -> Any:  # noqa: ANN401
        calls["n"] += 1
        if calls["n"] == 1:  # dispatcher design / fill-in pass
            return _StubResult(payload)
        if "Upstream outputs" in json.dumps(kwargs.get("messages") or []):
            return _StubResult("MERGED ANSWER")
        return _StubResult("WORKER OUTPUT")

    return _complete


async def _deliberate(config: ChimeraConfig, dag: dict[str, Any], payload: str):  # type: ignore[no-untyped-def]
    """Run a real deliberate through the real gateway (LiteLLM stubbed)."""
    gateway = LiteLLMGateway(config)
    with patch("litellm.acompletion", new=_scripted_acompletion(payload)):
        return await Engine(config, gateway).deliberate(
            "task", "auto", dag=dag, allow_custom_dag=True
        )


def _spans(result) -> dict[str, StageSpan]:  # type: ignore[no-untyped-def]
    return {span.stage_id: span for span in result.trace.stages}


# --------------------------------------------------------------------------- #
# Layer 1 — the gateway stamps the route it resolved onto the response
# --------------------------------------------------------------------------- #


async def test_native_route_stamps_provider_and_wire_model() -> None:
    """A natively-routed provider needs no api_base — the route has none."""
    gateway = LiteLLMGateway(_config())

    with patch("litellm.acompletion", new=_scripted_acompletion("WORKER OUTPUT")):
        response = await gateway.complete(
            OPENROUTER_MODEL, [{"role": "user", "content": "hi"}],
        )

    assert response.metadata["provider"] == "openrouter"
    assert response.metadata["wire_model"] == OPENROUTER_MODEL
    assert "api_base" not in response.metadata


async def test_custom_base_url_route_stamps_api_base() -> None:
    """The generic base_url branch reports the endpoint the call was sent to."""
    gateway = LiteLLMGateway(_config())

    with patch("litellm.acompletion", new=_scripted_acompletion("WORKER OUTPUT")):
        response = await gateway.complete(
            ROUTER9_MODEL, [{"role": "user", "content": "hi"}],
        )

    assert response.metadata == {
        "provider": ROUTER9_PROVIDER,
        "wire_model": ROUTER9_WIRE_MODEL,
        "api_base": ROUTER9_BASE_URL,
    }


async def test_fallback_route_stamps_the_serving_provider_not_the_prefix() -> None:
    """F8: the id prefix says anthropic, the serving provider is openrouter."""
    gateway = LiteLLMGateway(_config())  # no Anthropic key, OpenRouter key set

    with patch("litellm.acompletion", new=_scripted_acompletion("WORKER OUTPUT")):
        response = await gateway.complete(
            ANTHROPIC_MODEL, [{"role": "user", "content": "hi"}],
        )

    assert ANTHROPIC_MODEL.split("/", 1)[0] == "anthropic"  # the prefix
    assert response.metadata["provider"] == "openrouter"  # the truth
    assert response.metadata["wire_model"] == ANTHROPIC_WIRE_MODEL
    assert "api_base" not in response.metadata


async def test_circuit_fast_fail_carries_the_route_it_refused() -> None:
    """The route is resolved before the breaker check, so the skipped provider
    is attributable instead of invisible."""
    config = _config(
        circuit_breakers={"default": {
            "failure_threshold": 1, "recovery_timeout_s": 60,
            "half_open_max_requests": 1,
        }},
    )
    gateway = LiteLLMGateway(config)

    with (
        patch("litellm.acompletion", side_effect=RuntimeError("upstream down")),
        pytest.raises(GatewayError),
    ):
        await gateway.complete(ROUTER9_MODEL, [{"role": "user", "content": "hi"}])

    with patch("litellm.acompletion", new=_scripted_acompletion("WORKER OUTPUT")):
        response = await gateway.complete(ROUTER9_MODEL, [{"role": "user", "content": "hi"}])

    assert "[circuit open" in response.text
    assert response.metadata["provider"] == ROUTER9_PROVIDER
    assert response.metadata["wire_model"] == ROUTER9_WIRE_MODEL
    assert response.metadata["api_base"] == ROUTER9_BASE_URL


async def test_route_attribution_defaults_are_empty_without_metadata() -> None:
    """A response with no metadata channel reads as empty — never a guess."""
    bare = GatewayResponse(text="x", model=ROUTER9_MODEL, tokens_input=0, tokens_output=0)
    assert _route_attribution(bare) == ("", "", "")

    nulled = GatewayResponse(text="x", model=ROUTER9_MODEL, tokens_input=0,
                             tokens_output=0, metadata=None)  # type: ignore[arg-type]
    assert _route_attribution(nulled) == ("", "", "")


def test_stage_span_attribution_fields_default_to_empty() -> None:
    """Backward compatibility: existing constructions stay valid and empty."""
    span = StageSpan(stage_id="w", kind="worker", model=ROUTER9_MODEL,
                     prompt="p", response="r")
    assert (span.provider, span.wire_model, span.api_base) == ("", "", "")


# --------------------------------------------------------------------------- #
# Layer 2 — the engine puts the resolved route on the trace span
# --------------------------------------------------------------------------- #


async def test_successful_stage_spans_carry_the_resolved_route() -> None:
    """Worker (generic base_url) and aggregator (native) attribution, plus the
    serialized trace the API hands back."""
    result = await _deliberate(_config(), _dag(ROUTER9_MODEL), _payload(ROUTER9_MODEL))

    assert result.trace.source == "custom"
    spans = _spans(result)

    worker = spans["researcher"]
    assert worker.model == ROUTER9_MODEL
    assert worker.provider == ROUTER9_PROVIDER
    assert worker.wire_model == ROUTER9_WIRE_MODEL
    assert worker.api_base == ROUTER9_BASE_URL

    aggregator = spans["finalizer"]
    assert aggregator.model == OPENROUTER_MODEL
    assert aggregator.provider == "openrouter"
    assert aggregator.wire_model == OPENROUTER_MODEL
    assert aggregator.api_base == ""

    # CH-GAP-056: the dispatch stage runs the dispatcher model through the very
    # same gateway, so it carries the resolved route too — here the default
    # dispatcher model, natively routed by OpenRouter (no api_base).
    dispatch = result.trace.dispatch
    assert (dispatch.provider, dispatch.wire_model, dispatch.api_base) == (
        "openrouter",
        OPENROUTER_MODEL,
        "",
    )

    # AC2 / CH-GAP-056: real monotonic timestamps on the dispatch span, ordered.
    assert dispatch.started_at > 0
    assert dispatch.ended_at >= dispatch.started_at > 0

    # Acceptance 4: the fields survive into the serialized API payload.
    payload = result.trace.model_dump(mode="json")
    serialized = {s["stage_id"]: s for s in payload["stages"]}
    assert serialized["researcher"]["provider"] == ROUTER9_PROVIDER
    assert serialized["researcher"]["wire_model"] == ROUTER9_WIRE_MODEL
    assert serialized["researcher"]["api_base"] == ROUTER9_BASE_URL
    assert serialized["finalizer"]["provider"] == "openrouter"
    assert serialized["finalizer"]["api_base"] == ""
    assert payload["dispatch"]["provider"] == "openrouter"
    assert payload["dispatch"]["started_at"] > 0
    assert payload["dispatch"]["ended_at"] >= payload["dispatch"]["started_at"] > 0


async def test_fallback_route_reports_the_serving_provider_in_the_trace() -> None:
    """The catalog prefix and the serving provider disagree; the trace says so."""
    result = await _deliberate(_config(), _dag(ANTHROPIC_MODEL), _payload(ANTHROPIC_MODEL))

    worker = _spans(result)["researcher"]
    assert worker.model == ANTHROPIC_MODEL          # the catalog id (prefix: anthropic)
    assert worker.provider == "openrouter"          # the provider that served it
    assert worker.wire_model == ANTHROPIC_WIRE_MODEL

    # The aggregate here would be exactly the "eyeball the prefix" mistake.
    serialized = {
        s["stage_id"]: s for s in result.trace.model_dump(mode="json")["stages"]
    }
    assert serialized["researcher"]["provider"] != "anthropic"


async def test_dispatch_span_carries_the_dispatcher_routes_own_attribution() -> None:
    """CH-GAP-056 / AC1: the dispatch span reports the route the gateway
    resolved for the DISPATCHER call — read off the dispatcher response's
    metadata, never inferred from the dispatcher model id.

    The discriminator is a generic ``base_url`` route (``router9``): its model
    id prefix says ``router9`` but the WIRE model is a different string
    (``openai/ds/deepseek-v4-flash``) and it is the only route in this catalog
    that carries an ``api_base``.  A span built by prefix-guessing cannot
    produce that triple.
    """
    from chimera.config import DeliberationOverrides  # noqa: PLC0415

    config = _config()
    gateway = LiteLLMGateway(config)
    payload = _payload(OPENROUTER_MODEL, aggregator_model=OPENROUTER_MODEL)

    with patch("litellm.acompletion", new=_scripted_acompletion(payload)):
        result = await Engine(config, gateway).deliberate(
            "task",
            "auto",
            overrides=DeliberationOverrides(dispatcher_model=ROUTER9_MODEL),
            dag=_dag(OPENROUTER_MODEL),
            allow_custom_dag=True,
        )

    dispatch = result.trace.dispatch
    assert dispatch.model == ROUTER9_MODEL          # the catalog id the caller forced
    assert dispatch.provider == ROUTER9_PROVIDER    # the provider that served it
    assert dispatch.wire_model == ROUTER9_WIRE_MODEL
    assert dispatch.api_base == ROUTER9_BASE_URL

    # The dispatcher route is genuinely one of the attributed routes: the same
    # triple the gateway stamps on a direct call for this model (Layer 1).
    with patch("litellm.acompletion", new=_scripted_acompletion("x")):
        direct = await LiteLLMGateway(config).complete(
            ROUTER9_MODEL, [{"role": "user", "content": "hi"}]
        )
    assert (dispatch.provider, dispatch.wire_model, dispatch.api_base) == _route_attribution(
        direct
    )

    # ...and it is not what the model-id prefix alone would have produced.
    assert dispatch.api_base != ""


async def test_dispatch_span_timestamps_are_real_and_differ_per_run() -> None:
    """CH-GAP-056 / AC2: the dispatch span's timestamps are real monotonic
    readings — ordered, non-zero, and different for two separate runs.  A
    constant (or a re-timed "now" captured after the fact) cannot satisfy the
    bracket/ordering relation against the call it measured.
    """
    first = await _deliberate(_config(), _dag(ROUTER9_MODEL), _payload(ROUTER9_MODEL))
    second = await _deliberate(_config(), _dag(ROUTER9_MODEL), _payload(ROUTER9_MODEL))

    s1, s2 = first.trace.dispatch, second.trace.dispatch
    for span in (s1, s2):
        assert span.started_at > 0
        assert span.ended_at >= span.started_at
        # The bracket is the same reading pair latency_ms comes from: they
        # cannot contradict each other by more than the ms truncation.
        assert (span.ended_at - span.started_at) * 1000 >= span.latency_ms - 1

    assert (s1.started_at, s1.ended_at) != (s2.started_at, s2.ended_at)
    assert s2.started_at >= s1.ended_at

    # The dispatch call really is the FIRST thing the run does: its bracket
    # starts before every worker/aggregator span in the trace.
    worker = _spans(first)["researcher"]
    assert s1.started_at <= worker.started_at
    assert s1.ended_at <= worker.ended_at


async def test_dispatch_latency_ms_is_unchanged_by_the_timestamps() -> None:
    """AC4: adding the bracket does not change ``latency_ms`` — it stays the
    integer elapsed milliseconds of the dispatcher call, on the same reading
    pair as before.
    """
    from chimera.dispatcher import Dispatcher  # noqa: PLC0415

    config = _config()
    gateway = FakeGateway(lambda model, messages, **kw: resp(
        _payload(ROUTER9_MODEL), model, 100, 200
    ))
    outcome = await Dispatcher(config, gateway).dispatch("design a system", "auto")

    assert isinstance(config, ChimeraConfig)
    assert outcome.latency_ms == int((outcome.ended_at - outcome.started_at) * 1000)
    assert outcome.latency_ms >= 0
    assert outcome.ended_at >= outcome.started_at > 0


async def test_degraded_and_unattributed_spans_report_empty_provider() -> None:
    """A degraded stage and a gateway that carries no metadata stay empty —
    and nothing raises on a response whose metadata lacks the keys."""
    payload = _payload(OPENROUTER_MODEL)

    def responder(model, messages, response_format=None, **kw):  # type: ignore[no-untyped-def]
        if response_format is not None:  # dispatcher
            return resp(payload, model, 100, 200)
        if "Upstream outputs" in json.dumps(messages):  # aggregator
            return resp("MERGED ANSWER", model, 10, 10)
        if model == ROUTER9_MODEL:
            raise GatewayError("provider down")
        return resp("WORKER OUTPUT", model, 10, 10)  # no metadata at all

    gateway = FakeGateway(responder)
    result = await Engine(_config(), gateway).deliberate(
        "task", "auto", dag=_dag(ROUTER9_MODEL), allow_custom_dag=True
    )

    spans = _spans(result)
    degraded = spans["researcher"]
    assert "unavailable" in degraded.response
    assert (degraded.provider, degraded.wire_model, degraded.api_base) == ("", "", "")

    for stage_id in ("finalizer",):
        span = spans[stage_id]
        assert span.model == OPENROUTER_MODEL
        assert (span.provider, span.wire_model, span.api_base) == ("", "", "")

    # AC3: this fake dispatcher stamps NO route metadata, so the dispatch span
    # reports "no route resolved" rather than a fabricated attribution — the
    # load-bearing guard against guessing from the model id.  Its timestamps
    # are still real: the dispatcher call happened, it just had no resolved
    # route to report.
    dispatch = result.trace.dispatch
    assert (dispatch.provider, dispatch.wire_model, dispatch.api_base) == ("", "", "")
    assert dispatch.started_at > 0
    assert dispatch.ended_at >= dispatch.started_at > 0


async def test_failed_dispatcher_call_keeps_empty_attribution() -> None:
    """AC3 (real path): when ``Dispatcher._call_dispatcher`` swallows a
    ``GatewayError`` and returns its ``{}`` fallback response, no route was
    resolved — the dispatch span stays ``("", "", "")`` while still carrying
    the real bracket of the failed call.  Attribution is read from the
    response metadata, never reconstructed.
    """
    def responder(model, messages, response_format=None, **kw):  # type: ignore[no-untyped-def]
        if response_format is not None:  # the dispatcher call — upstream is down
            raise GatewayError("dispatcher provider down")
        if "Upstream outputs" in json.dumps(messages):  # aggregator
            return resp("MERGED ANSWER", model, 10, 10)
        return resp("WORKER OUTPUT", model, 10, 10)

    result = await Engine(_config(), FakeGateway(responder)).deliberate(
        "task", "auto", dag=_dag(ROUTER9_MODEL), allow_custom_dag=True
    )

    dispatch = result.trace.dispatch
    assert dispatch.response == "{}"
    assert (dispatch.provider, dispatch.wire_model, dispatch.api_base) == ("", "", "")
    assert dispatch.started_at > 0
    assert dispatch.ended_at >= dispatch.started_at > 0
    # A fallback dispatch still resolves zero tokens and reports its own model.
    assert dispatch.tokens_input == 0
    assert dispatch.tokens_output == 0


# --------------------------------------------------------------------------- #
# Acceptance 4 at the HTTP boundary — the /v1/deliberate trace payload
# --------------------------------------------------------------------------- #


async def test_api_trace_payload_exposes_the_resolved_route() -> None:
    """A verifier reading the API response can attribute every stage."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from chimera.api.server import create_app  # noqa: PLC0415

    config = _config()
    gateway = LiteLLMGateway(config)
    app = create_app(config=config, engine=Engine(config, gateway))
    client = TestClient(app)

    with patch("litellm.acompletion", new=_scripted_acompletion(_payload(ROUTER9_MODEL))):
        response = client.post(
            "/v1/deliberate",
            json={
                "prompt": "hi",
                "dag": _dag(ROUTER9_MODEL),
                "allow_custom_dag": True,
            },
        )

    assert response.status_code == 200, response.text
    trace = response.json()["trace"]
    stages = {s["stage_id"]: s for s in trace["stages"]}

    assert stages["researcher"]["provider"] == ROUTER9_PROVIDER
    assert stages["researcher"]["wire_model"] == ROUTER9_WIRE_MODEL
    assert stages["researcher"]["api_base"] == ROUTER9_BASE_URL
    assert stages["finalizer"]["provider"] == "openrouter"
    # CH-GAP-056: the dispatch span reaches the API consumer attributed too.
    assert trace["dispatch"]["provider"] == "openrouter"
    assert trace["dispatch"]["wire_model"] == OPENROUTER_MODEL
    assert trace["dispatch"]["api_base"] == ""
    assert trace["dispatch"]["started_at"] > 0
    assert (
        trace["dispatch"]["ended_at"] >= trace["dispatch"]["started_at"] > 0
    )

    # Additive only: every pre-existing key survives, with its old meaning.
    assert stages["researcher"]["model"] == ROUTER9_MODEL
    assert set(stages["researcher"]) >= {
        "stage_id", "kind", "model", "provider", "wire_model", "api_base",
        "prompt", "response", "tokens_input", "tokens_output", "latency_ms",
        "cost", "depends_on", "iteration", "started_at", "ended_at",
    }


# --------------------------------------------------------------------------- #
# Optional surface: the /web trace view (item 7 of the task)
# --------------------------------------------------------------------------- #


def test_trace_viz_surfaces_the_resolved_provider() -> None:
    mermaid = trace_to_mermaid({
        "stages": [{
            "stage_id": "w1", "kind": "worker", "model": ROUTER9_MODEL,
            "provider": ROUTER9_PROVIDER, "prompt": "p", "response": "r",
        }],
    })
    assert "via router9" in mermaid


def test_trace_viz_label_is_unchanged_without_a_provider() -> None:
    """Older traces / internal spans keep their existing label byte-for-byte."""
    mermaid = trace_to_mermaid({
        "stages": [{
            "stage_id": "w1", "kind": "worker", "model": "deepseek/deepseek-chat",
        }],
    })
    assert 'w1["worker\\ndeepseek-chat"]' in mermaid
    assert "via" not in mermaid
