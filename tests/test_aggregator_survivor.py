"""A successful worker can serve as the final merge fallback."""

import json

import pytest

from chimera.engine import Engine
from chimera.gateway import GatewayError
from tests.conftest import FakeGateway, resp
from tests.test_aggregator_fallback_chain import (
    DEAD_AGGREGATOR,
    HEALTHY_FALLBACK,
    _cfg,
    _invoke,
    _run,
    _stub_gateway,
    _write_config,
)

SURVIVOR = "deepseek/deepseek-v4-flash"


def test_cli_survivor_serves_after_quota_failures(tmp_path, monkeypatch):
    config = _write_config(tmp_path, fallbacks=[HEALTHY_FALLBACK], worker_model=SURVIVOR)
    calls = []

    def respond(model, messages, **kwargs):
        calls.append(model)
        if model == SURVIVOR:
            return resp("WORKER" if calls.count(model) == 1 else "MERGED", model)
        raise GatewayError("Insufficient Balance")

    _stub_gateway(monkeypatch, respond)
    result = _invoke(config, "--json", "-f", "code-review", "test")
    assert result.exit_code == 0, (result.output, result.exception)
    payload = json.loads(result.stdout)
    assert payload["answer"] == "MERGED"
    assert payload["trace"]["aggregator_model"] == SURVIVOR
    assert any(
        x["model"] == SURVIVOR and x["status"] == "served" and x["source"] == "this_run_survivor"
        for x in payload["trace"]["aggregator_fallbacks"]
    )
    assert DEAD_AGGREGATOR in calls and HEALTHY_FALLBACK in calls


@pytest.mark.asyncio
async def test_explicit_fallback_precedes_survivor():
    calls = []

    def respond(model, messages, **kwargs):
        calls.append(model)
        if model == DEAD_AGGREGATOR:
            raise GatewayError("Insufficient Balance")
        return resp("OK", model)

    from tests.test_aggregator_fallback_chain import _dag

    dag = _dag()
    dag["stages"][0]["model"] = SURVIVOR
    result = await _run(Engine(_cfg(fallbacks=[HEALTHY_FALLBACK]), FakeGateway(respond)), dag)
    assert result.trace.aggregator_model == HEALTHY_FALLBACK
    assert calls.count(SURVIVOR) == 1


@pytest.mark.asyncio
async def test_survivor_quota_death_mid_run_is_bounded_and_preserves_workers(monkeypatch, tmp_path):
    """A survivor whose provider dies BETWEEN its worker stage and the merge is
    still attempted (credential check is skipped, quota is not), records one
    bounded failed entry, and the run falls through to workers_preserved."""
    import chimera.blocked_models as blocked_models

    # Isolate BOTH layers: the session-shared registry object AND the persisted
    # default state file (which carries real quota blocks from live runs on
    # this deployment). Fresh registry + tmp state file => dispatch sees a
    # clean slate; monkeypatch restores the session registry afterwards.
    monkeypatch.setattr(
        blocked_models,
        "shared_registry",
        blocked_models.ModelBlockRegistry(state_path=tmp_path / "blocked-state.json"),
    )
    calls = []

    def respond(model, messages, **kwargs):
        calls.append(model)
        if model == SURVIVOR and calls.count(SURVIVOR) == 1:
            return resp("OK", model)  # served its worker stage...
        raise GatewayError("Insufficient Balance")  # ...then quota died mid-run

    from tests.test_aggregator_fallback_chain import _dag

    dag = _dag()
    dag["stages"][0]["model"] = SURVIVOR
    result = await _run(Engine(_cfg(fallbacks=[]), FakeGateway(respond)), dag)

    assert calls.count(SURVIVOR) == 2  # worker stage + exactly one bounded merge attempt
    assert result.answer_usable is False
    survivor_entries = [x for x in result.trace.aggregator_fallbacks if x.model == SURVIVOR]
    assert survivor_entries and all(x.status != "served" for x in survivor_entries)
    assert any(x.status == "failed" for x in survivor_entries)


@pytest.mark.asyncio
async def test_survivor_has_reserved_call_after_budget_is_exhausted(monkeypatch):
    monkeypatch.setattr("chimera.engine.MAX_AGGREGATOR_FALLBACK_ATTEMPTS", 0)

    def respond(model, messages, **kwargs):
        if model == DEAD_AGGREGATOR:
            raise GatewayError("Insufficient Balance")
        return resp("OK", model)

    from tests.test_aggregator_fallback_chain import _dag

    dag = _dag()
    dag["stages"][0]["model"] = SURVIVOR
    result = await _run(Engine(_cfg(fallbacks=[HEALTHY_FALLBACK]), FakeGateway(respond)), dag)
    assert result.trace.aggregator_model == SURVIVOR
    assert any(
        entry.source == "this_run_survivor" and entry.status == "served"
        for entry in result.trace.aggregator_fallbacks
    )
