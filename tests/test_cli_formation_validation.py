"""DF-CHIMERA-V2-7 — an unknown formation is rejected on the CLI surface.

Before this fix ``chimera -f nope --quiet "..."`` handed the name to the
dispatcher, which logged a structlog ``unknown_formation`` warning and silently
fell back to ``auto``: the command printed an answer and exited 0, billing a
full deliberation on the wrong formation, while ``POST /v1/deliberate``
answered 422 for the same input. These tests pin the CLI half of the parity —
exit 2, actionable error on **stderr** only, and proof (via a spy engine +
gateway) that zero provider calls happened — plus the explicit ``--dag``
exemption. The MCP half lives in tests/test_mcp.py.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

pytest.importorskip("click")
from click.testing import CliRunner  # noqa: E402

from chimera.cli.main import _validate_formation, main  # noqa: E402
from tests.conftest import CONFIG_DICT  # noqa: E402

# CONFIG_DICT (tests/conftest.py) ships formations: audit, auto, debate,
# simple, speed — the same names the live config exposes.
AVAILABLE_SORTED = "audit, auto, debate, simple, speed"
UNKNOWN = "nope"
KNOWN = "simple"


def _spy(monkeypatch):  # type: ignore[no-untyped-def]
    """Install a spy Engine + gateway; return the record of what they saw.

    ``built`` non-empty means the CLI constructed an engine (i.e. got past
    validation); ``calls`` non-empty means a deliberation actually ran.
    ``gateway_built`` catches a gateway constructed without an engine.
    """
    record: dict[str, list] = {"built": [], "calls": [], "gateway_built": []}

    class SpyEngine:
        def __init__(self, *args, **kwargs):  # noqa: ANN002, ANN003
            record["built"].append((args, kwargs))

        async def deliberate(self, prompt, formation, **kwargs):  # noqa: ANN003
            record["calls"].append((prompt, formation, kwargs))
            span = SimpleNamespace(
                stage_id="dispatch", kind="dispatch", model="m",
                tokens_input=1, tokens_output=2, latency_ms=5, cost=0.0,
            )
            trace = SimpleNamespace(
                request_id="r1", dispatch=span, stages=[], total_tokens=3,
                total_duration_ms=9, total_cost=0.0, source="auto",
                answer_stage_id="aggregator", worker_failures=[],
                dispatch_note=None,
            )
            return SimpleNamespace(answer="ok", trace=trace)

    def spy_gateway(*args, **kwargs):  # noqa: ANN002, ANN003
        record["gateway_built"].append((args, kwargs))
        return None

    monkeypatch.setattr("chimera.cli.main.Engine", SpyEngine)
    monkeypatch.setattr("chimera.cli.main.LiteLLMGateway", spy_gateway)
    return record


# ---------------------------------------------------------------------------
# The pure helper (unit level)
# ---------------------------------------------------------------------------

def test_validate_formation_accepts_known_name(config) -> None:  # type: ignore[no-untyped-def]
    assert _validate_formation(config, KNOWN, None) is None


def test_validate_formation_exempts_explicit_dag(config) -> None:  # type: ignore[no-untyped-def]
    """An explicit DAG replaces formation selection — unknown name is fine."""
    dag = {"stages": [{"id": "s1", "kind": "worker", "model": "m1",
                       "depends_on": []}], "edges": []}
    assert _validate_formation(config, UNKNOWN, dag) is None


def test_validate_formation_rejects_unknown_name(config, capsys) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(SystemExit) as excinfo:
        _validate_formation(config, UNKNOWN, None)
    assert excinfo.value.code == 2
    err = capsys.readouterr().err
    assert UNKNOWN in err
    assert AVAILABLE_SORTED in err
    assert "chimera formations" in err


# ---------------------------------------------------------------------------
# CLI end-to-end (CliRunner)
# ---------------------------------------------------------------------------

def test_cli_unknown_formation_exits_2_without_deliberating(config_file, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """C1: exit 2, stderr names the value + the available names, no engine."""
    record = _spy(monkeypatch)
    result = CliRunner().invoke(
        main, ["-c", str(config_file), "-f", UNKNOWN, "--quiet",
               "reply with the word ok"],
    )
    assert result.exit_code == 2, result.output
    assert UNKNOWN in result.stderr
    assert "Available formations:" in result.stderr
    assert AVAILABLE_SORTED in result.stderr
    assert "chimera formations" in result.stderr
    # Zero provider calls: no engine, no gateway, no deliberation.
    assert record["built"] == []
    assert record["gateway_built"] == []
    assert record["calls"] == []


def test_cli_unknown_formation_keeps_stdout_empty(config_file, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """stdout purity (DF-CHIMERA-V2-3): the diagnostic goes to stderr only."""
    _spy(monkeypatch)
    result = CliRunner().invoke(
        main, ["-c", str(config_file), "-f", UNKNOWN, "--quiet",
               "reply with the word ok"],
    )
    assert result.exit_code == 2
    assert result.stdout == ""
    assert "ok" not in result.stdout


def test_cli_known_formation_still_deliberates(config_file, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """C4: a valid formation proceeds down the normal path, exit 0."""
    record = _spy(monkeypatch)
    result = CliRunner().invoke(
        main, ["-c", str(config_file), "-f", KNOWN, "--quiet",
               "reply with the word ok"],
    )
    assert result.exit_code == 0, result.output
    assert result.stdout.strip() == "ok"
    assert len(record["calls"]) == 1
    prompt, formation, _kwargs = record["calls"][0]
    assert prompt == "reply with the word ok"
    assert formation == KNOWN


def test_cli_default_formation_is_accepted(config_file, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """No -f at all → the ``auto`` default still validates and runs."""
    record = _spy(monkeypatch)
    result = CliRunner().invoke(
        main, ["-c", str(config_file), "--quiet", "reply with the word ok"],
    )
    assert result.exit_code == 0, result.output
    assert record["calls"][0][1] == "auto"


def test_cli_dag_bypasses_formation_validation(config_file, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """C4: --dag is exempt — the unknown -f value must not block it."""
    record = _spy(monkeypatch)
    dag_dict = {
        "stages": [{"id": "s1", "kind": "worker", "model": "m1",
                    "depends_on": []}],
        "edges": [],
    }
    result = CliRunner().invoke(
        main, ["-c", str(config_file), "-f", UNKNOWN,
               "--dag", json.dumps(dag_dict), "--allow-custom-dag",
               "--quiet", "prompt"],
    )
    assert result.exit_code == 0, result.output
    assert len(record["calls"]) == 1
    _prompt, _formation, kwargs = record["calls"][0]
    assert kwargs["dag"] == dag_dict
    assert kwargs["allow_custom_dag"] is True


def test_cli_unknown_formation_lists_config_names(config_file, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """The listed names come from the loaded config, not a hardcoded list."""
    _spy(monkeypatch)
    result = CliRunner().invoke(
        main, ["-c", str(config_file), "-f", "dabate", "--quiet", "hi"],
    )
    assert result.exit_code == 2
    for name in sorted(CONFIG_DICT["formations"]):
        assert name in result.stderr
