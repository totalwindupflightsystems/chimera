"""DF-CHIMERA-V2-44 — a fully degraded turn is an error, never a fake answer.

When every worker stage fails upstream the engine still hands back a result
whose ``answer`` is ``None``/empty while ``trace.worker_failures`` lists
everyone.  ``POST /web/sessions/{id}/chat`` used to store that answer verbatim
and answer 200, so the SPA rendered the literal text ``None`` as the answer
bubble, the DAG stayed green, and the user was billed full tokens with zero
signal that nothing worked.

This locks the fixed contract end to end:

* **A1 API** — such a run answers 502 with the ``all_workers_failed`` envelope:
  the failures list plus the token total the user was billed.
* **A2 regression** — a normal run answers 200 with the answer exactly as
  before (and a run with a surviving worker's answer is NOT treated as a
  failure), while the stored turn for a degraded run carries a clear
  ``[all workers failed]`` marker instead of the engine's answer.
* **SSE** — the ``deliberation_done`` frame for a degraded run carries the same
  envelope, so the live SPA renders the failure bubble.
* **A3 SPA** — the shipped ``index.html`` has a distinct failure-bubble branch
  keyed on that envelope, on BOTH the POST and the ``deliberation_done`` paths,
  and the success path still renders through ``addMessageBubble``.
* **A4 coherence** — the degraded turn is still recorded, so the next chat on
  the same session works and carries the failure marker in its history
  preamble.

Hermetic: no provider calls.  The engine is a stub handing back hand-built
``DeliberationResult``/trace objects (the real Engine is exercised for the
success-path regression guard, against a FakeGateway).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

import chimera.web.routes as web_routes  # noqa: E402
from chimera.api.server import create_app  # noqa: E402
from chimera.engine import (  # noqa: E402
    DeliberationResult,
    DeliberationTrace,
    Engine,
    StageSpan,
    WorkerFailure,
)
from chimera.gateway import GatewayResponse  # noqa: E402
from chimera.web.session import SessionManager  # noqa: E402
from chimera.web.sse import SSEBroadcaster  # noqa: E402
from tests.conftest import FakeGateway, dispatch_json  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
SPA_SOURCE = (REPO_ROOT / "src" / "chimera" / "web" / "static" / "index.html").read_text(encoding="utf-8")

#: The billed total the degraded trace reports (what the envelope must disclose).
TOKENS_BILLED = 412
COST_BILLED = 0.0042

_FAILURES = [
    WorkerFailure(
        stage_id="worker_1",
        model="deepseek/deepseek-chat",
        error="gateway timeout after 60s",
    ),
    WorkerFailure(
        stage_id="worker_2",
        model="openrouter/google/gemini-2.5-flash",
        error="HTTP 402: insufficient credits",
    ),
]


# ---------------------------------------------------------------------------
# Fixtures and stubs
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_web_singletons() -> Any:
    """Keep module-level web state isolated without replacing production behavior."""
    web_routes._session_manager = SessionManager()
    web_routes._sse_broadcaster = SSEBroadcaster()
    yield
    web_routes._session_manager = SessionManager()
    web_routes._sse_broadcaster = SSEBroadcaster()


def _span(stage_id: str, kind: str, model: str) -> StageSpan:
    return StageSpan(
        stage_id=stage_id,
        kind=kind,
        model=model,
        prompt="prompt",
        response="response",
        tokens_input=10,
        tokens_output=5,
        latency_ms=7,
        cost=0.0002,
    )


def _trace(
    *,
    failures: list[WorkerFailure] | None = None,
    total_tokens: int = TOKENS_BILLED,
    total_cost: float = COST_BILLED,
) -> DeliberationTrace:
    """A REAL trace (the route serializes it with ``model_dump``)."""
    return DeliberationTrace(
        request_id="req-degraded",
        formation="simple",
        source="preset",
        dispatch=_span("dispatch", "dispatch", "zai-coding-plan/glm-5.2"),
        stages=[
            _span("worker_1", "worker", "deepseek/deepseek-chat"),
            _span("worker_2", "worker", "openrouter/google/gemini-2.5-flash"),
            _span("aggregator", "aggregator", "zai-coding-plan/glm-5.2"),
        ],
        answer_stage_id="aggregator",
        total_tokens=total_tokens,
        total_cost=total_cost,
        total_duration_ms=1234,
        worker_failures=list(failures or []),
    )


class _StubResult:
    """A result whose ``answer`` may be None.

    ``DeliberationResult.answer`` is declared ``str``, so pydantic rejects
    ``answer=None`` at construction — but the degraded path this ticket
    describes hands the route a None/empty answer at runtime.  The stub keeps
    the REAL trace object so the route serializes exactly what production
    serializes.
    """

    def __init__(self, answer: str | None, trace: DeliberationTrace) -> None:
        self.answer = answer
        self.trace = trace


class _StubEngine:
    """Engine stub replaying one scripted result per call; records the prompts."""

    def __init__(self, results: list[Any]) -> None:
        self._results = list(results)
        self.prompts: list[str] = []

    async def deliberate(self, prompt: str, formation: str, **kwargs: Any) -> Any:
        self.prompts.append(prompt)
        return self._results.pop(0)


class _ScriptedEngine:
    """First call returns *first* (a degraded result); later calls delegate."""

    def __init__(self, first: Any, engine: Engine) -> None:
        self._first = first
        self._engine = engine
        self.prompts: list[str] = []

    async def deliberate(self, prompt: str, formation: str, **kwargs: Any) -> Any:
        self.prompts.append(prompt)
        if self._first is not None:
            first, self._first = self._first, None
            return first
        return await self._engine.deliberate(prompt, formation, **kwargs)


def _success_responder(dispatch_messages: list[str] | None = None):  # type: ignore[no-untyped-def]
    def responder(model, messages, response_format=None, **kw):  # type: ignore[no-untyped-def]
        if response_format is not None:
            if dispatch_messages is not None:
                dispatch_messages.append(json.dumps(messages))
            return GatewayResponse(text=dispatch_json(), model=model, tokens_input=100, tokens_output=200)
        joined = json.dumps(messages)
        if "Upstream outputs" in joined:
            return GatewayResponse(text="FINAL ANSWER", model=model, tokens_input=60, tokens_output=90)
        return GatewayResponse(text=f"worker {model}", model=model, tokens_input=20, tokens_output=40)

    return responder


def _client(config, engine: Any) -> TestClient:  # type: ignore[no-untyped-def]
    return TestClient(create_app(config=config, engine=engine))


def _new_session(client: TestClient) -> str:
    created = client.post("/web/sessions")
    assert created.status_code == 200
    return str(created.json()["session_id"])


def _chat(client: TestClient, session_id: str, prompt: str):  # type: ignore[no-untyped-def]
    return client.post(
        f"/web/sessions/{session_id}/chat",
        json={"prompt": prompt, "formation": "simple"},
    )


# ---------------------------------------------------------------------------
# A1 — the API answers a real failure with the envelope, not a fake-success turn
# ---------------------------------------------------------------------------


def test_empty_answer_with_all_workers_failed_answers_502_envelope(config) -> None:  # type: ignore[no-untyped-def]
    """A1: no usable answer + populated worker_failures ⇒ 502 + envelope."""
    client = _client(config, _StubEngine([_StubResult("", _trace(failures=_FAILURES))]))
    session_id = _new_session(client)

    response = _chat(client, session_id, "summarise the release notes")

    assert response.status_code != 200, f"a fully degraded run must not answer 200: {response.text}"
    assert response.status_code == 502, response.text
    detail = response.json()["detail"]

    assert detail["error"] == web_routes.ALL_WORKERS_FAILED_ERROR == "all_workers_failed"
    assert [f["stage_id"] for f in detail["worker_failures"]] == ["worker_1", "worker_2"]
    assert detail["worker_failures"][0] == {
        "stage_id": "worker_1",
        "model": "deepseek/deepseek-chat",
        "error": "gateway timeout after 60s",
    }
    assert detail["worker_failures"][1]["error"] == "HTTP 402: insufficient credits"
    # The user was billed — the envelope has to say how much.
    assert detail["tokens_billed"] == TOKENS_BILLED
    assert detail["cost_billed"] == pytest.approx(COST_BILLED)
    # No fake answer smuggled into the failure body.
    assert "answer" not in detail

    # Wording follows the CLI's dropped-worker announcement: stage, model, error.
    assert "worker_1" in detail["message"]
    assert "deepseek/deepseek-chat" in detail["message"]
    assert "gateway timeout after 60s" in detail["message"]


def test_none_answer_with_all_workers_failed_answers_502(config) -> None:  # type: ignore[no-untyped-def]
    """A1: the None-answer shape (what the SPA rendered as the text ``None``)."""
    client = _client(config, _StubEngine([_StubResult(None, _trace(failures=_FAILURES))]))
    session_id = _new_session(client)

    response = _chat(client, session_id, "hello")

    assert response.status_code == 502, response.text
    assert response.json()["detail"]["error"] == "all_workers_failed"
    assert response.json()["detail"]["tokens_billed"] == TOKENS_BILLED
    assert "None" not in json.dumps(response.json()["detail"]["message"])


def test_degraded_turn_is_stored_with_a_marker_never_as_the_answer(config) -> None:  # type: ignore[no-untyped-def]
    """A2: the turn stays in history (the user was billed) but is marked failed."""
    client = _client(config, _StubEngine([_StubResult(None, _trace(failures=_FAILURES))]))
    session_id = _new_session(client)
    assert _chat(client, session_id, "the prompt").status_code == 502

    history = client.get(f"/web/sessions/{session_id}").json()

    assert history["turn_count"] == 1
    stored = history["turns"][0]["answer"]
    assert stored != "None"
    assert stored != ""
    assert web_routes.ALL_WORKERS_FAILED_MARKER in stored
    assert "2 stage(s) failed" in stored
    assert f"{TOKENS_BILLED} tokens billed" in stored
    assert history["turns"][0]["user_prompt"] == "the prompt"
    assert history["turns"][0]["total_tokens"] == TOKENS_BILLED


def test_degraded_run_broadcasts_the_failure_envelope_on_done(config) -> None:  # type: ignore[no-untyped-def]
    """The live SSE path renders from the same envelope as the POST."""
    client = _client(config, _StubEngine([_StubResult("", _trace(failures=_FAILURES))]))
    session_id = _new_session(client)
    assert _chat(client, session_id, "hello").status_code == 502

    session = web_routes._session_manager.get(session_id)
    assert session is not None
    assert [name for name, _ in session.last_sse_events] == [
        "deliberation_started",
        "dag_designed",
        "deliberation_done",
    ]
    done = session.last_sse_events[-1][1]
    assert done["error"] == "all_workers_failed"
    assert [f["stage_id"] for f in done["worker_failures"]] == ["worker_1", "worker_2"]
    assert done["tokens_billed"] == TOKENS_BILLED
    assert done["answer"] == ""  # never the engine's None/placeholder on the wire
    # The stream is closed deliberately, exactly like a finished turn.
    assert session_id not in web_routes._sse_broadcaster._subscribers
    assert session.deliberation_in_flight is False


def test_message_elides_a_huge_error_but_the_failures_list_keeps_it(config) -> None:  # type: ignore[no-untyped-def]
    """The full upstream text stays in ``worker_failures``; only the message caps."""
    long_error = "upstream exploded " * 100
    failures = [WorkerFailure(stage_id="worker_1", model="deepseek/deepseek-chat", error=long_error)]
    client = _client(config, _StubEngine([_StubResult(None, _trace(failures=failures))]))
    session_id = _new_session(client)

    response = _chat(client, session_id, "hello")

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert detail["worker_failures"][0]["error"] == long_error
    assert long_error not in detail["message"]
    assert "truncated" in detail["message"]
    assert len(detail["message"]) < 600


# ---------------------------------------------------------------------------
# A2 — the success path is unchanged
# ---------------------------------------------------------------------------


def test_normal_run_answers_200_exactly_as_before(config) -> None:  # type: ignore[no-untyped-def]
    """A2: a healthy run keeps the pre-fix response shape and body."""
    client = _client(config, Engine(config, FakeGateway(_success_responder())))
    session_id = _new_session(client)

    response = _chat(client, session_id, "hello")

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"answer", "trace", "turn_number", "mermaid"}
    assert body["answer"] == "FINAL ANSWER"
    assert body["turn_number"] == 1
    assert body["mermaid"].startswith("flowchart TB")
    assert body["trace"]["elapsed_ms"] >= 0
    assert body["trace"]["worker_failures"] == []

    session = web_routes._session_manager.get(session_id)
    assert session is not None
    assert session.turns[0].answer == "FINAL ANSWER"
    assert [name for name, _ in session.last_sse_events] == [
        "deliberation_started",
        "dag_designed",
        "deliberation_done",
    ]
    stored_done = session.last_sse_events[-1][1]
    assert stored_done["answer"] == "FINAL ANSWER"
    assert "error" not in stored_done


def test_partial_failure_with_a_surviving_answer_still_answers_200(config) -> None:  # type: ignore[no-untyped-def]
    """The guard is narrow: one dropped worker must NOT fail a run that answered."""
    result = DeliberationResult(answer="PARTIAL ANSWER", trace=_trace(failures=_FAILURES[:1]))
    client = _client(config, _StubEngine([result]))
    session_id = _new_session(client)

    response = _chat(client, session_id, "hello")

    assert response.status_code == 200, response.text
    assert response.json()["answer"] == "PARTIAL ANSWER"
    session = web_routes._session_manager.get(session_id)
    assert session is not None
    assert session.turns[0].answer == "PARTIAL ANSWER"


# ---------------------------------------------------------------------------
# A4 — session coherence after a degraded turn
# ---------------------------------------------------------------------------


def test_session_keeps_working_after_a_degraded_turn(config) -> None:  # type: ignore[no-untyped-def]
    """A4: the next chat on the same session runs normally and sees the failure."""
    dispatch_messages: list[str] = []
    real_engine = Engine(config, FakeGateway(_success_responder(dispatch_messages)))
    engine = _ScriptedEngine(_StubResult(None, _trace(failures=_FAILURES)), real_engine)
    client = _client(config, engine)
    session_id = _new_session(client)

    first = _chat(client, session_id, "first question")
    assert first.status_code == 502, first.text

    # unsubscribe_all consumed the readiness signal — re-arm it (as test_web.py
    # does) so the second chat does not wait out the 2s readiness timeout.
    web_routes._sse_broadcaster.ensure_ready(session_id).set()

    second = _chat(client, session_id, "follow-up question")

    assert second.status_code == 200, second.text
    assert second.json()["answer"] == "FINAL ANSWER"
    assert second.json()["turn_number"] == 2
    # The failed turn is part of the session's history for the NEXT deliberation.
    assert "## Conversation history" in engine.prompts[-1]
    assert "first question" in engine.prompts[-1]
    assert web_routes.ALL_WORKERS_FAILED_MARKER in engine.prompts[-1]

    history = client.get(f"/web/sessions/{session_id}").json()
    assert history["turn_count"] == 2
    assert history["turns"][1]["answer"] == "FINAL ANSWER"


# ---------------------------------------------------------------------------
# A3 — the SPA handles the failure envelope on both paths
# ---------------------------------------------------------------------------


def test_spa_defines_a_distinct_failure_bubble() -> None:
    """A3: a failure bubble of its own — never the normal answer bubble."""
    assert "function failureFromEnvelope(" in SPA_SOURCE
    assert "function addFailureBubble(" in SPA_SOURCE
    # Keyed on the server's discriminator, not on a bare 502.
    assert "all_workers_failed" in SPA_SOURCE
    # A class of its own, with styling — the answer bubble is untouched.
    assert "msg-bubble msg-failure" in SPA_SOURCE
    assert ".msg-failure" in SPA_SOURCE
    # Lists the failed stages, their errors, and what the run cost the user.
    assert "failure-list" in SPA_SOURCE
    assert "Tokens billed:" in SPA_SOURCE


def test_spa_failure_branch_is_wired_into_post_and_sse_paths() -> None:
    """A3: the POST 502 envelope AND the deliberation_done frame both route in."""
    # SSE live path: deliberation_done is parsed for the failure envelope.
    assert "failureFromEnvelope(data)" in SPA_SOURCE
    # POST path: the non-2xx body is parsed for the same envelope.
    assert "failureFromEnvelope(payload" in SPA_SOURCE
    # Definition + both call sites.
    assert SPA_SOURCE.count("failureFromEnvelope(") >= 3


def test_spa_success_path_still_renders_through_the_answer_bubble() -> None:
    """A3: success renders exactly where it did before."""
    assert "addMessageBubble(data.answer, data.turn_number, currentMermaid," in SPA_SOURCE
    assert "addMessageBubble(data.answer, data.turn_number, data.mermaid, data.trace);" in SPA_SOURCE
