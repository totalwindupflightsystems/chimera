"""DF-CHIMERA-V2-120: the merge fallback chain (a dead aggregator must not discard work).

Measured board finding: 3 of 4 live deliberations ended rc=2 after 83-187 s with
NO answer while all three workers had already succeeded and been billed — the
single configured aggregator model failed with ``Insufficient Balance`` and there
was nothing else to try.

The contract pinned here, in both directions:

* aggregator-dead + fallback-healthy → exit 0, a real answer, ``trace.aggregator_model``
  naming the model that served the merge, and a per-entry skip reason in
  ``trace.aggregator_fallbacks``;
* nothing can serve the merge but a worker succeeded → exit non-zero AND the paid
  worker output preserved on the ``--json`` payload (``worker_outputs``);
* ``lock_aggregator: true`` does not disable the chain (the lock forbids ad-hoc
  overrides, not resilience);
* a lane that cannot reach ANY provider fails fast (well under 15 s) with the
  provider + the env var to set on stderr, instead of a retry tail.

Everything runs against a scriptable in-process gateway: no provider call, no
credential, no network.
"""

from __future__ import annotations

import copy
import json
import time
from pathlib import Path
from typing import Any

import pytest
import yaml

pytest.importorskip("click")
from click.testing import CliRunner  # noqa: E402

from chimera.cli.main import main  # noqa: E402
from chimera.config import ChimeraConfig, resolve_aggregator_fallbacks  # noqa: E402
from chimera.engine import (  # noqa: E402
    ANSWER_DEGRADED_SUBSTITUTED,
    ANSWER_DEGRADED_WORKERS_PRESERVED,
    Engine,
)
from chimera.exceptions import LaneUnreachableError  # noqa: E402
from chimera.gateway import GatewayError  # noqa: E402
from tests.conftest import CONFIG_DICT, FakeGateway, resp  # noqa: E402

#: Catalog ids from the compact test catalog (``tests.conftest.CONFIG_DICT``).
WORKER = "deepseek/deepseek-chat"  # provider openrouter
DEAD_AGGREGATOR = "zai-coding-plan/glm-5.2"  # provider zai — the configured aggregator
HEALTHY_FALLBACK = "openrouter/qwen/qwen3-coder"  # provider openrouter
OTHER = "openrouter/google/gemini-2.5-flash"

#: ``Insufficient Balance`` verbatim — the live error class the board row measured.
QUOTA_ERROR = "Insufficient Balance"
GENERIC_ERROR = "provider endpoint unreachable (simulated outage)"

_DAG: dict[str, Any] = {
    "stages": [
        {"id": "worker_1", "kind": "worker", "model": WORKER, "depends_on": []},
        {"id": "merge", "kind": "aggregator", "model": DEAD_AGGREGATOR, "depends_on": ["worker_1"]},
    ],
    "edges": [["worker_1", "merge"]],
}


def _cfg(*, fallbacks: list[str] | None = None, **defaults_extra: Any) -> ChimeraConfig:
    """A hermetic config: no discovery, deterministic fake credentials per provider.

    Fake keys are deliberate — they make ``credentials_configured`` true (so the
    fallback skip logic runs its real branches) and keep the test independent of
    whatever real keys happen to sit in the ambient environment.
    """
    doc = copy.deepcopy(CONFIG_DICT)
    doc["provider_discovery"] = False
    doc["api_keys"] = {
        "openrouter": "sk-test-not-a-real-key",
        "zai": "test-not-a-real-key",
        "deepseek": "test-not-a-real-key",
    }
    doc["defaults"].update(defaults_extra)
    if fallbacks is not None:
        doc["defaults"]["aggregator_fallbacks"] = fallbacks
    return ChimeraConfig.model_validate(doc)


def _dag(aggregator: str = DEAD_AGGREGATOR) -> dict[str, Any]:
    dag = copy.deepcopy(_DAG)
    dag["stages"][1]["model"] = aggregator
    return dag


