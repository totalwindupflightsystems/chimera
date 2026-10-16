"""DF-CHIMERA-V2-89 — a totally failed deliberation is an MCP ERROR, not an answer.

Dogfood run 23 (2026-10-15) drove ``chimera-mcp`` over stdio as a real client in
a keyless environment: ``chimera_deliberate`` returned ``result.isError=false``
with ``answer`` set to the engine's rendered failure text — ``[stage aggregator
(deepseek/deepseek-v4-flash) unavailable: … set DEEPSEEK_API_KEY …]`` — while the
machine-readable signal lived only in ``trace.worker_failures``. A scripted MCP
consumer could not tell a failed run from a successful one. The unknown-formation
arm had already been fixed (DF-CHIMERA-V2-7), the total-degradation arm had not;
the REST/CLI/chat surfaces already treat the identical result as a failure
(HTTP 502 on ``POST /v1/deliberate``, exit 2 on the CLI — DF-CHIMERA-V2-71 — and
the web chat's ``all_workers_failed`` envelope, DF-CHIMERA-V2-44/75).

The contract pinned here, driven through the MCP tool-call path the dogfood used:

* **failed run** — every provider call fails, so the answer stage degrades:
  ``isError: true`` with the payload (``answer`` + ``trace`` incl.
  ``worker_failures`` and the dispatch info) still present, plus the markers
  ``error: "no_usable_answer"`` / ``answer_degraded: true`` / ``answer_error``.
* **successful run** — ``isError: false`` with the merged answer, unchanged.
* **partial degradation** — one dropped worker beside a real merged answer is
  NOT a failure, and keeps reporting the dropped stage in ``worker_failures``.
* **rendered-error answer** — an answer that is only the engine's placeholder is
  an error even when the ``answer_degraded`` flag is absent (defensive arm for a
  bare result object).

Hermetic: no provider calls, no credential handling, no subprocess, no network.
The all-degraded gateway is the canonical no-credentials shape used by
``tests/test_cli_degraded_answer_exit.py`` for the same engine result. A REAL
keyless child process would drive the live engine and record credential blocks in
the repo-local ``.chimera/blocked-models.json`` (a 7-day cooldown that removes
models from the dispatcher catalog for the rest of the suite), so the failure is
reproduced at the gateway seam instead.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest

pytest.importorskip("mcp")
from mcp.server.fastmcp import FastMCP  # noqa: E402
from mcp.shared.memory import create_connected_server_and_client_session  # noqa: E402

from chimera.engine import (  # noqa: E402
    DeliberationResult,
    DeliberationTrace,
    Engine,
    StageSpan,
    WorkerFailure,
)
from chimera.gateway import GatewayError, GatewayResponse  # noqa: E402
from chimera.mcp.server import (  # noqa: E402
    NO_USABLE_ANSWER_ERROR,
    _is_degraded_placeholder_only,
    _no_usable_answer_reason,
    build_server,
)
from tests.conftest import CONFIG_DICT, FakeGateway, dispatch_json  # noqa: E402

#: Deliberately NOT a credential-error string (no "missing credentials", no 401
#: shape), so the fixture never depends on the blocked-models classifier.
UPSTREAM_ERROR = "provider endpoint unreachable (simulated outage)"

GLM = "zai-coding-plan/glm-5.2"  # the configured dispatcher + default aggregator
FLASH = "deepseek/deepseek-chat"


def _resp(text: str, model: str, tok_in: int, tok_out: int) -> GatewayResponse:
    return GatewayResponse(text=text, model=model, tokens_input=tok_in, tokens_output=tok_out)


def _placeholder(stage_id: str, model: str) -> str:
    """The engine's degraded rendering (``engine._degraded_stage``)."""
    return f"[stage {stage_id} ({model}) unavailable: {UPSTREAM_ERROR}]"


async def _call(server: FastMCP, **arguments: Any) -> Any:
    """Call ``chimera_deliberate`` over the REAL MCP tool-call path.

    The in-memory session drives the same protocol a stdio client does
    (``tools/call`` → ``CallToolResult``), which is what makes ``isError``
    observable exactly as the dogfood's scripted consumer saw it.
    """
    async with create_connected_server_and_client_session(server._mcp_server) as client:
        return await client.call_tool("chimera_deliberate", arguments)


def _payload(result: Any) -> dict[str, Any]:
    """The JSON payload a scripted consumer parses out of ``content``."""
    assert result.content, "the tool must answer with content"
    return json.loads(result.content[0].text)


