"""INT-CI-009 — the audit formation must not degrade on a delimited string.

The dispatcher authors the final ``output_schema``, but the wire cannot always
enforce it: :func:`chimera.gateway.negotiate_response_format` strips
``response_format`` for a :attr:`FormatCapability.NONE` provider (deepseek and
openrouter are NONE — CH-GAP-024), so the model never sees the schema and
answers ``{"answer": ..., "sources": "worker_1, worker_2"}`` where the schema
declared an array of strings. The engine then replaced a perfectly good answer
with ``{"passed": false, "errors": ["'worker_1, worker_2' is not of type
'array'"]}`` and the SSE integration leg went red (CI run 35284159959).

This module pins both arms of the fix:

* ARM A — :meth:`Engine._normalize_delimited_string_arrays`, the ONE documented
  coercion, exercised at the helper level AND end-to-end through
  :meth:`Engine.deliberate` (the regression the row names), together with the
  negative controls that prove the schema was not loosened.
* ARM B — the prompt-side restatement in
  :func:`chimera.aggregator._schema_restatement` and the capability derivation
  that decides when it fires (``_schema_enforceable_on_wire``), asserted at the
  ``build_merge_prompt`` level and through ``Aggregator.execute`` so the real
  config-derived flag is exercised, not a hand-passed boolean.

Hermetic: every provider call is a ``FakeGateway``; no network.
"""

from __future__ import annotations

import copy
import json
from typing import Any

import pytest

from chimera.aggregator import (
    Aggregator,
    _schema_enforceable_on_wire,
    _schema_restatement,
    build_merge_prompt,
)
from chimera.config import ChimeraConfig
from chimera.dispatcher import Stage
from chimera.engine import Engine
from tests.conftest import CONFIG_DICT, FakeGateway, resp

#: The exact shape the dispatcher documents for the final answer
#: (``src/chimera/dispatcher.py``), including the ``sources`` array of strings
#: that the live failure tripped over.
AUDIT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "answer": {
            "type": "string",
            "description": "The final merged answer for the user",
        },
        "sources": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Worker IDs that contributed",
        },
    },
    "required": ["answer"],
}

#: The measured CI failure shape: valid JSON, wrong TYPE for ``sources``.
DELIMITED_SOURCES_ANSWER = json.dumps(
    {"answer": "The answer is 20.", "sources": "worker_1, worker_2"}
)


# ═══════════════════════════════════════════════════════════════════════════
# End-to-end replay through Engine.deliberate (the regression the row names)
# ═══════════════════════════════════════════════════════════════════════════


def _audit_payload(schema: dict[str, Any] | None = AUDIT_SCHEMA) -> str:
    """A dispatcher payload with an ``audit`` terminal stage carrying *schema*.

    Mirrors ``tests/test_engine_coverage.py::test_audit_stage_validates_against_schema``
    (worker_1 → aggregator → audit) but uses the dispatcher-documented final
    schema, and every stage runs on a NONE-capability provider — exactly the
    configuration the integration leg uses (``BUDGET_MODELS`` are deepseek).
    """
    stages = [
        {"id": "worker_1", "kind": "worker", "model": "deepseek/deepseek-chat",
         "depends_on": [], "output_schema": schema},
        {"id": "aggregator", "kind": "aggregator", "model": "deepseek/deepseek-chat",
         "depends_on": ["worker_1"]},
        {"id": "audit", "kind": "audit", "model": "deepseek/deepseek-chat",
         "depends_on": ["aggregator"], "iterate_on": ["worker_1"],
         "iteration_limit": 1, "output_schema": schema},
    ]
    return json.dumps({
        "formation": {
            "stages": stages,
            "edges": [["worker_1", "aggregator"], ["aggregator", "audit"]],
        },
        "worker_prompts": [
            {"stage_id": "worker_1", "model": "deepseek/deepseek-chat",
             "prompt": "hi", "expected_output_schema": None},
        ],
        "aggregator_instructions": "merge",
        "stage_instructions": {"audit": "Check."},
        "output_schema": schema,
    })