async def _run(engine: Engine, dag: dict[str, Any] | None = None) -> Any:
    return await engine.deliberate(
        "Explain the CAP theorem briefly.",
        "custom",
        dag=dag or _dag(),
        allow_custom_dag=True,
    )


def _responder(*, dead: tuple[str, ...], error: str = QUOTA_ERROR, worker_text: str = "WORKER OUTPUT") -> Any:
    """Fail every model in *dead*, answer every other model normally."""

    def _respond(model: str, messages: list[dict[str, str]], **kw: Any) -> Any:
        if model in dead:
            raise GatewayError(error)
        if model == WORKER:
            return resp(worker_text, model, tok_in=20, tok_out=30)
        return resp(f"MERGED BY {model}", model, tok_in=20, tok_out=30)

    return _respond


# --------------------------------------------------------------------------- #
# Engine: the fallback chain serves the merge
# --------------------------------------------------------------------------- #


def test_config_chain_semantics_defaults_override_and_disable() -> None:
    """The chain resolver: formation override REPLACES, empty list DISABLES, unset inherits."""
    inherited = _cfg(fallbacks=[HEALTHY_FALLBACK])
    assert resolve_aggregator_fallbacks(inherited, "custom") == [HEALTHY_FALLBACK]
    # Unknown/unset formation still inherits the defaults list.
    assert resolve_aggregator_fallbacks(inherited, None) == [HEALTHY_FALLBACK]

    doc = copy.deepcopy(CONFIG_DICT)
    doc["defaults"]["aggregator_fallbacks"] = [HEALTHY_FALLBACK]
    doc["formations"] = {
        "own-chain": {"workers": 1, "aggregator": "default", "aggregator_fallbacks": [OTHER]},
        "no-chain": {"workers": 1, "aggregator": "default", "aggregator_fallbacks": []},
    }
    both = ChimeraConfig.model_validate(doc)
    assert resolve_aggregator_fallbacks(both, "own-chain") == [OTHER], "formation list must win"
    assert resolve_aggregator_fallbacks(both, "no-chain") == [], "explicit empty list must disable"
    assert resolve_aggregator_fallbacks(both, "auto") == [HEALTHY_FALLBACK], "unset must inherit"

    # The ``default`` alias resolves to default_aggregator, and duplicates collapse.
    aliased = _cfg(fallbacks=["default", DEAD_AGGREGATOR, HEALTHY_FALLBACK])
    chain = resolve_aggregator_fallbacks(aliased, "custom")
    assert chain == [DEAD_AGGREGATOR, HEALTHY_FALLBACK]


@pytest.mark.asyncio
async def test_fallback_serves_the_merge_and_is_traced() -> None:
    """Criterion 1: a dead aggregator is replaced by the next chain entry, exit-usable."""
    engine = Engine(
        _cfg(fallbacks=["not/a-catalog-model", HEALTHY_FALLBACK]),
        FakeGateway(_responder(dead=(DEAD_AGGREGATOR,))),
    )
    result = await _run(engine)

    assert result.answer == f"MERGED BY {HEALTHY_FALLBACK}"
    assert result.trace.aggregator_model == HEALTHY_FALLBACK, "trace must name the model that served"
    assert result.trace.aggregator is not None and result.trace.aggregator.model == HEALTHY_FALLBACK
    assert result.answer_degraded is True
    assert result.answer_degraded_reason == ANSWER_DEGRADED_SUBSTITUTED
    assert result.answer_usable is True

    statuses = [(entry.model, entry.status) for entry in result.trace.aggregator_fallbacks]
    assert ("not/a-catalog-model", "skipped") in statuses
    unknown = next(e for e in result.trace.aggregator_fallbacks if e.model == "not/a-catalog-model")
    assert unknown.reason and "unknown model" in unknown.reason
    assert any(
        entry.status == "served" and entry.model == HEALTHY_FALLBACK
        for entry in result.trace.aggregator_fallbacks
    )
    # A skipped entry never costs a provider call.
    called_models = [call[0] for call in engine.gateway.calls]
    assert HEALTHY_FALLBACK in called_models
    assert "not/a-catalog-model" not in called_models


