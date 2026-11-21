"""DF-CHIMERA-V2-131: a locked role must never silently swallow a request override.

Pre-fix, ``lock_aggregator: true`` (or ``lock_dispatcher: true``) made a request's
``aggregator_model`` / ``dispatcher_model`` vanish: the field validated, the run
answered 200 with no mention of the discard, and a 502/503 named only the LOCKED
model — so a caller whose configured aggregator was dead could not escape it
through the API and never learned why.

The contract proven here (option (c) of the row's acceptance criteria — least
breaking, one behaviour only):

* the discard is a FIRST-CLASS field — ``discarded_overrides`` on
  ``POST /v1/deliberate`` (and its trace), ``chimera_discarded_overrides`` on
  ``POST /v1/chat/completions`` (and its trace) — with ``field`` / ``requested``
  / ``locked_by`` / ``reason``;
* the SAME field rides the 502 no-usable-answer envelope and the 503
  no-healthy-candidate / lane-unreachable envelope, and the failure MESSAGE
  carries the same clause, so a client reading only ``error.message`` still
  learns its override was ignored;
* with the lock OFF the override still wins and nothing is reported (clean
  responses stay byte-identical: the field is absent at the top level).

Coverage matrix (row criterion 3): lock true + lock false × upstream success +
upstream failure.
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from chimera.api.server import create_app  # noqa: E402
from chimera.config import DeliberationOverrides  # noqa: E402
from chimera.engine import Engine  # noqa: E402
from chimera.exceptions import (  # noqa: E402
    LaneUnreachableError,
    NoHealthyCandidateError,
    override_discard_clause,
)
from chimera.gateway import GatewayError, GatewayResponse  # noqa: E402
from tests.conftest import FakeGateway, dispatch_json  # noqa: E402

AGGREGATOR_OVERRIDE = "openrouter/anthropic/claude-sonnet-4"


def _resp(text, model, ti=20, to=40):  # type: ignore[no-untyped-def]
    return GatewayResponse(text=text, model=model, tokens_input=ti, tokens_output=to)


def _success_responder(model, messages, response_format=None, **kw):  # type: ignore[no-untyped-def]
    """Dispatcher answers with a DAG; workers and the aggregator answer for real."""
    if response_format is not None:
        return _resp(
            dispatch_json(
                workers=[
                    ("worker_1", "deepseek/deepseek-chat"),
                    ("worker_2", "openrouter/google/gemini-2.5-flash"),
                ],
                aggregator_instructions="Merge both workers.",
            ),
            model,
            100,
            200,
        )
    if "Upstream outputs" in json.dumps(messages):
        return _resp(f"FINAL ANSWER from {model}", model, 60, 90)
    return _resp(f"worker output from {model}", model, 25, 35)


def _all_stages_fail(model, messages, response_format=None, **kw):  # type: ignore[no-untyped-def]
    """Dispatcher succeeds; every worker and the aggregator fail upstream."""
    if response_format is not None:
        return _resp(dispatch_json(), model, 10, 10)
    raise GatewayError("upstream exploded")


def _locked(config, **update):  # type: ignore[no-untyped-def]
    return config.model_copy(
        update={"defaults": config.defaults.model_copy(update=update)},
    )


def _client(config, responder) -> TestClient:  # type: ignore[no-untyped-def]
    return TestClient(create_app(config=config, engine=Engine(config, FakeGateway(responder))))


# --------------------------------------------------------------------------- #
# Engine: the discard is structured on the trace (success and failure runs)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_locked_aggregator_override_is_structured_on_the_trace(config) -> None:  # type: ignore[no-untyped-def]
    cfg = _locked(config, lock_aggregator=True)
    result = await Engine(cfg, FakeGateway(_success_responder)).deliberate(
        "task",
        "auto",
        overrides=DeliberationOverrides(aggregator_model=AGGREGATOR_OVERRIDE),
    )
    trace = result.trace
    assert [entry.field for entry in trace.discarded_overrides] == ["aggregator_model"]
    entry = trace.discarded_overrides[0]
    assert entry.requested == AGGREGATOR_OVERRIDE
    assert entry.locked_by == "lock_aggregator"
    assert "override discarded" in entry.reason
    # The locked model still served the merge — the override really was dropped.
    assert trace.aggregator is not None
    assert trace.aggregator.model == cfg.defaults.default_aggregator
    # The prose note keeps its pre-existing wording (CLI surfaces unchanged).
    assert trace.dispatch_note is not None
    assert "override discarded: aggregator_model=" in trace.dispatch_note


@pytest.mark.asyncio
async def test_unlocked_aggregator_override_applies_and_reports_nothing(config) -> None:  # type: ignore[no-untyped-def]
    assert config.defaults.lock_aggregator is False
    result = await Engine(config, FakeGateway(_success_responder)).deliberate(
        "task",
        "auto",
        overrides=DeliberationOverrides(aggregator_model=AGGREGATOR_OVERRIDE),
    )
    assert result.trace.discarded_overrides == []
    assert result.trace.aggregator is not None
    assert result.trace.aggregator.model == AGGREGATOR_OVERRIDE


@pytest.mark.asyncio
async def test_locked_dispatcher_override_is_structured(config) -> None:  # type: ignore[no-untyped-def]
    cfg = _locked(config, lock_dispatcher=True)
    result = await Engine(cfg, FakeGateway(_success_responder)).deliberate(
        "task",
        "auto",
        overrides=DeliberationOverrides(dispatcher_model="deepseek/deepseek-chat"),
    )
    assert [entry.field for entry in result.trace.discarded_overrides] == ["dispatcher_model"]
    assert result.trace.discarded_overrides[0].locked_by == "lock_dispatcher"


@pytest.mark.asyncio
async def test_both_locks_discard_in_one_run(config) -> None:  # type: ignore[no-untyped-def]
    """Two locked roles → two records, both surfaced (never just the first)."""
    cfg = _locked(config, lock_aggregator=True, lock_dispatcher=True)
    result = await Engine(cfg, FakeGateway(_success_responder)).deliberate(
        "task",
        "auto",
        overrides=DeliberationOverrides(
            aggregator_model=AGGREGATOR_OVERRIDE,
            dispatcher_model="deepseek/deepseek-chat",
        ),
    )
    fields = sorted(entry.field for entry in result.trace.discarded_overrides)
    assert fields == ["aggregator_model", "dispatcher_model"]


@pytest.mark.asyncio
async def test_a_per_stage_override_still_wins_under_the_lock(config) -> None:  # type: ignore[no-untyped-def]
    """Documented precedence: the locks absorb the GLOBAL override fields only.

    ``stage_models`` is applied AFTER the lock decision, so naming the
    aggregator stage explicitly still selects that model — the escape hatch a
    caller keeps while ``lock_aggregator: true`` (docs/CONFIG.md
    § "What a locked config absorbs").
    """
    cfg = _locked(config, lock_aggregator=True)
    result = await Engine(cfg, FakeGateway(_success_responder)).deliberate(
        "task",
        "auto",
        overrides=DeliberationOverrides(
            aggregator_model=AGGREGATOR_OVERRIDE,
            stage_models={"aggregator": "deepseek/deepseek-chat"},
        ),
    )
    assert [entry.field for entry in result.trace.discarded_overrides] == ["aggregator_model"]
    assert result.trace.aggregator is not None
    assert result.trace.aggregator.model == "deepseek/deepseek-chat"


# --------------------------------------------------------------------------- #
# REST: success body states the discard (criterion 1)
# --------------------------------------------------------------------------- #


def test_deliberate_success_body_states_the_discard(config) -> None:  # type: ignore[no-untyped-def]
    client = _client(_locked(config, lock_aggregator=True), _success_responder)
    r = client.post(
        "/v1/deliberate",
        json={"prompt": "hi", "formation": "auto", "aggregator_model": AGGREGATOR_OVERRIDE},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["answer"]
    assert [e["field"] for e in body["discarded_overrides"]] == ["aggregator_model"]
    assert body["discarded_overrides"][0]["requested"] == AGGREGATOR_OVERRIDE
    assert body["discarded_overrides"][0]["locked_by"] == "lock_aggregator"
    # Mirrored on the trace too, so trace-only consumers see it as well.
    assert body["trace"]["discarded_overrides"][0]["field"] == "aggregator_model"


def test_deliberate_success_body_is_clean_without_a_lock(config) -> None:  # type: ignore[no-untyped-def]
    client = _client(config, _success_responder)
    r = client.post(
        "/v1/deliberate",
        json={"prompt": "hi", "formation": "auto", "aggregator_model": AGGREGATOR_OVERRIDE},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "discarded_overrides" not in body  # absent, not null (exclude_none)
    assert body["trace"]["discarded_overrides"] == []
    assert body["trace"]["aggregator_model"] == AGGREGATOR_OVERRIDE


# --------------------------------------------------------------------------- #
# REST: the failure envelope carries the same information (criterion 2)
# --------------------------------------------------------------------------- #


def test_deliberate_502_states_the_discard(config) -> None:  # type: ignore[no-untyped-def]
    client = _client(_locked(config, lock_aggregator=True), _all_stages_fail)
    r = client.post(
        "/v1/deliberate",
        json={"prompt": "hi", "formation": "auto", "aggregator_model": AGGREGATOR_OVERRIDE},
    )
    assert r.status_code == 502, r.text
    err = r.json()["error"]
    assert [e["field"] for e in err["discarded_overrides"]] == ["aggregator_model"]
    assert err["discarded_overrides"][0]["locked_by"] == "lock_aggregator"
    # A client that only reads the message still learns the override was dropped:
    # the failure no longer names only the locked model.
    assert "lock_aggregator" in err["message"]
    assert AGGREGATOR_OVERRIDE in err["message"]
    assert "discarded" in err["message"]


def test_chat_502_states_the_discard(config) -> None:  # type: ignore[no-untyped-def]
    client = _client(_locked(config, lock_aggregator=True), _all_stages_fail)
    r = client.post(
        "/v1/chat/completions",
        json={
            "model": "auto",
            "messages": [{"role": "user", "content": "hi"}],
            "aggregator_model": AGGREGATOR_OVERRIDE,
        },
    )
    assert r.status_code == 502, r.text
    err = r.json()["error"]
    assert err["discarded_overrides"][0]["requested"] == AGGREGATOR_OVERRIDE
    assert "lock_aggregator" in err["message"]


def test_deliberate_502_without_a_lock_is_unchanged(config) -> None:  # type: ignore[no-untyped-def]
    """Negative control: no lock → no discard field, message keeps its old shape."""
    client = _client(config, _all_stages_fail)
    r = client.post(
        "/v1/deliberate",
        json={"prompt": "hi", "formation": "auto", "aggregator_model": AGGREGATOR_OVERRIDE},
    )
    assert r.status_code == 502, r.text
    err = r.json()["error"]
    assert "discarded_overrides" not in err
    assert "discarded by config locks" not in err["message"]
    assert "upstream exploded" in err["message"]


# --------------------------------------------------------------------------- #
# Chat success body (the compat twin of DeliberateResponse.discarded_overrides)
# --------------------------------------------------------------------------- #


def test_chat_success_body_states_the_discard(config) -> None:  # type: ignore[no-untyped-def]
    client = _client(_locked(config, lock_aggregator=True), _success_responder)
    r = client.post(
        "/v1/chat/completions",
        json={
            "model": "auto",
            "messages": [{"role": "user", "content": "hi"}],
            "aggregator_model": AGGREGATOR_OVERRIDE,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert [e["field"] for e in body["chimera_discarded_overrides"]] == ["aggregator_model"]
    assert body["chimera_discarded_overrides"][0]["requested"] == AGGREGATOR_OVERRIDE


def test_chat_success_body_is_clean_without_a_lock(config) -> None:  # type: ignore[no-untyped-def]
    client = _client(config, _success_responder)
    r = client.post(
        "/v1/chat/completions",
        json={
            "model": "auto",
            "messages": [{"role": "user", "content": "hi"}],
            "aggregator_model": AGGREGATOR_OVERRIDE,
        },
    )
    assert r.status_code == 200, r.text
    assert "chimera_discarded_overrides" not in r.json()


# --------------------------------------------------------------------------- #
# 503 arm: the pre-call refusals carry the discard too
# --------------------------------------------------------------------------- #


class _RefusingEngine:
    """Engine stand-in whose deliberate() raises one of the 503 exceptions."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def deliberate(self, *args: object, **kwargs: object) -> object:  # noqa: D401
        raise self._exc


