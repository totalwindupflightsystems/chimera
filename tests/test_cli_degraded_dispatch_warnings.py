"""DF-CHIMERA-V2-34: the documented ``warning:`` contract on degraded runs.

USAGE.md's "Streams and exit codes" table promises that a ``--quiet``/``--json``
run with ``a dropped worker or degraded dispatch`` writes ``warning: ...`` lines
to stderr, and that human mode keeps them beside the panel. The row was filed
from the 2026-09-22 custom-formation dogfood run, where a custom-DAG
deliberation answered from partial input while the only trace of it looked like
structlog noise.

Both halves of that promise are pinned here against a REAL ``Engine`` driven
through the click CLI with a stub gateway (no provider call, no network, no
sleep beyond the simulated per-stage timeout):

* **dropped worker** — a stage that timed out or raised while the deliberation
  still produced an answer emits the documented line in every CLI mode
  (``--quiet`` and ``--json``: stderr; human: beside the panel). Earlier
  investigation of this row reproduced that shape and found the contract
  honored, so these are regression pins, not bug proofs.
* **degraded dispatch** — the half that DID break. When the dispatcher's design
  is discarded (its answer is unparseable, or the dispatcher call itself fails)
  on a PRESET or a CUSTOM DAG, ``Dispatcher._dispatch_preset`` /
  ``_dispatch_custom`` overwrite ``DispatchResult.source`` with the formation
  type (``"preset"`` / ``"custom"``) — the only structural marker of the
  collapse — so the CLI's ``source == "fallback"`` check never fired. The run
  finished RC=0 with a normal-looking answer and NO warning on any mode, with
  the discard visible only in ``dispatch_note`` and a structlog line
  (``dispatcher_bad_json`` / ``dispatcher_call_failed``).

The config's auto-formation path keeps its pre-existing
``warning: dispatch degraded — source=fallback (...)`` message: a fallback that
the CLI can already see must not be reported twice or reworded.
"""

from __future__ import annotations

import asyncio
import copy
import json
from pathlib import Path
from typing import Any

import pytest
import yaml

pytest.importorskip("click")
from click.testing import CliRunner  # noqa: E402

from chimera.cli.main import main  # noqa: E402
from chimera.gateway import GatewayError  # noqa: E402
from tests.conftest import CONFIG_DICT, FakeGateway, dispatch_json, resp  # noqa: E402

#: Models from the compact test catalog (``tests/conftest.CONFIG_DICT``).
FLASH = "deepseek/deepseek-chat"
QWEN = "openrouter/qwen/qwen3-coder"
SONNET = "openrouter/anthropic/claude-sonnet-4"
GEMINI = "openrouter/google/gemini-2.5-flash"
GLM = "zai-coding-plan/glm-5.2"  # the configured dispatcher + default aggregator

#: The answer text the stub gateway returns for the terminal merge stage.
MERGE_TEXT = f"[merged answer from {SONNET}]"
#: The dispatcher's normal (parseable) answer.
DISPATCH_OK = dispatch_json()

#: The incident's formation shape: two reviewers + one MERGE terminal, authored
#: as a config preset with an explicit ``dag`` block.
CODE_REVIEW_DAG: dict[str, Any] = {
    "stages": [
        {"id": "security", "kind": "worker", "model": FLASH, "depends_on": []},
        {"id": "performance", "kind": "worker", "model": QWEN, "depends_on": []},
        {"id": "verdict", "kind": "merge", "model": SONNET, "depends_on": ["security", "performance"]},
    ],
    "edges": [["security", "verdict"], ["performance", "verdict"]],
}

#: Same formation inline, as a client-defined DAG (``--dag --allow-custom-dag``).
INLINE_DAG: dict[str, Any] = {
    "stages": [
        {"id": "security", "kind": "worker", "model": FLASH, "depends_on": []},
        {"id": "performance", "kind": "worker", "model": QWEN, "depends_on": []},
        {"id": "verdict", "kind": "merge", "model": SONNET, "depends_on": ["security", "performance"]},
    ],
    "edges": [["security", "verdict"], ["performance", "verdict"]],
}

