"""DF-CHIMERA-V2-81: the implicit-prompt form honours flags AFTER the prompt.

``ChimeraGroup.resolve_command`` redirects an unknown first token (the
implicit-prompt form) to the ``run`` subcommand with ALL remaining args —
including flags placed after the prompt: ``chimera "hello" -f debate``. The
``run`` command had no options of its own, so click rejected them with
"No such option" (exit 2). The fix mirrors the group's options onto ``run``.

These tests pin the four acceptance forms AND the group-value precedence
contract (an explicit ``run`` flag wins over the group's; a flag passed
only at the group level survives the redirect), so a future "simplify"
cannot drop the ``ParameterSource`` guard without going red here.
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("click")
from click.testing import CliRunner  # noqa: E402

from chimera.cli.main import main  # noqa: E402


@pytest.fixture
def captured(monkeypatch):  # type: ignore[no-untyped-def]
    """Stub engine + gateway recording (prompt, formation); answer "42"."""
    seen: dict = {}

    class StubEngine:
        def __init__(self, *args, **kwargs):  # noqa: ANN002, ANN003
            pass

        async def deliberate(self, prompt, formation, **kwargs):  # noqa: ANN001
            seen["prompt"] = prompt
            seen["formation"] = formation
            from chimera.engine import DeliberationResult, DeliberationTrace, StageSpan

            trace = DeliberationTrace(
                request_id="req-81",
                formation=formation,
                source="auto",
                dispatch=StageSpan(
                    stage_id="dispatch",
                    kind="dispatch",
                    model="zai-coding-plan/glm-5.2",
                    prompt="p",
                    response="r",
                    tokens_input=1,
                    tokens_output=1,
                    latency_ms=1,
                    cost=0.0,
                ),
                stages=[],
                answer_stage_id="aggregator",
                total_tokens=2,
                total_cost=0.0,
                total_duration_ms=2,
            )
            return DeliberationResult(answer="42", trace=trace)

    monkeypatch.setattr("chimera.cli.main.Engine", StubEngine)
    monkeypatch.setattr("chimera.cli.main.LiteLLMGateway", lambda *a, **k: None)
    monkeypatch.setattr(
        "chimera.provider_discovery.discover_providers",
        lambda **kwargs: ({}, {}),
    )
    return seen


def _invoke(config_file, *args: str):  # type: ignore[no-untyped-def]
    return CliRunner().invoke(main, ["-c", str(config_file), *args])


def test_implicit_prompt_trailing_formation(config_file, captured, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Acceptance 1: ``chimera "hello" -f debate`` → formation "debate"."""
    monkeypatch.setattr("chimera.cli.main._validate_formation", lambda *a: None)
    result = _invoke(config_file, "hello", "-f", "debate")

    assert result.exit_code == 0, result.output
    assert "42" in result.output
    assert captured["formation"] == "debate"
    assert captured["prompt"] == "hello"


def test_implicit_prompt_trailing_verbose(config_file, captured, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Acceptance 2: ``chimera "hello" --verbose`` works (exit 0)."""
    result = _invoke(config_file, "hello", "--verbose")

    assert result.exit_code == 0, result.output
    assert captured["formation"] == "auto"


def test_implicit_prompt_trailing_quiet(config_file, captured, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Acceptance 3: ``chimera "hello" --quiet`` stdout is exactly "42"."""
    result = _invoke(config_file, "hello", "--quiet")

    assert result.exit_code == 0, result.output
    assert result.stdout == "42\n"


def test_implicit_prompt_trailing_json(config_file, captured, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Acceptance 4: ``chimera "hello" --json`` stdout is one JSON object."""
    result = _invoke(config_file, "hello", "--json")

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["answer"] == "42"


def test_mixed_form_group_flag_plus_run_flag_override(config_file, captured, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """An explicit ``run`` flag overrides the group's value.

    Without the ParameterSource guard the run-level default ("auto") would
    silently clobber the group-parsed ``-f debate`` in the mixed form
    ``chimera -f debate run "hello"``.
    """
    monkeypatch.setattr("chimera.cli.main._validate_formation", lambda *a: None)
    result = _invoke(config_file, "-f", "debate", "run", "hello", "-f", "auto")

    assert result.exit_code == 0, result.output
    assert captured["formation"] == "auto"


def test_mixed_form_group_flag_survives_redirect(config_file, captured, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """A group-level flag with NO run-level twin keeps its parsed value."""
    monkeypatch.setattr("chimera.cli.main._validate_formation", lambda *a: None)
    result = _invoke(config_file, "-f", "debate", "run", "hello")

    assert result.exit_code == 0, result.output
    assert captured["formation"] == "debate"


def test_mixed_form_group_and_run_output_flags_conflict(config_file, captured, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """``chimera --json run "p" --quiet`` is a usage error (exit 2)."""
    result = _invoke(config_file, "--json", "run", "hello", "--quiet")

    assert result.exit_code == 2
    assert "--quiet and --json are mutually exclusive" in result.output
