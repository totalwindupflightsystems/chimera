"""Offline tests for scripts/litellm_pin_check.py (CH-MAINT-007).

The probe itself is NEVER executed here: every verdict-path test feeds a
synthetic child report (the JSON shape ``litellm_pin_check._child_report``
returns) straight into the pure ``derive_verdict``/``_defects`` layer, so the
suite neither needs network nor a specific installed litellm version.
One subprocess-level test proves a garbage child (non-JSON stdout) collapses
to the import-unknown shape instead of crashing the harness.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

REPO = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO / "scripts" / "litellm_pin_check.py"

#: First release with the LevelRoutingStreamHandler stdout regression.
CAP_TUPLE = (1, 100, 0)


def _load_script() -> ModuleType:
    """Load scripts/litellm_pin_check.py as a module (scripts/ is not a package)."""
    spec = importlib.util.spec_from_file_location("litellm_pin_check", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["litellm_pin_check"] = mod
    spec.loader.exec_module(mod)
    return mod


pin_check = _load_script()


def _child(
    *,
    version: str | None = "1.100.0",
    banner_fired: bool | None = True,
    banner_suppressed_ok: bool | None = True,
    feedback_fired: bool | None = False,
    info_to_stdout: bool | None = False,
    handler: str = "StreamHandler",
    import_error: str | None = None,
) -> dict:
    """A child report shaped exactly like the embedded probe emits."""
    return {
        "schema": pin_check.CHILD_SCHEMA,
        "python": "3.11.0",
        "litellm_version": version,
        "litellm_path": "/tmp/venv/lib/python3.11/site-packages/litellm",
        "suppress_flag_default": True,
        "banner": {"fired": banner_fired, "error": None},
        "banner_suppressed": {
            "fired": None if banner_suppressed_ok is None else False,
            "ok": banner_suppressed_ok,
            "error": None,
        },
        "feedback": {"fired": feedback_fired, "error": None},
        "log_routing": {
            "handler": handler,
            "info_to_stdout": info_to_stdout,
            "stderr_has_info": not info_to_stdout,
            "error": None,
        },
        "import_error": import_error,
    }


# --- pure helpers ------------------------------------------------------------


def test_parse_version_handles_common_shapes() -> None:
    assert pin_check.parse_version("1.100.0") == (1, 100, 0)
    assert pin_check.parse_version("1.99.4") == (1, 99, 4)
    assert pin_check.parse_version("1.99") == (1, 99, 0)
    assert pin_check.parse_version("v1.100.0rc1") == (1, 100, 0)
    assert pin_check.parse_version("1.100.0.post2") == (1, 100, 0)
    assert pin_check.parse_version("") is None
    assert pin_check.parse_version(None) is None
    assert pin_check.parse_version("not-a-version") is None


def test_constants_match_the_pin() -> None:
    assert pin_check.PIN_SPEC == "litellm>=1.50.0,<1.100"
    assert pin_check.VERSION_CAP == "1.100.0"
    assert pin_check.parse_version(pin_check.VERSION_CAP) == CAP_TUPLE
    assert pin_check.SCRATCH_REQUIREMENT == "litellm>=1.100.0"


def test_extract_child_json_tolerates_prefix_noise_and_scans_from_end() -> None:
    noise = "\n\x1b[1;31mProvider List: https://docs.litellm.ai/docs/providers\x1b[0m\n"
    child = _child()
    payload = json.dumps(child, sort_keys=True)
    found = pin_check._extract_child_json(f"{noise}\n{payload}\n")
    assert found is not None
    assert found["schema"] == pin_check.CHILD_SCHEMA
    # A JSON line WITHOUT the schema key must not win when a schema line exists.
    assert pin_check._extract_child_json('{"foo": 1}\n' + payload) is not None


def test_extract_child_json_returns_none_for_garbage() -> None:
    assert pin_check._extract_child_json("hello world\nno json here") is None
    assert pin_check._extract_child_json("") is None
    assert pin_check._extract_child_json('{"foo": 1}\n') is None


# --- verdict derivation: the installed-pin default run -----------------------


def test_installed_version_inside_range_is_inconclusive() -> None:
    verdict, reason = pin_check.derive_verdict(_child(version="1.99.4"), CAP_TUPLE)
    assert verdict == "INCONCLUSIVE"
    assert "INSIDE the pinned range" in reason
    assert "--scratch" in reason


def test_missing_litellm_is_inconclusive_with_import_detail() -> None:
    verdict, reason = pin_check.derive_verdict(
        _child(version=None, import_error="ModuleNotFoundError: litellm"), CAP_TUPLE
    )
    assert verdict == "INCONCLUSIVE"
    assert "not importable" in reason
    assert "ModuleNotFoundError" in reason


def test_unparseable_version_is_inconclusive() -> None:
    verdict, reason = pin_check.derive_verdict(_child(version="??unknown??"), CAP_TUPLE)
    assert verdict == "INCONCLUSIVE"
    assert "unparseable" in reason


def test_boundary_evidence_with_zero_defects_is_safe_to_test() -> None:
    child = _child(
        version="1.100.0",
        banner_fired=False,
        banner_suppressed_ok=True,
        feedback_fired=False,
        info_to_stdout=False,
    )
    verdict, reason = pin_check.derive_verdict(child, CAP_TUPLE)
    assert verdict == "SAFE_TO_TEST"
    assert "no stdout debug output" in reason
    assert "probe_mcp_stdio" in reason


def test_version_above_cap_with_zero_defects_is_safe_to_test() -> None:
    child = _child(
        version="1.104.2",
        banner_fired=False,
        banner_suppressed_ok=True,
        feedback_fired=False,
        info_to_stdout=False,
    )
    verdict, _ = pin_check.derive_verdict(child, CAP_TUPLE)
    assert verdict == "SAFE_TO_TEST"


def test_still_pinned_when_newer_litellm_prints_the_banner() -> None:
    verdict, reason = pin_check.derive_verdict(
        _child(version="1.101.0", banner_fired=True, banner_suppressed_ok=True), CAP_TUPLE
    )
    assert verdict == "STAY_PINNED"
    assert "Provider List" in reason


def test_still_pinned_when_newer_litellm_routes_logs_to_stdout() -> None:
    verdict, reason = pin_check.derive_verdict(
        _child(
            version="1.100.0", banner_fired=False, info_to_stdout=True, handler="LevelRoutingStreamHandler"
        ),
        CAP_TUPLE,
    )
    assert verdict == "STAY_PINNED"
    assert "LevelRoutingStreamHandler" in reason or "routed to stdout" in reason


def test_still_pinned_when_suppression_stops_working() -> None:
    """banner_suppressed.ok=False is a defect on ANY version — the runtime
    guard ensure_litellm_quiet() would be ineffective."""
    verdict, reason = pin_check.derive_verdict(
        _child(version="1.101.0", banner_fired=False, banner_suppressed_ok=False),
        CAP_TUPLE,
    )
    assert verdict == "STAY_PINNED"
    assert "ensure_litellm_quiet" in reason


def test_boundary_version_with_all_probes_errored_is_inconclusive() -> None:
    child = _child(
        version="1.100.0",
        banner_fired=None,
        banner_suppressed_ok=None,
        feedback_fired=None,
        info_to_stdout=None,
        handler=None,
    )
    verdict, reason = pin_check.derive_verdict(child, CAP_TUPLE)
    assert verdict == "INCONCLUSIVE"
    assert "every probe errored" in reason


def test_boundary_version_with_only_routing_answered_counts_as_answered() -> None:
    """banner/feedback resolves can fail while log_routing still answers —
    one working probe is enough for a verdict."""
    child = _child(
        version="1.100.0",
        banner_fired=None,
        feedback_fired=None,
        banner_suppressed_ok=None,
        info_to_stdout=False,
        handler="StreamHandler",
    )
    verdict, _ = pin_check.derive_verdict(child, CAP_TUPLE)
    assert verdict == "SAFE_TO_TEST"


# --- defect classification details -------------------------------------------


def test_defects_list_names_each_class() -> None:
    child = _child(
        banner_fired=True,
        banner_suppressed_ok=False,
        feedback_fired=True,
        info_to_stdout=True,
        handler="LevelRoutingStreamHandler",
    )
    defects = pin_check._defects(child)
    assert len(defects) == 4
    assert any("Provider List" in d for d in defects)
    assert any("Give Feedback" in d for d in defects)
    assert any("LevelRoutingStreamHandler" in d for d in defects)
    assert any("ensure_litellm_quiet" in d for d in defects)


def test_defects_empty_when_all_probes_clean() -> None:
    child = _child(
        banner_fired=False,
        banner_suppressed_ok=True,
        feedback_fired=False,
        info_to_stdout=False,
        handler="StreamHandler",
    )
    assert pin_check._defects(child) == []


def test_handler_class_alone_flags_the_routing_defect() -> None:
    """Even if the behavioural fd probe errored, a LevelRoutingStreamHandler
    in the handler census is the regression by name."""
    child = _child(
        banner_fired=False,
        banner_suppressed_ok=True,
        feedback_fired=False,
        info_to_stdout=None,
        handler="LevelRoutingStreamHandler",
    )
    defects = pin_check._defects(child)
    assert any("LevelRoutingStreamHandler" in d for d in defects)


# --- garbage child / spawn-failure shapes -------------------------------------


def test_spawn_failure_shape_derives_inconclusive() -> None:
    """The synthetic report _child_report builds when no JSON line is found."""
    spawned = {
        "schema": pin_check.CHILD_SCHEMA,
        "litellm_version": None,
        "import_error": None,
        "spawn": {"returncode": 1, "stderr_tail": "Segmentation fault"},
    }
    verdict, reason = pin_check.derive_verdict(spawned, CAP_TUPLE)
    assert verdict == "INCONCLUSIVE"
    assert "not importable" in reason
    assert "Segmentation fault" in reason


# --- CLI contract -------------------------------------------------------------


def test_main_default_run_is_exit_zero_with_one_json_line(capsys: object, monkeypatch: object) -> None:
    """A completed check exits 0 regardless of verdict and prints exactly one
    JSON line on stdout; the human summary goes to stderr."""
    report = {
        "schema": pin_check.REPORT_SCHEMA,
        "verdict": "INCONCLUSIVE",
        "reason": "synthetic",
        "probe_mode": "target",
        "version_cap": pin_check.VERSION_CAP,
        "pin_spec": pin_check.PIN_SPEC,
        "target_python": "/bin/true",
        "litellm_version": None,
        "detail": None,
        "harness_error": None,
    }
    calls: list[tuple] = []

    def fake_run_check(target: str | None, scratch: bool) -> dict:
        calls.append((target, scratch))
        return report

    monkeypatch.setattr(pin_check, "run_check", fake_run_check)
    rc = pin_check.main([])
    captured = capsys.readouterr()
    assert rc == 0
    assert calls == [(None, False)]
    lines = [line for line in captured.out.splitlines() if line.strip()]
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["schema"] == pin_check.REPORT_SCHEMA
    assert parsed["verdict"] == "INCONCLUSIVE"
    assert "VERDICT: INCONCLUSIVE" in captured.err


def test_main_harness_crash_exits_two() -> None:
    def exploding_run_check(target: str | None, scratch: bool) -> dict:
        raise RuntimeError("boom")

    original = pin_check.run_check
    pin_check.run_check = exploding_run_check
    try:
        rc = pin_check.main([])
    finally:
        pin_check.run_check = original
    assert rc == 2


def test_report_shape_from_run_check_installed_mode(monkeypatch: object, tmp_path: Path) -> None:
    """run_check() in installed mode returns the full parent report with the
    child detail embedded (probe subprocess mocked at the boundary)."""
    child = _child(version="1.99.4")
    monkeypatch.setattr(pin_check, "_child_report", lambda python_path: child)
    monkeypatch.setattr(pin_check, "_default_target_python", lambda: "/does/not/matter")
    report = pin_check.run_check(target=None, scratch=False)
    assert report["schema"] == pin_check.REPORT_SCHEMA
    assert report["probe_mode"] == "installed"
    assert report["litellm_version"] == "1.99.4"
    assert report["verdict"] == "INCONCLUSIVE"
    assert report["detail"]["schema"] == pin_check.CHILD_SCHEMA
    assert report["harness_error"] is None
    del tmp_path  # unused; kept for fixture symmetry


def test_scratch_mode_pip_failure_is_inconclusive_and_never_probes(
    monkeypatch: object,
) -> None:
    """Offline/degraded: pip fails -> INCONCLUSIVE, no probe run, no crash."""
    made: list[Path] = []

    def fake_scratch_venv(parent_dir: Path) -> str:
        marker = parent_dir / "venv"
        marker.mkdir()
        made.append(marker)
        return str(parent_dir / "venv" / "bin" / "python")

    probed: list[str] = []

    def fail_probe(python_path: str) -> dict:
        probed.append(python_path)
        raise AssertionError("probe must not run after a pip failure")

    monkeypatch.setattr(pin_check, "_scratch_venv_python", fake_scratch_venv)
    monkeypatch.setattr(pin_check, "_pip_install", lambda py, req: (False, "Network is unreachable"))
    monkeypatch.setattr(pin_check, "_child_report", fail_probe)
    report = pin_check.run_check(target=None, scratch=True)
    assert report["verdict"] == "INCONCLUSIVE"
    assert "pip install" in report["reason"]
    assert "Network is unreachable" in report["reason"]
    assert probed == []
    assert len(made) == 1


def test_scratch_mode_probes_the_scratch_python(monkeypatch: object, tmp_path: Path) -> None:
    probed: list[str] = []
    monkeypatch.setattr(
        pin_check,
        "_scratch_venv_python",
        lambda parent_dir: str(parent_dir / "bin" / "python"),
    )
    monkeypatch.setattr(pin_check, "_pip_install", lambda py, req: (True, ""))
    monkeypatch.setattr(
        pin_check,
        "_child_report",
        lambda python_path: (
            probed.append(python_path)
            or _child(
                version="1.100.1",
                banner_fired=False,
                banner_suppressed_ok=True,
                feedback_fired=False,
                info_to_stdout=False,
            )
        ),
    )
    report = pin_check.run_check(target=None, scratch=True)
    assert report["probe_mode"] == "scratch"
    assert len(probed) == 1
    assert probed[0].endswith("bin" + pin_check.os.sep + "python")
    assert report["verdict"] == "SAFE_TO_TEST"


def test_target_mode_failure_is_inconclusive_not_fatal(monkeypatch: object) -> None:
    def broken_child(python_path: str) -> dict:
        raise OSError("interpreter vanished")

    monkeypatch.setattr(pin_check, "_child_report", broken_child)
    report = pin_check.run_check(target="/no/such/python", scratch=False)
    assert report["verdict"] == "INCONCLUSIVE"
    assert "could not run probe" in report["reason"]
    assert report["harness_error"] is None
