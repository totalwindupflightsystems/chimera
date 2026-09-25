"""Task-router registry adapter and preferred-source tests."""

from __future__ import annotations

import builtins
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

import pytest

from chimera.provider_discovery import discover_providers, load_preferred_registry
from chimera.task_router_registry import load_task_router_registry

REPO = Path(__file__).resolve().parent.parent
SYNC_PATH = REPO / "scripts" / "model_sync.py"


MODELS_DEV_FALLBACK = {
    "deepseek": {
        "id": "deepseek",
        "env": ["DEEPSEEK_API_KEY"],
        "api": "https://api.deepseek.com",
        "models": {
            "deepseek-v4-pro": {
                "id": "deepseek-v4-pro",
                "cost": {"input": 0.55, "output": 2.19},
            }
        },
    }
}


def _write_jsonl(path: Path, rows: list[dict[str, object] | str]) -> None:
    lines = [row if isinstance(row, str) else json.dumps(row) for row in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _live_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "provider": "deepseek",
        "model": "deepseek-v4-pro",
        "normalized_price": 0.9553,
        "public_in_per_m": 0.66,
        "public_out_per_m": 1.98,
        "data_class": "zdr",
        "context_limit": 1_000_000,
        "api_type": "responses",
        "vision": False,
        "thinking": True,
        "disabled": None,
        "valid_from": "2026-09-21",
        "valid_to": None,
        "archive": False,
    }
    row.update(overrides)
    return row


def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_valid_task_router_table_is_preferred_and_translated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    table = tmp_path / "models.jsonl"
    _write_jsonl(
        table,
        [
            _live_row(),
            _live_row(model="disabled-model", disabled=True),
            _live_row(model="expired-model", valid_to="2026-09-01"),
        ],
    )
    monkeypatch.setenv("CHIMERA_TASK_ROUTER_MODELS_PATH", str(table))

    # DF-CHIMERA-V2-49: a valid preferred source still unions the models.dev
    # cache UNDERNEATH (router rows win) so labs the router table cannot cover
    # reach the core scan and discovery. The network fetch must NOT happen —
    # only the local cache may fill gaps — so the fetch raises if touched.
    with patch(
        "chimera.provider_discovery._fetch_models_dev",
        side_effect=AssertionError("models.dev must not be fetched for a valid preferred source"),
    ):
        snapshot = load_preferred_registry()

    assert snapshot.source == "task-router"
    assert snapshot.path == table
    provider = snapshot.data["deepseek"]
    assert provider["env"] == ["DEEPSEEK_API_KEY"]
    assert provider["api"] == "https://api.deepseek.com/v1"
    assert set(provider["models"]) == {"deepseek-v4-pro"}
    model = provider["models"]["deepseek-v4-pro"]
    assert model["cost"] == {"input": 0.66, "output": 1.98}
    assert model["release_date"] == "2026-09-21"

    # Provider discovery consumes the translated shape without importing
    # credentials from the registry: config-supplied availability still wins.
    discovered, pricing = discover_providers(api_keys={"deepseek": "test-only"})
    assert discovered["deepseek"] == {
        "base_url": "https://api.deepseek.com/v1",
        "api_key_env": "DEEPSEEK_API_KEY",
    }
    assert pricing["deepseek/deepseek-v4-pro"] == {
        "input": pytest.approx(0.00066),
        "output": pytest.approx(0.00198),
    }


def test_absent_explicit_path_falls_back_to_models_dev(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing = tmp_path / "missing.jsonl"
    monkeypatch.setenv("CHIMERA_TASK_ROUTER_MODELS_PATH", str(missing))
    monkeypatch.setattr("chimera.provider_discovery.CACHE_PATH", str(tmp_path / "models-dev-cache.json"))

    with (
        patch("chimera.provider_discovery._fetch_models_dev", return_value=MODELS_DEV_FALLBACK),
        patch("chimera.provider_discovery._save_cache"),
        patch("chimera.provider_discovery.log") as log_mock,
    ):
        snapshot = load_preferred_registry()

    assert snapshot.source == "models.dev"
    assert snapshot.data == MODELS_DEV_FALLBACK
    log_mock.warning.assert_any_call(
        "registry_source_fallback",
        preferred="task-router",
        fallback="models.dev",
        reason=f"configured table does not exist: {missing}",
    )


def test_malformed_task_router_row_falls_back_instead_of_returning_partial_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    table = tmp_path / "models.jsonl"
    _write_jsonl(table, [_live_row(), "{not-json"])
    monkeypatch.setenv("CHIMERA_TASK_ROUTER_MODELS_PATH", str(table))
    monkeypatch.setattr("chimera.provider_discovery.CACHE_PATH", str(tmp_path / "models-dev-cache.json"))

    with (
        patch("chimera.provider_discovery._fetch_models_dev", return_value=MODELS_DEV_FALLBACK),
        patch("chimera.provider_discovery._save_cache"),
        patch("chimera.provider_discovery.log") as log_mock,
    ):
        snapshot = load_preferred_registry()

    assert snapshot.source == "models.dev"
    assert snapshot.data == MODELS_DEV_FALLBACK
    fallback_call = next(
        call for call in log_mock.warning.call_args_list if call.args == ("registry_source_fallback",)
    )
    assert fallback_call.kwargs["preferred"] == "task-router"
    assert fallback_call.kwargs["fallback"] == "models.dev"
    assert "line 2" in fallback_call.kwargs["reason"]


def test_adapter_has_no_task_router_python_dependency(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    table = tmp_path / "models.jsonl"
    _write_jsonl(table, [_live_row()])
    real_import = builtins.__import__

    def reject_task_router_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "task_router" or name.startswith("task_router."):
            raise AssertionError("adapter must read JSONL without importing task-router")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", reject_task_router_import)
    data = load_task_router_registry(table)

    assert data["deepseek"]["models"]["deepseek-v4-pro"]["id"] == "deepseek-v4-pro"


def test_model_sync_scan_all_uses_the_preferred_registry_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model_sync = _load_module("model_sync_task_router_registry", SYNC_PATH)
    registry = {
        "deepseek": {
            "models": {
                "deepseek-v4-pro": {
                    "id": "deepseek-v4-pro",
                    "family": "",
                    "release_date": "2026-09-21",
                    "cost": {"input": 0.66, "output": 1.98},
                }
            }
        }
    }
    calls = 0

    def preferred() -> object:
        nonlocal calls
        calls += 1
        return type(
            "Snapshot",
            (),
            {"data": registry, "source": "task-router", "path": Path("models.jsonl")},
        )()

    monkeypatch.setattr(model_sync, "load_preferred_registry", preferred)
    monkeypatch.setattr(model_sync, "_load_chimera_models", lambda: set())
    # DF-CHIMERA-V2-49: the fill goes through the _load_cache seam; pin it to
    # an empty dict so the fixture stays a closed world (no real models.dev
    # cache leaks into the pass) — the router table remains the only data.
    monkeypatch.setattr(model_sync, "_load_cache", lambda *a, **k: {})

    candidates, watch, blind, scope = model_sync.scan_all()

    assert calls == 1
    assert candidates["deepseek"][0]["chimera_id"] == "deepseek/deepseek-v4-pro"
    assert candidates["deepseek"][0]["input_per_1k"] == pytest.approx(0.00066)
    assert watch == []
    assert blind == []
    # MEASURED scope (DF-CHIMERA-V2-49): only labs the source actually has a
    # block for — the fixture registry carries deepseek alone.
    assert scope["core"] == ["deepseek"]
