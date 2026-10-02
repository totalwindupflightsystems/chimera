"""``--diff`` seen-filter basename resolution — DF-CHIMERA-V2-64.

``.seen_models.json`` records the id a candidate carried on the day it was
first seen, but the candidate's ``chimera_id`` is the LANE-resolved id: the
same model reaches a later run under a different prefix shape. Measured
2026-09-26 (``reports/latest.md``: "Candidates: 7 new models"): only one row
was a first appearance — the other six were re-reports.

    openai/openai/gpt-6-sol     after seen  openai/gpt-6-sol
    openai/openai/gpt-6-luna    after seen  openai/gpt-6-luna
    xai/x-ai/grok-4.7           after seen  xai/grok-4.7
    xai/xai/grok-4.7            same model, second lane
    zai/z-ai/glm-5.3-flashx     after seen  zai/glm-5.3-flashx
    stepfun/stepfun/Step-5-Preview  after seen  stepfun/step-5-preview

The fix gives the seen comparison the same basename resolution the catalog-hit
dedupe received in DF-CHIMERA-V2-50 (both use the one ``_basename`` helper),
without weakening the filter: equality on the WHOLE trailing segment, never a
prefix, so a plain entry for ``openai/gpt-6-sol`` still does not cover
``openai/gpt-6-sol-mini``.

These tests are entirely offline (scratch seen-file, no network, no API key,
no live ``.seen_models.json``). They pin:

* both id shapes of one model match a single seen entry (the acceptance
  contract) and the measured 2026-09-26 rows are covered;
* the plain-entry filter is NOT weakened to prefix matching;
* the marker entries of DF-CHIMERA-V2-50 keep working, in both directions;
* ``format_report()`` drops the lane-shaped re-report from ``--diff`` (and from
  the saved ``--diff-json`` set the cron pipeline scores) while a genuinely-new
  basename still reports;
* the comparison reuses the one ``_basename`` helper.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

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


model_sync = _load_module("model_sync_seen", SYNC_PATH)


def _core_candidate(chimera_id: str, provider: str = "openai") -> dict[str, Any]:
    """A core candidate dict in the exact shape scan_models_dev() produces."""
    return {
        "model_id": chimera_id.rsplit("/", 1)[-1],
        "chimera_id": chimera_id,
        "family": "gpt",
        "description": "",
        "input_cost_mtok": 0.3,
        "output_cost_mtok": 1.2,
        "input_per_1k": 0.0003,
        "output_per_1k": 0.0012,
        "recency_score": 100.0,
        "recency_ts": None,
        "provider": provider,
    }


@pytest.fixture()
def isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, Any]:
    """Offline harness: a scratch seen-file and a clean skip trail.

    ``LAST_BASENAME_SKIPS`` is a module global written by a scan; clearing it
    keeps a sibling test's scan from leaking SKIP lines (and seen entries) into
    the reports formatted here.
    """
    seen_path = tmp_path / "seen_models.json"
    monkeypatch.setattr(model_sync, "SEEN_PATH", seen_path)
    monkeypatch.setattr(model_sync, "LAST_BASENAME_SKIPS", [])
    return {"seen_path": seen_path}


def _write_seen(isolated: dict[str, Any], entries: list[str]) -> None:
    isolated["seen_path"].write_text(json.dumps(entries), encoding="utf-8")


# --- the acceptance contract ------------------------------------------------ #


def test_both_lane_id_shapes_match_one_seen_entry() -> None:
    """DF-CHIMERA-V2-64 acceptance: both id shapes cover one seen entry."""
    seen = {"openai/gpt-6-sol"}
    for candidate_id in ["openai/openai/gpt-6-sol", "openai/gpt-6-sol"]:
        assert model_sync._seen_match(candidate_id, seen) is not None


def test_measured_2026_09_26_re_reports_are_covered() -> None:
    """Every re-report row of the 2026-09-26 run now matches a seen entry."""
    seen = {
        "openai/gpt-6-sol",
        "openai/gpt-6-luna",
        "xai/grok-4.7",
        "zai/glm-5.3-flashx",
        "stepfun/step-5-preview",
    }
    for row_id in (
        "openai/openai/gpt-6-sol",
        "openai/openai/gpt-6-luna",
        "xai/x-ai/grok-4.7",
        "xai/xai/grok-4.7",
        "zai/z-ai/glm-5.3-flashx",
        "stepfun/stepfun/Step-5-Preview",  # case-insensitive: the lane changed casing too
    ):
        assert model_sync._seen_match(row_id, seen) is not None, row_id

    # The one genuine first appearance of that run stays a new find.
    assert model_sync._seen_match("anthropic/anthropic/claude-opus-5.5", seen) is None


def test_reverse_direction_bare_candidate_matches_lane_shaped_seen_entry() -> None:
    """The recorded shape may be the lane-shaped one; the bare row still matches."""
    seen = {"openai/openai/gpt-6-sol"}
    assert model_sync._seen_match("openai/gpt-6-sol", seen) == "openai/openai/gpt-6-sol"


def test_empty_seen_matches_nothing() -> None:
    assert model_sync._seen_match("openai/gpt-6-sol", set()) is None


# --- the filter is NOT weakened to prefix matching -------------------------- #


@pytest.mark.parametrize(
    "candidate",
    [
        "openai/gpt-6-sol-mini",  # longer basename
        "openai/gpt-6-sol-turbo",
        "openai/gpt-6-sola",
        "openai/gpt-6-sol.1",
        "openai/gpt-6",  # SHORTER basename must not match a longer entry either
        "openai/openai/gpt-6-sol-mini",  # lane prefix AND a longer basename
    ],
)
def test_plain_entry_never_covers_a_different_basename(candidate: str) -> None:
    """A plain seen entry covers exactly one basename — never a prefix of one."""
    assert model_sync._seen_match(candidate, {"openai/gpt-6-sol"}) is None


def test_sibling_model_that_shares_no_basename_stays_new() -> None:
    """The pre-existing exact-id behaviour of DF-CHIMERA-V2-50 is unchanged."""
    assert model_sync._seen_match("google/foo-v3", {"google/foo-v2"}) is None


# --- DF-CHIMERA-V2-50 marker entries keep working --------------------------- #


def test_seen_entry_id_strips_the_basename_marker() -> None:
    assert model_sync._seen_entry_id("minimax/minimax-m3 [basename=openrouter/minimax/minimax-m3]") == (
        "minimax/minimax-m3"
    )
    assert model_sync._seen_entry_id("plain/id") == "plain/id"


def test_marked_entry_matches_by_marker_and_by_basename() -> None:
    """A marked entry is consumed both ways — marker id and basename."""
    marked = "openai/openai/gpt-6-sol [basename=openrouter/openai/gpt-6-sol]"
    assert model_sync._seen_match("openai/openai/gpt-6-sol", {marked}) is not None  # marker branch
    assert model_sync._seen_match("openai/gpt-6-sol", {marked}) is not None  # basename branch


def test_marker_branch_does_not_prefix_match_a_longer_id() -> None:
    """The marker branch also requires the WHOLE id, not a prefix of one."""
    marked = "openai/gpt-6-sol [basename=openrouter/openai/gpt-6-sol]"
    assert model_sync._seen_match("openai/gpt-6-sol-mini", {marked}) is None


# --- format_report: the diff filter and the [NEW] tag ----------------------- #


def test_diff_report_drops_the_lane_shaped_re_report(isolated: dict[str, Any]) -> None:
    """The measured defect: the re-report no longer reaches the --diff report."""
    _write_seen(isolated, ["openai/gpt-6-sol"])
    candidates = {"openai": [_core_candidate("openai/openai/gpt-6-sol")]}

    report = model_sync.format_report(candidates, diff_only=True)

    assert "Candidates: 0 new models" in report
    assert "openai/openai/gpt-6-sol" not in report


def test_diff_report_keeps_a_genuinely_new_basename(isolated: dict[str, Any]) -> None:
    """Control: a distinct basename in the same provider row is still reported."""
    _write_seen(isolated, ["openai/gpt-6-sol"])
    candidates = {
        "openai": [
            _core_candidate("openai/openai/gpt-6-sol"),  # re-report — filtered
            _core_candidate("openai/gpt-6-sol-mini"),  # distinct basename — new
        ]
    }

    report = model_sync.format_report(candidates, diff_only=True)

    assert "Candidates: 1 new models across 1 providers" in report
    assert "openai/openai/gpt-6-sol " not in report and "| `openai/openai/gpt-6-sol` |" not in report
    assert "openai/gpt-6-sol-mini" in report


def test_full_report_does_not_tag_the_lane_shaped_row_as_new(isolated: dict[str, Any]) -> None:
    """The full report's [NEW] tag consumes the same comparison."""
    _write_seen(isolated, ["openai/gpt-6-sol"])
    candidates = {
        "openai": [
            _core_candidate("openai/openai/gpt-6-sol"),  # already seen under the bare id
            _core_candidate("openai/gpt-6-sol-mini"),  # genuinely new
        ]
    }

    report = model_sync.format_report(candidates)

    tagged = [ln for ln in report.splitlines() if "[NEW]" in ln]
    assert len(tagged) == 1
    assert "openai/gpt-6-sol-mini" in tagged[0]


