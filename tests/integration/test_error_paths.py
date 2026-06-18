"""Error path tests — auth failures, validation errors, rate limiting.

All tests hit the **auth_server** (port 8811) which has:

* ``auth.enabled: true``, ``auth.mode: env``, ``CHIMERA_API_KEY`` set.
* ``rate_limit.enabled: true``, ``burst_size: 2``, ``requests_per_minute: 2``.

Test matrix:

* ``401`` — invalid API key / missing API key.
* ``400`` — unknown formation name.
* ``422`` — missing ``prompt`` field (Pydantic validation).
* ``429`` — rate limit burst exhaustion.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from tests.integration.conftest import BUDGET_MODELS, VALID_API_KEY

pytestmark = [pytest.mark.integration, pytest.mark.slow]

TIMEOUT = 120.0


# ═══════════════════════════════════════════════════════════════════════════
#  401 — Authentication failures
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_invalid_api_key_401(auth_server: str) -> None:
    """POST /v1/deliberate with a wrong Bearer token → 401."""
    payload = {
        "prompt": "hello",
        "formation": "simple",
        "allowed_models": BUDGET_MODELS,
    }
    headers = {"Authorization": "Bearer this-key-is-definitely-wrong"}

    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{auth_server}/v1/deliberate",
            json=payload,
            headers=headers,
            timeout=10.0,
        )

    assert r.status_code == 401, f"Expected 401, got {r.status_code}: {r.text[:300]}"
    body = r.json()
    error_detail = body.get("detail", body)
    assert error_detail.get("error") == "unauthorized" or "key" in str(error_detail).lower()


@pytest.mark.asyncio
async def test_missing_api_key_401(auth_server: str) -> None:
    """POST /v1/deliberate with no auth header at all → 401."""
    payload = {
        "prompt": "hello",
        "formation": "simple",
        "allowed_models": BUDGET_MODELS,
    }
    # No Authorization or X-API-Key header

    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{auth_server}/v1/deliberate",
            json=payload,
            timeout=10.0,
        )

    assert r.status_code == 401, f"Expected 401, got {r.status_code}: {r.text[:300]}"


# ═══════════════════════════════════════════════════════════════════════════
#  400 — Invalid request semantics
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_dag_without_allow_flag_400(auth_server: str) -> None:
    """POST /v1/deliberate with a ``dag`` but no ``allow_custom_dag`` → 400.

    The server checks this *before* calling ``engine.deliberate()`` so the
    400 is returned immediately (no API calls, no dispatcher latency).

    Note: an unknown *formation name* does NOT return 400 — the dispatcher's
    ``_resolve_preset`` logs a warning and falls back to auto mode (returns
    200 with a real deliberation).  The dag/allow_custom_dag mismatch is the
    deterministic 400 path.
    """
    payload = {
        "prompt": "hello",
        "formation": "simple",
        "allowed_models": BUDGET_MODELS,
        "dag": {"stages": [], "edges": []},  # DAG provided without flag
    }
    headers = {"Authorization": f"Bearer {VALID_API_KEY}"}

    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{auth_server}/v1/deliberate",
            json=payload,
            headers=headers,
            timeout=10.0,
        )

    assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text[:300]}"
    body = r.json()
    detail = body.get("detail", body)
    assert "allow_custom_dag" in str(detail).lower() or "dag" in str(detail).lower()


# ═══════════════════════════════════════════════════════════════════════════
#  422 — Missing required field (Pydantic validation)
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_missing_prompt_422(auth_server: str) -> None:
    """POST /v1/deliberate without the required ``prompt`` field → 422.

    FastAPI/Pydantic validates the request body before the handler runs.
    A missing required field returns 422 Unprocessable Entity (not 400).
    """
    # No "prompt" key — only formation
    payload = {"formation": "simple", "allowed_models": BUDGET_MODELS}
    headers = {"Authorization": f"Bearer {VALID_API_KEY}"}

    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{auth_server}/v1/deliberate",
            json=payload,
            headers=headers,
            timeout=10.0,
        )

    assert r.status_code == 422, f"Expected 422, got {r.status_code}: {r.text[:300]}"
    body = r.json()
    # FastAPI validation error has a "detail" list
    assert "detail" in body, f"Expected 'detail' in validation error: {body}"


# ═══════════════════════════════════════════════════════════════════════════
#  429 — Rate limit burst exhaustion
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_rate_limit_burst_429(auth_server: str) -> None:
    """Fire enough concurrent requests to exhaust burst_size=2 → 429.

    The auth_server has ``burst_size: 2`` and ``requests_per_minute: 2``.
    Previous tests on this session-scoped server may have already consumed
    some tokens, so we fire 6 requests to guarantee exhaustion regardless
    of prior state.

    We use ``allowed_models`` to constrain to budget deepseek models so the
    requests that DO pass are cheap.  At most 2 can pass the rate limiter;
    the rest get 429.
    """
    payload = {
        "prompt": "Reply with: ok",
        "formation": "simple",
        "allowed_models": BUDGET_MODELS,
    }
    headers = {"Authorization": f"Bearer {VALID_API_KEY}"}

    async with httpx.AsyncClient() as client:
        # Fire 6 requests concurrently — burst_size=2 guarantees exhaustion
        tasks = [
            client.post(
                f"{auth_server}/v1/deliberate",
                json=payload,
                headers=headers,
                timeout=TIMEOUT,
            )
            for _ in range(6)
        ]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

    statuses: list[int | None] = []
    rate_limited_response: httpx.Response | None = None
    for r in responses:
        if isinstance(r, httpx.Response):
            statuses.append(r.status_code)
            if r.status_code == 429:
                rate_limited_response = r
        else:
            statuses.append(None)

    # At least one should be rate-limited (429) — this is the core assertion
    assert 429 in statuses, (
        f"Expected at least one 429 from burst exhaustion, got statuses: {statuses}"
    )

    # Verify the 429 response has the expected error structure
    assert rate_limited_response is not None
    body = rate_limited_response.json()
    error_detail = body.get("detail", body)
    assert error_detail.get("error") == "rate_limited", (
        f"Expected error=rate_limited in 429 body: {error_detail}"
    )
    # Should have a Retry-After header
    assert "retry-after" in {k.lower() for k in rate_limited_response.headers}, (
        "429 response missing Retry-After header"
    )
