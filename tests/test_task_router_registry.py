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
from chimera.task_router_registry import (
    TASK_ROUTER_HOME_ENV,
    TASK_ROUTER_REGISTRY_RELATIVE_PATH,
    TaskRouterRegistryError,
    load_task_router_registry,
    locate_task_router_models,
)

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
    # DF-CHIMERA-V2-93: the price row is scoped to the provider that published
    # it — the ``deepseek`` block owns this key; its provider-agnostic twin sits
    # under the ``None`` provider key as the coverage fallback.
    assert pricing[("deepseek", "deepseek/deepseek-v4-pro")]["input"] == pytest.approx(0.00066)
    assert pricing[("deepseek", "deepseek/deepseek-v4-pro")]["output"] == pytest.approx(0.00198)
    assert (None, "deepseek/deepseek-v4-pro") in pricing


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


# ═══════════════════════════════════════════════════════════════════════════
#  DF-CHIMERA-V2-94 — TASK_ROUTER_HOME is a candidate, never a silent one
#
#  TASK_ROUTER_HOME names a CHECKOUT, so its registry is only the first
#  candidate; discovery legitimately continues to ~/task-router or a package
#  sibling when the named checkout has no data/tables/models.jsonl. That
#  substitution used to be invisible (info level at best, DF-94): an operator
#  who pointed the variable at a checkout could not tell WHICH registry was
#  read. It now warns at the same level the authoritative file variable warns,
#  naming the table that was actually selected.
# ═══════════════════════════════════════════════════════════════════════════


def _fake_home_with_checkout(root: Path, rows: list[dict[str, object] | str] | None = None) -> Path:
    """Create a fake ``$HOME`` holding a real ``~/task-router`` checkout.

    Returns the checkout's registry table — the fallback a bogus
    ``TASK_ROUTER_HOME`` falls through to.
    """
    table = root / "home" / "task-router" / TASK_ROUTER_REGISTRY_RELATIVE_PATH
    table.parent.mkdir(parents=True, exist_ok=True)
    _write_jsonl(table, rows if rows is not None else [_live_row()])
    return table


def _checkout(root: Path, name: str = "checkout") -> Path:
    """Create a checkout directory holding exactly one live-row registry."""
    home = root / name
    table = home / TASK_ROUTER_REGISTRY_RELATIVE_PATH
    table.parent.mkdir(parents=True, exist_ok=True)
    _write_jsonl(table, [_live_row()])
    return home