def test_diff_filter_reuses_the_one_basename_helper(
    isolated: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The seen comparison goes through THE ``_basename`` helper (no second copy)."""
    calls: list[str] = []
    original = model_sync._basename

    def spy(model_id: str) -> str:
        calls.append(model_id)
        return original(model_id)

    monkeypatch.setattr(model_sync, "_basename", spy)
    _write_seen(isolated, ["openai/gpt-6-sol"])

    model_sync.format_report({"openai": [_core_candidate("openai/openai/gpt-6-sol")]}, diff_only=True)

    assert "openai/openai/gpt-6-sol" in calls


# --- the cron pipeline's saved diff set (``--diff-json``) ------------------- #


def test_diff_json_saved_set_excludes_the_lane_shaped_re_report(
    isolated: dict[str, Any], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Step 1 of the cron pipeline saves the same set the printed diff shows."""
    _write_seen(isolated, ["openai/gpt-6-sol"])
    candidates = {
        "openai": [
            _core_candidate("openai/openai/gpt-6-sol"),  # re-report — excluded
            _core_candidate("openai/gpt-6-sol-mini"),  # new — saved
        ]
    }
    monkeypatch.setattr(
        model_sync,
        "scan_all",
        lambda: (candidates, [], [], {"core": [], "reseller": [], "out_of_scope": 0}),
    )
    out_json = tmp_path / "out" / "diff.json"
    monkeypatch.setattr(sys, "argv", ["model_sync.py", "--diff", "--diff-json", str(out_json)])

    model_sync.main()

    saved = json.loads(out_json.read_text(encoding="utf-8"))
    saved_ids = [m["chimera_id"] for models in saved.values() for m in models]
    assert saved_ids == ["openai/gpt-6-sol-mini"]


# --- backward compatibility of the seen file -------------------------------- #


def test_plain_seen_file_is_still_consumed_verbatim(isolated: dict[str, Any]) -> None:
    """A pre-change file (plain id strings) needs no migration."""
    _write_seen(isolated, ["openai/gpt-6-sol", "minimax/minimax-m3"])

    seen = model_sync._load_seen()

    assert seen == {"openai/gpt-6-sol", "minimax/minimax-m3"}
    assert model_sync._seen_match("openai/gpt-6-sol", seen) == "openai/gpt-6-sol"


# --- DF-CHIMERA-V2-66: "Pending — seen, not catalogued" --------------------- #
#
# The --diff seen filter silences a candidate the moment it enters the ledger
# — whether it was ADMITTED to the catalog or ignored. Verified live
# 2026-10-02: openrouter/anthropic/claude-opus-5.5 was verified and
# recommended ADD on 2026-09-24/25/26, never applied, and never re-reported.
# The --diff report now carries a "Pending — seen, not catalogued" section
# listing every ledger id that resolves to NO catalog entry, so the
# seen-but-never-admitted backlog stays visible until admitted or dismissed.


def _pending_block(report: str) -> list[str]:
    """The lines of the "Pending — seen, not catalogued" section (only)."""
    lines = report.splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.startswith("## Pending"))
    block: list[str] = []
    for ln in lines[start:]:
        if block and (ln.startswith("## ") or ln.startswith("---")):
            break
        block.append(ln)
    return block


