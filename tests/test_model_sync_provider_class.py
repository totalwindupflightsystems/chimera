"""Provider-class regression tests for scripts/model_sync.py — DF-CHIMERA-V2-65.

The task-router registry carries the fleet's scheduling LANES (xkiro,
openai-codex, ...) beside core labs. The core loop ATTRIBUTES lane SKUs to
their owning lab (DF-CHIMERA-V2-49), and format_report() printed them under
the lab's header inside the "across N providers" headline. Measured 09-28:
7 diff rows, 5 of them lane rows (xkiro → kimi-k2.7-code-highspeed /
kimi-k2.8-preview / kimi-k3-256k; openai-codex → gpt-daybreak-blue-latest /
gpt-daybreak-red-latest), yet the headline claimed "7 new models across 13
providers"; the 2 genuine core rows were alibaba's qwen3.7-flash and
qwen3.5-flash. The openai-codex rows are vendor-program ALIASES (alias_of
gpt-5.6-sol / gpt-5.6-cyber, both already catalogued).

These tests pin the fixed contract, entirely offline (fixture snapshot, no
network, no API key, no live cache, no live catalog):

* a lane-provider row does NOT increment the core-lab provider count — the
  headline states core providers from the core population and lane finds as a
  separate count;
* lane rows still appear in the report, attributed to their lane, in a
  section clearly separate from every core-lab section — never dropped;
* a registry row with ``alias_of`` set is NEVER reported as a new model (scan
  level and report level), and the report names the alias target;
* the scope statement names the lanes in scope separately from core labs.
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


model_sync = _load_module("model_sync_provider_class", SYNC_PATH)


# --- fixtures ---------------------------------------------------------------- #


def _row(
    model_id: str,
    *,
    family: str = "",
    alias_of: str | None = None,
    in_price: float = 1.5,
    out_price: float = 6.0,
    release_date: str = "2026-09-20",
) -> dict[str, Any]:
    """One task-router-shaped model row (empty family = the lane-row shape)."""
    entry: dict[str, Any] = {
        "id": model_id,
        "family": family,
        "cost": {"input": in_price, "output": out_price},
        "release_date": release_date,
    }
    if alias_of is not None:
        entry["alias_of"] = alias_of
    return entry


def _registry_snapshot_2026_09_28() -> RegistrySnapshot:
    """The measured 09-28 registry: 5 lane rows + 2 genuine core rows.

    xkiro → 3 kimi SKUs (moonshotai by id marker); openai-codex → 2 vendor
    ALIASES of already-catalogued ids; alibaba (a core lab block) → 2 qwen
    rows carrying family + description — the only genuine core candidates.
    """
    data: dict[str, Any] = {
        "xkiro": {
            "id": "xkiro",
            "models": {
                "kimi-k2.7-code-highspeed": _row("kimi-k2.7-code-highspeed"),
                "kimi-k2.8-preview": _row("kimi-k2.8-preview"),
                "kimi-k3-256k": _row("kimi-k3-256k"),
            },
        },
        "openai-codex": {
            "id": "openai-codex",
            "models": {
                "gpt-daybreak-blue-latest": _row("gpt-daybreak-blue-latest", alias_of="gpt-5.6-sol"),
                "gpt-daybreak-red-latest": _row("gpt-daybreak-red-latest", alias_of="gpt-5.6-cyber"),
            },
        },
        "alibaba": {
            "id": "alibaba",
            "models": {
                "qwen3.7-flash": _row(
                    "qwen3.7-flash",
                    family="qwen",
                    release_date="2026-09-25",
                ),
                "qwen3.5-flash": _row(
                    "qwen3.5-flash",
                    family="qwen",
                    release_date="2026-09-18",
                ),
            },
        },
    }
    return RegistrySnapshot(data=data, source="task-router", path=Path("/fake/models.jsonl"))


@pytest.fixture()
def isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, Any]:
    """Offline harness: the 09-28 snapshot, empty catalog, scratch seen-file."""
    snapshot = _registry_snapshot_2026_09_28()
    seen_path = tmp_path / "seen_models.json"
    monkeypatch.setattr(model_sync, "load_preferred_registry", lambda **_: snapshot)
    # The fill goes through the _load_cache seam first; pin it to EMPTY so the
    # REAL models.dev cache can never leak into a test.
    monkeypatch.setattr(model_sync, "_load_cache", lambda *a, **k: {})
    monkeypatch.setattr(model_sync, "_load_models_dev_registry", lambda **_: {})
    monkeypatch.setattr(model_sync, "_load_chimera_models", lambda: set())
    monkeypatch.setattr(model_sync, "SEEN_PATH", seen_path)
    return {"snapshot": snapshot, "seen_path": seen_path}


def _scan() -> dict[str, list[dict[str, Any]]]:
    return model_sync.scan_models_dev()


def _all_candidates(candidates: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    return [m for models in candidates.values() for m in models]


# --- A: lane rows never increment the core-lab provider count ----------------- #


class TestLaneRowsOutOfCoreCount:
    def test_scan_buckets_lane_finds_under_the_lab_but_tags_the_lane_provider(
        self, isolated: dict[str, Any]
    ) -> None:
        """Attribution is unchanged (DF-CHIMERA-V2-49): the kimi SKUs land in
        the moonshotai bucket — but each carries the LANE as its provider."""
        candidates = _scan()
        ids = {m["model_id"] for m in candidates.get("moonshotai", [])}
        assert {"kimi-k2.7-code-highspeed", "kimi-k2.8-preview", "kimi-k3-256k"} <= ids
        for m in candidates["moonshotai"]:
            assert m["provider"] == "xkiro"

    def test_headline_counts_core_providers_not_lane_inflated(self, isolated: dict[str, Any]) -> None:
        """The measured defect: '7 new models across 13 providers' style
        inflation. The headline counts CORE-lab candidates and providers —
        here 2 new models across 1 core provider (alibaba) — and states the
        lane finds as a separate count."""
        candidates = _scan()
        report = model_sync.format_report(candidates, scope=model_sync.scan_all()[3])
        assert "Candidates: 2 new models across 1 providers" in report
        assert ", plus 3 task-router lane finds" in report
        # The pre-fix wording (provider count over the whole candidates dict,
        # lanes included) must be gone: no bare "across N providers" claim.
        assert "across 3 providers" not in report  # lab buckets moonshotai+alibaba+openai
        assert "across 13 providers" not in report

    def test_markdown_headline_counts_core_providers(self, isolated: dict[str, Any]) -> None:
        candidates = _scan()
        report = model_sync.format_report(candidates, markdown=True)
        assert "**Candidates:** 2 new models across 1 providers" in report
        assert ", plus 3 task-router lane finds" in report

    def test_zero_lane_finds_still_state_the_lane_count(self, isolated: dict[str, Any]) -> None:
        """Core-only run: the headline names 0 lane finds (no silent lane
        accounting either way)."""
        candidates = {
            "alibaba": [
                {
                    "model_id": "qwen3.9-flash",
                    "chimera_id": "alibaba/qwen3.9-flash",
                    "family": "qwen",
                    "description": "",
                    "input_cost_mtok": 1.5,
                    "output_cost_mtok": 6.0,
                    "input_per_1k": 0.0015,
                    "output_per_1k": 0.006,
                    "recency_score": 90.0,
                    "recency_ts": None,
                    "provider": "alibaba",
                }
            ]
        }
        report = model_sync.format_report(candidates)
        assert "Candidates: 1 new models across 1 providers" in report
        assert ", plus 0 task-router lane finds" in report


# --- B: lane rows reported separately, provider named, never dropped ---------- #


class TestLaneSection:
    def test_lane_finds_render_in_their_own_section_with_the_lane_named(
        self, isolated: dict[str, Any]
    ) -> None:
        candidates = _scan()
        report = model_sync.format_report(candidates)
        assert "Task-Router Lane Providers" in report
        assert "xkiro" in report
        # Every lane SKU survives — attributed, not deleted.
        for model_id in ("kimi-k2.7-code-highspeed", "kimi-k2.8-preview", "kimi-k3-256k"):
            assert model_id in report

    def test_lane_section_is_separate_from_core_lab_sections(self, isolated: dict[str, Any]) -> None:
        """The Moonshot lab holds ONLY lane rows here, so it renders NO core
        section at all (the pre-fix report printed one) — everything kimi sits
        inside the lane section, strictly after the alibaba core section."""
        candidates = _scan()
        report = model_sync.format_report(candidates)
        lane_header = report.index("Task-Router Lane Providers")
        alibaba_header = report.index("Alibaba (Qwen)")
        assert alibaba_header < lane_header
        assert "Moonshot (Kimi)" not in report  # zero genuine core rows → no section
        # The kimi rows' report lines sit AFTER the lane header, i.e. inside
        # the lane section, never under any core-lab header.
        lane_body = report[lane_header:]
        assert "kimi-k2.8-preview" in lane_body
        core_body = report[alibaba_header:lane_header]
        assert "kimi-k2.8-preview" not in core_body

    def test_lane_rows_counted_in_the_headline_come_only_from_core_rows(
        self, isolated: dict[str, Any]
    ) -> None:
        """5 of 7 candidates are lane rows; only the 2 alibaba rows are core."""
        candidates = _scan()
        report = model_sync.format_report(candidates)
        assert "Candidates: 2 new models across 1 providers" in report
        core_section = report.split("Task-Router Lane Providers")[0]
        assert "qwen3.7-flash" in core_section
        assert "qwen3.5-flash" in core_section
        assert "kimi-k2.8-preview" not in core_section

    def test_lane_only_lab_bucket_renders_no_core_section(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """A lab whose ONLY rows come from a lane renders no core section for
        that lab — the finds belong to the lane section."""
        snapshot = RegistrySnapshot(
            data={"xkiro": {"id": "xkiro", "models": {"kimi-v9": _row("kimi-v9")}}},
            source="task-router",
            path=Path("/fake/models.jsonl"),
        )
        monkeypatch.setattr(model_sync, "load_preferred_registry", lambda **_: snapshot)
        monkeypatch.setattr(model_sync, "_load_cache", lambda *a, **k: {})
        monkeypatch.setattr(model_sync, "_load_models_dev_registry", lambda **_: {})
        monkeypatch.setattr(model_sync, "_load_chimera_models", lambda: set())
        monkeypatch.setattr(model_sync, "SEEN_PATH", tmp_path / "seen.json")

        candidates = model_sync.scan_models_dev()
        report = model_sync.format_report(candidates)
        assert "Moonshot (Kimi)" not in report  # no core section for the lab
        assert "Task-Router Lane Providers" in report
        assert "kimi-v9" in report
        assert "Candidates: 0 new models across 0 providers" in report
        assert ", plus 1 task-router lane find" in report

    def test_mixed_bucket_core_row_under_lab_and_lane_row_in_lane_section(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """A lab bucket holding BOTH a genuine core row (own lab block) and a
        lane row splits at the report boundary."""
        snapshot = RegistrySnapshot(
            data={
                "moonshotai": {  # a core-lab block: its rows are genuine
                    "id": "moonshotai",
                    "models": {"kimi-core-row": _row("kimi-core-row", family="kimi")},
                },
                "xkiro": {"id": "xkiro", "models": {"kimi-lane-row": _row("kimi-lane-row")}},
            },
            source="task-router",
            path=Path("/fake/models.jsonl"),
        )
        monkeypatch.setattr(model_sync, "load_preferred_registry", lambda **_: snapshot)
        monkeypatch.setattr(model_sync, "_load_cache", lambda *a, **k: {})
        monkeypatch.setattr(model_sync, "_load_models_dev_registry", lambda **_: {})
        monkeypatch.setattr(model_sync, "_load_chimera_models", lambda: set())
        monkeypatch.setattr(model_sync, "SEEN_PATH", tmp_path / "seen.json")

        candidates = model_sync.scan_models_dev()
        assert len(candidates.get("moonshotai", [])) == 2  # attribution unchanged
        report = model_sync.format_report(candidates)
        moonshot_body = report.split("Moonshot (Kimi)")[1].split("Task-Router Lane Providers")[0]
        assert "kimi-core-row" in moonshot_body
        assert "kimi-lane-row" not in moonshot_body
        lane_body = report.split("Task-Router Lane Providers")[1]
        assert "kimi-lane-row" in lane_body
        assert "kimi-core-row" not in lane_body
        assert "Candidates: 1 new models across 1 providers" in report
        assert ", plus 1 task-router lane find" in report

    def test_scope_statement_names_lanes_separately(self, isolated: dict[str, Any]) -> None:
        """The scope statement lists the lane ids IN scope, apart from the
        core providers, and states the lane-classification policy."""
        _candidates, _watch, _blind, scope = model_sync.scan_all()
        assert scope["lanes"] == ["openai-codex", "xkiro"]
        report = model_sync.format_report(_scan(), scope=scope)
        assert "Task-router lanes scanned (openai-codex, xkiro)" in report
        assert "never counted in the core-lab headline" in report


# --- C: alias rows are never new models --------------------------------------- #


class TestAliasRows:
    def test_alias_of_helper(self) -> None:
        """The alias reader: set / blank / non-string / absent rows."""
        assert model_sync._alias_of({"alias_of": "gpt-5.6-sol"}) == "gpt-5.6-sol"
        assert model_sync._alias_of({"alias_of": "  gpt-5.6-sol  "}) == "gpt-5.6-sol"
        assert model_sync._alias_of({"alias_of": ""}) is None
        assert model_sync._alias_of({"alias_of": "   "}) is None
        assert model_sync._alias_of({"alias_of": None}) is None
        assert model_sync._alias_of({"alias_of": 7}) is None
        assert model_sync._alias_of({}) is None
        assert model_sync._alias_of(None) is None

    def test_alias_row_never_becomes_a_candidate(self, isolated: dict[str, Any]) -> None:
        """Scan level: an alias_of row produces NO candidate anywhere."""
        candidates = _scan()
        ids = [m["model_id"] for m in _all_candidates(candidates)]
        assert "gpt-daybreak-blue-latest" not in ids
        assert "gpt-daybreak-red-latest" not in ids

    def test_alias_row_never_counted_and_reported_with_target(self, isolated: dict[str, Any]) -> None:
        """Report level: the alias lands in the Alias Skips section with the
        target id named, the provider named, and the headline unaffected."""
        candidates = _scan()
        report = model_sync.format_report(candidates)
        assert "Alias Skips" in report
        assert "gpt-daybreak-blue-latest" in report  # stated, not silently dropped
        assert "gpt-5.6-sol" in report  # the moving pointer's target
        assert "gpt-5.6-cyber" in report
        assert "openai-codex" in report  # the provider named
        # Never counted: headline stays 2 core + 3 lane.
        assert "Candidates: 2 new models across 1 providers" in report
        assert ", plus 3 task-router lane finds" in report

    def test_alias_skip_recorded_in_scan_trail(self, isolated: dict[str, Any]) -> None:
        """The scan's skip trail carries the alias with its target (the same
        stated-not-dropped contract the basename skips follow)."""
        _scan()
        alias_entries = [s for s in model_sync.LAST_SCAN_SKIPS if "alias_of" in s]
        assert sorted((s["model_id"], s["alias_of"]) for s in alias_entries) == [
            ("gpt-daybreak-blue-latest", "gpt-5.6-sol"),
            ("gpt-daybreak-red-latest", "gpt-5.6-cyber"),
        ]
        assert all(s["provider"] == "openai-codex" for s in alias_entries)
        # The historical seam name still exposes the same trail object.
        assert model_sync.LAST_BASENAME_SKIPS is model_sync.LAST_SCAN_SKIPS

    def test_alias_row_never_enters_seen_file(self, isolated: dict[str, Any]) -> None:
        """An alias is a moving pointer: recording it would let the pointer's
        CURRENT target shadow tomorrow's DIFFERENT target. Never recorded."""
        model_sync.format_report(_scan())
        seen = json.loads(isolated["seen_path"].read_text())
        assert not any("daybreak" in entry for entry in seen)

    def test_alias_guard_also_applies_to_lane_rows(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """An alias row found via the LANE pass is skipped the same way."""
        snapshot = RegistrySnapshot(
            data={
                "some-lane": {
                    "id": "some-lane",
                    "models": {"glm-alias-x": _row("glm-alias-x", alias_of="glm-5.9")},
                },
            },
            source="task-router",
            path=Path("/fake/models.jsonl"),
        )
        monkeypatch.setattr(model_sync, "load_preferred_registry", lambda **_: snapshot)
        monkeypatch.setattr(model_sync, "_load_cache", lambda *a, **k: {})
        monkeypatch.setattr(model_sync, "_load_models_dev_registry", lambda **_: {})
        monkeypatch.setattr(model_sync, "_load_chimera_models", lambda: set())
        monkeypatch.setattr(model_sync, "SEEN_PATH", tmp_path / "seen.json")

        candidates = model_sync.scan_models_dev()
        assert candidates == {}  # no candidate anywhere
        alias_entries = [s for s in model_sync.LAST_SCAN_SKIPS if "alias_of" in s]
        assert len(alias_entries) == 1
        assert alias_entries[0]["alias_of"] == "glm-5.9"
        assert alias_entries[0]["provider"] == "some-lane"

    def test_catalogued_target_does_not_resurrect_the_alias(
        self, isolated: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Even with the alias targets admitted to the catalog, the alias rows
        produce no candidates and no basename skips — the alias guard fires
        first, on the row itself."""
        monkeypatch.setattr(
            model_sync,
            "_load_chimera_models",
            lambda: {"openrouter/openai/gpt-5.6-sol", "openrouter/openai/gpt-5.6-cyber"},
        )
        candidates = _scan()
        ids = [m["model_id"] for m in _all_candidates(candidates)]
        assert "gpt-daybreak-blue-latest" not in ids
        assert "gpt-daybreak-red-latest" not in ids
        assert not [s for s in model_sync.LAST_SCAN_SKIPS if "catalog_id" in s]

    def test_alias_skips_stated_not_counted_in_diff_mode(self, isolated: dict[str, Any]) -> None:
        """--diff: alias rows are neither in the diff nor counted, but stay
        visible in the Alias Skips section."""
        candidates = _scan()
        report = model_sync.format_report(candidates, diff_only=True)
        assert "Alias Skips" in report
        assert "gpt-daybreak-blue-latest" in report
        assert "Candidates: 2 new models across 1 providers" in report