#: A mid-DAG aggregator between the workers and the terminal merge: the degraded
#: stage is a DEPENDENCY of the answer stage rather than the answer itself.
#: Every stage carries a distinct model so the stub gateway can degrade exactly
#: one of them.
MID_DAG: dict[str, Any] = {
    "stages": [
        {"id": "security", "kind": "worker", "model": FLASH, "depends_on": []},
        {"id": "performance", "kind": "worker", "model": QWEN, "depends_on": []},
        {
            "id": "review_merge",
            "kind": "aggregator",
            "model": GEMINI,
            "depends_on": ["security", "performance"],
        },
        {"id": "verdict", "kind": "merge", "model": SONNET, "depends_on": ["review_merge"]},
    ],
    "edges": [
        ["security", "review_merge"],
        ["performance", "review_merge"],
        ["review_merge", "verdict"],
    ],
}


def _write_config(
    tmp_path: Path, *, dag: dict[str, Any] | None = CODE_REVIEW_DAG, per_stage_s: float = 120.0
) -> Path:
    """A minimal, hermetic config: no discovery, no credentials, stub gateway."""
    doc = copy.deepcopy(CONFIG_DICT)
    doc["provider_discovery"] = False
    doc["timeout"] = {"per_stage_s": per_stage_s}
    doc["formations"] = {"code-review": {"dag": copy.deepcopy(dag or CODE_REVIEW_DAG)}}
    path = tmp_path / "chimera.yaml"
    path.write_text(yaml.safe_dump(doc), encoding="utf-8")
    return path


def _hanging(
    degrade_model: str | None,
    *,
    dispatcher: str = DISPATCH_OK,
    raise_gateway: bool = False,
    failure: str = "timeout",
    hang_answer_stage: bool = False,
):
    """Stub-gateway responder: one stage degrades, everything else answers.

    ``failure`` selects the failure class of the degraded stage: ``"timeout"``
    hangs (the engine's real ``asyncio.wait_for`` per-stage budget fires) and
    ``"gateway"`` raises :class:`GatewayError` instead.
    """

    def _responder(model: str, messages: list[dict[str, str]], **kw: Any) -> Any:
        if model == GLM:  # the single dispatcher call
            if raise_gateway:
                raise GatewayError("dispatcher upstream 503")
            return resp(dispatcher, model, tok_in=100, tok_out=200)
        if model == degrade_model:
            if failure == "gateway":
                raise GatewayError("upstream connect error")
            return asyncio.sleep(5)  # cancelled by the per-stage budget
        if model == SONNET:  # the terminal merge stage
            return resp(MERGE_TEXT, model, tok_in=50, tok_out=80)
        return resp(f"[fake output {model}]", model, tok_in=20, tok_out=30)

    return _responder


def _stub_gateway(monkeypatch: pytest.MonkeyPatch, responder: Any) -> None:
    monkeypatch.setattr("chimera.cli.main.LiteLLMGateway", lambda *a, **k: FakeGateway(responder))


def _invoke(config: Path, *args: str) -> Any:
    return CliRunner().invoke(main, ["-c", str(config), *args])


def _report(label: str, result: Any) -> None:  # pragma: no cover - failure detail
    pytest.fail(
        f"{label}\n  exit={result.exit_code}\n  stdout={result.stdout!r}\n"
        f"  stderr={result.stderr!r}\n  exception={result.exception!r}"
    )


# --------------------------------------------------------------------------- #
# 1. Dropped worker (the incident's claimed trigger) — contract HOLDS: pinned
# --------------------------------------------------------------------------- #