async def _run_audit(
    config: ChimeraConfig,
    audit_answer: str,
    schema: dict[str, Any] | None = AUDIT_SCHEMA,
):
    """Deliberate once; the audit stage answers with *audit_answer* verbatim."""
    payload = _audit_payload(schema)

    def respond(model, messages, response_format=None, **kw):
        joined = json.dumps(messages)
        if "## Dispatcher's instructions for you (audit)" in joined:
            return resp(audit_answer, model, 30, 50)
        if response_format is not None:
            return resp(payload, model, 100, 200)
        if "Upstream outputs" in joined:
            return resp("aggregator output", model, 40, 60)
        return resp("worker output", model, 20, 30)

    engine = Engine(config, FakeGateway(respond))
    return await engine.deliberate("hi")


def _span(result, stage_id: str):
    for span in result.trace.stages:
        if span.stage_id == stage_id:
            return span
    raise AssertionError(f"no span for stage {stage_id!r}")


@pytest.mark.asyncio
async def test_audit_delimited_sources_string_is_not_degraded(
    config: ChimeraConfig,
) -> None:
    """INT-CI-009 regression: ``sources`` as ``"worker_1, worker_2"`` survives.

    Pre-fix the audit response was REPLACED by the validation-failure object and
    the SSE leg reported ``degraded on attempt 3/3``; the model's own answer
    must reach the result untouched.
    """
    result = await _run_audit(config, DELIMITED_SOURCES_ANSWER)

    audit_span = _span(result, "audit")
    assert audit_span.response == DELIMITED_SOURCES_ANSWER, (
        "the audit response was rewritten — the delimited string was not "
        f"normalized before validation: {audit_span.response!r}"
    )
    assert "is not of type" not in audit_span.response
    assert '"passed": false' not in audit_span.response

    # …and the answer the caller actually receives is the model's answer, not
    # the validation object (the envelope unwrap yields the ``answer`` field).
    assert result.answer == "The answer is 20."
    assert not result.answer_degraded


@pytest.mark.asyncio
async def test_audit_number_sources_still_degrades(config: ChimeraConfig) -> None:
    """NEGATIVE CONTROL: the schema is NOT loosened.

    ``sources`` as a NUMBER is a genuine violation — no coercion applies, so the
    engine must still replace the answer with the validation-failure object.
    """
    bad = json.dumps({"answer": "The answer is 20.", "sources": 3})
    result = await _run_audit(config, bad)

    body = json.loads(_span(result, "audit").response)
    assert body["passed"] is False
    assert any("is not of type 'array'" in err for err in body["errors"]), body
    assert result.answer.startswith('{"passed": false')


@pytest.mark.asyncio
async def test_audit_empty_sources_string_still_degrades(
    config: ChimeraConfig,
) -> None:
    """The documented empty-string decision, pinned end-to-end.

    ``""`` (like ``"   "`` and ``","``) yields no list information, so it is
    DELIBERATELY left as a string rather than becoming a fabricated ``[]``: the
    type check still fails and the audit degrades loudly.
    """
    bad = json.dumps({"answer": "The answer is 20.", "sources": "   "})
    result = await _run_audit(config, bad)

    body = json.loads(_span(result, "audit").response)
    assert body["passed"] is False
    assert any("is not of type 'array'" in err for err in body["errors"]), body


@pytest.mark.asyncio
async def test_audit_non_string_items_are_not_widened(
    config: ChimeraConfig,
) -> None:
    """NEGATIVE CONTROL: no scalar→array widening for non-string items."""
    schema = {
        "type": "object",
        "properties": {
            "answer": {"type": "string"},
            "sources": {"type": "array", "items": {"type": "integer"}},
        },
        "required": ["answer"],
    }
    bad = json.dumps({"answer": "The answer is 20.", "sources": "1, 2"})
    result = await _run_audit(config, bad, schema=schema)

    body = json.loads(_span(result, "audit").response)
    assert body["passed"] is False
    assert any("is not of type 'array'" in err for err in body["errors"]), body