class _StubEngine:
    """An engine handing back a prepared result (no provider calls)."""

    def __init__(self, result: Any) -> None:
        self._result = result

    async def deliberate(self, *args: Any, **kwargs: Any) -> Any:  # noqa: ANN002, ANN003
        return self._result


def _trace(
    *,
    failures: list[WorkerFailure] | None = None,
    answer_stage_id: str = "aggregator",
) -> DeliberationTrace:
    span = StageSpan(
        stage_id=answer_stage_id,
        kind="aggregator",
        model=GLM,
        prompt="prompt",
        response="response",
        tokens_input=10,
        tokens_output=5,
        latency_ms=7,
        cost=0.0002,
    )
    return DeliberationTrace(
        request_id="req-d89",
        formation="auto",
        source="auto",
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
        answer_stage_id=answer_stage_id,
        worker_failures=list(failures or []),
    )


# --------------------------------------------------------------------------- #
# 1. The reported failure: a keyless-shaped run over MCP is an ERROR
# --------------------------------------------------------------------------- #


def _all_degraded(model: str, messages: list[dict[str, str]], **kw: Any) -> Any:
    """Every provider call fails — the no-credentials / dead-upstream shape."""
    raise GatewayError(UPSTREAM_ERROR)


@pytest.mark.asyncio
async def test_keyless_run_is_an_mcp_error(config) -> None:  # type: ignore[no-untyped-def]
    """Acceptance 1: no usable answer → ``isError=true``, never a fake success."""
    engine = Engine(config, FakeGateway(_all_degraded))
    server = build_server(config=config, engine=engine)

    result = await _call(server, prompt="Name one HTTP status code", formation="simple")

    assert result.isError is True, (
        "a run whose every provider call failed must be an MCP error — the "
        "reported defect was isError=false with the failure text in `answer`"
    )
    payload = _payload(result)
    # The machine-readable markers a scripted consumer acts on.
    assert payload["error"] == NO_USABLE_ANSWER_ERROR
    assert payload["answer_degraded"] is True
    assert UPSTREAM_ERROR in str(payload["answer_error"])
    assert "no usable answer" in payload["message"]
    # The engine's placeholder is still kept for forensics (as the CLI's --json
    # payload does) — it is simply no longer presented as a success.
    assert payload["answer"].startswith("[stage ")
    assert UPSTREAM_ERROR in payload["answer"]
    # Acceptance 3: the trace survives in the result, worker_failures included.
    trace = payload["trace"]
    assert trace["request_id"]
    assert trace["answer_stage_id"]
    assert trace["dispatch"]["kind"] == "dispatch"
    assert trace["worker_failures"], "the failed stages must stay inspectable"
    failure = trace["worker_failures"][0]
    assert set(failure) == {"stage_id", "model", "error"}
    assert UPSTREAM_ERROR in failure["error"]
    # Both channels the success arm fills carry the payload.
    assert result.structuredContent == {"result": result.content[0].text}


@pytest.mark.asyncio
async def test_failed_run_never_reports_iserror_false(config) -> None:  # type: ignore[no-untyped-def]
    """The reported signature: a placeholder answer with no flag set.

    A result object without ``answer_degraded`` (a bare test double, or an
    engine whose flag went missing) must not resurrect the defect when its
    ``answer`` is nothing but the rendered failure text.
    """
    result_obj = SimpleNamespace(
        answer=_placeholder("aggregator", GLM),
        trace=SimpleNamespace(
            model_dump=lambda mode: {
                "formation": "auto",
                "request_id": "req-d89-ns",
                "answer_stage_id": "aggregator",
                "dispatch": {"stage_id": "dispatch", "kind": "dispatch"},
                "worker_failures": [{"stage_id": "aggregator", "model": GLM, "error": UPSTREAM_ERROR}],
            }
        ),
    )
    server = build_server(config=config, engine=_StubEngine(result_obj))

    result = await _call(server, prompt="hello", formation="auto")

    assert result.isError is True
    payload = _payload(result)
    assert payload["error"] == NO_USABLE_ANSWER_ERROR
    assert payload["answer_degraded"] is True
    assert payload["answer_error"] is None  # unknown upstream error, not invented
    assert payload["trace"]["worker_failures"]


# --------------------------------------------------------------------------- #
# 2. Acceptance 2: a successful deliberation is unchanged
# --------------------------------------------------------------------------- #


