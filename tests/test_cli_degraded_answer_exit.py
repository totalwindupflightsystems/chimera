"""DF-CHIMERA-V2-71: a fully-degraded panel is a FAILURE, not an answer.

The board row's repro (proven live on a fresh install): with NO
``DEEPSEEK_API_KEY`` set, ``chimera --quiet 'Name one HTTP status code'``
exited **0** and stdout carried ``[stage aggregator (deepseek/deepseek-v4-flash)
unavailable: ... set DEEPSEEK_API_KEY ...]`` — the engine-fabricated degraded
placeholder text — while the honest ``warning: dispatch degraded`` line went to
stderr. The README's scripted pattern (``ANSWER=$(chimera --quiet ...)``)
therefore captured the upstream failure AS the answer, with a success exit code.
The REST surface already handles the identical result correctly (HTTP 502 via
``result.answer_degraded``); only the CLI fallback path lied.

The contract pinned here (all against a REAL ``Engine`` driven through the
click CLI with a stub gateway — every stage degrades, mirroring the repro's
no-credentials shape):

* **--quiet** — exit 2; stdout is EMPTY (the error-as-answer text never ships
  as the product); the honest ``error: deliberation produced no usable
  answer ...`` line lands on stderr beside the existing degraded-dispatch
  warnings.
* **--json** — exit 2; one parseable object still reaches stdout (the machine
  payload is not discarded), and the new top-level ``answer_degraded: true`` /
  ``answer_error`` markers let a consumer detect the failure without
  pattern-matching the answer text.
* **partial degradation still answers** — one dropped worker + one healthy
  merge stage keeps exit 0 and a real answer on stdout. The fix is scoped to
  the case where the ANSWER STAGE ITSELF degraded; a partially degraded panel
  keeps its documented exit-0-with-stderr-warnings contract
  (DF-CHIMERA-0906-5 / DF-CHIMERA-V2-34).
* **human mode** — exit 2 with the same error summary on stderr.

A no-credentials run is the canonical real-world trigger: the gateway raises a
missing-credential error for every provider call, the engine fabricates a
degraded placeholder for each stage (``engine._degraded_stage``), the
placeholder cascades into the merge stage, and the answer stage ends degraded —
exactly the ``answer_degraded=True`` path the API layer rejects with 502
(``api/server.py``). No credential error text is used in fixtures, so these
tests stay hermetic (no ``DEEPSEEK_API_KEY`` handling, no network, no
``~/.chimera`` writes).
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
import yaml

pytest.importorskip("click")
from click.testing import CliRunner  # noqa: E402

from chimera.cli.main import main  # noqa: E402
from chimera.engine import DeliberationResult, DeliberationTrace, StageSpan  # noqa: E402
from chimera.gateway import GatewayError  # noqa: E402
from tests.conftest import CONFIG_DICT, FakeGateway, dispatch_json, resp  # noqa: E402

#: Models from the compact test catalog (``tests/conftest.CONFIG_DICT``).
FLASH = "deepseek/deepseek-chat"
GEMINI = "openrouter/google/gemini-2.5-flash"
GLM = "zai-coding-plan/glm-5.2"  # the configured dispatcher + default aggregator

#: Deliberately NOT a credential-error string (no "missing credentials",
#: no 401 shape): the fixture must not depend on the blocked-models
#: classifier, which only adds extra stderr lines.
UPSTREAM_ERROR = "provider endpoint unreachable (simulated outage)"


#: The engine's degraded-placeholder shape (``engine._degraded_stage``) —
#: exactly what shipped as "the answer" in the board row's repro.
def _placeholder(stage_id: str, model: str) -> str:
    return f"[stage {stage_id} ({model}) unavailable: {UPSTREAM_ERROR}]"


def _write_config(tmp_path: Path) -> Path:
    """A minimal, hermetic config: no discovery, no credentials, stub gateway."""
    doc = copy.deepcopy(CONFIG_DICT)
    doc["provider_discovery"] = False
    doc["formations"] = {
        "code-review": {
            "dag": {
                "stages": [
                    {"id": "reviewer", "kind": "worker", "model": FLASH, "depends_on": []},
                    {
                        "id": "verdict",
                        "kind": "merge",
                        "model": GEMINI,
                        "depends_on": ["reviewer"],
                    },
                ],
                "edges": [["reviewer", "verdict"]],
            }
        }
    }
    path = tmp_path / "chimera.yaml"
    path.write_text(yaml.safe_dump(doc), encoding="utf-8")
    return path


def _all_degraded(model: str, messages: list[dict[str, str]], **kw: Any) -> Any:
    """Every provider call fails — the no-credentials / dead-upstream shape.

    The ENGINE then fabricates each stage's degraded placeholder itself
    (``_degraded_stage``), so the run completes with an ``answer`` that is
    entirely placeholder text — exactly the ``answer_degraded`` result the
    REST API rejects with 502 and the CLI used to print as the answer.
    """
    raise GatewayError(UPSTREAM_ERROR)


def _degrade_one(*, degraded_model: str, dispatcher: str = dispatch_json()) -> Any:
    """One named model degrades; every other stage answers normally.

    Routed by model: the dispatcher (GLM), the worker (FLASH) and the merge
    stage (GEMINI) are three distinct catalog ids, so exactly one branch fires
    per call — no prompt-text sniffing.
    """

    def _responder(model: str, messages: list[dict[str, str]], **kw: Any) -> Any:
        if model == GLM:  # the single dispatcher call
            return resp(dispatcher, model, tok_in=100, tok_out=200)
        if model == degraded_model:
            raise GatewayError(UPSTREAM_ERROR)
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


def _degraded_result(answer: str = "unused") -> DeliberationResult:
    """A REAL pydantic result with ``answer_degraded=True`` (unit-level arm)."""
    span = StageSpan(
        stage_id="aggregator",
        kind="aggregator",
        model=GLM,
        prompt="prompt",
        response=answer,
        tokens_input=0,
        tokens_output=0,
        latency_ms=1,
        cost=0.0,
    )
    trace = DeliberationTrace(
        request_id="req-d71",
        formation="auto",
        source="fallback",
        dispatch=StageSpan(
            stage_id="dispatch",
            kind="dispatch",
            model=GLM,
            prompt="p",
            response="d",
            tokens_input=1,
            tokens_output=1,
            latency_ms=1,
            cost=0.0,
        ),
        stages=[span],
        aggregator=span,
        answer_stage_id="aggregator",
    )
    return DeliberationResult(
        answer=answer,
        trace=trace,
        answer_degraded=True,
        answer_error=UPSTREAM_ERROR,
    )


def _stub_engine(monkeypatch: pytest.MonkeyPatch, result: DeliberationResult) -> None:
    class StubEngine:
        def __init__(self, *args: Any, **kwargs: Any) -> None:  # noqa: ANN002, ANN003
            pass

        async def deliberate(self, prompt: str, formation: str, **kwargs: Any) -> DeliberationResult:
            return result

    monkeypatch.setattr("chimera.cli.main.Engine", StubEngine)
    monkeypatch.setattr("chimera.cli.main.LiteLLMGateway", lambda *a, **k: None)
    monkeypatch.setattr(
        "chimera.provider_discovery.discover_providers",
        lambda **kwargs: ({}, {}),
    )


# --------------------------------------------------------------------------- #
# 1. The board row's repro shape: every stage degraded (real Engine path)
# --------------------------------------------------------------------------- #


def test_quiet_fully_degraded_run_exits_2_with_empty_stdout(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """The core acceptance: exit 2, and stdout does NOT carry the error text."""
    config = _write_config(tmp_path)
    _stub_gateway(monkeypatch, _all_degraded)

    result = _invoke(config, "--quiet", "-f", "code-review", "Name one HTTP status code")

    assert result.exit_code == 2, _report("fully degraded --quiet run must fail", result)
    assert result.stdout == "", (
        f"the error-as-answer text must never ship as the --quiet answer; stdout was {result.stdout!r}"
    )
    assert _placeholder("verdict", GEMINI) not in result.stdout
    # The honest error summary reaches stderr, naming the failure class.
    assert "error:" in result.stderr, result.stderr
    assert "no usable answer" in result.stderr, result.stderr
    assert UPSTREAM_ERROR in result.stderr, result.stderr
    # The pre-existing honest warnings are still there too.
    assert "warning:" in result.stderr, result.stderr


def test_json_fully_degraded_run_exits_2_with_failure_markers(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """--json: machine payload still ships, with the failure markers set."""
    config = _write_config(tmp_path)
    _stub_gateway(monkeypatch, _all_degraded)

    result = _invoke(config, "--json", "-f", "code-review", "Name one HTTP status code")

    assert result.exit_code == 2, _report("fully degraded --json run must fail", result)
    assert result.stdout.count("\n") == 1, result.stdout
    payload = json.loads(result.stdout)  # still parseable
    assert payload["answer_degraded"] is True
    assert UPSTREAM_ERROR in (payload["answer_error"] or "")
    assert payload["answer"].startswith("[stage "), (
        "the payload keeps the engine's placeholder answer for forensics; only "
        "the markers + exit code changed"
    )
    # And the human-readable summary stays on stderr.
    assert "no usable answer" in result.stderr, result.stderr


def test_human_fully_degraded_run_exits_2(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Human mode: panel may render, but the run FAILS with the error summary."""
    config = _write_config(tmp_path)
    _stub_gateway(monkeypatch, _all_degraded)

    result = _invoke(config, "-f", "code-review", "Name one HTTP status code")

    assert result.exit_code == 2, _report("fully degraded human run must fail", result)
    assert "no usable answer" in result.stderr, result.stderr