# ═══════════════════════════════════════════════════════════════════════════
# ARM A helper units — exact scope of the ONE coercion
# ═══════════════════════════════════════════════════════════════════════════


def _normalize(schema: dict[str, Any], instance: Any) -> Any:
    return Engine._normalize_delimited_string_arrays(schema, instance)


def test_helper_splits_strips_and_drops_empty_parts() -> None:
    instance = {"answer": "x", "sources": " worker_1 ,\n worker_2 ,,worker_3\t"}
    out = _normalize(AUDIT_SCHEMA, instance)
    assert out["sources"] == ["worker_1", "worker_2", "worker_3"]
    assert out["answer"] == "x", "a non-array property must be untouched"


def test_helper_leaves_a_correct_array_unchanged() -> None:
    """Identity, not equality: an already-correct list is never rebuilt."""
    sources = ["worker_1", "worker_2"]
    instance = {"answer": "x", "sources": sources}
    out = _normalize(AUDIT_SCHEMA, instance)
    assert out is instance
    assert out["sources"] is sources


def test_helper_is_idempotent() -> None:
    once = _normalize(AUDIT_SCHEMA, {"sources": "a, b"})
    twice = _normalize(AUDIT_SCHEMA, once)
    assert twice["sources"] == ["a", "b"]


@pytest.mark.parametrize(
    "schema",
    [
        {"properties": {"sources": {"type": "array"}}},  # no items declared
        {"properties": {"sources": {"type": "array", "items": {"type": "integer"}}}},
        {"properties": {"sources": {"type": "string"}}},
        {"properties": {"sources": {"type": "object"}}},
        {"properties": {}},
        {"type": "object"},  # no properties at all
    ],
)
def test_helper_leaves_non_array_of_strings_alone(schema: dict[str, Any]) -> None:
    instance = {"sources": "worker_1, worker_2"}
    out = _normalize(schema, instance)
    assert out["sources"] == "worker_1, worker_2"


def test_helper_only_touches_top_level_properties() -> None:
    """A nested array-of-strings is OUT of scope — no recursion."""
    schema = {
        "type": "object",
        "properties": {
            "meta": {
                "type": "object",
                "properties": {"sources": {"type": "array", "items": {"type": "string"}}},
            },
        },
    }
    instance = {"meta": {"sources": "worker_1, worker_2"}}
    out = _normalize(schema, instance)
    assert out["meta"]["sources"] == "worker_1, worker_2"


def test_helper_missing_property_is_a_no_op() -> None:
    instance = {"answer": "x"}
    out = _normalize(AUDIT_SCHEMA, instance)
    assert out == {"answer": "x"}
    assert "sources" not in out  # never populated, never invented


@pytest.mark.parametrize("instance", ["plain text", ["a", "b"], None, 42, 3.5, True])
def test_helper_non_dict_instance_is_returned_unchanged(instance: Any) -> None:
    assert _normalize(AUDIT_SCHEMA, instance) is instance


@pytest.mark.parametrize("value", ["", "   ", ",", ", ,", "\n,\t"])
def test_helper_leaves_uninformative_strings_alone(value: str) -> None:
    """Pins the documented empty-string decision (no fabricated ``[]``)."""
    out = _normalize(AUDIT_SCHEMA, {"sources": value})
    assert out["sources"] == value


def test_helper_does_not_mutate_the_schema() -> None:
    schema = copy.deepcopy(AUDIT_SCHEMA)
    _normalize(schema, {"sources": "a, b"})
    assert schema == AUDIT_SCHEMA


# ═══════════════════════════════════════════════════════════════════════════
# ARM B — which providers can enforce the schema at all
# ═══════════════════════════════════════════════════════════════════════════