@pytest.mark.asyncio
async def test_quota_class_failure_demotes_the_dead_account() -> None:
    """A quota failure DEMOTES the dead account's entries instead of re-calling them.

    ``default`` here resolves to the failed aggregator's own provider, so the
    chain lists two zai-free options in this order: the dead model, then the
    healthy one. The quota class says the whole ACCOUNT is empty, so the
    different-provider entry must be tried FIRST — and the dead account must not
    be called a second time for nothing.
    """
    gateway = FakeGateway(_responder(dead=(DEAD_AGGREGATOR,)))
    engine = Engine(_cfg(fallbacks=["default", HEALTHY_FALLBACK]), gateway)
    result = await _run(engine)

    assert result.trace.aggregator_model == HEALTHY_FALLBACK
    assert result.answer_usable is True
    called = [call[0] for call in gateway.calls]
    assert called.count(DEAD_AGGREGATOR) == 1, called
    assert called.index(HEALTHY_FALLBACK) > called.index(DEAD_AGGREGATOR)


@pytest.mark.asyncio
async def test_failed_aggregator_entry_is_skipped_with_a_recorded_reason() -> None:
    """Every entry the engine passes over is traced with WHY, including the dead model."""
    engine = Engine(
        _cfg(fallbacks=["default", HEALTHY_FALLBACK]),
        # Not a quota-class error: no account-wide demotion, so the chain is
        # walked in its declared order.
        FakeGateway(_responder(dead=(DEAD_AGGREGATOR,), error=GENERIC_ERROR)),
    )
    result = await _run(engine)

    assert result.trace.aggregator_model == HEALTHY_FALLBACK
    assert result.answer_usable is True
    skipped = {
        entry.model: entry.reason for entry in result.trace.aggregator_fallbacks if entry.status == "skipped"
    }
    assert any("itself" in (reason or "") for reason in skipped.values()), skipped


@pytest.mark.asyncio
async def test_lock_aggregator_never_disables_the_chain() -> None:
    """Criterion 3: the lock forbids ad-hoc overrides, not resilience."""
    config = _cfg(fallbacks=[HEALTHY_FALLBACK], lock_aggregator=True)
    assert config.defaults.lock_aggregator is True
    engine = Engine(config, FakeGateway(_responder(dead=(DEAD_AGGREGATOR,))))
    result = await _run(engine)

    assert result.answer == f"MERGED BY {HEALTHY_FALLBACK}"
    assert result.trace.aggregator_model == HEALTHY_FALLBACK
    assert result.answer_usable is True


@pytest.mark.asyncio
async def test_unservable_merge_preserves_worker_outputs() -> None:
    """Criterion 2: no usable answer, but the paid worker output is NOT discarded.

    The worker here is on the ``deepseek`` provider, which this config has no
    credential for — that keeps every merge-side candidate (zai/openrouter)
    genuinely dead, so nothing can serve the merge while the worker's own call
    still succeeds.
    """
    worker_model = "deepseek/deepseek-v4-flash"

    def _respond(model: str, messages: list[dict[str, str]], **kw: Any) -> Any:
        if model == worker_model:
            return resp("WORKER OUTPUT", model, tok_in=20, tok_out=30)
        # Every merge candidate dies: the chain, the implicit tail and the
        # schema-free retry all fail, so there is no answer to serve.
        raise GatewayError(GENERIC_ERROR)

    doc = copy.deepcopy(CONFIG_DICT)
    doc["provider_discovery"] = False
    doc["api_keys"] = {"openrouter": "sk-test-not-a-real-key", "zai": "test-not-a-real-key"}
    doc["defaults"]["aggregator_fallbacks"] = [HEALTHY_FALLBACK]
    dag = _dag()
    dag["stages"][0]["model"] = worker_model
    engine = Engine(ChimeraConfig.model_validate(doc), FakeGateway(_respond))
    result = await _run(engine, dag=dag)

    assert result.answer_usable is False
    assert result.answer_degraded is True
    assert result.answer_degraded_reason == ANSWER_DEGRADED_WORKERS_PRESERVED
    assert result.worker_outputs == {"worker_1": "WORKER OUTPUT"}
    assert result.trace.aggregator_model is None, "no model served this merge"
    assert result.trace.aggregator_fallbacks, "the attempted chain must be visible in the trace"


