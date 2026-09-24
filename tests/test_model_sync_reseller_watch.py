"""Reseller-watch / blind-spot regression tests for scripts/model_sync.py — DF-CHIMERA-V2-26.

The sync scanned only the 13 CORE_PROVIDERS rows of models.dev, so a frontier
release that landed first in a RESELLER row was invisible: StepFun
``step-5-preview`` shipped 2026-09-18/20, was live on api.stepfun.ai, and
existed on models.dev only in the ``nano-gpt`` and ``vercel`` rows (both
outside CORE_PROVIDERS) — while ``model_sync.py --diff`` printed "0 new
models" that day.

These tests pin the fixed contract, entirely offline (fixture cache, no
network, no API key, no live ``.seen_models.json``), following the fixture
style of ``tests/test_model_sync_recency.py``:

* a new model visible ONLY in reseller rows surfaces in
  ``scan_reseller_watch()`` with a hypothesized owning lab (id-shape
  attribution) and the reseller rows that carry it;
* an unattributable reseller-only id is reported in the explicit BLIND-SPOT
  list instead of being dropped;
* a reseller id whose basename already appears in a core row is NOT reported
  (the core scan already sees that model);
* a reseller find whose resolved Chimera id is already in the catalog is NOT
  reported (admitted);
* non-chat reseller rows (embeddings etc.) are skipped by the same
  ``_is_chat_model`` filter the core loop uses;
* the report states the scan scope (which provider ids are IN, which are OUT)
  on every run, and carries explicit "Reseller Watch" / "Blind Spot" sections;
* reseller-only finds are never recorded in ``.seen_models.json`` — they are
  re-reported on every run until they appear in a core row or are admitted.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from chimera.provider_discovery import RegistrySnapshot

REPO = Path(__file__).resolve().parent.parent
SYNC_PATH = REPO / "scripts" / "model_sync.py"


def _load_module(name: str, path: Path) -> ModuleType:
    """Load a script as a module (scripts/ is not a package)."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


model_sync = _load_module("model_sync_reseller", SYNC_PATH)


# --- helpers ---------------------------------------------------------------- #


def _date(days_ago: float) -> str:
    """An ISO-8601 date string ``days_ago`` days before today (UTC)."""
    return (datetime.now(UTC) - timedelta(days=days_ago)).strftime("%Y-%m-%d")


def _reseller_cache() -> dict[str, Any]:
    """Fixture cache: step-5-preview exists ONLY in reseller rows.

    Mirrors the real 2026-09-20 models.dev state that exposed the blind spot:
    the core ``stepfun`` row tops out at step-3.7-flash while the nano-gpt and
    vercel rows already carry the namespaced ``stepfun/step-5-preview``.
    """
    return {
        "stepfun": {
            "models": {
                "step-3.7-flash": {
                    "id": "step-3.7-flash",
                    "family": "step",
                    "release_date": _date(200),
                    "cost": {"input": 0.15, "output": 0.6},
                },
            },
        },
        "nano-gpt": {
            "models": {
                "stepfun/step-5-preview": {
                    "id": "stepfun/step-5-preview",
                    "family": "step",
                    "release_date": _date(2),
                    "cost": {"input": 0.6, "output": 2.4},
                },
                "stepfun/step-3.7-flash": {
                    "id": "stepfun/step-3.7-flash",
                    "family": "step",
                    "release_date": _date(200),
                },
            },
        },
        "vercel": {
            "models": {
                "stepfun/step-5-preview": {
                    "id": "stepfun/step-5-preview",
                    "family": "step",
                    "release_date": _date(2),
                    "cost": {"input": 0.7, "output": 2.8},
                },
            },
        },
        "llmgateway": {
            "models": {
                # Unprefixed id with no family hint → genuinely unattributable.
                "qx-turbo-9000": {
                    "id": "qx-turbo-9000",
                    "family": "qx",
                    "release_date": _date(1),
                },
                "claude-sonnet-4-6": {
                    "id": "claude-sonnet-4-6",
                    "family": "claude",
                    "release_date": _date(120),
                },
                "some-vendor/embed-large": {
                    "id": "some-vendor/embed-large",
                    "family": "embedding",
                },
            },
        },
    }


def _core_candidate(chimera_id: str, provider: str = "stepfun") -> dict[str, Any]:
    """A core candidate dict in the exact shape scan_models_dev() produces."""
    return {
        "model_id": chimera_id.split("/")[-1],
        "chimera_id": chimera_id,
        "family": "step",
        "description": "",
        "input_cost_mtok": 0.15,
        "output_cost_mtok": 0.6,
        "input_per_1k": 0.00015,
        "output_per_1k": 0.0006,
        "recency_score": 50.0,
        "recency_ts": None,
        "provider": provider,
    }


