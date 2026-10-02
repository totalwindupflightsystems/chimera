"""Routable admission-key rendering tests for scripts/model_sync.py — DF-CHIMERA-V2-68.

Lane-carried candidates resolve their ``chimera_id`` against the attributed
LAB, but the lane's ``model_id`` already carries a prefix — measured live in
reports/latest.md (2026-10-01 run):

* ``openai/gpt-6.1-sol`` attributed to lab ``openai`` (carried by the
  openrouter lane) rendered ``openai/openai/gpt-6.1-sol``;
* the lane SKU ``deepseek/deepseek-v4.1-flash-fast`` attributed to lab
  ``deepseek`` rendered ``deepseek/deepseek/deepseek-v4.1-flash-fast``.

The Chimera gateway admission rule strips EXACTLY ONE leading provider
segment, so both shapes are NON-routable. The routable admission key is
``<serving-lane>/<model_id>`` (``openrouter/openai/gpt-6.1-sol``,
``deepseek/deepseek-v4.1-flash-fast``) — one strip yields exactly the id the
serving lane serves upstream.

These tests pin, entirely offline (fixture snapshot + fixture fill + fake
scorer reply — no network, no API key, no live cache, no live catalog):

* ``_routable_id`` on both measured shapes plus the no-slash case, and the
  one-strip admission property directly;
* the markdown report renders the routable key as the primary "Chimera ID"
  cell with the lane-resolved id still visible (never silently dropped) —
  in BOTH the core section (promoted lane-carried release) and the lane
  section (lane-only SKU), and the same for the plain-text format;
* every admission key rendered in a report passes the one-strip property;
* the scored-candidate YAML carries ``routable_id`` per scored model and
  never a double-prefix id as the only key — prompt shape AND the enforced
  post-reply normalization.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
import time
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from chimera.provider_discovery import RegistrySnapshot

REPO = Path(__file__).resolve().parent.parent
SYNC_PATH = REPO / "scripts" / "model_sync.py"

NOW = time.time()

#: Deliberately not key-shaped so the repo's secret scanner has nothing to match.
TEST_KEY = "routable-id-test-key-not-real"


def _load_module(name: str, path: Path) -> ModuleType:
    """Load a script as a module (scripts/ is not a package)."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


model_sync = _load_module("model_sync_routable_id", SYNC_PATH)


# --- fixtures ---------------------------------------------------------------- #


def _cand(
    model_id: str,
    chimera_id: str,
    provider: str,
    *,
    core_lab_member: bool = False,
    recency_score: float = 70.0,
    description: str = "a candidate",
) -> dict[str, Any]:
    """One candidate dict in the shape the scan produces."""
    entry: dict[str, Any] = {
        "model_id": model_id,
        "chimera_id": chimera_id,
        "family": "",
        "description": description,
        "input_cost_mtok": None,
        "output_cost_mtok": None,
        "input_per_1k": None,
        "output_per_1k": None,
        "recency_score": recency_score,
        "recency_ts": NOW,
        "provider": provider,
    }
    if core_lab_member:
        entry["core_lab_member"] = True
    return entry


#: The measured openrouter-lane shape (acceptance criterion 1): prefixed
#: model_id attributed to its own lab, chimera_id double-prefixed.
OPENROUTER_ROW = _cand(
    "openai/gpt-6.1-sol",
    "openai/openai/gpt-6.1-sol",
    "openrouter",
    core_lab_member=True,
)

#: The measured deepseek lane-SKU shape (acceptance criterion 2).
DEEPSEEK_SKU_ROW = _cand(
    "deepseek/deepseek-v4.1-flash-fast",
    "deepseek/deepseek/deepseek-v4.1-flash-fast",
    "deepseek",
)

#: The no-slash (already-routable) control shape.
BARE_ROW = _cand("gpt-6.1-sol", "openai/gpt-6.1-sol", "openai")


def _row(model_id: str, *, in_price: float | None = None, out_price: float | None = None) -> dict[str, Any]:
    """One task-router-shaped model row (empty family = the lane-row shape)."""
    entry: dict[str, Any] = {"id": model_id, "family": ""}
    if in_price is not None or out_price is not None:
        entry["cost"] = {"input": in_price, "output": out_price}
    return entry