def _quota_exc(cls=NoHealthyCandidateError) -> Exception:  # type: ignore[no-untyped-def]
    return cls(
        [{"provider": "deepseek", "model": "deepseek/deepseek-chat", "error_class": "quota"}],
        discarded_overrides=[
            {
                "field": "aggregator_model",
                "requested": AGGREGATOR_OVERRIDE,
                "locked_by": "lock_aggregator",
                "reason": "override discarded: aggregator_model=... ignored (lock_aggregator=true)",
            }
        ],
    )


@pytest.mark.parametrize(
    ("cls", "error_type"),
    [(NoHealthyCandidateError, "no_healthy_candidate"), (LaneUnreachableError, "lane_unreachable")],
)
def test_503_envelope_states_the_discard(config, cls, error_type) -> None:  # type: ignore[no-untyped-def]
    app = create_app(config=config, engine=_RefusingEngine(_quota_exc(cls)))
    r = TestClient(app).post("/v1/deliberate", json={"prompt": "hi", "formation": "auto"})
    assert r.status_code == 503, r.text
    err = r.json()["error"]
    assert err["type"] == error_type
    assert err["discarded_overrides"][0]["locked_by"] == "lock_aggregator"
    assert "lock_aggregator" in err["message"]


def test_exception_clause_is_empty_without_discards() -> None:
    """The happy path's message stays byte-identical (no stray clause)."""
    assert override_discard_clause(None) == ""
    assert override_discard_clause([]) == ""
    exc = NoHealthyCandidateError(
        [{"provider": "deepseek", "model": "deepseek/deepseek-chat", "error_class": "quota"}]
    )
    assert "discarded by config locks" not in exc.message
    assert exc.discarded_overrides == []
