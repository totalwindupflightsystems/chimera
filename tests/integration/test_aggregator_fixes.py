"""LIVE integration tests for aggregator fixes.

Two bugs were found and fixed during live E2E testing:

1. **DeepSeek json_object requires "json" in prompt** — Without it, the
   aggregator call fails with ``BadRequestError: Prompt must contain the word
   'json'``.  The fix appends ``Respond in valid JSON format.`` to the
   aggregator prompt.  Tested here by running the ``simple`` formation
   exclusively on DeepSeek models — if the aggregator degrades, the fix is
   broken.

2. **Plain-text fallback when aggregator == default model** — Previously, the
   ``_execute_stage`` retry only fired when ``stage.model != fallback_model``.
   When the dispatcher picked the default aggregator (the common case), a
   json_object failure would degrade the stage with no retry.  The fix always
   retries aggregator stages with ``output_schema=None`` (plain text) as a
   second fallback after a model-switch retry.

These tests hit ``POST /v1/deliberate`` against a REAL running server with
REAL provider API calls.
"""

from __future__ import annotations

import pytest

from tests.integration.conftest import BUDGET_MODELS

pytestmark = [pytest.mark.integration, pytest.mark.slow]

TIMEOUT = 120.0


# ── Helper ─────────────────────────────────────────────────────────────────


def _assert_no_degraded_stages(body: dict) -> None:
    """Verify no stage in the trace is degraded."""
    trace = body["trace"]
    stages = trace.get("stages", [])
    for stage in stages:
        # Integration tests pass raw responses; StageSpan is a plain dict here.
        assert not stage.get("degraded", False), (
            f"Stage {stage.get('stage_id', '?')} is degraded: "
            f"{stage.get('response', '')[:200]}"
        )
        # The response should NOT contain an unavailable/failed marker.
        resp = stage.get("response", "")
        assert "[stage " not in resp.lower() or "unavailable" not in resp.lower(), (
            f"Stage {stage.get('stage_id', '?')} response looks degraded: "
            f"{resp[:200]}"
        )


def _assert_has_valid_answer(body: dict, expected_substring: str = "4") -> None:
    """Assert the answer is present and contains the expected substring."""
    answer = body["answer"]
    assert isinstance(answer, str), f"answer is {type(answer)}, expected str"
    assert answer.strip(), "answer is empty"
    answer_lower = answer.lower()
    assert "unavailable" not in answer_lower, (
        f"Answer is a degraded/unavailable message: {answer!r}"
    )
    assert "error" not in answer_lower or "json" in answer_lower, (
        f"Answer contains 'error': {answer!r}"
    )
    assert expected_substring in answer_lower, (
        f"Answer doesn't contain '{expected_substring}': {answer!r}"
    )


# ═══════════════════════════════════════════════════════════════════════════
#  Fix 1 — json_object prompt includes "json" keyword
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_json_object_works_on_deepseek_simple(live_server: str) -> None:
    """``simple`` formation on pure DeepSeek — aggregator must NOT degrade.

    The ``simple`` formation uses a 2-worker → aggregator DAG.  The
    aggregator runs with structured output (``json_schema`` downgraded to
    ``json_object`` for DeepSeek).  With the fix, the prompt includes
    "Respond in valid JSON format." and the call succeeds.
    """
    import httpx

    payload = {
        "prompt": "What is 2+2? Reply with just the number, nothing else.",
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
    _assert_has_valid_answer(body, expected_substring="4")
    _assert_no_degraded_stages(body)


@pytest.mark.asyncio
async def test_json_object_works_on_deepseek_simple_aggregator(live_server: str) -> None:
    """``simple`` formation on pure DeepSeek — aggregator must NOT degrade.

    Tests the aggregator json_object fix.  The ``simple`` formation provides
    a preset DAG so the dispatcher doesn't choose models outside budget.
    """
    payload = {
        "prompt": "What is 2+2? Reply with just the number, nothing else.",
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
    _assert_has_valid_answer(body, expected_substring="4")
    _assert_no_degraded_stages(body)


# ═══════════════════════════════════════════════════════════════════════════
#  Fix 2 — Plain-text fallback retry
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_aggregator_default_model_produces_answer(live_server: str) -> None:
    """Aggregator is the DEFAULT model — must still produce clean answer.

    Before the fix, if the aggregator model matched the default and the
    json_object call failed, the stage would degrade with no retry.  Now
    the plain-text fallback (``output_schema=None``) always runs.
    """
    import httpx

    # Force the dispatcher and aggregator to be the SAME budget model so the
    # "different model" retry path is skipped.  Only the plain-text fallback
    # can save us if json_object fails here.
    payload = {
        "prompt": "What is 3+5? Reply with just the number.",
        "formation": "simple",
        "allowed_models": ["deepseek/deepseek-v4-flash"],
        "aggregator_model": "deepseek/deepseek-v4-flash",
        "dispatcher_model": "deepseek/deepseek-v4-flash",
    }

    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{live_server}/v1/deliberate",
            json=payload,
            timeout=TIMEOUT,
        )

    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text[:500]}"
    body = r.json()
    _assert_has_valid_answer(body, expected_substring="8")
    _assert_no_degraded_stages(body)


# ═══════════════════════════════════════════════════════════════════════════
#  Stress — Multiple iterations
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_three_consecutive_simple_formations(live_server: str) -> None:
    """Run 3 simple deliberations in a row — all must succeed.

    Flaky failures (intermittent json_object errors) would show up here.
    """
    import asyncio

    import httpx

    async def run_one(i: int) -> dict:
        payload = {
            "prompt": f"What is {i}+{i}? Reply with just the number, nothing else.",
            "formation": "simple",
            "allowed_models": BUDGET_MODELS,
        }
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{live_server}/v1/deliberate",
                json=payload,
                timeout=TIMEOUT,
            )
        assert r.status_code == 200, f"Iteration {i}: expected 200, got {r.status_code}"
        return r.json()

    results = await asyncio.gather(*(run_one(i) for i in range(1, 4)))

    for i, body in enumerate(results, 1):
        expected = str(i + i)
        _assert_has_valid_answer(body, expected_substring=expected)
        _assert_no_degraded_stages(body)
