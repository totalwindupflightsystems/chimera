"""Lane-carried core-release promotion tests for scripts/model_sync.py — DF-CHIMERA-V2-67.

The DF-CHIMERA-V2-65 split routes report candidates by the row's ``provider``
field into core vs lane sections. Correct for lane SKUs — WRONG when a
genuine core-lab release arrives ONLY through lane provider rows: the core
block's models.dev fill row is deliberately skipped in favour of the router
row (DF-CHIMERA-V2-49, router pricing is the authority), so the row's
``provider`` is the lane id and the release lands in the lane section.
Measured 2026-09-30: openai/gpt-6.1-sol (real OpenAI release, 2026-09-29,
present in the models.dev core ``openai`` block) arrived via commandcode
(``gpt-6.1-sol``) and xkiro (``openai/gpt-6.1-sol``) lane rows, was demoted
to the lane section, and the run headlined "0 new models". Same run, same
surface: lane ids were never written to .seen_models.json (new_seen was
updated only in the core loop), so lane finds re-reported every run.

These tests pin the fixed contract, entirely offline (fixture snapshot +
fixture models.dev fill, no network, no API key, no live cache, no live
catalog), using the measured 2026-09-30 diff set as the fixture:

* a lane-carried core-lab release (gpt-6.1-sol via commandcode/xkiro) is
  flagged ``core_lab_member`` at scan time, PROMOTED to the openai core
  section and counted in the core headline — as ONE candidate (the two lane
  rows are prefix-shape twins of one release; the priced row wins);
* a lane-only SKU (deepseek/deepseek-v4.1-flash-fast — no core block, no
  OpenRouter row) stays in the lane section and is NOT counted as core;
* rendered lane ids ARE recorded in .seen_models.json, so the next --diff
  run reports neither the promoted release nor the lane SKU again.
"""

from __future__ import annotations

import importlib.util
import json
import sys
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


model_sync = _load_module("model_sync_lane_core_promotion", SYNC_PATH)


# --- fixtures ---------------------------------------------------------------- #


def _row(
    model_id: str,
    *,
    in_price: float | None = None,
    out_price: float | None = None,
) -> dict[str, Any]:
    """One task-router-shaped model row (empty family = the lane-row shape)."""
    entry: dict[str, Any] = {"id": model_id, "family": ""}
    if in_price is not None or out_price is not None:
        entry["cost"] = {"input": in_price, "output": out_price}
    return entry


def _registry_snapshot_2026_09_30() -> RegistrySnapshot:
    """The measured 09-30 diff set: 3 lane rows, 0 core rows from the router.

    commandcode → ``gpt-6.1-sol`` (no pricing) and
    ``deepseek/deepseek-v4.1-flash-fast`` (lane-only SKU); xkiro →
    ``openai/gpt-6.1-sol`` (priced) — the SAME openai release under another
    prefix shape.
    """
    data: dict[str, Any] = {
        "commandcode": {
            "id": "commandcode",
            "models": {
                "gpt-6.1-sol": _row("gpt-6.1-sol"),
                "deepseek/deepseek-v4.1-flash-fast": _row("deepseek/deepseek-v4.1-flash-fast"),
            },
        },
        "xkiro": {
            "id": "xkiro",
            "models": {
                "openai/gpt-6.1-sol": _row("openai/gpt-6.1-sol", in_price=2.0, out_price=10.0),
            },
        },
    }
    return RegistrySnapshot(data=data, source="task-router", path=Path("/fake/models.jsonl"))


def _models_dev_fill_2026_09_30() -> dict[str, Any]:
    """The models.dev fill underneath the router table (09-30 shape).

    The core ``openai`` block carries ``gpt-6.1-sol`` (the release IS a core
    release — the fill row is skipped by the core scan in favour of the
    router row, per DF-CHIMERA-V2-49). The core ``deepseek`` block does NOT
    carry ``deepseek-v4.1-flash-fast``: that SKU exists only on the lane.
    """
    return {
        "openai": {
            "id": "openai",
            "models": {
                "gpt-6.1-sol": {
                    "id": "gpt-6.1-sol",
                    "family": "gpt",
                    "cost": {"input": 2.0, "output": 10.0},
                    "release_date": "2026-09-29",
                },
            },
        },
        "deepseek": {
            "id": "deepseek",
            "models": {
                "deepseek-v4.1-flash": {
                    "id": "deepseek-v4.1-flash",
                    "family": "deepseek",
                    "cost": {"input": 0.3, "output": 1.2},
                    "release_date": "2026-08-01",
                },
            },
        },
    }


