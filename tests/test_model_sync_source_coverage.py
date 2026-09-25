"""Source-coverage tests for scripts/model_sync.py — DF-CHIMERA-V2-49.

The task-router registry names provider blocks by SCHEDULING LANE (xkiro,
zai-glm, clinepass, ...), while the model-sync core scan iterates CORE_PROVIDERS
lab ids. Measured 2026-09-24: 3/13 labs present, core candidates 181 -> 5,
exact pricing keys 35/42 -> 24/42 — the registry swap silently gutted the
core scan.

These tests pin the fixed contract, entirely offline (no network, no API key,
no live cache, no real task-router checkout):

* a lab present ONLY under a lane id (xkiro → anthropic) yields candidates in
  the core scan, bucketed under the LAB id;
* a lab absent from the router source is filled from the models.dev registry
  (merge fills gaps, never overwrites a router block);
* where the same (lab, model) exists in BOTH sources the router row wins —
  it is the pricing authority;
* the measured scope lists only labs with rows behind them and never prints
  the constant CORE_PROVIDERS list as if every lab were covered;
* the lane→lab attribution itself: explicit lane ownership wins, an
  unambiguous id marker attributes unlisted lanes, unattributable rows are
  left out (never mis-attributed).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from chimera.provider_discovery import (
    RegistrySnapshot,
    merge_registry_with_models_dev,
)

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


model_sync = _load_module("model_sync_source_coverage", SYNC_PATH)


# --- fixtures ---------------------------------------------------------------- #


def _router_block(model_id: str, in_price: float = 1.5, out_price: float = 6.0) -> dict[str, Any]:
    """A task-router-shaped provider block (the shape load_task_router_registry
    produces from JSONL rows: cost carries per-MTok numbers)."""
    return {
        "id": "lane",
        "models": {
            model_id: {
                "id": model_id,
                "family": "",
                "cost": {"input": in_price, "output": out_price},
                "release_date": "2026-09-01",
            }
        },
    }


def _models_dev_block(model_id: str, in_price: float = 2.0, out_price: float = 8.0) -> dict[str, Any]:
    """A models.dev-shaped provider block."""
    return {
        "id": "lab",
        "api": "https://api.example.com/v1",
        "env": [],
        "models": {
            model_id: {
                "id": model_id,
                "family": "",
                "cost": {"input": in_price, "output": out_price},
                "release_date": "2026-08-01",
            }
        },
    }


def _router_snapshot(data: dict[str, Any]) -> RegistrySnapshot:
    return RegistrySnapshot(data=data, source="task-router", path=Path("/fake/models.jsonl"))


@pytest.fixture()
def offline_scan(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Run scan_models_dev with no registry/network/live-catalog access."""

    def _run(
        snapshot: RegistrySnapshot,
        models_dev: dict[str, Any],
        catalog: set[str] | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        monkeypatch.setattr(model_sync, "load_preferred_registry", lambda **_: snapshot)
        # The fill goes through the _load_cache seam first; pin it to the
        # fixture so the REAL models.dev cache can never leak into a test.
        monkeypatch.setattr(model_sync, "_load_cache", lambda *a, **k: models_dev)
        monkeypatch.setattr(model_sync, "_load_models_dev_registry", lambda **_: models_dev)
        monkeypatch.setattr(model_sync, "_load_chimera_models", lambda: catalog or set())
        return model_sync.scan_models_dev()

    return _run


# --- lane attribution -------------------------------------------------------- #


class TestLabOfRouterProvider:
    def test_lane_row_attributed_by_id_marker(self):
        # xkiro is a lane, not a lab; the claude marker attributes the row.
        assert model_sync._lab_of_router_provider("xkiro", "claude-fable-5") == "anthropic"

    def test_zai_lane_maps_to_zhipuai_lab(self):
        assert model_sync._lab_of_router_provider("zai-glm", "glm-5.2") == "zhipuai"

    def test_unlisted_lane_attributed_by_id_marker(self):
        # 'fireworks-ai' is a lane; the id carries the lab.
        assert model_sync._lab_of_router_provider("fireworks-ai", "deepseek-v4-pro") == "deepseek"

    def test_lane_row_with_foreign_model_attributed_by_marker(self):
        # Mixed lanes carry foreign models: attribution follows the id, not
        # any block-level owner (block ownership mis-attributed foreign rows).
        assert model_sync._lab_of_router_provider("sambanova", "DeepSeek-V3.2") == "deepseek"

    def test_unattributable_row_returns_none(self):
        assert model_sync._lab_of_router_provider("crof", "some-internal-id") is None

    def test_reseller_namespace_never_attributed(self):
        # openrouter ids are deliberately namespaced — mapping them onto lab
        # keys collides with the owning lab's own pricing (DF-CHIMERA-V2-49).
        assert model_sync._lab_of_router_provider("openrouter", "deepseek-v4-pro") is None

    def test_core_lab_block_never_attributed(self):
        # A core-lab block resolves under its own id by design.
        assert model_sync._lab_of_router_provider("deepseek", "deepseek-v4-pro") is None


class TestMergeRegistryWithModelsDev:
    def test_fallback_fills_missing_blocks(self):
        primary = {"xkiro": _router_block("claude-fable-5")}
        fallback = {"openai": _models_dev_block("gpt-5.7")}
        merged = merge_registry_with_models_dev(primary, fallback)
        assert "xkiro" in merged and "openai" in merged

    def test_primary_wins_on_shared_block(self):
        primary = {"deepseek": _router_block("deepseek-v4-pro", 0.15, 0.6)}
        fallback = {"deepseek": _models_dev_block("deepseek-v4-pro", 0.99, 9.9)}
        merged = merge_registry_with_models_dev(primary, fallback)
        model = merged["deepseek"]["models"]["deepseek-v4-pro"]
        assert model["cost"] == {"input": 0.15, "output": 0.6}, "router row must win"

    def test_fetched_at_never_leaks(self):
        merged = merge_registry_with_models_dev(
            {"deepseek": {"models": {}}}, {"_fetched_at": 12345.0, "google": {"models": {}}}
        )
        assert "_fetched_at" not in merged
        assert "google" in merged


# --- core scan coverage ------------------------------------------------------- #


class TestCoreScanCoverage:
    def test_lab_under_lane_id_yields_candidates(self, offline_scan):
        """xkiro is the only source for anthropic models — the lab bucket must
        fill from the lane rows."""
        snapshot = _router_snapshot({"xkiro": _router_block("claude-fable-5")})
        candidates = offline_scan(snapshot, {})
        assert "anthropic" in candidates, f"lane rows must reach the lab bucket: {candidates.keys()}"
        ids = [c["model_id"] for c in candidates["anthropic"]]
        assert "claude-fable-5" in ids

    def test_lab_absent_from_router_filled_from_models_dev(self, offline_scan):
        """openai has no router block; the models.dev registry must fill it."""
        snapshot = _router_snapshot({"xkiro": _router_block("claude-fable-5")})
        models_dev = {"openai": _models_dev_block("gpt-5.7")}
        candidates = offline_scan(snapshot, models_dev)
        ids = [c["model_id"] for c in candidates.get("openai", [])]
        assert "gpt-5.7" in ids, "gap labs must be filled from models.dev"

    def test_router_row_wins_on_shared_id(self, offline_scan):
        """deepseek-v4-pro exists in both sources — the router's pricing must
        be the candidate's pricing."""
        snapshot = _router_snapshot({"ollama-cloud": _router_block("deepseek-v4-pro", 0.15, 0.6)})
        models_dev = {"deepseek": _models_dev_block("deepseek-v4-pro", 2.0, 8.0)}
        candidates = offline_scan(snapshot, models_dev)
        bucket = candidates.get("deepseek", [])
        entry = next(c for c in bucket if c["model_id"] == "deepseek-v4-pro")
        assert entry["input_cost_mtok"] == 0.15, "router (pricing authority) must win"
        # The router row must not be duplicated by the models.dev row.
        assert sum(1 for c in bucket if c["model_id"] == "deepseek-v4-pro") == 1

    def test_models_dev_only_rows_not_double_counted(self, offline_scan):
        """A models.dev block that the router also owns (same lab id) must not
        produce duplicate candidates for the same model id."""
        snapshot = _router_snapshot({"deepseek": _router_block("deepseek-v4-pro", 0.15, 0.6)})
        models_dev = {"deepseek": _models_dev_block("deepseek-v4-pro", 2.0, 8.0)}
        candidates = offline_scan(snapshot, models_dev)
        assert len(candidates.get("deepseek", [])) == 1

    def test_unattributable_lane_rows_stay_out(self, offline_scan):
        """Rows belonging to no core lab must never land in a wrong bucket."""
        snapshot = _router_snapshot({"crof": _router_block("some-internal-id")})
        candidates = offline_scan(snapshot, {})
        assert candidates == {}, f"unattributable rows must stay out: {candidates}"


# --- measured scope ----------------------------------------------------------- #


class TestMeasuredScope:
    def test_scope_lists_only_measured_labs(self):
        """The constant CORE_PROVIDERS list must never be printed as coverage:
        only labs with blocks in the source view count as IN."""
        cache = {"xkiro": _router_block("claude-fable-5"), "openai": _models_dev_block("gpt-5.7")}
        snapshot = _router_snapshot({"xkiro": _router_block("claude-fable-5")})
        measured = model_sync._measured_core_labs(cache, snapshot)
        # anthropic counts via the lane attribution; zhipuai/moonshotai/... do not.
        assert "anthropic" in measured
        assert "openai" in measured
        assert "zhipuai" not in measured
        assert "moonshotai" not in measured

    def test_scope_models_dev_source(self):
        cache = {"openai": _models_dev_block("gpt-5.7")}
        measured = model_sync._measured_core_labs(cache)
        assert measured == {"openai"}

    def test_lane_attribution_adds_lab_without_block(self):
        """A lab present only under a lane id is measured IN even though no
        block with its own id exists."""
        cache: dict[str, Any] = {"zai-glm": _router_block("glm-5.2")}
        snapshot = _router_snapshot(cache)
        measured = model_sync._measured_core_labs(cache, snapshot)
        assert "zhipuai" in measured