@pytest.mark.asyncio
async def test_unreachable_lane_fails_fast_with_remedy() -> None:
    """Criterion 4: nothing can be called → fail in well under 15 s naming the remedy."""
    doc = copy.deepcopy(CONFIG_DICT)
    doc["provider_discovery"] = False
    # Only openrouter resolves a credential, but this DAG needs deepseek + zai.
    doc["api_keys"] = {"openrouter": "sk-test-not-a-real-key"}
    config = ChimeraConfig.model_validate(doc)
    dag = _dag()
    dag["stages"][0]["model"] = "deepseek/deepseek-v4-flash"

    gateway = FakeGateway(_responder(dead=()))
    engine = Engine(config, gateway)

    started = time.monotonic()
    with pytest.raises(LaneUnreachableError) as excinfo:
        await _run(engine, dag=dag)
    elapsed = time.monotonic() - started

    assert elapsed < 15.0, f"fast-fail budget blown: {elapsed:.2f}s"
    assert gateway.calls == [], "a provably unreachable lane must make no provider call"
    message = str(excinfo.value)
    assert "ZAI_API_KEY" in message and "DEEPSEEK_API_KEY" in message, message
    assert "zai" in message and "deepseek" in message, message
    attempts = excinfo.value.attempts
    assert {str(a.get("error_class")) for a in attempts} == {"credential"}


# --------------------------------------------------------------------------- #
# CLI: exit codes and the --json payload
# --------------------------------------------------------------------------- #


def _write_config(
    tmp_path: Path,
    *,
    fallbacks: list[str] | None = None,
    lock: bool = True,
    worker_model: str = WORKER,
    api_keys: dict[str, str] | None = None,
) -> Path:
    doc = copy.deepcopy(CONFIG_DICT)
    doc["provider_discovery"] = False
    doc["api_keys"] = api_keys or {
        "openrouter": "sk-test-not-a-real-key",
        "zai": "test-not-a-real-key",
        "deepseek": "test-not-a-real-key",
    }
    if fallbacks is not None:
        doc["defaults"]["aggregator_fallbacks"] = fallbacks
    doc["defaults"]["lock_aggregator"] = lock
    dag = _dag()
    dag["stages"][0]["model"] = worker_model
    doc["formations"] = {"code-review": {"dag": dag}}
    path = tmp_path / "chimera.yaml"
    path.write_text(yaml.safe_dump(doc), encoding="utf-8")
    return path


def _stub_gateway(monkeypatch: pytest.MonkeyPatch, responder: Any) -> None:
    monkeypatch.setattr("chimera.cli.main.LiteLLMGateway", lambda *a, **k: FakeGateway(responder))


def _invoke(config: Path, *args: str) -> Any:
    return CliRunner().invoke(main, ["-c", str(config), *args])