def _run_main_diff(
    monkeypatch: pytest.MonkeyPatch,
    catalog: set[str],
    candidates: dict[str, Any] | None = None,
) -> None:
    """One offline ``--diff`` CLI run: stubbed scan, pinned catalog, clean skips."""
    monkeypatch.setattr(model_sync, "_load_chimera_models", lambda: set(catalog))
    monkeypatch.setattr(model_sync, "LAST_SCAN_SKIPS", [])
    monkeypatch.setattr(
        model_sync,
        "scan_all",
        lambda: (candidates or {}, [], [], {"core": [], "reseller": [], "out_of_scope": 0}),
    )
    monkeypatch.setattr(sys, "argv", ["model_sync.py", "--diff"])
    model_sync.main()


# (a) an uncatalogued-but-seen id IS reported


def test_pending_uncatalogued_seen_id_is_reported(
    isolated: dict[str, Any], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """DF-CHIMERA-V2-66 acceptance: the silent-opus-5.5 class cannot recur."""
    _write_seen(isolated, ["openrouter/anthropic/claude-opus-5.5"])

    _run_main_diff(monkeypatch, catalog=set())
    out = capsys.readouterr().out

    assert "## Pending — seen, not catalogued" in out
    assert any("openrouter/anthropic/claude-opus-5.5" in ln for ln in _pending_block(out))


# (b) an admitted (catalogued) id is NOT reported — including the openrouter
# normalization: the ledger id is namespaced, the catalog entry is bare.


def test_pending_admitted_id_is_not_reported(
    isolated: dict[str, Any], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An openrouter/* ledger id normalizes to its bare form for the catalog check."""
    _write_seen(isolated, ["openrouter/anthropic/claude-opus-5.5"])

    _run_main_diff(monkeypatch, catalog={"anthropic/claude-opus-5.5"})
    block = _pending_block(capsys.readouterr().out)

    assert any(ln.startswith("None") for ln in block)
    assert not any("claude-opus-5.5" in ln for ln in block)


# (c) idempotence / stability across two consecutive runs


def test_pending_section_is_idempotent_across_runs(
    isolated: dict[str, Any], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """No duplicate rows, deterministic sort, identical output on a re-run."""
    _write_seen(
        isolated,
        ["openrouter/anthropic/claude-opus-5.5", "openai/gpt-6-sol", "minimax/minimax-m3"],
    )

    _run_main_diff(monkeypatch, catalog={"openai/gpt-6-sol"})
    first = _pending_block(capsys.readouterr().out)
    _run_main_diff(monkeypatch, catalog={"openai/gpt-6-sol"})
    second = _pending_block(capsys.readouterr().out)

    assert first == second
    rows = [ln.strip() for ln in first if ln.strip().startswith(("openrouter/", "minimax/"))]
    assert rows == ["minimax/minimax-m3", "openrouter/anthropic/claude-opus-5.5"]
    assert len(rows) == len(set(rows))


def test_pending_excludes_this_runs_new_find(
    isolated: dict[str, Any], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The section is the BACKLOG: a find reported in this same run is not
    double-listed as pending — it joins on the NEXT run if still unadmitted."""
    _write_seen(isolated, ["openai/gpt-6-sol"])
    candidates = {"openai": [_core_candidate("openai/gpt-6-sol-mini")]}

    _run_main_diff(monkeypatch, catalog=set(), candidates=candidates)
    block = _pending_block(capsys.readouterr().out)

    assert any("openai/gpt-6-sol" in ln for ln in block if "mini" not in ln)
    assert not any("gpt-6-sol-mini" in ln for ln in block)


# the helper itself


def test_pending_helper_normalizes_openrouter_ids_to_basename() -> None:
    """Catalog membership is decided on the basename, via the shared helper."""
    seen = {"openrouter/anthropic/claude-opus-5.5"}
    assert model_sync._pending_seen_not_catalogued(seen, {"anthropic/claude-opus-5.5"}) == []
    assert model_sync._pending_seen_not_catalogued(seen, set()) == ["openrouter/anthropic/claude-opus-5.5"]


def test_pending_helper_strips_markers_and_never_prefix_matches() -> None:
    """A marked skip entry resolves against its stripped id; equality only."""
    marked = "minimax/minimax-m3 [basename=openrouter/minimax/minimax-m3]"
    assert model_sync._pending_seen_not_catalogued({marked}, {"openrouter/minimax/minimax-m3"}) == []
    # A catalogued foo-v2 never covers a seen foo-v3 (whole-basename equality).
    assert model_sync._pending_seen_not_catalogued({"google/foo-v3"}, {"google/foo-v2"}) == ["google/foo-v3"]


def test_pending_helper_dedupes_marker_and_plain_twins_and_sorts() -> None:
    """A plain entry and its marked twin strip to ONE row; output is sorted."""
    seen = {"b/model-x", "b/model-x [basename=z/model-x]", "a/model-y"}
    assert model_sync._pending_seen_not_catalogued(seen, set()) == ["a/model-y", "b/model-x"]


def test_pending_helper_reuses_the_one_basename_helper(monkeypatch: pytest.MonkeyPatch) -> None:
    """The pending comparison goes through THE ``_basename`` helper (no second copy)."""
    calls: list[str] = []
    original = model_sync._basename

    def spy(model_id: str) -> str:
        calls.append(model_id)
        return original(model_id)

    monkeypatch.setattr(model_sync, "_basename", spy)

    model_sync._pending_seen_not_catalogued(
        {"openrouter/anthropic/claude-opus-5.5"}, {"anthropic/claude-opus-5.5"}
    )

    assert "openrouter/anthropic/claude-opus-5.5" in calls


# format_report rendering


def test_format_report_renders_pending_section_markdown(isolated: dict[str, Any]) -> None:
    report = model_sync.format_report(
        {}, diff_only=True, markdown=True, pending_seen=["openrouter/anthropic/claude-opus-5.5"]
    )
    assert "## Pending — seen, not catalogued" in report
    assert "- `openrouter/anthropic/claude-opus-5.5`" in report


def test_format_report_renders_empty_pending_section(isolated: dict[str, Any]) -> None:
    report = model_sync.format_report({}, diff_only=True, pending_seen=[])
    assert "## Pending — seen, not catalogued" in report
    assert "None — every seen id resolves to a catalog entry." in report


def test_pending_section_requires_the_caller_supplied_list(isolated: dict[str, Any]) -> None:
    """Back-compat: callers that pass no pending list get no section at all."""
    report = model_sync.format_report({}, diff_only=True)
    assert "Pending" not in report
