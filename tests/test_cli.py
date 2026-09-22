"""Tests for the Click + Rich CLI."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("click")
from click.testing import CliRunner  # noqa: E402

from chimera.cli.main import _elide_worker_error, _repair_note_detail, main  # noqa: E402
from chimera.config import load_config  # noqa: E402

# ---------------------------------------------------------------------------
# Existing tests (unchanged)
# ---------------------------------------------------------------------------


def test_cli_formations(config_file) -> None:  # type: ignore[no-untyped-def]
    runner = CliRunner()
    result = runner.invoke(main, ["-c", str(config_file), "formations"])
    assert result.exit_code == 0
    assert "simple" in result.output
    assert "debate" in result.output


def test_cli_models(config_file) -> None:  # type: ignore[no-untyped-def]
    runner = CliRunner()
    result = runner.invoke(main, ["-c", str(config_file), "models"])
    assert result.exit_code == 0
    assert "deepseek/deepseek-chat" in result.output
    assert "code" in result.output  # category column header


def test_cli_bare_prompt_routes_to_run(config_file, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from types import SimpleNamespace

    captured = {}

    class StubEngine:
        def __init__(self, *a, **k):
            pass

        async def deliberate(self, prompt, formation):  # noqa: ANN001
            captured["prompt"] = prompt
            captured["formation"] = formation
            span = SimpleNamespace(
                stage_id="dispatch",
                kind="dispatch",
                model="m",
                tokens_input=1,
                tokens_output=2,
                latency_ms=5,
                cost=0.0,
            )
            trace = SimpleNamespace(
                request_id="r1",
                dispatch=span,
                stages=[],
                total_tokens=3,
                total_duration_ms=9,
                total_cost=0.0,
                source="auto",
                answer_stage_id="aggregator",
                worker_failures=[],
            )
            return SimpleNamespace(answer="42", trace=trace)

    monkeypatch.setattr("chimera.cli.main.Engine", StubEngine)
    monkeypatch.setattr("chimera.cli.main.LiteLLMGateway", lambda *a, **k: None)
    runner = CliRunner()
    result = runner.invoke(main, ["-c", str(config_file), "what is 2+2?"])
    assert result.exit_code == 0, result.output
    assert "42" in result.output
    assert captured["prompt"] == "what is 2+2?"
    assert captured["formation"] == "auto"


def test_cli_formation_option_passed(config_file, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    captured = {}

    class StubEngine:
        def __init__(self, *a, **k):
            pass

        async def deliberate(self, prompt, formation):  # noqa: ANN001
            captured["formation"] = formation
            raise SystemExit(0)

    monkeypatch.setattr("chimera.cli.main.Engine", StubEngine)
    monkeypatch.setattr("chimera.cli.main.LiteLLMGateway", lambda *a, **k: None)
    runner = CliRunner()
    runner.invoke(main, ["-c", str(config_file), "-f", "debate", "some prompt"])
    assert captured["formation"] == "debate"


def test_cli_no_args_shows_help() -> None:  # type: ignore[no-untyped-def]
    runner = CliRunner()
    result = runner.invoke(main, [])
    assert result.exit_code == 0
    assert "Usage:" in result.output


def test_cli_missing_config_errors(config_file, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr("chimera.cli.main.Engine", lambda *a, **k: None)
    monkeypatch.setattr("chimera.cli.main.LiteLLMGateway", lambda *a, **k: None)
    runner = CliRunner()
    result = runner.invoke(main, ["-c", "/no/such/chimera.yaml", "prompt"])
    assert result.exit_code == 2


# ---------------------------------------------------------------------------
# New tests for uncovered lines
# ---------------------------------------------------------------------------

# === 1. _parse_json_opt error path (lines 100-103) ===


def test_cli_invalid_dag_json(config_file) -> None:
    """--dag with invalid JSON raises click.BadParameter (exit code 2)."""
    runner = CliRunner()
    result = runner.invoke(main, ["-c", str(config_file), "--dag", "not-json", "prompt"])
    assert result.exit_code == 2
    assert "must be valid JSON" in result.output


def test_cli_invalid_stage_models_json(config_file) -> None:
    """--stage-models with invalid JSON raises click.BadParameter (exit code 2)."""
    runner = CliRunner()
    result = runner.invoke(main, ["-c", str(config_file), "--stage-models", "bad-json", "prompt"])
    assert result.exit_code == 2
    assert "must be valid JSON" in result.output


# === 2. _deliberate empty prompt path (lines 113-115) ===


def test_cli_empty_prompt_shows_help(config_file) -> None:
    """Empty prompt (no args to run subcommand) shows help text."""
    runner = CliRunner()
    result = runner.invoke(main, ["-c", str(config_file), "run"])
    assert result.exit_code == 0
    assert "Usage:" in result.output


# === 3. _deliberate stage_models override path (lines 128-131) ===


def test_cli_stage_models_forwarded(config_file, monkeypatch) -> None:
    """--stage-models is forwarded as DeliberationOverrides to engine.deliberate."""
    from chimera.config import DeliberationOverrides

    captured: dict = {}

    class StubEngine:
        def __init__(self, *a, **k):
            pass

        async def deliberate(self, prompt, formation, **kwargs):  # noqa: ANN001
            captured["kwargs"] = kwargs
            span = SimpleNamespace(
                stage_id="dispatch",
                kind="dispatch",
                model="m",
                tokens_input=1,
                tokens_output=2,
                latency_ms=5,
                cost=0.0,
            )
            trace = SimpleNamespace(
                request_id="r1",
                dispatch=span,
                stages=[],
                total_tokens=3,
                total_duration_ms=9,
                total_cost=0.0,
                source="auto",
                answer_stage_id="aggregator",
            )
            return SimpleNamespace(answer="ok", trace=trace)

    monkeypatch.setattr("chimera.cli.main.Engine", StubEngine)
    monkeypatch.setattr("chimera.cli.main.LiteLLMGateway", lambda *a, **k: None)
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "-c",
            str(config_file),
            "--stage-models",
            '{"stage1":"model1"}',
            "prompt",
        ],
    )
    assert result.exit_code == 0, result.output
    overrides = captured["kwargs"]["overrides"]
    assert isinstance(overrides, DeliberationOverrides)
    assert overrides.stage_models == {"stage1": "model1"}


# === 4. _deliberate dag override path (lines 132-134) ===


def test_cli_dag_forwarded(config_file, monkeypatch) -> None:
    """--dag and --allow-custom-dag are forwarded to engine.deliberate."""
    captured: dict = {}
    dag_dict = {"stages": [{"id": "s1", "kind": "worker", "model": "m1", "depends_on": []}], "edges": []}

    class StubEngine:
        def __init__(self, *a, **k):
            pass

        async def deliberate(self, prompt, formation, **kwargs):  # noqa: ANN001
            captured["kwargs"] = kwargs
            span = SimpleNamespace(
                stage_id="dispatch",
                kind="dispatch",
                model="m",
                tokens_input=1,
                tokens_output=2,
                latency_ms=5,
                cost=0.0,
            )
            trace = SimpleNamespace(
                request_id="r1",
                dispatch=span,
                stages=[],
                total_tokens=3,
                total_duration_ms=9,
                total_cost=0.0,
                source="auto",
                answer_stage_id="aggregator",
            )
            return SimpleNamespace(answer="ok", trace=trace)

    monkeypatch.setattr("chimera.cli.main.Engine", StubEngine)
    monkeypatch.setattr("chimera.cli.main.LiteLLMGateway", lambda *a, **k: None)
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "-c",
            str(config_file),
            "--dag",
            json.dumps(dag_dict),
            "--allow-custom-dag",
            "prompt",
        ],
    )
    assert result.exit_code == 0, result.output
    assert captured["kwargs"]["dag"] == dag_dict
    assert captured["kwargs"]["allow_custom_dag"] is True


# === 5. _deliberate ValueError handler (lines 139-141) ===


def test_cli_value_error_handled(config_file, monkeypatch) -> None:
    """Engine.deliberate raising ValueError prints error and exits with code 2."""

    class StubEngine:
        def __init__(self, *a, **k):
            pass

        async def deliberate(self, prompt, formation, **kwargs):  # noqa: ANN001
            raise ValueError("something went wrong in deliberation")

    monkeypatch.setattr("chimera.cli.main.Engine", StubEngine)
    monkeypatch.setattr("chimera.cli.main.LiteLLMGateway", lambda *a, **k: None)
    runner = CliRunner()
    result = runner.invoke(main, ["-c", str(config_file), "fail prompt"])
    assert result.exit_code == 2
    assert "error:" in result.output
    assert "something went wrong in deliberation" in result.output


def test_cli_unknown_stage_model_exits_2(config_file, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """--stage-models with an unknown stage id fails fast (DF-CHIMERA-V2-32).

    Real engine + stubbed gateway: the engine's ValueError surfaces through
    the CLI's existing handler as `error: ...` + exit 2 — never a normal
    answer with the override silently dropped.
    """
    from tests.conftest import FakeGateway

    monkeypatch.setattr(
        "chimera.cli.main.LiteLLMGateway",
        lambda *a, **k: FakeGateway(None),
    )
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "-c",
            str(config_file),
            "--stage-models",
            '{"no_such_stage":"deepseek/deepseek-chat"}',
            "prompt",
        ],
    )
    assert result.exit_code == 2, result.output
    assert "error:" in result.output
    assert "no_such_stage" in result.output


# === 6 + 7. _deliberate verbose trace + _print_trace (lines 143-175) ===


def test_cli_verbose_trace(config_file, monkeypatch) -> None:
    """--verbose flag prints the deliberation trace with all expected fields."""
    span = SimpleNamespace(
        stage_id="dispatch",
        kind="dispatch",
        model="deepseek/deepseek-chat",
        tokens_input=50,
        tokens_output=100,
        latency_ms=500,
        cost=0.002,
    )
    stage1 = SimpleNamespace(
        stage_id="worker_1",
        kind="worker",
        model="claude-3",
        tokens_input=100,
        tokens_output=200,
        latency_ms=1000,
        cost=0.005,
    )
    trace = SimpleNamespace(
        request_id="trace-abc-123",
        dispatch=span,
        stages=[stage1],
        total_tokens=350,
        total_duration_ms=1500,
        total_cost=0.007,
        source="cli",
        answer_stage_id="aggregator",
        model_dump=lambda mode: {"request_id": "trace-abc-123", "answer_stage_id": "aggregator"},
    )

    class StubEngine:
        def __init__(self, *a, **k):
            pass

        async def deliberate(self, prompt, formation, **kwargs):  # noqa: ANN001
            return SimpleNamespace(answer="verbose answer", trace=trace)

    monkeypatch.setattr("chimera.cli.main.Engine", StubEngine)
    monkeypatch.setattr("chimera.cli.main.LiteLLMGateway", lambda *a, **k: None)
    runner = CliRunner()
    result = runner.invoke(main, ["-c", str(config_file), "--verbose", "hello"])
    assert result.exit_code == 0, result.output

    # Answer panel
    assert "verbose answer" in result.output

    # Trace table title
    assert "trace-abc-123" in result.output

    # Summary line
    assert "total:" in result.output
    assert "350 tokens" in result.output
    assert "1500ms" in result.output
    assert "$0.007000" in result.output or "$0.007" in result.output
    assert "source=cli" in result.output
    assert "answer_stage=aggregator" in result.output

    # Full trace JSON panel
    assert "full trace json" in result.output


def test_cli_verbose_no_stages(config_file, monkeypatch) -> None:
    """--verbose with zero stages still prints trace (covers empty stages loop)."""
    span = SimpleNamespace(
        stage_id="dispatch",
        kind="dispatch",
        model="gpt-4",
        tokens_input=10,
        tokens_output=20,
        latency_ms=100,
        cost=0.001,
    )
    trace = SimpleNamespace(
        request_id="r2",
        dispatch=span,
        stages=[],
        total_tokens=30,
        total_duration_ms=100,
        total_cost=0.001,
        source="cli",
        answer_stage_id="aggregator",
        model_dump=lambda mode: {"request_id": "r2"},
    )

    class StubEngine:
        def __init__(self, *a, **k):
            pass

        async def deliberate(self, prompt, formation, **kwargs):  # noqa: ANN001
            return SimpleNamespace(answer="no stages answer", trace=trace)

    monkeypatch.setattr("chimera.cli.main.Engine", StubEngine)
    monkeypatch.setattr("chimera.cli.main.LiteLLMGateway", lambda *a, **k: None)
    runner = CliRunner()
    result = runner.invoke(main, ["-c", str(config_file), "--verbose", "hi"])
    assert result.exit_code == 0, result.output
    assert "r2" in result.output
    assert "total:" in result.output


# === 8. serve command (lines 243-252) ===


def _capture_run_api(captured: dict) -> object:
    """Return a callable that records (host, port) into *captured*."""

    def _run(host, port):
        captured.update({"host": host, "port": port})

    return _run


def _capture_run_mcp(captured: dict) -> object:
    """Return a callable that records config_path + parse_argv into *captured*."""

    def _run(config_path, parse_argv=True):  # type: ignore[no-untyped-def]
        captured.update({"config_path": config_path, "parse_argv": parse_argv})

    return _run


def test_cli_serve_with_host_port(config_file, monkeypatch) -> None:
    """serve --host and --port are forwarded to run_api."""
    captured: dict = {}
    monkeypatch.setattr("chimera.api.server.run", _capture_run_api(captured))
    runner = CliRunner()
    result = runner.invoke(main, ["-c", str(config_file), "serve", "--host", "0.0.0.0", "--port", "9999"])
    assert result.exit_code == 0, result.output
    assert captured["host"] == "0.0.0.0"
    assert captured["port"] == 9999


def test_cli_serve_defaults_from_config(config_file, monkeypatch) -> None:
    """serve without --host/--port uses config file defaults."""
    captured: dict = {}
    monkeypatch.setattr("chimera.api.server.run", _capture_run_api(captured))
    runner = CliRunner()
    result = runner.invoke(main, ["-c", str(config_file), "serve"])
    assert result.exit_code == 0, result.output
    # Config fixture has server.host="127.0.0.1", server.port=8000
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 8000


def test_cli_serve_env_var_fallback(config_file, monkeypatch) -> None:
    """serve honours CHIMERA_HOST / CHIMERA_PORT env vars when no --host/--port given."""
    captured: dict = {}
    monkeypatch.setattr("chimera.api.server.run", _capture_run_api(captured))
    monkeypatch.setenv("CHIMERA_HOST", "0.0.0.0")
    monkeypatch.setenv("CHIMERA_PORT", "3000")
    runner = CliRunner()
    result = runner.invoke(main, ["-c", str(config_file), "serve"])
    assert result.exit_code == 0, result.output
    assert captured["host"] == "0.0.0.0"
    assert captured["port"] == 3000


# === 9. mcp command (lines 257-261) ===


def test_cli_mcp(config_file, monkeypatch) -> None:
    """mcp command forwards config_path to chimera.mcp.server.run."""
    captured: dict = {}
    monkeypatch.setattr("chimera.mcp.server.run", _capture_run_mcp(captured))
    runner = CliRunner()
    result = runner.invoke(main, ["-c", str(config_file), "mcp"])
    assert result.exit_code == 0, result.output
    assert captured == {"config_path": str(config_file), "parse_argv": False}


def test_cli_mcp_no_config(config_file, monkeypatch) -> None:
    """mcp command passes None config_path when -c is not given."""
    captured: dict = {}
    monkeypatch.setattr("chimera.mcp.server.run", _capture_run_mcp(captured))
    runner = CliRunner()
    result = runner.invoke(main, ["mcp"])
    assert result.exit_code == 0, result.output
    assert captured == {"config_path": None, "parse_argv": False}


# ---------------------------------------------------------------------------
# Dropped-worker CLI warning (C1) — always printed, not just --verbose
# ---------------------------------------------------------------------------


def _stub_engine_with_failures(monkeypatch, failures):  # type: ignore[no-untyped-def]
    class StubEngine:
        def __init__(self, *a, **k):
            pass

        async def deliberate(self, prompt, formation):  # noqa: ANN001
            span = SimpleNamespace(
                stage_id="dispatch",
                kind="dispatch",
                model="m",
                tokens_input=1,
                tokens_output=2,
                latency_ms=5,
                cost=0.0,
            )
            trace = SimpleNamespace(
                request_id="r1",
                dispatch=span,
                stages=[],
                total_tokens=3,
                total_duration_ms=9,
                total_cost=0.0,
                source="auto",
                answer_stage_id="aggregator",
                worker_failures=failures,
            )
            return SimpleNamespace(answer="partial answer", trace=trace)

    monkeypatch.setattr("chimera.cli.main.Engine", StubEngine)
    monkeypatch.setattr("chimera.cli.main.LiteLLMGateway", lambda *a, **k: None)


def test_cli_warns_about_dropped_workers_without_verbose(config_file, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    failure = SimpleNamespace(
        stage_id="researcher",
        model="openrouter/qwen/qwen3.7-plus",
        error="No endpoints available matching your guardrail restrictions",
    )
    _stub_engine_with_failures(monkeypatch, [failure])
    runner = CliRunner()
    # NOTE: no --verbose flag — the warning must appear regardless.
    result = runner.invoke(main, ["-c", str(config_file), "hello"])
    assert result.exit_code == 0, result.output
    assert "warning" in result.output
    assert "researcher" in result.output
    assert "openrouter/qwen/qwen3.7-plus" in result.output
    assert "guardrail" in result.output
    # The (partial) answer panel still prints.
    assert "partial answer" in result.output


def test_cli_no_worker_warning_when_all_healthy(config_file, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _stub_engine_with_failures(monkeypatch, [])
    runner = CliRunner()
    result = runner.invoke(main, ["-c", str(config_file), "hello"])
    assert result.exit_code == 0, result.output
    assert "warning" not in result.output


def test_cli_worker_warning_truncates_long_errors(config_file, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    failure = SimpleNamespace(
        stage_id="worker_1",
        model="m",
        error="x" * 500,
    )
    _stub_engine_with_failures(monkeypatch, [failure])
    runner = CliRunner()
    result = runner.invoke(main, ["-c", str(config_file), "hello"])
    assert result.exit_code == 0, result.output
    assert "x" * 500 not in result.output  # truncated to ~200 chars
    assert "x" * 100 in result.output


# ---------------------------------------------------------------------------
# Dispatch degradation CLI warning (CH-GAP-044) — always printed, not --verbose
# ---------------------------------------------------------------------------


def _stub_engine_with_trace(monkeypatch, source, dispatch_note):  # type: ignore[no-untyped-def]
    class StubEngine:
        def __init__(self, *a, **k):
            pass

        async def deliberate(self, prompt, formation):  # noqa: ANN001
            span = SimpleNamespace(
                stage_id="dispatch",
                kind="dispatch",
                model="m",
                tokens_input=1,
                tokens_output=2,
                latency_ms=5,
                cost=0.0,
            )
            trace = SimpleNamespace(
                request_id="r1",
                dispatch=span,
                stages=[],
                total_tokens=3,
                total_duration_ms=9,
                total_cost=0.0,
                source=source,
                answer_stage_id="aggregator",
                worker_failures=[],
                dispatch_note=dispatch_note,
            )
            return SimpleNamespace(answer="looks-fine answer", trace=trace)

    monkeypatch.setattr("chimera.cli.main.Engine", StubEngine)
    monkeypatch.setattr("chimera.cli.main.LiteLLMGateway", lambda *a, **k: None)


def test_cli_warns_on_fallback_without_verbose(config_file, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """CH-GAP-044: a silent source=fallback is surfaced as a prominent warning.

    The answer can look fine while the dispatch collapsed to a generic
    single-worker formation — before this fix the CLI never flagged it.
    """
    _stub_engine_with_trace(
        monkeypatch,
        source="fallback",
        dispatch_note="invalid_dag: dispatch produced no aggregator/merge/audit stage",
    )
    runner = CliRunner()
    # NOTE: no --verbose flag — the degradation warning must appear regardless.
    result = runner.invoke(main, ["-c", str(config_file), "hello"])
    assert result.exit_code == 0, result.output
    assert "warning" in result.output
    assert "dispatch degraded" in result.output
    assert "source=fallback" in result.output
    assert "invalid_dag" in result.output
    # The answer panel still prints normally.
    assert "looks-fine answer" in result.output


def test_cli_warns_on_dispatch_repair_without_verbose(config_file, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """CH-GAP-044: a repaired dispatch (injected aggregator) is surfaced too."""
    _stub_engine_with_trace(
        monkeypatch,
        source="auto",
        dispatch_note=(
            "repaired: injected aggregator stage(s) aggregator "
            "referenced by dispatcher edges but missing from stages"
        ),
    )
    runner = CliRunner()
    result = runner.invoke(main, ["-c", str(config_file), "hello"])
    assert result.exit_code == 0, result.output
    assert "warning" in result.output
    assert "dispatch repaired" in result.output
    assert "injected aggregator stage" in result.output
    assert "looks-fine answer" in result.output


def test_cli_no_degradation_warning_when_clean(config_file, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """A clean auto dispatch (no note) prints no degradation warning."""
    _stub_engine_with_trace(monkeypatch, source="auto", dispatch_note=None)
    runner = CliRunner()
    result = runner.invoke(main, ["-c", str(config_file), "hello"])
    assert result.exit_code == 0, result.output
    assert "dispatch degraded" not in result.output
    assert "dispatch repaired" not in result.output


# ---------------------------------------------------------------------------
# DF-CHIMERA-V2-5: warning rendering — the dispatch-repair prefix must not be
# duplicated, and a long worker error must not be cut mid-token in silence.
# Both defects were hit by a real dogfood run and made a correct answer look
# suspicious.
# ---------------------------------------------------------------------------

#: The upstream error a real dogfood run printed. The old fixed 197-char slice
#: cut it inside "every" ("... so eve..."), dropping the words that named the
#: restriction and never saying the message had been shortened.
_LONG_GUARDRAIL_ERROR = (
    "No endpoints available matching your guardrail restrictions and data "
    "policy restrictions for model openrouter/qwen/qwen3.7-plus: this account "
    "has not opted into prompt-training data sharing, so every endpoint for "
    "that model is filtered out."
)

#: The dispatcher's REAL repair note — ``dispatcher.py`` writes the
#: ``repaired: `` prefix itself, which is why the CLI's own label duplicated it.
_DISPATCHER_REPAIR_NOTE = (
    "repaired: injected aggregator stage(s) aggregator referenced by "
    "dispatcher edges but missing from stages (1 edge target)"
)


def _flat(output: str) -> str:
    """Collapse Rich's word wrapping so assertions can match across folds."""
    return " ".join(output.split())


