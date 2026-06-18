"""FastAPI dependencies for authentication, rate limiting, and security.

Provides injectable dependencies that protect API endpoints without
modifying route handlers directly.
"""

from __future__ import annotations

import os
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from chimera.config import ChimeraConfig


def _get_config(request: Request) -> ChimeraConfig:
    """Extract the Chimera config from the app state."""
    return request.app.state.config


def require_api_key(
    request: Request,
    config: Annotated[ChimeraConfig, Depends(_get_config)],
) -> str:
    """FastAPI dependency that validates the API key for protected endpoints.

    Returns the validated key name on success, raises HTTP 401 on failure.

    Modes:
    * ``env`` — reads ``CHIMERA_API_KEY`` from the environment; a single
      shared key.
    * ``list`` — checks against config-defined keys in ``auth.keys``.

    Endpoints that use this dependency MUST pass authentication.
    Unauthenticated endpoints (health, models, formations, docs) should
    NOT include this dependency.
    """
    auth = config.auth

    # When disabled, allow all requests
    if not auth.enabled:
        return "anonymous"

    # Extract the key from the Authorization header or X-API-Key header
    provided_key = _extract_api_key(request)

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
