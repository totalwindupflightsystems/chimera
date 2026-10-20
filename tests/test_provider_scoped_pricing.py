"""Provider-scoped price resolution — DF-CHIMERA-V2-93.

The trace cost a user reads used to be provider-agnostic: ``MODEL_ID_MAP``
collapsed every registry block's same-named row onto one key and the LAST block
to write it won.  A deliberation routed to ``api.deepseek.com`` (catalog entry
``deepseek/deepseek-v4-flash``, ``provider: deepseek``) was therefore billed at
a foreign gateway's rate — clinepass 0.44/1.32 per M on the task-router path,
routing-run 0.112/0.224 on the models.dev path — instead of DeepSeek's own
0.15/0.60 per M.

The fix keys prices by ``(provider, model_id)`` where the provider is the block
that PUBLISHED the row, and resolves a catalog entry through its own
``provider`` label first (``resolve_model_pricing``).  These tests pin the
resolution on BOTH registry paths, the end-to-end trace cost, and the recorded
provenance.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import yaml

from chimera.config import load_config
from chimera.engine import Engine
from chimera.provider_discovery import (
    UNATTRIBUTED_PRICE_PROVIDER,
    discover_providers,
    resolve_model_pricing,
)
from tests.conftest import FakeGateway, dispatch_json, make_dispatcher_responder

TARGET = "deepseek/deepseek-v4-flash"
#: DeepSeek's own published rates for the flash SKU, per million tokens.
DEEPSEEK_IN_PER_M, DEEPSEEK_OUT_PER_M = 0.15, 0.60
#: A foreign gateway serving the same SKU under the same bare model id.
CLINEPASS_IN_PER_M, CLINEPASS_OUT_PER_M = 0.44, 1.32


@pytest.fixture(autouse=True)
def _isolate_registries(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Keep every case out of the developer's live registry and models.dev cache.

    An ambient task-router table or a fresh ``~/.chimera/models-dev-cache.json``
    would make these assertions depend on whatever the box last scanned.
    """
    monkeypatch.setattr(
        "chimera.provider_discovery.CACHE_PATH",
        str(tmp_path / "models-dev-cache.json"),
    )
    monkeypatch.setenv("CHIMERA_TASK_ROUTER_MODELS_PATH", str(tmp_path / "absent.jsonl"))


def _row(provider: str, model: str, input_per_m: float, output_per_m: float) -> dict[str, Any]:
    """One live task-router registry row (the JSONL wire shape)."""
    return {
        "provider": provider,
        "model": model,
        "public_in_per_m": input_per_m,
        "public_out_per_m": output_per_m,
        "valid_from": "2026-06-01",
        "valid_to": None,
        "archive": False,
        "disabled": None,
    }


def _write_table(path: Path, rows: list[dict[str, Any]]) -> Path:
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    return path


def _router_table(tmp_path: Path) -> Path:
    """The reported shape: the lab's own row, then a foreign gateway's row LAST.

    ``deepseek`` publishes the SKU under its live id ``deepseek-flash`` (same
    model, same 0.15/0.60); ``clinepass`` publishes a bare ``deepseek-v4-flash``
    row at 0.44/1.32 and, before the fix, overwrote the lab's price on the
    provider-agnostic key.
    """
    return _write_table(
        tmp_path / "models.jsonl",
        [
            _row("deepseek", "deepseek-flash", DEEPSEEK_IN_PER_M, DEEPSEEK_OUT_PER_M),
            _row("deepseek", "deepseek-v4-pro", 0.66, 1.98),
            _row("clinepass", "deepseek-v4-flash", CLINEPASS_IN_PER_M, CLINEPASS_OUT_PER_M),
        ],
    )


def _catalog_doc(**entry_overrides: Any) -> dict[str, Any]:
    """A minimal catalog with ONE entry, priced through discovery."""
    entry: dict[str, Any] = {
        "categories": {"code": 88.0},
        "cost_tier": "budget",
        "provider": "deepseek",
    }
    entry.update(entry_overrides)
    return {
        "api_keys": {"deepseek": "test-only"},
        "providers": {"deepseek": {"base_url": "https://api.deepseek.com/v1"}},
        "models": {TARGET: entry},
        "defaults": {"dispatcher": TARGET, "default_worker": TARGET, "default_aggregator": TARGET},
        "formations": {"auto": {"mode": "auto"}},
        "provider_discovery": True,
    }


def _write_catalog(tmp_path: Path, doc: dict[str, Any]) -> Path:
    path = tmp_path / "chimera.yaml"
    path.write_text(yaml.safe_dump(doc), encoding="utf-8")
    return path


# ═══════════════════════════════════════════════════════════════════════════
#  Unit: the scan keys rows by the provider that publishes them
# ═══════════════════════════════════════════════════════════════════════════


