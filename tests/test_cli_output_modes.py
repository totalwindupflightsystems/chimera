"""DF-CHIMERA-0906-5: machine-readable CLI output — ``--quiet`` / ``--json``.

The board task: the CLI interleaved structure logs with the answer and had
no machine-readable mode at all. The log-pollution half was fixed separately
(``cli.main._load_cfg`` pins structlog/Chimera logs to stderr, commit
27f0b35); THIS file covers the output modes:

* ``--quiet``  → stdout is EXACTLY the raw answer + one newline;
* ``--json``   → stdout is EXACTLY one JSON object (``answer`` + the complete
  ``trace`` serialization);
* both are group flags, so the implicit-prompt form (``chimera --quiet
  "prompt"``) and the explicit form (``chimera --quiet run "prompt"``) honour
  them identically;
* ``--quiet --json`` is a click usage error (exit 2);
* dropped-worker and dispatch-degradation warnings are NEVER suppressed — in
  the machine modes they move to stderr, in human mode they stay beside the
  panel exactly as before.

Click 8.5's ``CliRunner`` captures stdout and stderr separately
(``result.stdout`` / ``result.stderr``; ``result.output`` is the MIXED
stream), so stream claims are made against the split properties. The
subprocess driver tests at the bottom re-prove the same claims against real
file descriptors, with no click capture in the path.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

pytest.importorskip("click")
from click.testing import CliRunner  # noqa: E402

from chimera.cli.main import main  # noqa: E402
from chimera.dispatcher import DispatchRepair  # noqa: E402
from chimera.engine import (  # noqa: E402
    DeliberationResult,
    DeliberationTrace,
    StageSpan,
    WorkerFailure,
)

REPO = Path(__file__).resolve().parent.parent

#: ANSI escape prefix — must never reach stdout in a machine mode.
ANSI = "\x1b["
#: Rich panel/table drawing characters — the human-mode answer panel uses
#: them; a machine-mode stdout containing one means Rich leaked.
RICH_GLYPHS = ("╭", "╮", "╰", "╯", "│", "─", "━", "┃")


def _span(
    stage_id: str = "worker_1",
    kind: str = "worker",
    model: str = "deepseek/deepseek-chat",
) -> StageSpan:
    return StageSpan(
        stage_id=stage_id,
        kind=kind,
        model=model,
        prompt="prompt",
        response="response",
        tokens_input=10,
        tokens_output=20,
        latency_ms=12,
        cost=0.0001,
    )


def _result(
    answer: str = "42",
    *,
    source: str = "auto",
    dispatch_note: str | None = None,
    dispatch_repairs: list[DispatchRepair] | None = None,
    worker_failures: list[WorkerFailure] | None = None,
) -> DeliberationResult:
    """A REAL pydantic result (not a SimpleNamespace) — so ``--json`` is
    exercised against the same trace object the API/web UI serialize."""
    trace = DeliberationTrace(
        request_id="req-1",
        formation="auto",
        source=source,
        dispatch=_span("dispatch", "dispatch", "zai-coding-plan/glm-5.2"),
        stages=[_span()],
        answer_stage_id="aggregator",
        total_tokens=30,
        total_cost=0.001,
        total_duration_ms=42,
        dispatch_note=dispatch_note,
        dispatch_repairs=dispatch_repairs or [],
        worker_failures=worker_failures or [],
    )
    return DeliberationResult(answer=answer, trace=trace)


def _stub_engine(monkeypatch, result: DeliberationResult, captured: dict | None = None):
    """Install a stub engine + gateway; optionally record the call."""

    class StubEngine:
        def __init__(self, *args, **kwargs):  # noqa: ANN002, ANN003
            pass

        async def deliberate(self, prompt, formation, **kwargs):  # noqa: ANN001
            if captured is not None:
                captured["prompt"] = prompt
                captured["formation"] = formation
            return result

    monkeypatch.setattr("chimera.cli.main.Engine", StubEngine)
    monkeypatch.setattr("chimera.cli.main.LiteLLMGateway", lambda *a, **k: None)


def _invoke(config_file, *args: str):  # type: ignore[no-untyped-def]
    return CliRunner().invoke(main, ["-c", str(config_file), *args])


# ---------------------------------------------------------------------------
# 1. Help surface + mutual exclusion
# ---------------------------------------------------------------------------


def test_root_help_lists_quiet_and_json() -> None:
    """Acceptance 1: the root help exposes both output-mode flags."""
    result = CliRunner().invoke(main, ["--help"])
    assert result.exit_code == 0, result.output
    assert "--quiet" in result.stdout
    assert "--json" in result.stdout


@pytest.mark.parametrize("flags", [("--quiet", "--json"), ("--json", "--quiet")])
def test_quiet_and_json_are_mutually_exclusive(
    config_file, monkeypatch, flags: tuple[str, str]
) -> None:  # type: ignore[no-untyped-def]
    """Acceptance 1: both flags together → click usage error, exit code 2."""
    captured: dict = {}
    _stub_engine(monkeypatch, _result(), captured)
    result = _invoke(config_file, *flags, "hello")

    assert result.exit_code == 2, result.output
    assert "mutually exclusive" in result.stderr
    assert "--quiet" in result.stderr
    assert "--json" in result.stderr
    assert result.stdout == ""  # nothing on stdout — not even the answer
    assert captured == {}  # no deliberation was started


def test_quiet_json_mutual_exclusion_explicit_run_form(config_file, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """The exclusion also holds for ``chimera --quiet --json run "prompt"``."""
    captured: dict = {}
    _stub_engine(monkeypatch, _result(), captured)
    result = _invoke(config_file, "--quiet", "--json", "run", "hello")
    assert result.exit_code == 2, result.output
    assert "mutually exclusive" in result.stderr
    assert captured == {}


# ---------------------------------------------------------------------------
# 2. --quiet
# ---------------------------------------------------------------------------


def _assert_machine_stdout(stdout: str) -> None:
    """No ANSI, no Rich drawing glyphs anywhere in a machine-mode stdout."""
    assert ANSI not in stdout, f"ANSI escape on stdout: {stdout!r}"
    for glyph in RICH_GLYPHS:
        assert glyph not in stdout, f"rich glyph {glyph!r} on stdout: {stdout!r}"


def test_quiet_implicit_prompt_writes_exactly_the_answer(config_file, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Acceptance 2: ``chimera --quiet "prompt"`` → stdout is answer + \\n."""
    captured: dict = {}
    _stub_engine(monkeypatch, _result("42"), captured)

    result = _invoke(config_file, "--quiet", "what is 2+2?")

    assert result.exit_code == 0, result.output
    assert result.stdout == "42\n"
    _assert_machine_stdout(result.stdout)
    assert captured["prompt"] == "what is 2+2?"
    # No trace table, no panel title.
    assert "Chimera" not in result.stdout
    assert "full trace json" not in result.stdout