@pytest.fixture()
def isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, Any]:
    """Offline harness: the 09-30 snapshot + 09-30 fill, scratch seen-file.

    The catalog carries the OLD deepseek release (deepseek-v4.1-flash was
    admitted long ago) so the fill's deepseek block contributes no core
    candidate — exactly the 09-30 shape, where the ONLY new finds were the
    three lane rows.
    """
    snapshot = _registry_snapshot_2026_09_30()
    seen_path = tmp_path / "seen_models.json"
    monkeypatch.setattr(model_sync, "load_preferred_registry", lambda **_: snapshot)
    # The fill goes through the _load_cache seam; pin it to the 09-30
    # models.dev shape so the REAL cache can never leak into a test.
    monkeypatch.setattr(model_sync, "_load_cache", lambda *a, **k: _models_dev_fill_2026_09_30())
    monkeypatch.setattr(model_sync, "_load_models_dev_registry", lambda **_: _models_dev_fill_2026_09_30())
    monkeypatch.setattr(model_sync, "_load_chimera_models", lambda: {"deepseek/deepseek-v4.1-flash"})
    monkeypatch.setattr(model_sync, "SEEN_PATH", seen_path)
    return {"snapshot": snapshot, "seen_path": seen_path}


def _scan() -> dict[str, list[dict[str, Any]]]:
    return model_sync.scan_models_dev()


# --- A: lane-carried core-lab releases are promoted to the core section ------- #


class TestLaneCarriedCorePromotion:
    def test_scan_flags_the_release_core_lab_member_and_dedupes_the_twin(
        self, isolated: dict[str, Any]
    ) -> None:
        """Scan level: gpt-6.1-sol arrives via TWO lane rows (commandcode
        bare, xkiro prefixed) — one release. The bucket holds ONE candidate,
        flagged core_lab_member (the models.dev openai block carries the id),
        and the PRICED row (xkiro) wins over the priceless twin."""
        candidates = _scan()
        openai_rows = candidates.get("openai", [])
        sol_rows = [m for m in openai_rows if model_sync._basename(m["model_id"]) == "gpt-6.1-sol"]
        assert len(sol_rows) == 1
        (sol,) = sol_rows
        assert sol["core_lab_member"] is True
        assert sol["provider"] == "xkiro"  # provenance kept: it arrived via a lane
        assert sol["input_cost_mtok"] == 2.0

    def test_promoted_release_counts_in_the_core_headline(self, isolated: dict[str, Any]) -> None:
        """The measured defect: the 09-30 run headlined '0 new models' with
        gpt-6.1-sol sitting in the lane section. After the fix it is 1 core
        candidate under openai, plus 1 lane find (the deepseek SKU)."""
        report = model_sync.format_report(_scan())
        assert "Candidates: 1 new models across 1 providers" in report
        assert ", plus 1 task-router lane find" in report
        # The promoted row renders in the openai CORE section, not the lane one.
        assert "OpenAI" in report
        core_body = report.split("Task-Router Lane Providers")[0]
        assert "gpt-6.1-sol" in core_body
        lane_body = report.split("Task-Router Lane Providers")[1]
        assert "gpt-6.1-sol" not in lane_body

    def test_markdown_headline_counts_the_promoted_release(self, isolated: dict[str, Any]) -> None:
        report = model_sync.format_report(_scan(), markdown=True)
        assert "**Candidates:** 1 new models across 1 providers" in report
        assert ", plus 1 task-router lane find" in report


# --- B: lane-only SKUs stay in the lane section ------------------------------- #