def test_cli_exits_zero_when_a_fallback_served_the_merge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Gate arm A: aggregator-dead + fallback-healthy → exit 0 with a real answer."""
    config = _write_config(tmp_path, fallbacks=["not/a-catalog-model", HEALTHY_FALLBACK])
    _stub_gateway(monkeypatch, _responder(dead=(DEAD_AGGREGATOR,)))

    result = _invoke(config, "--quiet", "-f", "code-review", "explain CAP briefly")

    assert result.exit_code == 0, (result.stdout, result.stderr, result.exception)
    assert result.stdout.strip() == f"MERGED BY {HEALTHY_FALLBACK}"
    assert HEALTHY_FALLBACK in result.stderr, "the substitution must be announced on stderr"
    assert "configured aggregator failed" in result.stderr
    assert "unknown model" in result.stderr, "skip reasons must reach the operator"


def test_cli_json_preserves_worker_outputs_when_no_fallback_can_serve(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Gate arm B: nothing serves the merge → non-zero, but the paid work is in --json.

    The worker runs on the ``deepseek`` provider (no credential here), so every
    merge-side candidate is genuinely dead while the worker's own call succeeds
    — the exact live shape: paid workers, no merge.
    """
    worker_model = "deepseek/deepseek-v4-flash"
    config = _write_config(
        tmp_path,
        fallbacks=[HEALTHY_FALLBACK],
        worker_model=worker_model,
        api_keys={"openrouter": "sk-test-not-a-real-key", "zai": "test-not-a-real-key"},
    )

    def _respond(model: str, messages: list[dict[str, str]], **kw: Any) -> Any:
        if model == worker_model:
            return resp("WORKER OUTPUT", model, tok_in=20, tok_out=30)
        raise GatewayError(GENERIC_ERROR)

    _stub_gateway(monkeypatch, _respond)

    result = _invoke(config, "--json", "-f", "code-review", "explain CAP briefly")

    assert result.exit_code == 2, (result.stdout, result.stderr, result.exception)
    payload = json.loads(result.stdout)
    assert payload["answer_degraded"] is True
    assert payload["answer_degraded_reason"] == ANSWER_DEGRADED_WORKERS_PRESERVED
    assert payload["worker_outputs"] == {"worker_1": "WORKER OUTPUT"}
    assert payload["aggregator_model"] is None
    assert payload["trace"]["aggregator_fallbacks"], "the chain must be traced"
    assert "worker output(s) preserved" in result.stderr