def test_task_router_home_without_registry_warns_and_names_the_selected_table(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DF-CHIMERA-V2-94: the substitution is reported at WARNING level, by path."""
    monkeypatch.delenv("CHIMERA_TASK_ROUTER_MODELS_PATH", raising=False)
    fallback_table = _fake_home_with_checkout(tmp_path)
    monkeypatch.setenv("HOME", str(fallback_table.parents[3]))
    missing_home = tmp_path / "srv" / "task-router"
    monkeypatch.setenv(TASK_ROUTER_HOME_ENV, str(missing_home))
    missing_table = missing_home / TASK_ROUTER_REGISTRY_RELATIVE_PATH

    with patch("chimera.task_router_registry.log") as log_mock:
        data = load_task_router_registry()

    # The registry that was read is the fallback one — announced, not swapped in.
    assert data["deepseek"]["models"]["deepseek-v4-pro"]["id"] == "deepseek-v4-pro"
    log_mock.warning.assert_called_once_with(
        "task_router_home_registry_missing",
        env=TASK_ROUTER_HOME_ENV,
        home=str(missing_home),
        missing=str(missing_table),
        fallback=str(fallback_table),
        reason=(
            f"{TASK_ROUTER_HOME_ENV} checkout has no registry: {missing_table}; "
            f"selected {fallback_table} instead"
        ),
    )
    # Not a quiet info line: the file variable's diagnostic level is WARNING.
    assert log_mock.info.call_count == 0


def test_task_router_home_warning_level_matches_the_authoritative_file_variable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Level parity with CHIMERA_TASK_ROUTER_MODELS_PATH, on the discovery path.

    The file variable's missing-file diagnostic is logged via
    ``provider_discovery.log.warning``.  A named checkout that silently failed
    over used to leave that same discovery call claiming a clean
    ``registry_source_selected`` with no warning at all; both arms must warn.
    """
    monkeypatch.delenv("CHIMERA_TASK_ROUTER_MODELS_PATH", raising=False)
    monkeypatch.setattr("chimera.provider_discovery.CACHE_PATH", str(tmp_path / "models-dev-cache.json"))
    fallback_table = _fake_home_with_checkout(tmp_path)
    monkeypatch.setenv("HOME", str(fallback_table.parents[3]))
    monkeypatch.setenv(TASK_ROUTER_HOME_ENV, str(tmp_path / "srv" / "task-router"))

    with patch("chimera.task_router_registry.log") as registry_log:
        snapshot = load_preferred_registry()

    assert snapshot.source == "task-router"
    assert snapshot.path == fallback_table
    assert registry_log.warning.call_count == 1
    assert registry_log.warning.call_args.args == ("task_router_home_registry_missing",)
    assert registry_log.warning.call_args.kwargs["fallback"] == str(fallback_table)
    assert registry_log.info.call_count == 0


def test_task_router_home_with_registry_is_selected_without_a_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A usable checkout is a normal selection — no substitution, no warning."""
    monkeypatch.delenv("CHIMERA_TASK_ROUTER_MODELS_PATH", raising=False)
    named_home = _checkout(tmp_path, "named-task-router")
    named_table = named_home / TASK_ROUTER_REGISTRY_RELATIVE_PATH
    monkeypatch.setenv(TASK_ROUTER_HOME_ENV, str(named_home))
    # A DIFFERENT checkout is also reachable, so a wrong pick would be visible.
    _fake_home_with_checkout(tmp_path, [_live_row(model="deepseek-v4-flash")])
    monkeypatch.setenv("HOME", str(tmp_path / "home"))

    with patch("chimera.task_router_registry.log") as log_mock:
        assert locate_task_router_models() == named_table

    assert log_mock.warning.call_count == 0
    assert log_mock.info.call_count == 0


def test_explicit_table_wins_over_task_router_home_without_a_home_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both variables set: the explicit file is authoritative and consulted alone.

    DF-CHIMERA-V2-94 must not add noise to the documented precedence — with the
    file variable set, the home variable is not even inspected, so its absence
    of a registry is not (and must not be) a warning.
    """
    explicit_table = tmp_path / "explicit.jsonl"
    _write_jsonl(explicit_table, [_live_row()])
    monkeypatch.setenv("CHIMERA_TASK_ROUTER_MODELS_PATH", str(explicit_table))
    monkeypatch.setenv(TASK_ROUTER_HOME_ENV, str(tmp_path / "srv" / "task-router"))
    monkeypatch.setenv("HOME", str(tmp_path / "empty-home"))

    with patch("chimera.task_router_registry.log") as log_mock:
        assert locate_task_router_models() == explicit_table
        data = load_task_router_registry()

    assert data["deepseek"]["models"]["deepseek-v4-pro"]["id"] == "deepseek-v4-pro"
    assert log_mock.warning.call_count == 0


def test_task_router_home_without_registry_or_fallback_warns_before_raising(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nothing to fall through to: warn, then still raise naming every candidate."""
    monkeypatch.delenv("CHIMERA_TASK_ROUTER_MODELS_PATH", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "empty-home"))
    missing_home = tmp_path / "srv" / "task-router"
    monkeypatch.setenv(TASK_ROUTER_HOME_ENV, str(missing_home))
    missing_table = missing_home / TASK_ROUTER_REGISTRY_RELATIVE_PATH
    # Closed world: fabricate __file__ so the package-sibling candidate
    # (parents[3]/task-router) cannot resolve to a real checkout on this host.
    fake_module = tmp_path / "pkg" / "src" / "chimera" / "task_router_registry.py"
    fake_module.parent.mkdir(parents=True, exist_ok=True)
    fake_module.write_text("", encoding="utf-8")
    monkeypatch.setattr("chimera.task_router_registry.__file__", str(fake_module))

    with patch("chimera.task_router_registry.log") as log_mock:
        with pytest.raises(TaskRouterRegistryError) as excinfo:
            locate_task_router_models()

    assert log_mock.warning.call_count == 1
    assert log_mock.warning.call_args.args == ("task_router_home_registry_missing",)
    assert log_mock.warning.call_args.kwargs["missing"] == str(missing_table)
    assert log_mock.warning.call_args.kwargs["fallback"] is None
    assert "no fallback checkout was found" in log_mock.warning.call_args.kwargs["reason"]
    # The actionable error still names the named-checkout table among the tried.
    assert str(missing_table) in str(excinfo.value)
    assert str(excinfo.value).startswith("task-router table not found (tried: ")


@pytest.mark.parametrize(
    ("rows", "reason", "expected_line"),
    [
        pytest.param(["{not-json"], "malformed JSON in", 1, id="malformed-json"),
        pytest.param(
            [_live_row(), _live_row()], "unsupported duplicate live row", 2, id="duplicate-live-row"
        ),
        pytest.param([_live_row(archive=True)], "has no live supported rows", None, id="all-archived"),
        pytest.param([_live_row(disabled=True)], "has no live supported rows", None, id="all-disabled"),
        pytest.param([_live_row(valid_to="2026-09-01")], "has no live supported rows", None, id="all-expired"),
        pytest.param([], "has no live supported rows", None, id="empty-file"),
        pytest.param([_live_row(provider=None)], "provider must be a string", 1, id="non-string-provider"),
        pytest.param([_live_row(model="")], "model must be a string", 1, id="blank-model"),
        pytest.param([[1, 2, 3]], "expected an object", 1, id="non-object-row"),
    ],
)
def test_contract_probe_classes_stay_loud_and_precise(
    tmp_path: Path,
    rows: list[dict[str, object] | str],
    reason: str,
    expected_line: int | None,
) -> None:
    """The neighbouring contract probes (DF-94's AC set) keep their exact reasons.

    Each class invalidates the whole table and names the file — and, where the
    row is identifiable, the line — so the caller's models.dev fallback is
    diagnosable rather than mysterious. Pinned here because the DF-94 change
    touches the same selection path.
    """
    table = tmp_path / "models.jsonl"
    _write_jsonl(table, rows)

    with pytest.raises(TaskRouterRegistryError) as excinfo:
        load_task_router_registry(table)

    message = str(excinfo.value)
    assert reason in message
    assert str(table) in message
    if expected_line is not None:
        assert f"line {expected_line}" in message
