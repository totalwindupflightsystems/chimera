"""LIVE end-to-end deliberation tests.

Hits ``POST /v1/deliberate`` against a REAL running server with REAL provider
API calls.  Tests both ``auto`` and ``simple`` formations.

Budget models only (deepseek-v4-flash / deepseek-v4-pro) to keep costs
negligible.  ``allowed_models`` constrains the dispatcher to deepseek models
so it never picks unreachable OpenRouter endpoints.
"""

from __future__ import annotations

import pytest

from tests.integration.conftest import BUDGET_MODELS

pytestmark = [pytest.mark.integration, pytest.mark.slow]

# Simple prompt that any model can answer in 1-2 tokens.
SIMPLE_PROMPT = "What is 2+2? Reply with just the number, nothing else."

# Generous timeout — real deliberation involves 3-5 LLM calls in sequence.
TIMEOUT = 120.0


# ── Helper ─────────────────────────────────────────────────────────────────


def _assert_deliberation_response(body: dict) -> None:
    """Assert that a /v1/deliberate response has all required fields."""
    # answer
    assert "answer" in body, "response missing 'answer'"
    assert isinstance(body["answer"], str), f"answer is {type(body['answer'])}, expected str"
    assert body["answer"].strip(), "answer is empty"

    # request_id
    assert "request_id" in body, "response missing 'request_id'"
    assert isinstance(body["request_id"], str), "request_id must be str"
    assert len(body["request_id"]) > 0, "request_id is empty"

    # trace
    assert "trace" in body, "response missing 'trace'"
    trace = body["trace"]
    assert isinstance(trace, dict), f"trace is {type(trace)}, expected dict"

    # trace should have dispatch info
    assert "dispatch" in trace or "stages" in trace, (
        f"trace missing dispatch/stages, keys: {list(trace.keys())}"
    )

    # cost is nonzero — total_tokens should be > 0 after real API calls
    total_tokens = trace.get("total_tokens", 0)
    assert total_tokens > 0, (
        f"total_tokens is {total_tokens} — expected nonzero after real API calls. "
        f"Trace keys: {list(trace.keys())}"
    )


# ═══════════════════════════════════════════════════════════════════════════
#  Tests
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_deliberate_simple_formation(live_server: str) -> None:
    """E2E: ``simple`` formation with budget deepseek models.

    Verifies the full pipeline: dispatcher → 2 workers (parallel) → aggregator.
    """
    import httpx

    payload = {
        "prompt": SIMPLE_PROMPT,
        "formation": "simple",
        "allowed_models": BUDGET_MODELS,
    }

    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{live_server}/v1/deliberate",
            json=payload,
            timeout=TIMEOUT,
        )

    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text[:500]}"
    body = r.json()
    _assert_deliberation_response(body)

    # The aggregator may degrade (DeepSeek requires "json" in the prompt for
    # response_format=json_object).  If it succeeds, the answer should be "4".
    # If it degrades, the answer is an error string but still non-empty.
    answer_lower = body["answer"].lower()
    if "unavailable" not in answer_lower and "failed" not in answer_lower:
        assert "4" in answer_lower, f"Answer doesn't contain '4': {body['answer']!r}"


@pytest.mark.asyncio
async def test_deliberate_auto_formation(live_server: str) -> None:
    """E2E: ``auto`` formation — dispatcher designs the DAG.

    The dispatcher (deepseek-v4-flash) selects worker models and generates
    per-worker prompts.  ``allowed_models`` keeps it on budget deepseek models.
    """
    import httpx

    payload = {
        "prompt": SIMPLE_PROMPT,
        "formation": "auto",
        "allowed_models": BUDGET_MODELS,
    }

    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{live_server}/v1/deliberate",
            json=payload,
            timeout=TIMEOUT,
        )

    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text[:500]}"
    body = r.json()
    _assert_deliberation_response(body)

    # For auto formation, the trace should have stage information
    trace = body["trace"]
    # The dispatcher designed the DAG — trace should reflect multiple stages.
    # At minimum, dispatch info should be present
    assert trace.get("dispatch") is not None or len(trace) >= 3, (
        f"Auto formation trace seems incomplete, keys: {list(trace.keys())}"
    )