def test_scan_scopes_each_row_to_its_publishing_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    table = _router_table(tmp_path)
    monkeypatch.setenv("CHIMERA_TASK_ROUTER_MODELS_PATH", str(table))

    _providers, pricing = discover_providers(api_keys={"deepseek": "test-only"})

    # The lab's own row reaches the catalog id through MODEL_ID_MAP (its live
    # registry id is ``deepseek-flash``) and stays under the ``deepseek`` key.
    lab_row = pricing[("deepseek", TARGET)]
    assert lab_row["input"] == pytest.approx(DEEPSEEK_IN_PER_M / 1000)
    assert lab_row["output"] == pytest.approx(DEEPSEEK_OUT_PER_M / 1000)
    assert lab_row["source_provider"] == "deepseek"
    assert lab_row["source_model"] == "deepseek-flash"
    assert lab_row["registry"] == "task-router"

    # The foreign gateway's row is kept — under ITS OWN key, where it cannot
    # price a ``deepseek`` entry, and with the lab it was attributed to recorded.
    gateway_row = pricing[("clinepass", TARGET)]
    assert gateway_row["input"] == pytest.approx(CLINEPASS_IN_PER_M / 1000)
    assert gateway_row["source_provider"] == "clinepass"
    assert gateway_row["source_model"] == "deepseek-v4-flash"
    assert gateway_row["attributed_lab"] == "deepseek"

    # The provider-agnostic view is unchanged (last writer wins) — it exists
    # only as the coverage fallback, never as the authority.
    fallback_row = pricing[(UNATTRIBUTED_PRICE_PROVIDER, TARGET)]
    assert fallback_row["source_provider"] == "clinepass"
    assert fallback_row["input"] == pytest.approx(CLINEPASS_IN_PER_M / 1000)


def test_resolve_prefers_the_entry_provider_and_names_the_fallback_tier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    table = _router_table(tmp_path)
    monkeypatch.setenv("CHIMERA_TASK_ROUTER_MODELS_PATH", str(table))
    _providers, pricing = discover_providers(api_keys={"deepseek": "test-only"})

    row, tier = resolve_model_pricing(pricing, "deepseek", TARGET)
    assert tier == "provider"
    assert row is not None and row["input"] == pytest.approx(DEEPSEEK_IN_PER_M / 1000)

    row, tier = resolve_model_pricing(pricing, "clinepass", TARGET)
    assert tier == "provider"
    assert row is not None and row["input"] == pytest.approx(CLINEPASS_IN_PER_M / 1000)

    # A provider with no row for the id falls back — recorded as unattributed,
    # with the block it came from named (never a silent last-writer win).
    row, tier = resolve_model_pricing(pricing, "zai-glm", TARGET)
    assert tier == "unattributed"
    assert row is not None and row["source_provider"] == "clinepass"

    row, tier = resolve_model_pricing(pricing, "deepseek", "deepseek/no-such-model")
    assert (row, tier) == (None, "none")


# ═══════════════════════════════════════════════════════════════════════════
#  Catalog: the entry's provider label resolves the price
# ═══════════════════════════════════════════════════════════════════════════


def test_config_prices_entry_from_its_own_provider_not_the_last_writer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC 1+3 on the task-router path: the request goes to api.deepseek.com."""
    table = _router_table(tmp_path)
    monkeypatch.setenv("CHIMERA_TASK_ROUTER_MODELS_PATH", str(table))
    path = _write_catalog(tmp_path, _catalog_doc())

    cfg = load_config(path)

    entry = cfg.models[TARGET]
    assert entry.provider == "deepseek"
    assert entry.cost_per_1k_input == pytest.approx(DEEPSEEK_IN_PER_M / 1000), (
        "DeepSeek's own rate must price a deepseek entry, not clinepass's"
    )
    assert entry.cost_per_1k_output == pytest.approx(DEEPSEEK_OUT_PER_M / 1000)
    assert entry.cost_per_1k_input != pytest.approx(CLINEPASS_IN_PER_M / 1000)
    assert entry.cost_per_1k_output != pytest.approx(CLINEPASS_OUT_PER_M / 1000)
    # Provenance is recorded, so the served rate is explicable.
    assert cfg.cost_provenance[TARGET] == {
        "tier": "provider",
        "registry": "task-router",
        "source_provider": "deepseek",
        "source_model": "deepseek-flash",
    }


def test_config_prices_entry_from_its_own_provider_on_the_models_dev_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC 1 on the models.dev path: 25 blocks publish the same id; the lab wins."""
    api_json = {
        "deepseek": {
            "id": "deepseek",
            "env": ["DEEPSEEK_API_KEY"],
            "api": "https://api.deepseek.com",
            "models": {
                "deepseek-v4-flash": {
                    "id": "deepseek-v4-flash",
                    "cost": {"input": DEEPSEEK_IN_PER_M, "output": DEEPSEEK_OUT_PER_M},
                }
            },
        },
        # A foreign gateway block with the same bare model id, written LAST —
        # the pre-fix winner of the shared key.
        "routing-run": {
            "id": "routing-run",
            "env": ["ROUTING_RUN_API_KEY"],
            "api": "https://routing-run.example/v1",
            "models": {
                "deepseek-v4-flash": {
                    "id": "deepseek-v4-flash",
                    "cost": {"input": 0.112, "output": 0.224},
                }
            },
        },
    }
    path = _write_catalog(tmp_path, _catalog_doc())

    with (
        patch("chimera.provider_discovery._fetch_models_dev", return_value=api_json),
        patch("chimera.provider_discovery._save_cache"),
    ):
        cfg = load_config(path)

    entry = cfg.models[TARGET]
    assert entry.cost_per_1k_input == pytest.approx(DEEPSEEK_IN_PER_M / 1000)
    assert entry.cost_per_1k_output == pytest.approx(DEEPSEEK_OUT_PER_M / 1000)
    assert cfg.cost_provenance[TARGET]["source_provider"] == "deepseek"
    assert cfg.cost_provenance[TARGET]["registry"] == "models.dev"