def test_cli_dispatch_repair_warning_is_not_double_prefixed(config_file, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """DF-CHIMERA-V2-5: the note already self-describes — label it once.

    Before the fix a real run printed
    ``warning: dispatch repaired: repaired: injected aggregator ...``: the
    duplicated token reads like a second, unexplained repair.
    """
    _stub_engine_with_trace(monkeypatch, source="auto", dispatch_note=_DISPATCHER_REPAIR_NOTE)
    runner = CliRunner()
    result = runner.invoke(main, ["-c", str(config_file), "hello"])
    assert result.exit_code == 0, result.output
    assert "repaired: repaired" not in result.output
    assert result.output.count("repaired") == 1  # exactly one repaired token
    assert (
        "warning: dispatch repaired: injected aggregator stage(s) aggregator "
        "referenced by dispatcher edges but missing from stages (1 edge target)"
    ) in _flat(result.output)
    assert "looks-fine answer" in result.output


def test_cli_dispatch_repair_warning_keeps_a_note_without_the_prefix(config_file, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """A note that does not self-describe still carries the CLI's label."""
    _stub_engine_with_trace(
        monkeypatch,
        source="auto",
        dispatch_note="injected aggregator stage for 2 worker terminals",
    )
    runner = CliRunner()
    result = runner.invoke(main, ["-c", str(config_file), "hello"])
    assert result.exit_code == 0, result.output
    assert ("warning: dispatch repaired: injected aggregator stage for 2 worker terminals") in _flat(
        result.output
    )
    assert result.output.count("repaired") == 1


def test_cli_dispatch_repair_warning_does_not_mangle_other_words(config_file, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """``repairedness ...`` merely contains the substring — leave it alone."""
    _stub_engine_with_trace(
        monkeypatch,
        source="auto",
        dispatch_note="repairedness check found a dangling edge",
    )
    runner = CliRunner()
    result = runner.invoke(main, ["-c", str(config_file), "hello"])
    assert result.exit_code == 0, result.output
    assert ("warning: dispatch repaired: repairedness check found a dangling edge") in _flat(result.output)


@pytest.mark.parametrize(
    ("note", "expected"),
    [
        # Real dispatcher payload: prefix stripped, payload intact.
        (_DISPATCHER_REPAIR_NOTE, _DISPATCHER_REPAIR_NOTE[len("repaired: ") :]),
        (
            "repaired: added aggregator stage for 2 worker terminal",
            "added aggregator stage for 2 worker terminal",
        ),
        ("REPAIRED: added aggregator stage", "added aggregator stage"),
        # A doubled prefix is fully collapsed (never "repaired: repaired").
        ("repaired: repaired: doubly patched", "doubly patched"),
        # A bare prefix carries no detail.
        ("repaired", ""),
        ("repaired:", ""),
        # Not a repair token: no string surgery on other words.
        (
            "injected aggregator stage for 2 worker terminals",
            "injected aggregator stage for 2 worker terminals",
        ),
        ("repairedness check found a dangling edge", "repairedness check found a dangling edge"),
    ],
)
def test_repair_note_detail_strips_only_a_leading_repair_token(note: str, expected: str) -> None:
    assert _repair_note_detail(note) == expected


def test_cli_worker_warning_cuts_long_errors_on_a_word_boundary(config_file, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """DF-CHIMERA-V2-5: no mid-token chop, an explicit marker, a pointer to the trace."""
    failure = SimpleNamespace(
        stage_id="w1",
        model="openrouter/qwen/qwen3.7-plus",
        error=_LONG_GUARDRAIL_ERROR,
    )
    _stub_engine_with_failures(monkeypatch, [failure])
    runner = CliRunner()
    result = runner.invoke(main, ["-c", str(config_file), "hello"])
    assert result.exit_code == 0, result.output
    flat = _flat(result.output)
    assert len(_LONG_GUARDRAIL_ERROR) > 200  # the fixture must exceed the budget
    match = re.search(r"failed: (.*?)\.\.\. \[truncated (\d+) chars\]", flat)
    assert match, flat
    head, omitted = match.group(1), int(match.group(2))
    # The cut landed ON whitespace and the head ends with a complete word —
    # the old render ended "... data sharing, so eve...".
    assert _LONG_GUARDRAIL_ERROR.startswith(head)
    assert _LONG_GUARDRAIL_ERROR[len(head)] == " "
    assert head.rsplit(" ", 1)[-1] in _LONG_GUARDRAIL_ERROR.split()
    assert not head.endswith("eve")
    assert len(head) <= 200
    # The elision is explicit and the dropped text is not silently lost.
    assert omitted == len(_LONG_GUARDRAIL_ERROR) - len(head)
    assert _LONG_GUARDRAIL_ERROR not in flat
    # ... and the warning says where the complete message lives.
    assert "full error" in flat
    assert "--json" in flat
    assert str(len(_LONG_GUARDRAIL_ERROR)) in flat


def test_cli_worker_warning_short_error_is_unchanged(config_file, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """DF-CHIMERA-V2-5: an error within the budget renders exactly as before."""
    short = "upstream 503: the provider refused the request"
    exact = ("blocked " * 24) + "12345678"  # exactly 200 chars
    assert len(exact) == 200
    for error in (short, exact):
        _stub_engine_with_failures(monkeypatch, [SimpleNamespace(stage_id="w2", model="m", error=error)])
        runner = CliRunner()
        result = runner.invoke(main, ["-c", str(config_file), "hello"])
        assert result.exit_code == 0, result.output
        assert "truncated" not in result.output
        assert "full error" not in result.output
        assert _elide_worker_error(error) == (error, 0)
        assert f"warning: worker 'w2' (m) failed: {error}" in _flat(result.output)


def test_elide_worker_error_cuts_on_a_word_boundary_and_counts_the_rest() -> None:
    rendered, omitted = _elide_worker_error(_LONG_GUARDRAIL_ERROR)
    assert omitted > 0
    head = rendered.split("... [truncated")[0]
    assert _LONG_GUARDRAIL_ERROR.startswith(head)
    assert _LONG_GUARDRAIL_ERROR[len(head)] == " "
    assert omitted == len(_LONG_GUARDRAIL_ERROR) - len(head)
    # The longest word-boundary prefix inside the budget: no gratuitous loss.
    budget = _LONG_GUARDRAIL_ERROR[:200]
    assert head == budget[: budget.rfind(" ")].rstrip()
    assert rendered.endswith(f"... [truncated {omitted} chars]")


def test_elide_worker_error_passes_short_errors_through_byte_identically() -> None:
    for error in ("", "boom", "guardrail refused", "x" * 199, "y" * 200):
        assert _elide_worker_error(error) == (error, 0)


def test_elide_worker_error_bounds_an_unbreakable_token() -> None:
    """One token longer than the budget has no boundary to cut at (documented)."""
    rendered, omitted = _elide_worker_error("z" * 500)
    assert rendered == "z" * 200 + "... [truncated 300 chars]"
    assert omitted == 300


def test_cli_worker_warning_renders_bracket_text_verbatim(config_file, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Upstream ``[...]`` text is not Rich markup — it must render verbatim.

    Without escaping, Rich parses a bracketed run as a style tag and DROPS it,
    which is how the first cut of this fix silently ate its own
    ``[truncated N chars]`` marker.
    """
    cases = [
        "[Errno 111] Connection refused while contacting the provider",
        ("[Errno 111] " + "connection refused " * 12).strip(),
    ]
    assert len(cases[1]) > 200  # the long case also carries the marker
    for error in cases:
        _stub_engine_with_failures(monkeypatch, [SimpleNamespace(stage_id="w3", model="m", error=error)])
        runner = CliRunner()
        result = runner.invoke(main, ["-c", str(config_file), "hello"])
        assert result.exit_code == 0, result.output
        flat = _flat(result.output)
        assert "[Errno 111]" in flat
        if len(error) > 200:
            assert "[truncated" in flat
        else:
            assert f"failed: {error}" in flat


# ---------------------------------------------------------------------------
# DF-CHIMERA-V2-2: readable models/formations tables
# ---------------------------------------------------------------------------


def test_cli_models_no_truncation_at_80_cols(config_file, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Regression: `chimera models` used to add one column per category (32+),
    so an 80-column terminal truncated every cell to ~3 chars ("mo…", "pr…")
    with no legible model/provider/tier. The identity columns must render
    every long model name, provider, and tier in full at 80 columns.
    """
    monkeypatch.setenv("COLUMNS", "80")
    runner = CliRunner()
    result = runner.invoke(main, ["-c", str(config_file), "models"])
    assert result.exit_code == 0, result.output
    # Longest names/providers in the fixture must appear in full (no "…").
    assert "deepseek/deepseek-chat" in result.output
    assert "openrouter/qwen/qwen3-coder" in result.output
    assert "openrouter/google/gemini-2.5-flash" in result.output
    assert "openrouter/anthropic/claude-sonnet-4" in result.output
    assert "zai-coding-plan/glm-5.2" in result.output
    assert "deepseek/deepseek-v4-flash" in result.output
    # Provider + tier columns legible.
    assert "openrouter" in result.output
    assert "premium" in result.output
    assert "budget" in result.output
    # Rich truncation marker must not appear anywhere.
    assert "…" not in result.output
    # No per-category columns: a bare "code" header cell is gone (categories
    # only appear inside "model · category" rows in the detail table).
    assert "code" in result.output


def test_cli_models_transposed_weights_present(config_file) -> None:  # type: ignore[no-untyped-def]
    """Category weights are still presented, transposed as (model · category,
    weight) rows instead of one column per category."""
    runner = CliRunner()
    result = runner.invoke(main, ["-c", str(config_file), "models"])
    assert result.exit_code == 0, result.output
    assert "Category weights" in result.output
    # One transposed row per (model, category).
    assert "deepseek/deepseek-chat · code" in result.output
    assert "openrouter/google/gemini-2.5-flash · design" in result.output
    assert "90.00" in result.output  # gemini design weight (percent scale)
    assert "95.00" in result.output  # glm-5.2 reasoning weight


def test_cli_models_weights_sorted_strongest_first(config_file) -> None:  # type: ignore[no-untyped-def]
    """Within each model's block, weights sort strongest-first."""
    runner = CliRunner()
    result = runner.invoke(main, ["-c", str(config_file), "models"])
    assert result.exit_code == 0, result.output
    # glm-5.2: reasoning=95.0 > code=92.0 > analysis=90.0 > audit=88.0 >
    # design=85.0 — rows must appear in that order.
    order = [
        "zai-coding-plan/glm-5.2 · reasoning",
        "zai-coding-plan/glm-5.2 · code",
        "zai-coding-plan/glm-5.2 · analysis",
        "zai-coding-plan/glm-5.2 · audit",
        "zai-coding-plan/glm-5.2 · design",
    ]
    positions = [result.output.find(row) for row in order]
    assert all(p >= 0 for p in positions), result.output
    assert positions == sorted(positions)


def test_cli_formations_no_json_blob(config_file) -> None:  # type: ignore[no-untyped-def]
    """Regression: the definition column contained a raw json.dumps blob that
    rich truncated illegibly. It must now be a compact readable summary."""
    runner = CliRunner()
    result = runner.invoke(main, ["-c", str(config_file), "formations"])
    assert result.exit_code == 0, result.output
    assert "workers=2" in result.output
    assert "mode=auto" in result.output
    assert "merge=best_of_n" in result.output
    assert "aggregators=default" in result.output
    assert "worker_models=" in result.output
    # No JSON syntax from the old blob survives.
    assert '{"workers"' not in result.output
    assert "null" not in result.output


def test_cli_formations_dag_summarized(config_file) -> None:  # type: ignore[no-untyped-def]
    """A DAG formation renders as a compact stage count, not a JSON dump."""
    from chimera.cli.main import _summarize_preset
    from chimera.config import FormationPreset

    dag = {
        "stages": [
            {"id": "a", "kind": "worker", "model": "m1", "depends_on": []},
            {"id": "b", "kind": "aggregator", "model": "m2", "depends_on": ["a"]},
        ],
        "edges": [["a", "b"]],
    }
    summary = _summarize_preset(FormationPreset(dag=dag))
    assert summary == "dag: 2 stages"


# ---------------------------------------------------------------------------
# CH-GAP-050: config-less first-run — clean one-line error + `config init`
# ---------------------------------------------------------------------------

_CONFIGLESS_MSG = "No chimera.yaml found. Copy chimera.yaml.example to chimera.yaml."

#: DF-CHIMERA-V2-8: the remedy that works from a bare pip install (it
#: bootstraps from the wheel-shipped template) — a message that only points at
#: ``chimera.yaml.example`` sends the user hunting for a file they lack.
_CONFIGLESS_REMEDY = "chimera config init"


def _assert_configless_error(result) -> None:  # type: ignore[no-untyped-def]
    """Fresh dir + config-needing command → one-line error, exit 2, no traceback."""
    assert result.exit_code == 2, result.output
    assert _CONFIGLESS_MSG in result.output
    assert _CONFIGLESS_REMEDY in result.output
    assert "Traceback" not in result.output


def _fresh_dir(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """chdir to an empty dir with no chimera.yaml and no CHIMERA_CONFIG env."""
    monkeypatch.delenv("CHIMERA_CONFIG", raising=False)
    monkeypatch.chdir(tmp_path)


def test_cli_models_missing_config_one_line_error(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """CH-GAP-050: `chimera models` with no chimera.yaml → clean one-line error."""
    _fresh_dir(monkeypatch, tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["models"])
    _assert_configless_error(result)


def test_cli_serve_missing_config_one_line_error(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """CH-GAP-050: `chimera serve` with no chimera.yaml → clean one-line error."""
    _fresh_dir(monkeypatch, tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["serve"])
    _assert_configless_error(result)


def test_cli_formations_missing_config_one_line_error(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """CH-GAP-050: `chimera formations` with no chimera.yaml → clean one-line error."""
    _fresh_dir(monkeypatch, tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["formations"])
    _assert_configless_error(result)


def test_cli_run_missing_config_one_line_error(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """CH-GAP-050: bare prompt (run) with no chimera.yaml → clean one-line error."""
    _fresh_dir(monkeypatch, tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["what is 2+2?"])
    _assert_configless_error(result)


def test_cli_missing_config_remedy_is_one_line_at_80_columns(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """DF-CHIMERA-V2-8: the remedy survives a narrow terminal as ONE line.

    Naming ``chimera config init`` grows the message to ~200 chars; rich's
    default hard-wrap turned it into three lines at 80 columns (and can break
    inside the command itself at some widths), which defeats both the
    CH-GAP-050 one-liner contract and the point of naming a runnable remedy.
    The handler prints it with ``soft_wrap``, so the byte stream is one line
    at any terminal width — a real terminal still soft-wraps the display.
    """
    _fresh_dir(monkeypatch, tmp_path)
    runner = CliRunner(env={"COLUMNS": "80"})
    result = runner.invoke(main, ["what is 2+2?"])
    assert result.exit_code == 2, result.output
    assert result.output.count("\n") == 1, repr(result.output)
    assert "chimera config init" in result.output
    assert "Traceback" not in result.output


def test_cli_config_init_creates_working_config(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """CH-GAP-050: `chimera config init` copies the example → load_config parses it.

    The copy uses the repo-root/wheel-shipped ``chimera.yaml.example``, and the
    resulting ``chimera.yaml`` must round-trip through ``load_config``.
    """
    example = Path(__file__).resolve().parent.parent / "chimera.yaml.example"
    assert example.is_file(), "repo-root chimera.yaml.example must exist"
    shutil.copyfile(example, tmp_path / "chimera.yaml.example")
    monkeypatch.delenv("CHIMERA_CONFIG", raising=False)
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["config", "init"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "chimera.yaml").is_file()
    cfg = load_config(tmp_path / "chimera.yaml")
    assert cfg.defaults.dispatcher == "deepseek/deepseek-v4-flash"
    assert "simple" in cfg.formations


def test_cli_config_init_refuses_overwrite(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """CH-GAP-050: existing chimera.yaml is not clobbered without --force."""
    (tmp_path / "chimera.yaml.example").write_text("defaults: {}\n", encoding="utf-8")
    (tmp_path / "chimera.yaml").write_text("existing: true\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["config", "init"])
    assert result.exit_code == 2, result.output
    assert "already exists" in result.output
    assert "--force" in result.output
    assert (tmp_path / "chimera.yaml").read_text() == "existing: true\n"


def test_cli_config_init_force_overwrites(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """CH-GAP-050: --force replaces an existing chimera.yaml."""
    (tmp_path / "chimera.yaml.example").write_text("defaults: {}\n", encoding="utf-8")
    (tmp_path / "chimera.yaml").write_text("old: true\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["config", "init", "--force"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "chimera.yaml").read_text() == "defaults: {}\n"


# ---------------------------------------------------------------------------
# DF-CHIMERA-V2-4: group-level --version
# ---------------------------------------------------------------------------


def test_cli_version_flag() -> None:
    """``chimera --version`` prints the package version and exits 0.

    A group flag (like ``--quiet`` / ``--json``), so it is accepted before any
    subcommand and needs no config file.
    """
    from chimera import __version__

    runner = CliRunner()
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0, result.output
    assert __version__ in result.output