def _config(api_keys: dict[str, str] | None = None) -> ChimeraConfig:
    cfg_dict = copy.deepcopy(CONFIG_DICT)
    if api_keys is not None:
        cfg_dict["api_keys"] = api_keys
    return ChimeraConfig.model_validate(cfg_dict)


def _config_with_anthropic_model(api_keys: dict[str, str] | None = None) -> ChimeraConfig:
    """CONFIG_DICT has no anthropic-PROVIDER model (its anthropic models are
    routed through openrouter), so add one to exercise the F8 reroute."""
    cfg_dict = copy.deepcopy(CONFIG_DICT)
    cfg_dict["models"]["anthropic/claude-sonnet-4"] = {
        **cfg_dict["models"]["openrouter/anthropic/claude-sonnet-4"],
        "provider": "anthropic",
    }
    if api_keys is not None:
        cfg_dict["api_keys"] = api_keys
    return ChimeraConfig.model_validate(cfg_dict)


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        ("zai-coding-plan/glm-5.2", True),          # zai — JSON_SCHEMA
        ("deepseek/deepseek-chat", False),          # openrouter — NONE
        ("deepseek/deepseek-v4-flash", False),      # deepseek — NONE (CH-GAP-024)
        ("openrouter/google/gemini-2.5-flash", False),
        ("not-in-the-catalog/at-all", False),       # unknown model → not enforceable
    ],
)
def test_schema_enforceable_per_provider(model: str, expected: bool) -> None:
    assert _schema_enforceable_on_wire(_config(), model) is expected


def test_schema_not_enforceable_on_the_f8_anthropic_reroute() -> None:
    """Anthropic is JSON_SCHEMA-capable, but F8 reroutes it to OpenRouter when
    no Anthropic credential resolves — and that route strips the schema."""
    cfg = _config_with_anthropic_model({"openrouter": "sk-test-only"})
    assert not _schema_enforceable_on_wire(cfg, "anthropic/claude-sonnet-4")


def test_schema_enforceable_when_the_anthropic_credential_resolves() -> None:
    cfg = _config_with_anthropic_model({"anthropic": "sk-test-only"})
    assert _schema_enforceable_on_wire(cfg, "anthropic/claude-sonnet-4")


def test_schema_enforceable_when_anthropic_resolves_from_the_provider_entry() -> None:
    """The gateway reads a native key from ``providers.anthropic.api_key`` too —
    so that route does NOT reroute, even with an OpenRouter key present."""
    cfg_dict = copy.deepcopy(CONFIG_DICT)
    cfg_dict["models"]["anthropic/claude-sonnet-4"] = {
        **cfg_dict["models"]["openrouter/anthropic/claude-sonnet-4"],
        "provider": "anthropic",
    }
    cfg_dict["api_keys"] = {"openrouter": "sk-test-only"}
    cfg_dict["providers"]["anthropic"]["api_key"] = "sk-native-only"
    cfg = ChimeraConfig.model_validate(cfg_dict)
    assert _schema_enforceable_on_wire(cfg, "anthropic/claude-sonnet-4")


def test_schema_enforceable_for_anthropic_without_an_openrouter_fallback() -> None:
    """No credential to reroute WITH means no reroute — the catalog provider
    (anthropic, JSON_SCHEMA-capable) stands."""
    assert _schema_enforceable_on_wire(
        _config_with_anthropic_model(), "anthropic/claude-sonnet-4",
    )


@pytest.mark.asyncio
async def test_aggregator_restates_schema_for_a_none_capability_provider(
    config: ChimeraConfig,
) -> None:
    """The flag is derived from the real config — not passed by the caller."""
    gw = FakeGateway(lambda m, msgs, **kw: resp("ok", m))
    aggregator = Aggregator(config, gw)
    stage = Stage(id="audit", kind="audit", model="deepseek/deepseek-chat")

    await aggregator.execute(stage, _dispatch(), _deps(), "hi",
                             output_schema=AUDIT_SCHEMA)

    prompt = json.dumps(gw.calls[-1][1])
    assert "## Required output shape" in prompt
    assert "never a comma-joined string" in prompt


