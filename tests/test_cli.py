"""Tests for the Click + Rich CLI."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

pytest.importorskip("click")
from click.testing import CliRunner  # noqa: E402

from chimera.cli.main import main  # noqa: E402

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
            span = SimpleNamespace(stage_id="dispatch", kind="dispatch", model="m",
                                   tokens_input=1, tokens_output=2, latency_ms=5, cost=0.0)
            trace = SimpleNamespace(request_id="r1", dispatch=span, stages=[],
                                    total_tokens=3, total_duration_ms=9, total_cost=0.0,
                                    source="auto", answer_stage_id="aggregator")
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
            span = SimpleNamespace(stage_id="dispatch", kind="dispatch", model="m",
                                   tokens_input=1, tokens_output=2, latency_ms=5, cost=0.0)
            trace = SimpleNamespace(request_id="r1", dispatch=span, stages=[],
                                    total_tokens=3, total_duration_ms=9, total_cost=0.0,
                                    source="auto", answer_stage_id="aggregator")
            return SimpleNamespace(answer="ok", trace=trace)

    monkeypatch.setattr("chimera.cli.main.Engine", StubEngine)
    monkeypatch.setattr("chimera.cli.main.LiteLLMGateway", lambda *a, **k: None)
    runner = CliRunner()
    result = runner.invoke(main, [
        "-c", str(config_file),
        "--stage-models", '{"stage1":"model1"}',
        "prompt",
    ])
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
            span = SimpleNamespace(stage_id="dispatch", kind="dispatch", model="m",
                                   tokens_input=1, tokens_output=2, latency_ms=5, cost=0.0)
            trace = SimpleNamespace(request_id="r1", dispatch=span, stages=[],
                                    total_tokens=3, total_duration_ms=9, total_cost=0.0,
                                    source="auto", answer_stage_id="aggregator")
            return SimpleNamespace(answer="ok", trace=trace)

    monkeypatch.setattr("chimera.cli.main.Engine", StubEngine)
    monkeypatch.setattr("chimera.cli.main.LiteLLMGateway", lambda *a, **k: None)
    runner = CliRunner()
    result = runner.invoke(main, [
        "-c", str(config_file),
        "--dag", json.dumps(dag_dict),
        "--allow-custom-dag",
        "prompt",
    ])
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


# === 6 + 7. _deliberate verbose trace + _print_trace (lines 143-175) ===

def test_cli_verbose_trace(config_file, monkeypatch) -> None:
    """--verbose flag prints the deliberation trace with all expected fields."""
    span = SimpleNamespace(
        stage_id="dispatch", kind="dispatch", model="deepseek/deepseek-chat",
        tokens_input=50, tokens_output=100, latency_ms=500, cost=0.002,
    )
    stage1 = SimpleNamespace(
        stage_id="worker_1", kind="worker", model="claude-3",
        tokens_input=100, tokens_output=200, latency_ms=1000, cost=0.005,
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
        stage_id="dispatch", kind="dispatch", model="gpt-4",
        tokens_input=10, tokens_output=20, latency_ms=100, cost=0.001,
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
    """Return a callable that records config_path into *captured*."""
    def _run(config_path):
        captured.update({"config_path": config_path})
    return _run


def test_cli_serve_with_host_port(config_file, monkeypatch) -> None:
    """serve --host and --port are forwarded to run_api."""
    captured: dict = {}
    monkeypatch.setattr("chimera.api.server.run", _capture_run_api(captured))
    runner = CliRunner()
    result = runner.invoke(main, ["-c", str(config_file), "serve",
                                   "--host", "0.0.0.0", "--port", "9999"])
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
    assert captured["config_path"] == str(config_file)


def test_cli_mcp_no_config(config_file, monkeypatch) -> None:
    """mcp command passes None config_path when -c is not given."""
    captured: dict = {}
    monkeypatch.setattr("chimera.mcp.server.run", _capture_run_mcp(captured))
    runner = CliRunner()
    result = runner.invoke(main, ["mcp"])
    assert result.exit_code == 0, result.output
    assert captured["config_path"] is None
