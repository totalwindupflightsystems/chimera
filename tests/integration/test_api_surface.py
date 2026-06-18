"""API surface tests — verify endpoint schemas for unauthenticated endpoints.

Hits ``GET /v1/health``, ``GET /v1/health/ready``, ``GET /v1/models``, and
``GET /v1/formations`` against the live server.  These endpoints do NOT
require authentication (per ``require_api_key`` docs).

``/v1/health`` and ``/v1/health/ready`` call ``_check_providers()`` which
pings each provider with a 5 s timeout — so these can take up to ~15 s.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]


# ═══════════════════════════════════════════════════════════════════════════
#  Health endpoints
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_health_live(live_server: str) -> None:
    """``GET /v1/health/live`` — liveness probe, always 200."""
    import httpx

    async with httpx.AsyncClient() as client:
        r = await client.get(f"{live_server}/v1/health/live", timeout=10.0)

    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "alive"
    assert "uptime_models" in body
    assert isinstance(body["uptime_models"], int)
    assert body["uptime_models"] > 0, "no models configured"


@pytest.mark.asyncio
async def test_health(live_server: str) -> None:
    """``GET /v1/health`` — health check with provider connectivity.

    Returns 200 with status ``healthy`` or ``degraded``.  Never fails (200)
    even if providers are unreachable.
    """
    import httpx

    async with httpx.AsyncClient() as client:
        r = await client.get(f"{live_server}/v1/health", timeout=30.0)

    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("healthy", "degraded"), f"Unexpected status: {body['status']}"

    details = body["details"]
    assert details["config_loaded"] is True
    assert details["models_configured"] > 0
    assert details["providers_configured"] > 0

    # Provider status should be present
    if "providers" in details:
        for provider_name, info in details["providers"].items():
            assert "healthy" in info, f"Provider {provider_name} missing 'healthy' key"


@pytest.mark.asyncio
async def test_health_ready(live_server: str) -> None:
    """``GET /v1/health/ready`` — readiness probe.

    Returns 200 if at least one provider is reachable, 503 if none.
    """
    import httpx

    async with httpx.AsyncClient() as client:
        r = await client.get(f"{live_server}/v1/health/ready", timeout=30.0)

    # 200 = at least one provider reachable; 503 = none reachable
    assert r.status_code in (200, 503), f"Unexpected status: {r.status_code}"

    if r.status_code == 200:
        body = r.json()
        assert body["status"] == "ready"
        assert "providers" in body
    # 503 is acceptable if all providers are temporarily down


# ═══════════════════════════════════════════════════════════════════════════
#  Models & formations
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_models(live_server: str) -> None:
    """``GET /v1/models`` — list configured models with category weights."""
    import httpx

    async with httpx.AsyncClient() as client:
        r = await client.get(f"{live_server}/v1/models", timeout=10.0)

    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, dict)
    assert len(body) > 0, "no models returned"

    # Verify schema for each model entry
    for name, entry in body.items():
        assert "categories" in entry, f"Model {name} missing 'categories'"
        assert isinstance(entry["categories"], dict)
        assert "cost_tier" in entry, f"Model {name} missing 'cost_tier'"
        assert "provider" in entry, f"Model {name} missing 'provider'"

    # Should contain the budget models we use in other tests
    assert "deepseek/deepseek-v4-flash" in body, "deepseek-v4-flash not in models"
    assert "deepseek/deepseek-v4-pro" in body, "deepseek-v4-pro not in models"


@pytest.mark.asyncio
async def test_formations(live_server: str) -> None:
    """``GET /v1/formations`` — list formation presets."""
    import httpx

    async with httpx.AsyncClient() as client:
        r = await client.get(f"{live_server}/v1/formations", timeout=10.0)

    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, dict)
    assert len(body) > 0, "no formations returned"

    # Verify expected formations from chimera.yaml
    assert "auto" in body, "'auto' formation missing"
    assert "simple" in body, "'simple' formation missing"

    # Verify formation schema
    for name, preset in body.items():
        assert isinstance(preset, dict), f"Formation {name} is not a dict"

    # auto formation should have mode=auto
    assert body["auto"].get("mode") == "auto", f"auto formation mode wrong: {body['auto']}"

    # simple formation should have workers >= 1
    assert body["simple"].get("workers", 0) >= 1, (
        f"simple formation workers wrong: {body['simple']}"
    )