def test_catalog_declaration_wins_and_is_recorded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    table = _router_table(tmp_path)
    monkeypatch.setenv("CHIMERA_TASK_ROUTER_MODELS_PATH", str(table))
    doc = _catalog_doc(cost_per_1k_input=0.0099, cost_per_1k_output=0.0299)
    path = _write_catalog(tmp_path, doc)

    cfg = load_config(path)

    assert cfg.models[TARGET].cost_per_1k_input == 0.0099
    assert cfg.models[TARGET].cost_per_1k_output == 0.0299
    assert cfg.cost_provenance[TARGET] == {"tier": "catalog"}


def test_cost_provenance_is_never_serialized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    table = _router_table(tmp_path)
    monkeypatch.setenv("CHIMERA_TASK_ROUTER_MODELS_PATH", str(table))
    cfg = load_config(_write_catalog(tmp_path, _catalog_doc()))

    assert cfg.cost_provenance, "the fixture must record provenance"
    assert "cost_provenance" not in cfg.model_dump()
    assert "cost_provenance" not in cfg.model_dump_json()


# ═══════════════════════════════════════════════════════════════════════════
#  End to end: the number a user reads in the trace
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_trace_cost_uses_the_entries_provider_rate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC 1 end to end: the trace bills DeepSeek's rate, not clinepass's."""
    table = _router_table(tmp_path)
    monkeypatch.setenv("CHIMERA_TASK_ROUTER_MODELS_PATH", str(table))
    config = load_config(_write_catalog(tmp_path, _catalog_doc()))

    dag = {
        "stages": [
            {"id": "researcher", "kind": "worker", "model": TARGET},
            {"id": "finalizer", "kind": "aggregator", "model": TARGET, "depends_on": ["researcher"]},
        ],
        "edges": [["researcher", "finalizer"]],
    }
    gateway = FakeGateway(
        make_dispatcher_responder(
            config, payload=dispatch_json(workers=[("researcher", TARGET)], aggregator=TARGET)
        )
    )

    result = await Engine(config, gateway).deliberate(
        "Reply with exactly: PONG", dag=dag, allow_custom_dag=True
    )

    rate_in = DEEPSEEK_IN_PER_M / 1000
    rate_out = DEEPSEEK_OUT_PER_M / 1000
    wrong_in = CLINEPASS_IN_PER_M / 1000
    wrong_out = CLINEPASS_OUT_PER_M / 1000

    spans = [*result.trace.workers, result.trace.aggregator, result.trace.dispatch]
    assert all(span is not None for span in spans)
    assert result.trace.workers and result.trace.aggregator is not None
    for span in spans:
        assert span is not None
        assert span.model == TARGET
        expected = rate_in * span.tokens_input / 1000.0 + rate_out * span.tokens_output / 1000.0
        billed_wrong = wrong_in * span.tokens_input / 1000.0 + wrong_out * span.tokens_output / 1000.0
        assert span.cost == pytest.approx(expected)
        assert span.cost != pytest.approx(billed_wrong)

    # Concrete numbers: every stage in this DAG runs the target model, so the
    # fake gateway's dispatcher-branch token counts (100 in / 200 out) apply.
    worker = result.trace.workers[0]
    assert (worker.tokens_input, worker.tokens_output) == (100, 200)
    assert worker.cost == pytest.approx(0.000135)  # 100*0.00015/1k + 200*0.0006/1k
    assert worker.cost != pytest.approx(0.000308)  # clinepass: 0.44/1.32 per M
    assert result.trace.total_cost == pytest.approx(0.000405)  # 3 spans