@pytest.fixture()
def isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, Any]:
    """Offline fixture harness: fixture cache, empty catalog, scratch seen-file."""
    cache = _reseller_cache()
    seen_path = tmp_path / "seen_models.json"
    monkeypatch.setattr(model_sync, "_load_cache", lambda *a, **k: cache)
    monkeypatch.setattr(
        model_sync,
        "load_preferred_registry",
        lambda **_kwargs: RegistrySnapshot(data=cache, source="models.dev"),
    )
    monkeypatch.setattr(model_sync, "_load_chimera_models", lambda: set())
    monkeypatch.setattr(model_sync, "SEEN_PATH", seen_path)
    return {"cache": cache, "seen_path": seen_path}


# --- scan_reseller_watch -----------------------------------------------------#


def test_step5_preview_surfaces_from_reseller_only_row(isolated: dict[str, Any]) -> None:
    """A model visible only in reseller rows surfaces with lab + carrier rows."""
    # Derive core basenames exactly the way scan_all() does.
    candidates = model_sync.scan_models_dev()
    core_basenames = {m["model_id"] for models in candidates.values() for m in models}
    watch, blind = model_sync.scan_reseller_watch(isolated["cache"], core_basenames)

    by_id = {m["model_id"]: m for m in watch}
    assert "stepfun/step-5-preview" in by_id
    entry = by_id["stepfun/step-5-preview"]
    assert entry["lab"] == "stepfun"
    assert sorted(entry["reseller_rows"]) == ["nano-gpt", "vercel"]
    # Newest-first ordering within the watch list.
    assert entry["recency_score"] >= 90.0
    assert entry["recency_ts"] is not None

    # Pre-fix behaviour: the core scan printed NOTHING for this model.
    candidates = model_sync.scan_models_dev()
    core_ids = [m["chimera_id"] for models in candidates.values() for m in models]
    assert "stepfun/step-5-preview" not in core_ids

    # The duplicate-carrier id (step-3.7-flash is in the core row) is NOT
    # reported — the core scan already sees that model.
    assert "stepfun/step-3.7-flash" not in by_id


def test_unattributable_id_lands_in_blind_spot(isolated: dict[str, Any]) -> None:
    """A reseller-only id with no lab segment and no family hint → blind spot."""
    watch, blind = model_sync.scan_reseller_watch(isolated["cache"], set())

    blind_ids = [m["model_id"] for m in blind]
    assert "qx-turbo-9000" in blind_ids
    entry = next(m for m in blind if m["model_id"] == "qx-turbo-9000")
    assert entry["lab"] is None
    assert entry["reseller_rows"] == ["llmgateway"]
    assert all(m["model_id"] != "qx-turbo-9000" for m in watch)


def test_family_hint_attributes_unprefixed_reseller_id(isolated: dict[str, Any]) -> None:
    """An unprefixed id whose basename carries a known lab family is attributed."""
    watch, blind = model_sync.scan_reseller_watch(isolated["cache"], set())

    # claude-sonnet-4-6 carries no path segment but the family hint attributes
    # it to anthropic... unless its basename is in a core row (it is not in
    # this fixture) or the resolved chimera id is in the catalog (empty here).
    by_id = {m["model_id"]: m for m in watch}
    assert "claude-sonnet-4-6" in by_id
    assert by_id["claude-sonnet-4-6"]["lab"] == "anthropic"
    assert all(m["model_id"] != "claude-sonnet-4-6" for m in blind)


def test_nonchat_reseller_rows_skipped(isolated: dict[str, Any]) -> None:
    """Embeddings/etc. in reseller rows never reach watch or blind."""
    watch, blind = model_sync.scan_reseller_watch(isolated["cache"], set())
    all_ids = [m["model_id"] for m in watch] + [m["model_id"] for m in blind]
    assert "some-vendor/embed-large" not in all_ids