@pytest.fixture()
def isolated_scan(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, Any]:
    """Offline scan harness — the measured 09-30/10-01 lane-carried shapes.

    xkiro carries the prefixed ``openai/gpt-6.1-sol`` (priced — the SAME core
    release, promoted); commandcode carries its bare twin ``gpt-6.1-sol``
    (no pricing — the priced twin wins) and the lane-only SKU
    ``deepseek/deepseek-v4.1-flash-fast``. The models.dev fill holds the
    openai core block (promotion signal) and a deepseek block WITHOUT the
    flash-fast SKU.
    """
    snapshot = RegistrySnapshot(
        data={
            "commandcode": {
                "id": "commandcode",
                "models": {
                    "gpt-6.1-sol": _row("gpt-6.1-sol"),
                    "deepseek/deepseek-v4.1-flash-fast": _row("deepseek/deepseek-v4.1-flash-fast"),
                },
            },
            "xkiro": {
                "id": "xkiro",
                "models": {"openai/gpt-6.1-sol": _row("openai/gpt-6.1-sol", in_price=2.0, out_price=10.0)},
            },
        },
        source="task-router",
        path=Path("/fake/models.jsonl"),
    )
    fill = {
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
    seen_path = tmp_path / "seen_models.json"
    monkeypatch.setattr(model_sync, "load_preferred_registry", lambda **_: snapshot)
    monkeypatch.setattr(model_sync, "_load_cache", lambda *a, **k: fill)
    monkeypatch.setattr(model_sync, "_load_models_dev_registry", lambda **_: fill)
    monkeypatch.setattr(model_sync, "_load_chimera_models", lambda: {"deepseek/deepseek-v4.1-flash"})
    monkeypatch.setattr(model_sync, "SEEN_PATH", seen_path)
    return {"seen_path": seen_path}


@pytest.fixture()
def seen_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Scratch seen-file for format_report-only tests."""
    seen_path = tmp_path / "seen_models.json"
    monkeypatch.setattr(model_sync, "SEEN_PATH", seen_path)
    return seen_path


#: One markdown table row's first two backticked cells: model, admission key.
TABLE_ROW = re.compile(r"^\| `([^`]+)` \| `([^`]+)` \|", re.MULTILINE)


def _upstream_id(row: dict[str, Any]) -> str:
    """The id the row's serving lane serves upstream (lane-prefix collapsed)."""
    lane = row.get("provider") or row["chimera_id"].split("/", 1)[0]
    mid = row["model_id"]
    return mid[len(lane) + 1 :] if mid.startswith(f"{lane}/") else mid


def _admission_keys(report: str) -> list[tuple[str, str]]:
    """(model_id, admission-key) pairs from every rendered markdown table row."""
    return TABLE_ROW.findall(report)


# --- A: the helper contract ---------------------------------------------------- #


class TestRoutableIdHelper:
    def test_prefixed_lane_row_yields_serving_lane_prefix(self) -> None:
        """Acceptance shape 1: model_id already carries a prefix, so the
        routable key is <serving-lane>/<model_id>, never the lab-doubled id."""
        assert model_sync._routable_id(OPENROUTER_ROW) == "openrouter/openai/gpt-6.1-sol"

    def test_lane_sku_yields_single_prefix(self) -> None:
        """Acceptance shape 2: the lane SKU's routable key strips the doubled
        lab segment — never ``deepseek/deepseek/deepseek-v4.1-flash-fast``."""
        rid = model_sync._routable_id(DEEPSEEK_SKU_ROW)
        assert rid == "deepseek/deepseek-v4.1-flash-fast"
        assert rid != "deepseek/deepseek/deepseek-v4.1-flash-fast"

    def test_no_slash_model_id_is_already_routable(self) -> None:
        """Bare model_id: the lane-resolved chimera_id IS the admission key."""
        assert model_sync._routable_id(BARE_ROW) == "openai/gpt-6.1-sol"

    def test_missing_provider_falls_back_to_chimera_prefix(self) -> None:
        row = {"model_id": "openai/gpt-6.1-sol", "chimera_id": "openai/openai/gpt-6.1-sol"}
        # Fallback lane = chimera_id's first segment ("openai"); model_id
        # already carries it, so the collapse makes model_id itself the key.
        assert model_sync._routable_id(row) == "openai/gpt-6.1-sol"
        row_bare = {"model_id": "gpt-6.1-sol", "chimera_id": "openai/gpt-6.1-sol"}
        assert model_sync._routable_id(row_bare) == "openai/gpt-6.1-sol"

    @pytest.mark.parametrize("row", [OPENROUTER_ROW, DEEPSEEK_SKU_ROW, BARE_ROW])
    def test_one_strip_yields_the_upstream_servable_id(self, row: dict[str, Any]) -> None:
        """THE admission property: stripping EXACTLY ONE leading segment from
        the routable key yields the id the serving lane serves upstream."""
        rid = model_sync._routable_id(row)
        lane, upstream = rid.split("/", 1)
        assert lane == row["provider"]
        assert upstream == _upstream_id(row)


# --- B: markdown report rendering ----------------------------------------------- #


class TestMarkdownReport:
    def test_prefixed_lane_row_renders_routable_key_with_lane_resolved_visible(self, seen_file: Path) -> None:
        """Acceptance criterion 1: admission key is openrouter/..., the
        non-routable openai/openai/... stays visible (second column)."""
        report = model_sync.format_report({"openai": [OPENROUTER_ROW]}, markdown=True)
        assert "| Model | Chimera ID | Lane-resolved | Recency |" in report
        assert (
            "| `openai/gpt-6.1-sol` | `openrouter/openai/gpt-6.1-sol` | `openai/openai/gpt-6.1-sol` |"
            in report
        )

    def test_lane_sku_never_renders_the_double_prefix_as_admission_key(self, seen_file: Path) -> None:
        """Acceptance criterion 2 (report side): the admission cell carries
        the single-prefix key; the triple-prefix appears ONLY lane-resolved."""
        report = model_sync.format_report({"deepseek": [DEEPSEEK_SKU_ROW]}, markdown=True)
        assert (
            "| `deepseek/deepseek-v4.1-flash-fast` | `deepseek/deepseek-v4.1-flash-fast` | "
            "`deepseek/deepseek/deepseek-v4.1-flash-fast` |" in report
        )
        keys = dict(_admission_keys(report))
        assert keys["deepseek/deepseek-v4.1-flash-fast"] == "deepseek/deepseek-v4.1-flash-fast"
        assert "deepseek/deepseek/deepseek-v4.1-flash-fast" not in keys.values()

    def test_no_slash_row_keeps_the_single_column_table(self, seen_file: Path) -> None:
        """Non-lane rows are UNCHANGED: same chimera_id, same 5-column table."""
        report = model_sync.format_report({"openai": [BARE_ROW]}, markdown=True)
        assert "Lane-resolved" not in report
        assert "| `gpt-6.1-sol` | `openai/gpt-6.1-sol` |" in report

    def test_every_rendered_admission_key_passes_the_one_strip_property(self, seen_file: Path) -> None:
        """Acceptance criterion 3: parse every table row of a mixed report and
        verify one strip of the admission key yields the row's model_id."""
        candidates = {
            "openai": [OPENROUTER_ROW, BARE_ROW],
            "deepseek": [DEEPSEEK_SKU_ROW],
        }
        report = model_sync.format_report(candidates, markdown=True)
        keys = _admission_keys(report)
        assert len(keys) == 3
        for model_id, admission_key in keys:
            upstream = admission_key.split("/", 1)[1]
            assert model_id == upstream or model_id.endswith(f"/{upstream}")

    def test_text_format_renders_routable_key_with_inline_note(self, seen_file: Path) -> None:
        report = model_sync.format_report({"openai": [OPENROUTER_ROW]})
        assert "openrouter/openai/gpt-6.1-sol" in report
        assert "lane-resolved=openai/openai/gpt-6.1-sol" in report


# --- C: end-to-end scan → report ------------------------------------------------- #


class TestScanToReport:
    def test_promoted_release_renders_routable_key_in_the_core_section(
        self, isolated_scan: dict[str, Any]
    ) -> None:
        """The lane-carried core release (promoted into the openai section)
        renders xkiro/openai/gpt-6.1-sol — its serving lane's prefix."""
        report = model_sync.format_report(model_sync.scan_models_dev(), markdown=True)
        core_body = report.split("Task-Router Lane Providers")[0]
        assert "`xkiro/openai/gpt-6.1-sol`" in core_body
        assert "`openai/openai/gpt-6.1-sol`" in core_body  # lane-resolved, still visible

    def test_lane_sku_renders_routable_key_in_the_lane_section(self, isolated_scan: dict[str, Any]) -> None:
        report = model_sync.format_report(model_sync.scan_models_dev(), markdown=True)
        lane_body = report.split("Task-Router Lane Providers")[1]
        assert "`commandcode/deepseek/deepseek-v4.1-flash-fast`" in lane_body
        keys = dict(_admission_keys(lane_body))
        assert "deepseek/deepseek/deepseek-v4.1-flash-fast" not in keys.values()

    def test_scanned_report_keys_all_pass_the_one_strip_property(self, isolated_scan: dict[str, Any]) -> None:
        report = model_sync.format_report(model_sync.scan_models_dev(), markdown=True)
        keys = _admission_keys(report)
        assert keys  # the scan produced rendered rows
        for model_id, admission_key in keys:
            upstream = admission_key.split("/", 1)[1]
            assert model_id == upstream or model_id.endswith(f"/{upstream}")


# --- D: scored-candidate YAML ----------------------------------------------------- #


def _score_candidates() -> dict[str, list[dict[str, Any]]]:
    return {"openai": [OPENROUTER_ROW], "deepseek": [DEEPSEEK_SKU_ROW]}


class TestScoredYaml:
    def test_prompt_carries_the_routable_key_as_the_scored_id(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The scorer prompt names the routable key (lane-resolved id as an
        inline note) and asks for a ``routable_id`` field back."""
        captured: dict[str, str] = {}

        def fake_reply(prompt: str, api_key: str, post: Any = None) -> dict[str, Any]:
            captured["prompt"] = prompt
            return {"models": []}

        monkeypatch.setattr(model_sync, "_score_llm_reply", fake_reply)
        monkeypatch.setattr(model_sync, "REPO_ROOT", tmp_path)
        monkeypatch.setenv("DEEPSEEK_API_KEY", TEST_KEY)

        model_sync._llm_score_candidates(_score_candidates())

        prompt = captured["prompt"]
        assert '"routable_id"' in prompt
        assert (
            "- `openrouter/openai/gpt-6.1-sol` (lane-resolved chimera_id: `openai/openai/gpt-6.1-sol`)"
            in prompt
        )
        assert "- `deepseek/deepseek-v4.1-flash-fast`" in prompt
        # The double-prefix shapes never appear as the scored id line.
        assert "- `openai/openai/gpt-6.1-sol`" not in prompt
        assert "- `deepseek/deepseek/deepseek-v4.1-flash-fast`" not in prompt

    def test_written_yaml_carries_routable_id_per_scored_model(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The YAML contract is ENFORCED: even a reply that echoes only the
        legacy chimera_id gets its routable_id written in from the candidate
        record — never a double-prefix id as the only key."""
        import yaml as yaml_lib

        def fake_reply(prompt: str, api_key: str, post: Any = None) -> dict[str, Any]:
            return {
                "models": [
                    {  # legacy echo: chimera_id only — must be backfilled
                        "chimera_id": "openai/openai/gpt-6.1-sol",
                        "cost_tier": "standard",
                        "scores": {"coding/backend": 80},
                        "reasoning": "legacy echo",
                    },
                    {  # obedient echo: routable_id present
                        "routable_id": "deepseek/deepseek-v4.1-flash-fast",
                        "cost_tier": "budget",
                        "scores": {"chat/casual": 70},
                        "reasoning": "obedient echo",
                    },
                ]
            }

        monkeypatch.setattr(model_sync, "_score_llm_reply", fake_reply)
        monkeypatch.setattr(model_sync, "REPO_ROOT", tmp_path)
        monkeypatch.setenv("DEEPSEEK_API_KEY", TEST_KEY)

        model_sync._llm_score_candidates(_score_candidates())

        score_files = list((tmp_path / "reports").glob("model_scores_*.yaml"))
        assert len(score_files) == 1
        scored = yaml_lib.safe_load(score_files[0].read_text(encoding="utf-8"))
        by_routable = {m["routable_id"]: m for m in scored["models"]}
        assert set(by_routable) == {
            "openrouter/openai/gpt-6.1-sol",
            "deepseek/deepseek-v4.1-flash-fast",
        }
        # The lane-resolved id is kept alongside, never rendered AS the key.
        assert by_routable["openrouter/openai/gpt-6.1-sol"]["chimera_id"] == "openai/openai/gpt-6.1-sol"
        # Every YAML admission key passes the one-strip property.
        upstreams = {_upstream_id(m) for rows in _score_candidates().values() for m in rows}
        for routable_id in by_routable:
            assert routable_id.split("/", 1)[1] in upstreams

    def test_attach_routable_ids_tolerates_unmatched_and_malformed_entries(self) -> None:
        scored = {
            "models": [
                {"chimera_id": "hallucinated/model", "scores": {}},
                "not-a-dict",
                {"chimera_id": "openai/openai/gpt-6.1-sol", "scores": {}},
            ]
        }
        out = model_sync._attach_routable_ids(scored, [OPENROUTER_ROW])
        assert out["models"][0] == {"chimera_id": "hallucinated/model", "scores": {}}  # untouched
        assert out["models"][1] == "not-a-dict"
        assert out["models"][2]["routable_id"] == "openrouter/openai/gpt-6.1-sol"

    def test_attach_routable_ids_no_models_key_is_a_noop(self) -> None:
        assert model_sync._attach_routable_ids({"unexpected": 1}, [OPENROUTER_ROW]) == {"unexpected": 1}


# --- E: seen-ledger identity is unchanged ------------------------------------------ #


class TestSeenLedgerUnchanged:
    def test_seen_records_the_lane_resolved_id_not_the_routable_key(self, seen_file: Path) -> None:
        """The seen ledger keeps the lane-resolved chimera_id identity (the
        --diff comparison contract of DF-CHIMERA-V2-64/67) — only the RENDER
        changes."""
        model_sync.format_report({"openai": [OPENROUTER_ROW]}, diff_only=True)
        seen = json.loads(seen_file.read_text())
        assert "openai/openai/gpt-6.1-sol" in seen
        assert "openrouter/openai/gpt-6.1-sol" not in seen
