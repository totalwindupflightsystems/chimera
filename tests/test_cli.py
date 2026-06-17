"""Tests for the Click + Rich CLI."""

from __future__ import annotations


import pytest

pytest.importorskip("click")
from click.testing import CliRunner  # noqa: E402

from chimera.cli.main import main  # noqa: E402


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
                                    source="auto", answer_stage_id="judge")
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