def test_catalog_admitted_reseller_find_not_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A reseller find whose resolved Chimera id is already in the catalog drops out."""
    cache = _reseller_cache()
    monkeypatch.setattr(model_sync, "_load_cache", lambda *a, **k: cache)
    monkeypatch.setattr(model_sync, "_load_chimera_models", lambda: {"stepfun/step-5-preview"})
    # Empty core-basename set: the drop must come from the CATALOG admission
    # path, not from the "already in a core row" dedupe.
    watch, blind = model_sync.scan_reseller_watch(cache, set())
    assert all(m["model_id"] != "stepfun/step-5-preview" for m in watch)
    # The genuinely-unattributable id is unaffected by admission.
    assert [m["model_id"] for m in blind] == ["qx-turbo-9000"]


# --- report shape ------------------------------------------------------------#


def test_report_states_scan_scope(isolated: dict[str, Any]) -> None:
    """Scope statement names IN (core + reseller) and OUT counts on every run."""
    scope = {
        "core": sorted(model_sync.CORE_PROVIDERS),
        "reseller": sorted(model_sync.RESELLER_WATCH),
        "out_of_scope": 205,
    }
    for markdown in (True, False):
        report = model_sync.format_report(
            {}, markdown=markdown, reseller_watch=[], blind_spot=[], scope=scope
        )
        assert "Scan scope" in report
        for core_id in ("stepfun", "openai", "anthropic"):
            assert core_id in report
        for reseller_id in ("nano-gpt", "vercel", "openrouter", "kilo", "llmgateway"):
            assert reseller_id in report
        assert "205" in report

    # Default scope (no cache known): the statement is still present.
    report = model_sync.format_report({}, markdown=True, scope=None)
    assert "Scan scope" in report


def test_report_carries_watch_and_blindspot_sections(isolated: dict[str, Any]) -> None:
    """The markdown report has explicit Reseller Watch and Blind Spot sections."""
    watch, blind = model_sync.scan_reseller_watch(isolated["cache"], set())
    report = model_sync.format_report(
        {},
        markdown=True,
        reseller_watch=watch,
        blind_spot=blind,
        scope={
            "core": sorted(model_sync.CORE_PROVIDERS),
            "reseller": sorted(model_sync.RESELLER_WATCH),
            "out_of_scope": 205,
        },
    )
    assert "## Reseller Watch" in report
    assert "`stepfun/step-5-preview`" in report
    assert "stepfun" in report  # hypothesized owning lab
    assert "nano-gpt" in report and "vercel" in report  # carrier rows
    assert "## Blind Spot" in report
    assert "`qx-turbo-9000`" in report
    # The tracking policy is stated in the report itself.
    assert ".seen_models.json" in report
    assert "NOT recorded" in report


def test_diff_mode_still_reports_watch_sections(
    isolated: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    """Reseller-only finds are reported on EVERY run, including --diff."""
    watch, blind = model_sync.scan_reseller_watch(isolated["cache"], set())
    report = model_sync.format_report(
        {},
        diff_only=True,
        markdown=True,
        reseller_watch=watch,
        blind_spot=blind,
        scope={
            "core": sorted(model_sync.CORE_PROVIDERS),
            "reseller": sorted(model_sync.RESELLER_WATCH),
            "out_of_scope": 205,
        },
    )
    assert "Reseller Watch" in report
    assert "stepfun/step-5-preview" in report


# --- seen-file discipline -----------------------------------------------------#


def test_seen_file_not_polluted_by_reseller_finds(isolated: dict[str, Any]) -> None:
    """Core finds are tracked; reseller watch/blind ids are never recorded."""
    isolated["seen_path"].write_text(json.dumps(["stepfun/step-old"]))
    candidates = {"stepfun": [_core_candidate("stepfun/step-3.7-flash")]}
    watch, blind = model_sync.scan_reseller_watch(isolated["cache"], set())

    model_sync.format_report(
        candidates,
        diff_only=True,
        markdown=False,
        reseller_watch=watch,
        blind_spot=blind,
    )

    seen = set(json.loads(isolated["seen_path"].read_text()))
    assert "stepfun/step-3.7-flash" in seen  # core find tracked as before
    assert "stepfun/step-5-preview" not in seen  # reseller-only NOT tracked
    assert not any("qx-turbo-9000" in s for s in seen)  # blind spot NOT tracked


# --- wiring -------------------------------------------------------------------#


def test_scan_all_returns_candidates_watch_blind_scope(
    isolated: dict[str, Any],
) -> None:
    """scan_all() is one cache pass returning core + watch + blind + scope."""
    candidates, watch, blind, scope = model_sync.scan_all()

    assert "stepfun" in candidates  # core loop intact
    assert any(m["model_id"] == "stepfun/step-5-preview" for m in watch)
    assert any(m["model_id"] == "qx-turbo-9000" for m in blind)
    assert sorted(scope["reseller"]) == sorted(model_sync.RESELLER_WATCH)
    assert sorted(scope["core"]) == sorted(model_sync.CORE_PROVIDERS)
    assert isinstance(scope["out_of_scope"], int)
    assert scope["out_of_scope"] >= 0
