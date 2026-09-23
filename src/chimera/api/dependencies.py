"""FastAPI dependencies for authentication, rate limiting, and security.

Provides injectable dependencies that protect API endpoints without
modifying route handlers directly.
"""

from __future__ import annotations

import os
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from chimera.config import ChimeraConfig

#: Query parameter carrying the API key for the ONE surface a browser cannot
#: give a header to: the SSE stream (`EventSource` has no header API).  The SPA
#: builds its dial URL from this same name, so the two halves cannot drift.
SSE_API_KEY_PARAM = "api_key"


def _get_config(request: Request) -> ChimeraConfig:
    """Extract the Chimera config from the app state."""
    return request.app.state.config


def require_api_key(
    request: Request,
    config: Annotated[ChimeraConfig, Depends(_get_config)],
) -> str:
    """FastAPI dependency that validates the API key for protected endpoints.

    Reads the key from the ``Authorization: Bearer <key>`` / ``X-API-Key``
    headers only; the verification itself lives in :func:`verify_api_key`, so
    the header path and the SSE query-parameter path
    (:func:`require_api_key_or_query`) can never disagree.

    Endpoints that use this dependency MUST pass authentication.
    Unauthenticated endpoints (health, models, formations, docs, and the SPA
    shell/static assets that have to load before a key can be entered) should
    NOT include this dependency.
    """
    return verify_api_key(config, _extract_api_key(request))


def require_api_key_or_query(
    request: Request,
    config: Annotated[ChimeraConfig, Depends(_get_config)],
) -> str:
    """Like :func:`require_api_key`, but also accepts ``?api_key=<key>``.

    DF-CHIMERA-V2-41: the SSE stream is dialed by a browser ``EventSource``,
    which cannot set request headers at all — so this ONE route takes the key
    from the query string as well, verified by the SAME
    :func:`verify_api_key` comparison (header first, then parameter; no forked
    check).  Tradeoff, accepted for the local web UI: a key in a query string
    can end up in server/proxy access logs, so every other route keeps the
    header-only gate.
    """
    provided = _extract_api_key(request)
    if not provided:
        provided = (request.query_params.get(SSE_API_KEY_PARAM) or "").strip() or None
    return verify_api_key(config, provided)


def verify_api_key(config: ChimeraConfig, provided_key: str | None) -> str:
    """Validate *provided_key* against *config* — the one comparison.

    Returns the validated key name on success (``"anonymous"`` when auth is
    disabled, ``"env"`` for env mode, the configured name for list mode) and
    raises HTTP 401 on failure.  Both entry points funnel through here so a
    future auth mode lands in exactly one place.
    """
    auth = config.auth

    # When disabled, allow all requests
    if not auth.enabled:
        return "anonymous"

    if not provided_key:
        _fail("Missing API key. Provide via Authorization: Bearer <key> or X-API-Key header.")

    if auth.mode == "env":
        expected = os.environ.get("CHIMERA_API_KEY")
        if expected and provided_key == expected:
            return "env"
        _fail("Invalid API key.")

    if auth.mode == "list":
        for entry in auth.keys:
            if entry.key == provided_key:
                return entry.name
        _fail("Invalid API key.")

    # disabled — allow all
    return "anonymous"


def _extract_api_key(request: Request) -> str | None:
    """Pull an API key from the Authorization header or X-API-Key header."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:].strip()

    x_api_key = request.headers.get("X-API-Key", "")
    if x_api_key:
        return x_api_key.strip()

    return None


def _fail(detail: str) -> None:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"error": "unauthorized", "message": detail},
    )