def test_quiet_worker_timeout_warns_on_stderr(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """``--quiet``: stdout stays the answer alone, the warning lands on stderr."""
    config = _write_config(tmp_path, per_stage_s=0.05)
    _stub_gateway(monkeypatch, _hanging(QWEN))

    result = _invoke(config, "--quiet", "-f", "code-review", "review this")

    assert result.exit_code == 0, result.output
    # stdout purity (DF-CHIMERA-0906-5) — the answer and nothing else.
    assert result.stdout == MERGE_TEXT + "\n", result.stdout
    assert "warning:" not in result.stdout
    assert "\x1b[" not in result.stdout
    # ... and the dropped stage is named, as the docs table promises.
    assert "warning:" in result.stderr, result.stderr
    assert "worker 'performance'" in result.stderr, result.stderr
    assert "timed out" in result.stderr, result.stderr


def test_json_worker_timeout_warns_on_stderr_and_names_the_stage(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """``--json``: one parseable document on stdout, warning + trace on stderr."""
    config = _write_config(tmp_path, per_stage_s=0.05)
    _stub_gateway(monkeypatch, _hanging(QWEN))

    result = _invoke(config, "--json", "-f", "code-review", "review this")

    assert result.exit_code == 0, result.output
    assert result.stdout.count("\n") == 1, result.stdout
    payload = json.loads(result.stdout)  # not corrupted by the warning
    assert payload["answer"] == MERGE_TEXT
    failures = payload["trace"]["worker_failures"]
    assert [f["stage_id"] for f in failures] == ["performance"], failures
    assert failures[0]["model"] == QWEN, failures
    assert failures[0]["error"].startswith("timed out"), failures
    assert "warning:" in result.stderr, result.stderr
    assert "worker 'performance'" in result.stderr, result.stderr
    assert "warning:" not in result.stdout


def test_human_worker_timeout_keeps_the_warning_beside_the_panel(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Default mode is unchanged: panel + warning on stdout, stderr log-only."""
    config = _write_config(tmp_path, per_stage_s=0.05)
    _stub_gateway(monkeypatch, _hanging(QWEN))

    result = _invoke(config, "-f", "code-review", "review this")

    assert result.exit_code == 0, result.output
    assert "╭" in result.stdout  # the Rich panel
    assert "warning:" in result.stdout, result.stdout
    assert "worker 'performance'" in result.stdout, result.stdout
    assert "warning:" not in result.stderr, result.stderr


def test_gateway_error_worker_also_warns(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """The failure CLASS does not matter: GatewayError warns like a timeout."""
    config = _write_config(tmp_path)
    _stub_gateway(monkeypatch, _hanging(QWEN, failure="gateway"))

    result = _invoke(config, "--quiet", "-f", "code-review", "review this")

    assert result.exit_code == 0, result.output
    assert result.stdout == MERGE_TEXT + "\n", result.stdout
    assert "warning:" in result.stderr, result.stderr
    assert "worker 'performance'" in result.stderr, result.stderr


def test_mid_dag_aggregator_degradation_warns(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """A degraded stage that is a DEPENDENCY of the answer stage also warns."""
    config = _write_config(tmp_path, dag=MID_DAG, per_stage_s=0.05)
    _stub_gateway(monkeypatch, _hanging(GEMINI))

    result = _invoke(config, "--json", "-f", "code-review", "review this")

    assert result.exit_code == 0, result.output
    failures = json.loads(result.stdout)["trace"]["worker_failures"]
    assert [f["stage_id"] for f in failures] == ["review_merge"], failures
    assert "warning:" in result.stderr, result.stderr
    assert "worker 'review_merge'" in result.stderr, result.stderr


def test_degraded_answer_stage_warns(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """The terminal merge itself timing out is still announced (rc stays 0)."""
    config = _write_config(tmp_path, per_stage_s=0.05)
    _stub_gateway(monkeypatch, _hanging(SONNET))

    result = _invoke(config, "--quiet", "-f", "code-review", "review this")

    assert result.exit_code == 0, result.output
    assert "warning:" in result.stderr, result.stderr
    assert "worker 'verdict'" in result.stderr, result.stderr


# --------------------------------------------------------------------------- #
# 2. Degraded dispatch on a preset / custom DAG — the gap (RED before the fix)
# --------------------------------------------------------------------------- #


def test_quiet_preset_dispatcher_fallback_warns_on_stderr(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """A discarded dispatcher design must warn — even though it is a preset.

    ``--quiet`` is exactly the mode the docs table covers, and exactly the mode
    in which a CLI user piping the answer has nothing else to look at.
    """
    config = _write_config(tmp_path)
    _stub_gateway(monkeypatch, _hanging(None, dispatcher="I could not produce JSON, sorry."))

    result = _invoke(config, "--quiet", "-f", "code-review", "review this")

    assert result.exit_code == 0, result.output
    assert result.stdout == MERGE_TEXT + "\n", result.stdout
    if "warning:" not in result.stderr:
        _report("a discarded dispatcher design printed no warning (quiet)", result)
    assert "dispatch degraded" in result.stderr, result.stderr
    assert "malformed_json" in result.stderr, result.stderr


def test_json_preset_dispatcher_fallback_carries_the_reason(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """``--json``: the warning on stderr, the machine-readable reason in the trace."""
    config = _write_config(tmp_path)
    _stub_gateway(monkeypatch, _hanging(None, dispatcher="not json at all"))

    result = _invoke(config, "--json", "-f", "code-review", "review this")

    assert result.exit_code == 0, result.output
    trace = json.loads(result.stdout)["trace"]
    # The formation is still the preset (the DAG is honored) — only the
    # dispatcher's own design pass was discarded.
    assert trace["source"] == "preset", trace["source"]
    assert trace["dispatch_note"] == "malformed_json", trace["dispatch_note"]
    assert trace["dispatch_fallback_reason"] == "malformed_json", trace
    if "warning:" not in result.stderr:
        _report("a discarded dispatcher design printed no warning (json)", result)
    assert "malformed_json" in result.stderr, result.stderr
    assert "warning:" not in result.stdout


def test_json_custom_dag_dispatcher_fallback_warns(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """The inline ``--dag --allow-custom-dag`` shape is masked the same way."""
    config = _write_config(tmp_path)
    _stub_gateway(monkeypatch, _hanging(None, dispatcher="dispatcher said no"))

    result = _invoke(
        config,
        "--json",
        "--dag",
        json.dumps(INLINE_DAG),
        "--allow-custom-dag",
        "review this",
    )

    assert result.exit_code == 0, result.output
    trace = json.loads(result.stdout)["trace"]
    assert trace["source"] == "custom", trace["source"]
    assert trace["dispatch_fallback_reason"] == "malformed_json", trace
    assert "warning:" in result.stderr, result.stderr


def test_human_preset_dispatcher_fallback_warns_beside_the_panel(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Human mode must show it too (this half was silent on every mode)."""
    config = _write_config(tmp_path)
    _stub_gateway(monkeypatch, _hanging(None, dispatcher="nope, no json here"))

    result = _invoke(config, "-f", "code-review", "review this")

    assert result.exit_code == 0, result.output
    assert "╭" in result.stdout
    assert "warning:" in result.stdout, result.stdout
    assert "dispatch degraded" in result.stdout, result.stdout
    assert "warning:" not in result.stderr, result.stderr


def test_preset_dispatcher_call_failure_warns(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """A dispatcher call that FAILED is a degraded dispatch, not a clean preset.

    ``_call_dispatcher`` converts a GatewayError into an empty response, so the
    parse falls back to templated prompts: the per-stage design is gone while
    the formation still runs, and the run looks perfectly normal.
    """
    config = _write_config(tmp_path)
    _stub_gateway(monkeypatch, _hanging(None, raise_gateway=True))

    result = _invoke(config, "--quiet", "-f", "code-review", "review this")

    assert result.exit_code == 0, result.output
    if "warning:" not in result.stderr:
        _report("a failed dispatcher call printed no warning (quiet)", result)
    assert "dispatch degraded" in result.stderr, result.stderr
    assert "invalid_dag" in result.stderr, result.stderr


def test_clean_preset_run_has_no_dispatch_warning(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Negative control: a parsed dispatch must NOT be reported as degraded."""
    config = _write_config(tmp_path)
    _stub_gateway(monkeypatch, _hanging(None))

    result = _invoke(config, "--quiet", "-f", "code-review", "review this")

    assert result.exit_code == 0, result.output
    assert result.stdout == MERGE_TEXT + "\n", result.stdout
    assert "warning:" not in result.stderr, result.stderr


def test_json_clean_preset_run_reports_no_fallback_reason(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """The new trace field is ``None`` for a clean dispatch (no false positives)."""
    config = _write_config(tmp_path)
    _stub_gateway(monkeypatch, _hanging(None))

    result = _invoke(config, "--json", "-f", "code-review", "review this")

    assert result.exit_code == 0, result.output
    trace = json.loads(result.stdout)["trace"]
    assert trace["dispatch_fallback_reason"] is None, trace
    assert trace["dispatch_note"] is None, trace