def test_quiet_explicit_run_form_writes_exactly_the_answer(config_file, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Acceptance 4: ``chimera --quiet run "prompt"`` behaves identically."""
    captured: dict = {}
    _stub_engine(monkeypatch, _result("42"), captured)

    result = _invoke(config_file, "--quiet", "run", "what is 2+2?")

    assert result.exit_code == 0, result.output
    assert result.stdout == "42\n"
    _assert_machine_stdout(result.stdout)
    assert captured["prompt"] == "what is 2+2?"
    assert captured["formation"] == "auto"


def test_quiet_preserves_multiline_answer(config_file, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """A multi-line answer is emitted verbatim plus exactly one newline."""
    _stub_engine(monkeypatch, _result("line one\nline two\nline three"))
    result = _invoke(config_file, "--quiet", "hello")
    assert result.exit_code == 0, result.output
    assert result.stdout == "line one\nline two\nline three\n"


def test_quiet_preserves_unicode_answer(config_file, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """No ASCII mangling: unicode survives byte-for-hexadecimally as typed."""
    answer = "café — ¿qué? 日本語 ✅"
    _stub_engine(monkeypatch, _result(answer))
    result = _invoke(config_file, "--quiet", "hello")
    assert result.exit_code == 0, result.output
    assert result.stdout == answer + "\n"


def test_quiet_ignores_verbose_trace(config_file, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """``--quiet --verbose`` stays quiet: machine output is not upgraded to a
    trace table (documented rule — the trace is in ``--json`` instead)."""
    _stub_engine(monkeypatch, _result("42"))
    result = _invoke(config_file, "--quiet", "--verbose", "hello")
    assert result.exit_code == 0, result.output
    assert result.stdout == "42\n"
    assert "full trace json" not in result.stdout


def test_quiet_keeps_degradation_warnings_on_stderr(config_file, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Acceptance 2: dropped-worker + dispatch-degradation warnings are NOT
    suppressed in quiet mode — they are routed to stderr."""
    failure = WorkerFailure(
        stage_id="researcher",
        model="openrouter/qwen/qwen3.7-plus",
        error="No endpoints available matching your guardrail restrictions",
    )
    _stub_engine(
        monkeypatch,
        _result(
            "partial answer",
            source="fallback",
            dispatch_note="invalid_dag: dispatch produced no aggregator/merge stage",
            worker_failures=[failure],
        ),
    )

    result = _invoke(config_file, "--quiet", "hello")

    assert result.exit_code == 0, result.output
    # stdout is STILL exactly the raw answer.
    assert result.stdout == "partial answer\n"
    _assert_machine_stdout(result.stdout)
    # ... and the operational truth is on stderr, both classes.
    assert "warning" in result.stderr
    assert "worker 'researcher'" in result.stderr
    assert "guardrail" in result.stderr
    assert "dispatch degraded" in result.stderr
    assert "source=fallback" in result.stderr
    assert "invalid_dag" in result.stderr
    assert "warning" not in result.stdout


# ---------------------------------------------------------------------------
# 3. --json
# ---------------------------------------------------------------------------


def test_json_implicit_prompt_writes_one_object(config_file, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Acceptance 3: stdout is exactly one parseable JSON object."""
    result_obj = _result("42")
    _stub_engine(monkeypatch, result_obj)

    result = _invoke(config_file, "--json", "what is 2+2?")

    assert result.exit_code == 0, result.output
    _assert_machine_stdout(result.stdout)
    assert result.stdout.count("\n") == 1
    assert result.stdout.endswith("\n")

    payload = json.loads(result.stdout)
    assert set(payload) == {"answer", "trace"}
    assert payload["answer"] == "42"
    assert payload["trace"] == result_obj.trace.model_dump(mode="json")
    # The trace is COMPLETE, not a subset: every declared field is present.
    assert set(payload["trace"]) == set(DeliberationTrace.model_fields)
    assert payload["trace"]["stages"], "stage spans must survive serialization"
    assert payload["trace"]["dispatch"]["stage_id"] == "dispatch"


def test_json_explicit_run_form_writes_one_object(config_file, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Acceptance 4: ``chimera --json run "prompt"`` behaves identically."""
    captured: dict = {}
    result_obj = _result("42")
    _stub_engine(monkeypatch, result_obj, captured)

    result = _invoke(config_file, "--json", "run", "what is 2+2?")

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["answer"] == "42"
    assert payload["trace"] == result_obj.trace.model_dump(mode="json")
    assert captured["prompt"] == "what is 2+2?"


def test_json_preserves_unicode_answer(config_file, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """``ensure_ascii=False``: the answer is not escaped to \\uXXXX."""
    answer = "café — ¿qué? 日本語 ✅"
    _stub_engine(monkeypatch, _result(answer))

    result = _invoke(config_file, "--json", "hello")

    assert result.exit_code == 0, result.output
    assert answer in result.stdout  # literal unicode on the wire
    assert "\\u" not in result.stdout
    assert json.loads(result.stdout)["answer"] == answer


def test_json_keeps_degradation_warnings_on_stderr(config_file, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Acceptance 3: warnings do not corrupt the JSON document on stdout."""
    failure = WorkerFailure(
        stage_id="researcher", model="m", error="No endpoints available"
    )
    _stub_engine(
        monkeypatch,
        _result(
            "partial answer",
            source="fallback",
            dispatch_note="invalid_dag: no aggregator",
            worker_failures=[failure],
        ),
    )

    result = _invoke(config_file, "--json", "hello")

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)  # parses despite the warnings
    assert payload["answer"] == "partial answer"
    assert result.stdout.count("\n") == 1
    _assert_machine_stdout(result.stdout)
    assert "worker 'researcher'" in result.stderr
    assert "dispatch degraded" in result.stderr
    assert "warning" not in result.stdout


def test_json_has_no_rich_panel_or_trace_table(config_file, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """``--json --verbose`` still emits ONLY the JSON document."""
    _stub_engine(monkeypatch, _result("42"))
    result = _invoke(config_file, "--json", "--verbose", "hello")
    assert result.exit_code == 0, result.output
    _assert_machine_stdout(result.stdout)
    assert json.loads(result.stdout)["answer"] == "42"
    assert "full trace json" not in result.stdout
    assert "total:" not in result.stdout


#: The dispatcher's REAL repair note (``dispatcher.py`` writes the prefix).
_REPAIR_NOTE = "repaired: added aggregator stage for 2 worker terminals"


def test_json_carries_structured_dispatch_repairs(config_file, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """DF-CHIMERA-V2-5: machine-readable repair provenance reaches CLI JSON.

    A repaired dispatch used to reach ``--json`` consumers as an opaque
    free-form ``dispatch_note``; the structured ``dispatch_repairs`` list is
    now part of the trace they receive.
    """
    _stub_engine(
        monkeypatch,
        _result(
            "42",
            source="auto",
            dispatch_note=_REPAIR_NOTE,
            dispatch_repairs=[
                DispatchRepair(
                    kind="missing_aggregator",
                    action="appended_aggregator",
                    stage_ids=["aggregator"],
                    depends_on=["worker_1", "worker_2"],
                    reason=_REPAIR_NOTE,
                )
            ],
        ),
    )

    result = _invoke(config_file, "--json", "hello")

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["trace"]["dispatch_note"] == _REPAIR_NOTE
    assert payload["trace"]["dispatch_repairs"] == [
        {
            "kind": "missing_aggregator",
            "action": "appended_aggregator",
            "stage_ids": ["aggregator"],
            "depends_on": ["worker_1", "worker_2"],
            "reason": _REPAIR_NOTE,
        }
    ]


def test_verbose_trace_json_includes_dispatch_repairs(config_file, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """``--verbose``'s full-trace JSON panel shows the repair provenance."""
    _stub_engine(
        monkeypatch,
        _result(
            "42",
            source="auto",
            dispatch_note=_REPAIR_NOTE,
            dispatch_repairs=[
                DispatchRepair(
                    kind="missing_aggregator",
                    action="appended_aggregator",
                    stage_ids=["aggregator"],
                    depends_on=["worker_1", "worker_2"],
                    reason=_REPAIR_NOTE,
                )
            ],
        ),
    )

    result = _invoke(config_file, "--verbose", "hello")

    assert result.exit_code == 0, result.output
    assert "full trace json" in result.stdout
    assert '"dispatch_repairs"' in result.stdout
    assert "missing_aggregator" in result.stdout


# ---------------------------------------------------------------------------
# 4. Human modes stay backward compatible
# ---------------------------------------------------------------------------


def test_default_human_mode_still_prints_panel_and_stdout_warnings(config_file, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Acceptance 4: default mode is unchanged — boxed panel, warnings beside
    it on stdout (rich markup, no stderr reroute)."""
    failure = WorkerFailure(stage_id="worker_1", model="m", error="boom")
    _stub_engine(monkeypatch, _result("42", worker_failures=[failure]))

    result = _invoke(config_file, "hello")

    assert result.exit_code == 0, result.output
    assert "╭" in result.stdout  # the Rich panel border
    assert "Chimera" in result.stdout
    assert "42" in result.stdout
    assert "warning" in result.stdout
    assert "worker 'worker_1'" in result.stdout
    assert "warning" not in result.stderr


def test_verbose_human_mode_still_prints_trace(config_file, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Acceptance 4: ``--verbose`` keeps the trace table + full-trace panel."""
    _stub_engine(monkeypatch, _result("42"))

    result = _invoke(config_file, "--verbose", "hello")

    assert result.exit_code == 0, result.output
    assert "42" in result.stdout
    assert "Trace req-1" in result.stdout
    assert "total:" in result.stdout
    assert "full trace json" in result.stdout
    # The real trace model_dump is embedded in the panel.
    assert "req-1" in result.stdout


def test_human_mode_degradation_warning_unchanged(config_file, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """The pre-existing CH-GAP-044 warning text/stream is untouched."""
    _stub_engine(
        monkeypatch,
        _result(
            "looks-fine answer",
            source="fallback",
            dispatch_note="invalid_dag: dispatch produced no aggregator stage",
        ),
    )
    result = _invoke(config_file, "hello")
    assert result.exit_code == 0, result.output
    assert "dispatch degraded" in result.stdout
    assert "source=fallback" in result.stdout
    assert "looks-fine answer" in result.stdout


# ---------------------------------------------------------------------------
# 5. Subprocess seam — real file descriptors, no click capture
# ---------------------------------------------------------------------------

#: Driver script: stubs the engine, then invokes the REAL CLI entry point in a
#: fresh interpreter. stdout/stderr are genuine pipes, so stream separation is
#: proven end-to-end rather than through CliRunner's capture objects.
_DRIVER = textwrap.dedent(
    '''
    """Stub-engine driver for CLI output-mode stream tests (see the test file)."""

    import sys

    import chimera.cli.main as cli
    from chimera.engine import (
        DeliberationResult,
        DeliberationTrace,
        StageSpan,
        WorkerFailure,
    )


    def _span(stage_id="worker_1", kind="worker", model="deepseek/deepseek-chat"):
        return StageSpan(
            stage_id=stage_id,
            kind=kind,
            model=model,
            prompt="p",
            response="r",
            tokens_input=10,
            tokens_output=20,
            latency_ms=12,
            cost=0.0001,
        )


    class _StubEngine:
        def __init__(self, *args, **kwargs):
            pass

        async def deliberate(self, prompt, formation, **kwargs):
            trace = DeliberationTrace(
                request_id="subprocess-req",
                formation=formation,
                source="fallback",
                dispatch=_span("dispatch", "dispatch", "zai-coding-plan/glm-5.2"),
                stages=[_span()],
                answer_stage_id="aggregator",
                total_tokens=30,
                total_cost=0.001,
                total_duration_ms=42,
                dispatch_note="invalid_dag: dispatch produced no aggregator stage",
                worker_failures=[
                    WorkerFailure(
                        stage_id="researcher",
                        model="openrouter/qwen/qwen3.7-plus",
                        error="No endpoints available matching your guardrail restrictions",
                    )
                ],
            )
            return DeliberationResult(answer="subprocess café answer", trace=trace)


    cli.Engine = _StubEngine
    cli.LiteLLMGateway = lambda *a, **k: None

    cli.main.main(
        ["-c", sys.argv[1], *sys.argv[2:], "hello"],
        standalone_mode=True,
        prog_name="chimera",
    )
    '''
)


@pytest.fixture
def driver(tmp_path: Path) -> Path:
    path = tmp_path / "cli_output_driver.py"
    path.write_text(_DRIVER, encoding="utf-8")
    return path


def _run_driver(driver: Path, config_file, *flags: str) -> subprocess.CompletedProcess[str]:  # type: ignore[no-untyped-def]
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO / "src") + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, str(driver), str(config_file), *flags],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        cwd=str(REPO),
        timeout=120,
        check=False,
    )


def test_subprocess_quiet_stream_separation(driver: Path, config_file) -> None:  # type: ignore[no-untyped-def]
    """Real fds: ``--quiet`` stdout is byte-exactly the answer; warnings stderr."""
    proc = _run_driver(driver, config_file, "--quiet")

    assert proc.returncode == 0, f"{proc.stdout!r}\n{proc.stderr!r}"
    assert proc.stdout == "subprocess café answer\n"
    _assert_machine_stdout(proc.stdout)
    assert "warning" not in proc.stdout
    assert "worker 'researcher'" in proc.stderr
    assert "guardrail" in proc.stderr
    assert "dispatch degraded" in proc.stderr


def test_subprocess_json_stream_separation(driver: Path, config_file) -> None:  # type: ignore[no-untyped-def]
    """Real fds: ``--json`` stdout is one JSON document; warnings on stderr."""
    proc = _run_driver(driver, config_file, "--json")

    assert proc.returncode == 0, f"{proc.stdout!r}\n{proc.stderr!r}"
    _assert_machine_stdout(proc.stdout)
    assert proc.stdout.count("\n") == 1
    payload = json.loads(proc.stdout)
    assert payload["answer"] == "subprocess café answer"
    assert payload["trace"]["request_id"] == "subprocess-req"
    assert set(payload["trace"]) == set(DeliberationTrace.model_fields)
    assert "worker 'researcher'" in proc.stderr
    assert "warning" not in proc.stdout


def test_subprocess_human_mode_keeps_warnings_on_stdout(driver: Path, config_file) -> None:  # type: ignore[no-untyped-def]
    """Real fds: human mode is unchanged — panel + warnings on stdout."""
    proc = _run_driver(driver, config_file)

    assert proc.returncode == 0, f"{proc.stdout!r}\n{proc.stderr!r}"
    assert "╭" in proc.stdout
    assert "subprocess café answer" in proc.stdout
    assert "dispatch degraded" in proc.stdout
    assert "worker 'researcher'" in proc.stdout
    assert "warning" not in proc.stderr
