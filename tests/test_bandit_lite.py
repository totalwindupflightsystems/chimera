"""Tests for ``scripts/bandit_lite.py`` — the category-score learning loop.

DF-CHIMERA-V2-104. Three things are pinned here, in the order the loop needs
them: the delta math (bounded step, floor/ceiling, insufficient-sample no-op),
what counts as an acceptance in a stored trace, and the write discipline
(dry-run touches nothing; ``--write`` moves exactly one number per adjusted
pair and refuses anything it cannot locate unambiguously).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "bandit_lite.py"

CATALOG = """\
# Fixture catalog — comments and ordering must survive a --write.
api_keys: {}

models:
  deepseek/deepseek-v4-flash:
    categories:
      technology_code/code_generation/python: 88   # measured: SWE-bench Verified
      technology_code/testing_debugging/error_analysis: 55
    cost_tier: budget
    provider: deepseek
    enabled: true

  legacy/unit-model:
    categories:
      code: 0.8
    cost_tier: standard
    provider: legacy
    enabled: true

server:
  host: 0.0.0.0
  port: 8765
"""


def _load_script() -> Any:
    spec = importlib.util.spec_from_file_location("bandit_lite_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


bandit = _load_script()


# ═══════════════════════════════════════════════════════════════════════════
#  Fixtures
# ═══════════════════════════════════════════════════════════════════════════


def stage(
    *,
    model: str = "deepseek/deepseek-v4-flash",
    kind: str = "worker",
    prompt: str = "Write a python web scraper",
    response: str = "def scrape(): ...",
    stage_id: str = "worker_0",
    **extra: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "stage_id": stage_id,
        "kind": kind,
        "model": model,
        "prompt": prompt,
        "response": response,
        "finish_reason": "stop",
    }
    payload.update(extra)
    return payload


def trace(stages: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "request_id": "req-1",
        "formation": "simple",
        "source": "preset",
        "stages": stages,
        "worker_failures": [],
    }
    payload.update(extra)
    return {"answer": "ok", "trace": payload}


def write_json(tmp_path: Path, doc: Any, name: str = "trace.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return path


def write_catalog(tmp_path: Path, text: str = CATALOG, name: str = "chimera.yaml") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def run_cli(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str, str]:
    code = bandit.main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


# ═══════════════════════════════════════════════════════════════════════════
#  Delta math
# ═══════════════════════════════════════════════════════════════════════════


class TestDeltaMath:
    def test_bounded_step_clamps_movement(self) -> None:
        """Unanimous evidence still moves at most ``step`` points."""
        up = bandit.compute_delta(40, 0, current=50.0, step=2.0)
        down = bandit.compute_delta(0, 40, current=50.0, step=2.0)
        assert up.delta == pytest.approx(2.0)
        assert up.new_score == pytest.approx(52.0)
        assert down.delta == pytest.approx(-2.0)
        assert down.new_score == pytest.approx(48.0)
        assert up.status == bandit.STATUS_ADJUSTED
        assert down.status == bandit.STATUS_ADJUSTED

    def test_delta_never_exceeds_step(self) -> None:
        for accepts in range(0, 21):
            for rejects in range(0, 21):
                decision = bandit.compute_delta(accepts, rejects, current=50.0, step=1.5)
                assert abs(decision.raw_delta) <= 1.5 + 1e-12
                assert abs(decision.delta) <= 1.5 + 1e-12

    def test_insufficient_samples_is_a_noop(self) -> None:
        """Fewer than min_samples observations must adjust NOTHING."""
        for accepts, rejects in ((0, 0), (1, 0), (3, 0), (2, 2), (0, 4)):
            decision = bandit.compute_delta(accepts, rejects, current=42.0, min_samples=5)
            assert decision.n == accepts + rejects
            assert decision.delta == 0.0
            assert decision.new_score == pytest.approx(42.0)
            assert decision.status == bandit.STATUS_INSUFFICIENT

    def test_min_samples_boundary_moves(self) -> None:
        decision = bandit.compute_delta(5, 0, current=42.0, min_samples=5, step=2.0)
        assert decision.status == bandit.STATUS_ADJUSTED
        assert decision.delta == pytest.approx(2.0)

    def test_min_samples_is_configurable(self) -> None:
        one_sample = bandit.compute_delta(1, 0, current=42.0, min_samples=1, step=2.0)
        assert one_sample.delta == pytest.approx(2.0)

    def test_neutral_evidence_does_not_move(self) -> None:
        decision = bandit.compute_delta(5, 5, current=42.0, step=2.0)
        assert decision.delta == 0.0
        assert decision.new_score == pytest.approx(42.0)
        assert decision.status == bandit.STATUS_NO_CHANGE

    def test_floor_bounds_the_result(self) -> None:
        decision = bandit.compute_delta(0, 10, current=1.0, step=2.0, floor=1.0, ceiling=99.0)
        assert decision.new_score == pytest.approx(1.0)
        assert decision.delta == 0.0
        assert decision.raw_delta == pytest.approx(-2.0)
        assert decision.status == bandit.STATUS_AT_BOUND

    def test_ceiling_bounds_the_result(self) -> None:
        decision = bandit.compute_delta(10, 0, current=99.0, step=2.0, floor=1.0, ceiling=99.0)
        assert decision.new_score == pytest.approx(99.0)
        assert decision.delta == 0.0
        assert decision.status == bandit.STATUS_AT_BOUND

    def test_partial_clamp_reports_the_applied_delta(self) -> None:
        """A step that would cross the ceiling lands on it and reports the real move."""
        decision = bandit.compute_delta(10, 0, current=98.5, step=2.0, floor=1.0, ceiling=99.0)
        assert decision.new_score == pytest.approx(99.0)
        assert decision.delta == pytest.approx(0.5)
        assert decision.raw_delta == pytest.approx(2.0)
        assert decision.status == bandit.STATUS_ADJUSTED

    def test_invalid_bounds_are_rejected(self) -> None:
        with pytest.raises(bandit.BanditError):
            bandit.compute_delta(5, 0, current=50.0, floor=90.0, ceiling=10.0)
        with pytest.raises(bandit.BanditError):
            bandit.compute_delta(5, 0, current=50.0, step=-1.0)
        with pytest.raises(bandit.BanditError):
            bandit.compute_delta(5, 0, current=50.0, min_samples=0)


# ═══════════════════════════════════════════════════════════════════════════
#  What counts as an acceptance
# ═══════════════════════════════════════════════════════════════════════════


class TestAcceptance:
    def test_answered_stage_is_accepted(self) -> None:
        accepted, reason = bandit.classify_stage(stage())
        assert accepted is True
        assert reason == "answered"

    def test_truncated_response_is_a_reject(self) -> None:
        accepted, reason = bandit.classify_stage(stage(finish_reason="length"))
        assert accepted is False
        assert reason == "truncated"

    def test_degraded_placeholder_is_a_reject(self) -> None:
        placeholder = "[stage worker_0 (deepseek/deepseek-v4-flash) unavailable: timeout]"
        accepted, reason = bandit.classify_stage(stage(response=placeholder))
        assert accepted is False
        assert reason == "degraded-placeholder"

    def test_empty_response_is_a_reject(self) -> None:
        assert bandit.classify_stage(stage(response="   \n")) == (False, "empty-response")

    def test_degraded_flag_is_a_reject(self) -> None:
        assert bandit.classify_stage(stage(degraded=True)) == (False, "degraded-flag")

    def test_worker_failure_by_stage_id_is_a_reject(self) -> None:
        rejected, reason = bandit.classify_stage(stage(stage_id="worker_7"), failed_stage_ids={"worker_7"})
        assert (rejected, reason) == (False, "worker-failure")

    def test_worker_failure_by_model_is_a_reject(self) -> None:
        rejected, reason = bandit.classify_stage(stage(model="m/x"), failed_models={"m/x"})
        assert (rejected, reason) == (False, "worker-failure")

    def test_explicit_accepted_reject_overrides_a_good_looking_response(self) -> None:
        assert bandit.classify_stage(stage(accepted=False)) == (False, "explicit-reject")

    def test_explicit_accepted_approval_overrides_a_truncation(self) -> None:
        assert bandit.classify_stage(stage(accepted=True, finish_reason="length")) == (True, "explicit")

    def test_dispatch_stage_is_not_scored(self) -> None:
        doc = trace([stage(kind="dispatch", model="deepseek/deepseek-v4-pro"), stage()])
        observations = list(bandit.iter_observations(doc))
        assert [obs.model for obs in observations] == ["deepseek/deepseek-v4-flash"]

    def test_stage_without_a_model_is_ignored(self) -> None:
        doc = trace([stage(model=""), stage(model="deepseek/deepseek-v4-flash", stage_id="worker_1")])
        assert len(list(bandit.iter_observations(doc))) == 1

    def test_worker_failures_in_the_trace_reach_the_stage(self) -> None:
        doc = trace(
            [stage(), stage(stage_id="worker_1")],
            worker_failures=[
                {"stage_id": "worker_1", "model": "deepseek/deepseek-v4-flash", "error": "boom"}
            ],
        )
        counts = bandit.aggregate(bandit.iter_observations(doc))
        tally = counts[("deepseek/deepseek-v4-flash", "technology_code/code_generation/python")]
        # The failure names ONE span: its sibling from the same model still counts.
        assert (tally.accepts, tally.rejects) == (1, 1)

    def test_failure_without_a_stage_id_falls_back_to_the_model(self) -> None:
        doc = trace(
            [stage()],
            worker_failures=[{"stage_id": "", "model": "deepseek/deepseek-v4-flash", "error": "x"}],
        )
        counts = bandit.aggregate(bandit.iter_observations(doc))
        tally = counts[("deepseek/deepseek-v4-flash", "technology_code/code_generation/python")]
        assert (tally.accepts, tally.rejects) == (0, 1)


# ═══════════════════════════════════════════════════════════════════════════
#  Categories
# ═══════════════════════════════════════════════════════════════════════════


class TestCategories:
    def test_category_is_derived_from_the_prompt(self) -> None:
        assert bandit.derive_category("Write a python web scraper") == (
            "technology_code/code_generation/python"
        )

    def test_empty_prompt_has_no_category(self) -> None:
        assert bandit.derive_category("   ") is None

    def test_explicit_stage_category_wins(self) -> None:
        doc = trace([stage(category="design")])
        categories = {obs.category for obs in bandit.iter_observations(doc)}
        assert categories == {"design"}

    def test_trace_category_applies_when_the_stage_has_none(self) -> None:
        doc = trace([stage()], category="audit")
        categories = {obs.category for obs in bandit.iter_observations(doc)}
        assert categories == {"audit"}

    def test_resolution_prefers_exact_then_parent_then_alias(self) -> None:
        exact = {"technology_code/code_generation/python": 80}
        parent = {"technology_code/code_generation": 70}
        alias = {"code": 60}
        expanded = {"technology_code": 50}
        hint = "technology_code/code_generation/python"
        assert bandit.resolve_catalog_key(exact, hint) == "technology_code/code_generation/python"
        assert bandit.resolve_catalog_key(parent, hint) == "technology_code/code_generation"
        assert bandit.resolve_catalog_key(expanded, hint) == "technology_code"
        # A short-form alias key is what the selector reads for a long hint.
        assert bandit.resolve_catalog_key(alias, hint) == "code"
        # ... and an alias hint expands to its long-form targets.
        assert bandit.resolve_catalog_key(exact, "code") == "technology_code/code_generation/python"
        assert bandit.resolve_catalog_key({"unrelated/path": 1}, hint) is None

    def test_hints_landing_on_one_key_are_merged(self) -> None:
        """Two hints resolving to the same catalog key must produce ONE delta."""
        catalog = {"m/x": {"categories": {"code": 80}}}
        tally = {
            ("m/x", "code"): bandit.Counts(accepts=3, rejects=0),
            ("m/x", "technology_code/code_generation/python"): bandit.Counts(accepts=2, rejects=0),
        }
        rows = bandit.build_plan(tally, catalog, min_samples=5, step=2.0)
        assert len(rows) == 1
        row = rows[0]
        assert row.category == "code"
        assert (row.counts.accepts, row.counts.rejects) == (5, 0)
        assert row.delta == pytest.approx(2.0)


# ═══════════════════════════════════════════════════════════════════════════
#  Loading stored traces
# ═══════════════════════════════════════════════════════════════════════════


class TestLoading:
    def test_single_document(self, tmp_path: Path) -> None:
        path = write_json(tmp_path, trace([stage()]))
        documents, warnings = bandit.load_trace_paths([path])
        assert len(documents) == 1
        assert warnings == []

    def test_list_of_documents(self, tmp_path: Path) -> None:
        path = write_json(tmp_path, [trace([stage()]), trace([stage()])])
        documents, _warnings = bandit.load_trace_paths([path])
        assert len(documents) == 2

    def test_jsonl_stream(self, tmp_path: Path) -> None:
        path = tmp_path / "runs.jsonl"
        path.write_text("\n".join(json.dumps(trace([stage()])) for _ in range(3)) + "\n", encoding="utf-8")
        documents, _warnings = bandit.load_trace_paths([path])
        assert len(documents) == 3

    def test_directory_sweep_and_dedup(self, tmp_path: Path) -> None:
        write_json(tmp_path, trace([stage()]), "a.json")
        write_json(tmp_path, trace([stage()]), "b.json")
        documents, _warnings = bandit.load_trace_paths([tmp_path, tmp_path / "a.json"])
        assert len(documents) == 2

    def test_malformed_jsonl_line_is_an_error(self, tmp_path: Path) -> None:
        path = tmp_path / "broken.jsonl"
        path.write_text(json.dumps(trace([stage()])) + "\n{not json\n", encoding="utf-8")
        with pytest.raises(bandit.BanditError, match="broken.jsonl:2"):
            bandit.load_trace_paths([path])

    def test_missing_path_is_an_error(self, tmp_path: Path) -> None:
        with pytest.raises(bandit.BanditError, match="does not exist"):
            bandit.load_trace_paths([tmp_path / "nope"])

    def test_document_without_a_trace_payload_is_skipped_with_a_warning(self, tmp_path: Path) -> None:
        write_json(tmp_path, {"unrelated": True}, "other.json")
        documents, warnings = bandit.load_trace_paths([tmp_path])
        assert documents == []
        assert len(warnings) == 1
        assert "no trace payload" in warnings[0]


# ═══════════════════════════════════════════════════════════════════════════
#  CLI: dry run, write, refusals
# ═══════════════════════════════════════════════════════════════════════════


def six_python_stages(*, accepts: int = 5, rejects: int = 1) -> list[dict[str, Any]]:
    stages = [stage(stage_id=f"worker_{i}") for i in range(accepts)]
    stages.extend(stage(stage_id=f"worker_bad_{i}", finish_reason="length") for i in range(rejects))
    return stages


class TestDryRun:
    def test_dry_run_is_the_default_and_writes_nothing(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        traces = write_json(tmp_path, trace(six_python_stages()), "run1.json")
        catalog = write_catalog(tmp_path)
        before = catalog.read_bytes()

        code, out, err = run_cli(capsys, "--traces", str(traces), "--catalog", str(catalog))

        assert code == 0, err
        assert "mode=DRY-RUN" in out
        assert "technology_code/code_generation/python" in out
        assert "+1.33" in out
        assert "1 adjustment(s) proposed, 0 written" in out
        assert catalog.read_bytes() == before, "a dry run must not touch the catalog"
        assert not list(tmp_path.glob("*.bandit-tmp")), "no temp file may survive a dry run"

    def test_write_flag_is_off_by_default(self) -> None:
        args = bandit._build_parser().parse_args(["--traces", "x"])
        assert args.write is False

    def test_insufficient_samples_leave_the_catalog_alone(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        traces = write_json(tmp_path, trace(six_python_stages(accepts=2, rejects=0)), "small.json")
        catalog = write_catalog(tmp_path)
        before = catalog.read_bytes()

        code, out, _err = run_cli(capsys, "--traces", str(traces), "--catalog", str(catalog), "--write")

        assert code == 0
        assert "insufficient-samples" in out
        assert "0 written" in out
        assert catalog.read_bytes() == before

    def test_unknown_model_is_reported_not_written(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        traces = write_json(tmp_path, trace(six_python_stages()), "run1.json")
        catalog = write_catalog(tmp_path)
        args = ["--traces", str(traces), "--catalog", str(catalog), "--json"]
        code, out, _err = run_cli(capsys, *args)
        payload = json.loads(out)
        assert code == 0
        assert [pair["status"] for pair in payload["pairs"]] == ["adjusted"]

        stranger = write_json(
            tmp_path,
            trace([stage(model="nobody/unknown", stage_id=f"w{i}") for i in range(5)]),
            "stranger.json",
        )
        code, out, _err = run_cli(capsys, "--traces", str(stranger), "--catalog", str(catalog), "--json")
        payload = json.loads(out)
        assert code == 0
        assert payload["pairs"][0]["status"] == "not-in-catalog"
        assert payload["pairs"][0]["delta"] == 0.0
        assert payload["written"] == []

    def test_json_mode_reports_the_plan(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        traces = write_json(tmp_path, trace(six_python_stages()), "run1.json")
        catalog = write_catalog(tmp_path)
        code, out, _err = run_cli(capsys, "--traces", str(traces), "--catalog", str(catalog), "--json")
        payload = json.loads(out)
        assert code == 0
        assert payload["mode"] == "dry-run"
        assert payload["write_switch"] == "--write"
        assert payload["traces"] == 1
        pair = payload["pairs"][0]
        assert pair["model"] == "deepseek/deepseek-v4-flash"
        assert pair["score"] == pytest.approx(88.0)
        assert pair["new_score"] == pytest.approx(89.33)
        assert pair["status"] == "adjusted"


class TestWrite:
    def test_write_updates_exactly_one_line(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        traces = write_json(tmp_path, trace(six_python_stages()), "run1.json")
        catalog = write_catalog(tmp_path)
        before_lines = catalog.read_text(encoding="utf-8").splitlines()
        before_models = yaml.safe_load("\n".join(before_lines))["models"]

        code, out, err = run_cli(capsys, "--traces", str(traces), "--catalog", str(catalog), "--write")

        assert code == 0, err
        assert "mode=WRITE" in out
        assert "1 written" in out
        after_lines = catalog.read_text(encoding="utf-8").splitlines()
        changed = [(old, new) for old, new in zip(before_lines, after_lines, strict=True) if old != new]
        assert len(changed) == 1, f"exactly one line may change, got {changed}"
        old, new = changed[0]
        assert old == ("      technology_code/code_generation/python: 88   # measured: SWE-bench Verified")
        assert new == ("      technology_code/code_generation/python: 89.33   # measured: SWE-bench Verified")

        after_models = yaml.safe_load(catalog.read_text(encoding="utf-8"))["models"]
        assert after_models["deepseek/deepseek-v4-flash"]["categories"][
            "technology_code/code_generation/python"
        ] == pytest.approx(89.33)
        # Everything else in the catalog survives untouched.
        for model, entry in before_models.items():
            for key, value in entry["categories"].items():
                if key == "technology_code/code_generation/python":
                    continue
                assert after_models[model]["categories"][key] == value
        assert yaml.safe_load(catalog.read_text(encoding="utf-8"))["server"]["port"] == 8765

    def test_unit_scale_catalog_scales_the_step(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A 0-1 catalog moves by 0.02, not by 2 — one run, same meaning."""
        stages = [stage(model="legacy/unit-model", stage_id=f"w{i}") for i in range(5)]
        traces = write_json(tmp_path, trace(stages), "unit.json")
        catalog = write_catalog(tmp_path)

        code, out, err = run_cli(capsys, "--traces", str(traces), "--catalog", str(catalog), "--write")

        assert code == 0, err
        assert "0.82" in out
        models = yaml.safe_load(catalog.read_text(encoding="utf-8"))["models"]
        assert models["legacy/unit-model"]["categories"]["code"] == pytest.approx(0.82)

    def test_write_refuses_a_shipped_template(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        traces = write_json(tmp_path, trace(six_python_stages()), "run1.json")
        template = write_catalog(tmp_path, name="chimera.yaml.example")
        before = template.read_bytes()

        code, _out, err = run_cli(capsys, "--traces", str(traces), "--catalog", str(template), "--write")

        assert code == 2
        assert "template" in err
        assert template.read_bytes() == before

    def test_write_refuses_a_flow_style_categories_mapping(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        flow_catalog = """\
models:
  deepseek/deepseek-v4-flash:
    categories: {technology_code/code_generation/python: 88}
    provider: deepseek
"""
        traces = write_json(tmp_path, trace(six_python_stages()), "run1.json")
        catalog = write_catalog(tmp_path, text=flow_catalog)
        before = catalog.read_bytes()

        code, _out, err = run_cli(capsys, "--traces", str(traces), "--catalog", str(catalog), "--write")

        assert code == 2
        assert "flow-style" in err
        assert catalog.read_bytes() == before, "a refused write must leave the catalog intact"

    def test_missing_catalog_is_an_error(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        traces = write_json(tmp_path, trace(six_python_stages()), "run1.json")
        code, _out, err = run_cli(capsys, "--traces", str(traces), "--catalog", str(tmp_path / "absent.yaml"))
        assert code == 2
        assert "cannot read catalog" in err

    def test_no_traces_found_is_an_error(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        catalog = write_catalog(tmp_path)
        empty = tmp_path / "traces"
        empty.mkdir()
        code, _out, err = run_cli(capsys, "--traces", str(empty), "--catalog", str(catalog))
        assert code == 2
        assert "no stored traces found" in err


class TestDocs:
    def test_help_documents_the_write_switch_and_the_default(self) -> None:
        help_text = " ".join(bandit._build_parser().format_help().split())
        assert "--write" in help_text
        assert "DRY RUN BY DEFAULT" in help_text
        assert "--min-samples" in help_text
        assert "clamp(step" in help_text

    def test_module_docstring_states_the_delta_rule(self) -> None:
        docstring = bandit.__doc__ or ""
        assert "delta = clamp(step * (a - r) / n, -step, +step)" in docstring
        assert "`--write`" in docstring or "--write" in docstring