@pytest.mark.asyncio
async def test_aggregator_omits_restatement_for_a_schema_capable_provider() -> None:
    """zai enforces the schema on the wire, so the prompt stays as it was."""
    cfg = _config()
    gw = FakeGateway(lambda m, msgs, **kw: resp("ok", m))
    aggregator = Aggregator(cfg, gw)
    stage = Stage(id="audit", kind="audit", model="zai-coding-plan/glm-5.2")

    await aggregator.execute(stage, _dispatch(), _deps(), "hi",
                             output_schema=AUDIT_SCHEMA)

    prompt = json.dumps(gw.calls[-1][1])
    assert "## Required output shape" not in prompt
    assert "comma-joined" not in prompt


def test_build_merge_prompt_restatement_is_opt_in_by_capability() -> None:
    """The restatement is present only when the wire cannot enforce the schema."""
    dispatch = _dispatch()
    stage = dispatch.formation.stage("audit")

    capable = build_merge_prompt(stage, dispatch, _deps(), "hi",
                                 output_schema=AUDIT_SCHEMA,
                                 wire_enforces_schema=True)
    incapable = build_merge_prompt(stage, dispatch, _deps(), "hi",
                                   output_schema=AUDIT_SCHEMA,
                                   wire_enforces_schema=False)
    default = build_merge_prompt(stage, dispatch, _deps(), "hi",
                                 output_schema=AUDIT_SCHEMA)

    # The capable path is byte-identical to the pre-change behaviour, and the
    # default (existing callers) keeps that behaviour.
    assert capable == default
    assert "## Required output shape" not in capable[1]["content"]

    user = incapable[1]["content"]
    assert user.startswith(capable[1]["content"]), (
        "the restatement must be appended to an otherwise untouched prompt"
    )
    assert "## Required output shape" in user
    assert "Required keys: answer." in user
    assert "answer: string" in user
    assert "sources: array of strings" in user
    assert 'MUST be a JSON ARRAY of strings' in user
    assert "never a comma-joined string" in user


def test_schema_restatement_lists_every_required_key() -> None:
    """The dispatcher's own shape (``required: ["answer"]``) names one key; a
    schema that requires more names all of them."""
    schema = {**AUDIT_SCHEMA, "required": ["answer", "sources"]}
    text = _schema_restatement(schema)
    assert "Required keys: answer, sources." in text
    assert "sources: array of strings" in text


def test_schema_restatement_survives_a_degenerate_schema() -> None:
    """A schema with nothing to restate yields the shape sentence only — never
    a crash, never a stray ``None``."""
    for schema in ({}, {"type": "object"}, {"properties": "nonsense"}):
        assert _schema_restatement(schema) == (
            "## Required output shape\n"
            "Reply with a single JSON object and nothing else — no prose, no code fences."
        )


# ─── small local fixtures for the Aggregator calls ─────────────────────────


def _dispatch():
    from chimera.dispatcher import DispatchResult, FormationDAG, WorkerPrompt

    dag = FormationDAG(
        stages=[
            Stage(id="worker_1", kind="worker", model="deepseek/deepseek-chat"),
            Stage(id="audit", kind="audit", model="deepseek/deepseek-chat",
                  depends_on=["worker_1"]),
        ],
        edges=[("worker_1", "audit")],
    )
    return DispatchResult(
        formation=dag,
        worker_prompts=[
            WorkerPrompt(stage_id="worker_1", model="deepseek/deepseek-chat",
                         prompt="Answer the question."),
        ],
        aggregator_instructions="Merge the worker outputs.",
        stage_instructions={"audit": "Check."},
    )


def _deps():
    from chimera.aggregator import StageResult

    return [
        StageResult(stage_id="worker_1", model="deepseek/deepseek-chat",
                    prompt="Answer the question.",
                    response=resp("20", "deepseek/deepseek-chat")),
    ]