# --------------------------------------------------------------------------- #
# 2. Partial degradation is NOT a failure — the documented exit-0 contract holds
# --------------------------------------------------------------------------- #


def test_quiet_partial_degradation_still_answers_with_exit_0(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """One dropped worker + a healthy merge: exit 0, real answer on stdout."""
    config = _write_config(tmp_path)
    _stub_gateway(monkeypatch, _degrade_one(degraded_model=FLASH))

    result = _invoke(config, "--quiet", "-f", "code-review", "review this")

    assert result.exit_code == 0, _report("partial degradation must keep exit 0", result)
    assert result.stdout.startswith("[fake output"), result.stdout
    assert "warning:" in result.stderr, result.stderr  # dropped worker still announced


# --------------------------------------------------------------------------- #
# 3. Unit-level arm: the result-object fields drive the behavior (no gateway)
# --------------------------------------------------------------------------- #


def test_quiet_degraded_result_object_exits_2_and_stdout_stays_clean(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """The engine's ``answer_degraded`` result alone flips the exit code."""
    config = _write_config(tmp_path)
    answer = _placeholder("aggregator", GLM)
    _stub_engine(monkeypatch, _degraded_result(answer))

    result = _invoke(config, "--quiet", "hello")

    assert result.exit_code == 2, _report("degraded result object must fail", result)
    assert result.stdout == "", result.stdout
    assert "no usable answer" in result.stderr, result.stderr
    assert answer not in result.stdout


def test_json_degraded_result_object_carries_markers(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Top-level ``answer_degraded`` / ``answer_error`` mirror the 502 fields."""
    config = _write_config(tmp_path)
    _stub_engine(monkeypatch, _degraded_result(_placeholder("aggregator", GLM)))

    result = _invoke(config, "--json", "hello")

    assert result.exit_code == 2, _report("degraded result object must fail", result)
    payload = json.loads(result.stdout)
    assert payload["answer_degraded"] is True
    assert payload["answer_error"] == UPSTREAM_ERROR