def _healthy_responder(
    model: str, messages: list[dict[str, str]], response_format: Any = None, **kw: Any
) -> Any:
    if response_format is not None:
        return _resp(dispatch_json(), model, 100, 200)
    if "Upstream outputs" in json.dumps(messages):
        return _resp("FINAL MCP ANSWER", model, 60, 90)
    return _resp(f"worker {model}", model, 20, 40)


@pytest.mark.asyncio
async def test_successful_deliberation_is_not_an_error(config) -> None:  # type: ignore[no-untyped-def]
    """A healthy run keeps ``isError=false``, the merged answer, no markers."""
    server = build_server(config=config, engine=Engine(config, FakeGateway(_healthy_responder)))

    result = await _call(server, prompt="hello", formation="auto")

    assert result.isError is False
    payload = _payload(result)
    assert payload["answer"] == "FINAL MCP ANSWER"
    assert payload["trace"]["formation"] == "auto"
    assert "error" not in payload
    assert "answer_degraded" not in payload
    # The success arm's channels are byte-identical to the failure arm's shape.
    assert result.structuredContent == {"result": result.content[0].text}


@pytest.mark.asyncio
async def test_partial_degradation_is_not_an_error(config) -> None:  # type: ignore[no-untyped-def]
    """One dropped worker + a healthy merge still answers successfully."""
    trace = _trace(
        failures=[WorkerFailure(stage_id="worker_1", model=FLASH, error=UPSTREAM_ERROR)],
    )
    result_obj = DeliberationResult(answer="MERGED ANSWER", trace=trace)
    server = build_server(config=config, engine=_StubEngine(result_obj))

    result = await _call(server, prompt="review this", formation="auto")

    assert result.isError is False
    payload = _payload(result)
    assert payload["answer"] == "MERGED ANSWER"
    assert "error" not in payload
    # The dropped worker is still announced (unchanged behaviour).
    assert payload["trace"]["worker_failures"][0]["stage_id"] == "worker_1"


# --------------------------------------------------------------------------- #
# 3. The predicate itself (unit arms)
# --------------------------------------------------------------------------- #


def _two_terminal_all_degraded() -> str:
    """The multi-terminal join ``_select_answer`` builds when both terms degrade."""
    return (
        f"### agg_a ({GLM})\n{_placeholder('agg_a', GLM)}\n\n### agg_b ({GLM})\n{_placeholder('agg_b', GLM)}"
    )


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        (_placeholder("aggregator", GLM), True),
        (_two_terminal_all_degraded(), True),
        # An upstream error containing brackets must not defeat the anchored match.
        ("[stage agg (m) unavailable: boom [see docs]]", True),
        # Real content beside a placeholder is a (partially degraded) answer.
        (f"MERGED ANSWER\n\n### agg_b ({GLM})\n{_placeholder('agg_b', GLM)}", False),
        ("Here is one HTTP status code: 200", False),
        ("[stage-ish text but not the placeholder shape]", False),
        ("", False),
        (None, False),
    ],
)
def test_degraded_placeholder_detection(answer: Any, expected: bool) -> None:
    assert _is_degraded_placeholder_only(answer) is expected


def test_reason_is_none_for_a_healthy_result() -> None:
    result = DeliberationResult(answer="real answer", trace=_trace(), answer_degraded=False)
    assert _no_usable_answer_reason(result) is None


def test_tool_description_documents_the_error_contract(config) -> None:  # type: ignore[no-untyped-def]
    """The tool's description (the consumer-facing contract) names the marker."""
    server = build_server(config=config, engine=_StubEngine(DeliberationResult(answer="a", trace=_trace())))
    tool = next(t for t in server._tool_manager.list_tools() if t.name == "chimera_deliberate")
    description = tool.description or ""
    assert "isError" in description
    assert NO_USABLE_ANSWER_ERROR in description


def test_other_tools_are_untouched(config) -> None:  # type: ignore[no-untyped-def]
    """The catalog tools keep their own (non-deliberation) contract."""
    server = build_server(config=config, engine=_StubEngine(DeliberationResult(answer="a", trace=_trace())))
    names = {t.name for t in server._tool_manager.list_tools()}
    assert names == {"chimera_deliberate", "chimera_formations", "chimera_models"}
    assert CONFIG_DICT["formations"], "premise: the fixture config defines formations"