class TestLaneOnlySkuStaysLane:
    def test_lane_only_sku_not_flagged(self, isolated: dict[str, Any]) -> None:
        """deepseek-v4.1-flash-fast has no core-lab block row (the models.dev
        deepseek block carries only deepseek-v4.1-flash — a DIFFERENT
        basename, so the whole-basename rule must not confuse them)."""
        candidates = _scan()
        ds_rows = [m for m in candidates.get("deepseek", []) if "flash-fast" in m["model_id"]]
        assert len(ds_rows) == 1
        assert "core_lab_member" not in ds_rows[0]
        assert ds_rows[0]["provider"] == "commandcode"

    def test_lane_only_sku_renders_in_the_lane_section_not_counted_as_core(
        self, isolated: dict[str, Any]
    ) -> None:
        report = model_sync.format_report(_scan())
        # Not promoted: the deepseek lab holds no genuine core row here, so
        # it renders NO core section (only the flash-fast lane find exists).
        assert "DeepSeek (" not in report.split("Task-Router Lane Providers")[0]
        lane_body = report.split("Task-Router Lane Providers")[1]
        assert "deepseek-v4.1-flash-fast" in lane_body
        assert "commandcode" in lane_body
        # Headline: exactly 1 core (the promoted sol release) + 1 lane.
        assert "Candidates: 1 new models across 1 providers" in report
        assert ", plus 1 task-router lane find" in report


# --- C: lane finds are recorded in the seen ledger ---------------------------- #


class TestLaneSeenLedger:
    def test_rendered_lane_ids_are_recorded(self, isolated: dict[str, Any]) -> None:
        """Second issue of the row: lane ids never entered new_seen, so lane
        finds re-reported every run. Both the promoted core id and the lane
        SKU id are now recorded."""
        model_sync.format_report(_scan(), diff_only=True)
        seen = json.loads(isolated["seen_path"].read_text())
        assert any("gpt-6.1-sol" in entry for entry in seen)
        assert any("deepseek-v4.1-flash-fast" in entry for entry in seen)

    def test_next_diff_run_reports_nothing_again(self, isolated: dict[str, Any]) -> None:
        """The re-report loop is closed: a second --diff over the same
        candidates shows 0 core + 0 lane and renders no lane section."""
        candidates = _scan()
        model_sync.format_report(candidates, diff_only=True)
        report = model_sync.format_report(candidates, diff_only=True)
        # (The provider count is derived from the pre-filter buckets — a
        # pre-existing headline quirk outside this row — so assert the NEW
        # counts and the absence of every id, not the provider figure.)
        assert "Candidates: 0 new models across" in report
        assert ", plus 0 task-router lane finds" in report
        assert "gpt-6.1-sol" not in report
        assert "deepseek-v4.1-flash-fast" not in report

    def test_unrendered_lane_rows_are_not_recorded(self, isolated: dict[str, Any]) -> None:
        """Only RENDERED lane finds enter the ledger: a lane row already
        covered by the seen file is filtered out of the diff and must not be
        re-recorded under a second id shape either (the basename branch of
        _seen_match is what covers shape drift, DF-CHIMERA-V2-64)."""
        isolated["seen_path"].write_text(json.dumps(["deepseek/deepseek/deepseek-v4.1-flash-fast"]))
        model_sync.format_report(_scan(), diff_only=True)
        seen = json.loads(isolated["seen_path"].read_text())
        flash_fast = [e for e in seen if "flash-fast" in e]
        assert flash_fast == ["deepseek/deepseek/deepseek-v4.1-flash-fast"]  # unchanged, no dupes
        assert any("gpt-6.1-sol" in entry for entry in seen)  # fresh core find still recorded


# --- D: helper contract -------------------------------------------------------- #


class TestCoreLabMemberHelper:
    def test_basename_membership_and_prefix_shapes(self) -> None:
        block = {"models": {"gpt-6.1-sol": {}}}
        assert model_sync._core_lab_member(block, "gpt-6.1-sol") is True
        assert model_sync._core_lab_member(block, "openai/gpt-6.1-sol") is True
        assert model_sync._core_lab_member(block, "openai/openai/gpt-6.1-sol") is True

    def test_whole_basename_only(self) -> None:
        block = {"models": {"deepseek-v4.1-flash": {}}}
        assert model_sync._core_lab_member(block, "deepseek/deepseek-v4.1-flash-fast") is False
        assert model_sync._core_lab_member(block, "deepseek-v4.1-flash") is True

    def test_malformed_blocks_are_not_members(self) -> None:
        assert model_sync._core_lab_member(None, "gpt-6.1-sol") is False
        assert model_sync._core_lab_member({}, "gpt-6.1-sol") is False
        assert model_sync._core_lab_member({"models": "oops"}, "gpt-6.1-sol") is False
        assert model_sync._core_lab_member({"models": {}}, "gpt-6.1-sol") is False
