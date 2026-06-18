"""LIVE integration tests for multi-turn context pipe.

The web UI's ``SessionManager`` injects past dispatcher choices and
aggregator results into the next deliberation's prompt.  These tests
verify that the context pipe works by:

1. Sending a calculation that requires the previous answer
2. Verifying the follow-up answer depends on prior state
3. Confirming no stages degrade across multiple turns
"""

from __future__ import annotations

import pytest

from tests.integration.conftest import BUDGET_MODELS

pytestmark = [pytest.mark.integration, pytest.mark.slow]

TIMEOUT = 120.0


def _assert_no_degraded(answer: str, trace: dict) -> None:
    """Verify answer is clean and no stages degraded."""
    assert "unavailable" not in answer.lower(), f"Degraded: {answer[:200]}"
    assert "[stage " not in answer.lower(), f"Stage error: {answer[:200]}"
    for stage in trace.get("stages", []):
        resp = stage.get("response", "")
        assert "[stage " not in resp.lower() or "unavailable" not in resp.lower(), (
            f"Stage {stage.get('stage_id', '?')} degraded: {resp[:200]}"
        )


# ═══════════════════════════════════════════════════════════════════════════
#  Multi-turn — answer depends on prior turn
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_two_turn_calculation_depends_on_prior(live_server: str) -> None:
    """Turn 1: compute 6+5. Turn 2: multiply that result by 3.

    Turn 2 must produce 33 (not some arbitrary number), proving the
    context pipe fed the previous aggregator result into the dispatcher.
    """
    import httpx

    # Create a session and send Turn 1
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{live_server}/web/sessions", timeout=10)
        assert r.status_code == 200, f"Session create: {r.status_code}"
        session_id = r.json()["session_id"]

        # Turn 1: simple arithmetic
        r1 = await client.post(
            f"{live_server}/web/sessions/{session_id}/chat",
            json={
                "prompt": "What is 6 plus 5? Answer with ONLY the number, nothing else.",
                "formation": "simple",
                "allowed_models": BUDGET_MODELS,
            },
            timeout=TIMEOUT,
        )
        assert r1.status_code == 200, f"Turn 1: {r1.status_code} {r1.text[:200]}"
        t1 = r1.json()
        answer1 = t1["answer"].strip()
        _assert_no_degraded(answer1, t1["trace"])
        assert "11" in answer1.lower() or answer1 in ("11", "11.", "11.0"), (
            f"Turn 1 expected 11, got: {answer1!r}"
        )

        # Turn 2: multiply the previous answer (which was 11) by 3
        r2 = await client.post(
            f"{live_server}/web/sessions/{session_id}/chat",
            json={
                "prompt": "Take the answer you just computed, and multiply it by 3. "
                          "Answer with ONLY the resulting number, nothing else.",
                "formation": "simple",
                "allowed_models": BUDGET_MODELS,
            },
            timeout=TIMEOUT,
        )
        assert r2.status_code == 200, f"Turn 2: {r2.status_code} {r2.text[:200]}"
        t2 = r2.json()
        answer2 = t2["answer"].strip()
        _assert_no_degraded(answer2, t2["trace"])
        assert "33" in answer2.lower() or answer2 in ("33", "33.", "33.0"), (
            f"Turn 2 expected 33 (11*3), got: {answer2!r}"
        )

        assert t2["turn_number"] == 2, f"Expected turn 2, got {t2['turn_number']}"


@pytest.mark.asyncio
async def test_three_turn_accumulating_context(live_server: str) -> None:
    """Three turns where each builds on the prior.

    Turn 1: 2+3=5
    Turn 2: result * 4 = 20
    Turn 3: result + 7 = 27

    Each turn's correct answer proves the context pipeline is working.
    """
    import httpx

    async with httpx.AsyncClient() as client:
        r = await client.post(f"{live_server}/web/sessions", timeout=10)
        session_id = r.json()["session_id"]

        # Turn 1
        r1 = await client.post(
            f"{live_server}/web/sessions/{session_id}/chat",
            json={
                "prompt": "What is 2 plus 3? Reply with JUST the number.",
                "formation": "simple",
                "allowed_models": BUDGET_MODELS,
            },
            timeout=TIMEOUT,
        )
        assert r1.status_code == 200
        a1 = r1.json()["answer"].strip()
        assert "5" in a1.lower() or a1 == "5", f"Turn 1: {a1}"

        # Turn 2
        r2 = await client.post(
            f"{live_server}/web/sessions/{session_id}/chat",
            json={
                "prompt": "Take your previous answer and multiply it by 4. "
                          "Reply with JUST the number.",
                "formation": "simple",
                "allowed_models": BUDGET_MODELS,
            },
            timeout=TIMEOUT,
        )
        assert r2.status_code == 200
        a2 = r2.json()["answer"].strip()
        assert "20" in a2.lower() or a2 == "20", f"Turn 2: {a2}"

        # Turn 3
        r3 = await client.post(
            f"{live_server}/web/sessions/{session_id}/chat",
            json={
                "prompt": "Take your previous answer and add 7. "
                          "Reply with JUST the number.",
                "formation": "simple",
                "allowed_models": BUDGET_MODELS,
            },
            timeout=TIMEOUT,
        )
        assert r3.status_code == 200
        a3 = r3.json()["answer"].strip()
        assert "27" in a3.lower() or a3 == "27", f"Turn 3: {a3}"


@pytest.mark.asyncio
async def test_session_persistence_across_fetches(live_server: str) -> None:
    """Verify that ``GET /web/sessions/{id}`` returns correct turn history.

    After two turns, the GET endpoint must show turn_count=2 with both
    prompts and answers.
    """
    import httpx

    async with httpx.AsyncClient() as client:
        r = await client.post(f"{live_server}/web/sessions", timeout=10)
        session_id = r.json()["session_id"]

        # Two quick turns
        for prompt in ("What is 1+1? Reply: just the number.", "What is 3+4? Reply: just the number."):
            r = await client.post(
                f"{live_server}/web/sessions/{session_id}/chat",
                json={
                    "prompt": prompt,
                    "formation": "simple",
                    "allowed_models": BUDGET_MODELS,
                },
                timeout=TIMEOUT,
            )
            assert r.status_code == 200

        # Verify session history
        r = await client.get(
            f"{live_server}/web/sessions/{session_id}", timeout=10,
        )
        assert r.status_code == 200
        info = r.json()
        assert info["turn_count"] == 2, f"Expected 2 turns, got {info['turn_count']}"
        assert len(info["turns"]) == 2, f"Expected 2 turn objects, got {len(info['turns'])}"

        # Each turn should have the required fields
        for turn in info["turns"]:
            assert "user_prompt" in turn
            assert "answer" in turn
            assert "formation" in turn
            assert "total_tokens" in turn
            assert "total_cost" in turn
            assert turn["total_tokens"] > 0, f"Tokens should be >0: {turn}"