def test_cli_json_reports_the_substituted_aggregator(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The --json payload names the serving model and the reason, and still exits 0."""
    config = _write_config(tmp_path, fallbacks=[HEALTHY_FALLBACK])
    _stub_gateway(monkeypatch, _responder(dead=(DEAD_AGGREGATOR,)))

    result = _invoke(config, "--json", "-f", "code-review", "explain CAP briefly")

    assert result.exit_code == 0, (result.stdout, result.stderr, result.exception)
    payload = json.loads(result.stdout)
    assert payload["answer"] == f"MERGED BY {HEALTHY_FALLBACK}"
    assert payload["answer_degraded_reason"] == ANSWER_DEGRADED_SUBSTITUTED
    assert payload["aggregator_model"] == HEALTHY_FALLBACK
    assert payload["worker_outputs"] == {}
    assert payload["trace"]["aggregator_model"] == HEALTHY_FALLBACK


# --------------------------------------------------------------------------- #
# REST: the same two outcomes on /v1/deliberate
# --------------------------------------------------------------------------- #


def test_rest_answers_200_when_a_fallback_served_the_merge() -> None:
    """A fallback-served merge is USABLE: no 502, even though ``answer_degraded`` is set."""
    from fastapi.testclient import TestClient

    from chimera.api.server import create_app

    doc = copy.deepcopy(CONFIG_DICT)
    doc["provider_discovery"] = False
    doc["api_keys"] = {
        "openrouter": "sk-test-not-a-real-key",
        "zai": "test-not-a-real-key",
        "deepseek": "test-not-a-real-key",
    }
    doc["defaults"]["aggregator_fallbacks"] = [HEALTHY_FALLBACK]
    doc["defaults"]["lock_aggregator"] = True
    doc["formations"] = {"code-review": {"dag": copy.deepcopy(_dag())}}
    config = ChimeraConfig.model_validate(doc)
    engine = Engine(config, FakeGateway(_responder(dead=(DEAD_AGGREGATOR,))))
    client = TestClient(create_app(config=config, engine=engine))

    response = client.post(
        "/v1/deliberate", json={"prompt": "explain CAP briefly", "formation": "code-review"}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["answer"] == f"MERGED BY {HEALTHY_FALLBACK}"
    assert body["trace"]["aggregator_model"] == HEALTHY_FALLBACK


def test_rest_502_carries_the_preserved_worker_outputs() -> None:
    """No merge and no fallback: still 502, but the paid worker text rides the error body."""
    from fastapi.testclient import TestClient

    from chimera.api.server import create_app

    worker_model = "deepseek/deepseek-v4-flash"
    doc = copy.deepcopy(CONFIG_DICT)
    doc["provider_discovery"] = False
    doc["api_keys"] = {"openrouter": "sk-test-not-a-real-key", "zai": "test-not-a-real-key"}
    doc["defaults"]["aggregator_fallbacks"] = [HEALTHY_FALLBACK]
    dag = _dag()
    dag["stages"][0]["model"] = worker_model
    doc["formations"] = {"code-review": {"dag": dag}}
    config = ChimeraConfig.model_validate(doc)

    def _respond(model: str, messages: list[dict[str, str]], **kw: Any) -> Any:
        if model == worker_model:
            return resp("WORKER OUTPUT", model, tok_in=20, tok_out=30)
        raise GatewayError(GENERIC_ERROR)

    engine = Engine(config, FakeGateway(_respond))
    client = TestClient(create_app(config=config, engine=engine))

    response = client.post(
        "/v1/deliberate", json={"prompt": "explain CAP briefly", "formation": "code-review"}
    )

    assert response.status_code == 502, response.text
    error = response.json()["error"]
    assert error["worker_outputs"] == {"worker_1": "WORKER OUTPUT"}
    assert error["answer_degraded_reason"] == "workers_preserved"


def test_rest_503_names_an_unreachable_lane() -> None:
    """Nothing reachable: HTTP 503 with the credential class, and no provider call."""
    from fastapi.testclient import TestClient

    from chimera.api.server import create_app

    doc = copy.deepcopy(CONFIG_DICT)
    doc["provider_discovery"] = False
    doc["api_keys"] = {"openrouter": "sk-test-not-a-real-key"}
    dag = _dag()
    dag["stages"][0]["model"] = "deepseek/deepseek-v4-flash"
    doc["formations"] = {"code-review": {"dag": dag}}
    config = ChimeraConfig.model_validate(doc)
    gateway = FakeGateway(_responder(dead=()))
    engine = Engine(config, gateway)
    client = TestClient(create_app(config=config, engine=engine))

    started = time.monotonic()
    response = client.post(
        "/v1/deliberate", json={"prompt": "explain CAP briefly", "formation": "code-review"}
    )
    elapsed = time.monotonic() - started

    assert response.status_code == 503, response.text
    assert elapsed < 15.0
    error = response.json()["error"]
    assert error["type"] == "lane_unreachable"
    assert {a["error_class"] for a in error["attempts"]} == {"credential"}
    assert "ZAI_API_KEY" in error["message"] and "DEEPSEEK_API_KEY" in error["message"]
    assert gateway.calls == []


@pytest.mark.asyncio
async def test_mcp_reports_a_substituted_merge_as_success() -> None:
    """MCP: ``isError`` stays false when a fallback served the merge, and says so."""
    from mcp.shared.memory import create_connected_server_and_client_session

    from chimera.mcp.server import build_server

    config = _cfg(fallbacks=[HEALTHY_FALLBACK])
    engine = Engine(config, FakeGateway(_responder(dead=(DEAD_AGGREGATOR,))))
    server = build_server(config=config, engine=engine)

    async with create_connected_server_and_client_session(server._mcp_server) as client:
        result = await client.call_tool(
            "chimera_deliberate",
            {"prompt": "explain CAP briefly", "formation": "auto"},
        )

    assert result.isError is False, result.content
    payload = json.loads(result.content[0].text)
    assert payload["answer"] == f"MERGED BY {HEALTHY_FALLBACK}"
    assert payload["answer_degraded"] is True
    assert payload["answer_degraded_reason"] == ANSWER_DEGRADED_SUBSTITUTED
    assert payload["aggregator_model"] == HEALTHY_FALLBACK
