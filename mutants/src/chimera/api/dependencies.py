"""FastAPI dependencies for authentication, rate limiting, and security.

Provides injectable dependencies that protect API endpoints without
modifying route handlers directly.
"""

from __future__ import annotations

import os
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from chimera.config import ChimeraConfig


from mutmut.mutation.trampoline import wrap_in_trampoline as _mutmut_mutated, MutantDict


def _get_config(request: Request) -> ChimeraConfig:
    """Extract the Chimera config from the app state."""
    return request.app.state.config
mutants_x_require_api_key__mutmut: MutantDict = {}  # type: ignore


@_mutmut_mutated(mutants_x_require_api_key__mutmut)
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


def x_require_api_key__mutmut_orig(
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


def x_require_api_key__mutmut_1(
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
    auth = None

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


def x_require_api_key__mutmut_2(
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
    if auth.enabled:
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


def x_require_api_key__mutmut_3(
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
        return "XXanonymousXX"

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


def x_require_api_key__mutmut_4(
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
        return "ANONYMOUS"

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


def x_require_api_key__mutmut_5(
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
    provided_key = None

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


def x_require_api_key__mutmut_6(
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
    provided_key = _extract_api_key(None)

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


def x_require_api_key__mutmut_7(
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

    if provided_key:
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


def x_require_api_key__mutmut_8(
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
        _fail(None)

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


def x_require_api_key__mutmut_9(
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
        _fail("XXMissing API key. Provide via Authorization: Bearer <key> or X-API-Key header.XX")

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


def x_require_api_key__mutmut_10(
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
        _fail("missing api key. provide via authorization: bearer <key> or x-api-key header.")

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


def x_require_api_key__mutmut_11(
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
        _fail("MISSING API KEY. PROVIDE VIA AUTHORIZATION: BEARER <KEY> OR X-API-KEY HEADER.")

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


def x_require_api_key__mutmut_12(
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

    if auth.mode != "env":
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


def x_require_api_key__mutmut_13(
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

    if auth.mode == "XXenvXX":
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


def x_require_api_key__mutmut_14(
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

    if auth.mode == "ENV":
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


def x_require_api_key__mutmut_15(
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
        expected = None
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


def x_require_api_key__mutmut_16(
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
        expected = os.environ.get(None)
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


def x_require_api_key__mutmut_17(
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
        expected = os.environ.get("XXCHIMERA_API_KEYXX")
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


def x_require_api_key__mutmut_18(
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
        expected = os.environ.get("chimera_api_key")
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


def x_require_api_key__mutmut_19(
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
        if expected or provided_key == expected:
            return "env"
        _fail("Invalid API key.")

    if auth.mode == "list":
        for entry in auth.keys:
            if entry.key == provided_key:
                return entry.name
        _fail("Invalid API key.")

    # disabled — allow all
    return "anonymous"


def x_require_api_key__mutmut_20(
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
        if expected and provided_key != expected:
            return "env"
        _fail("Invalid API key.")

    if auth.mode == "list":
        for entry in auth.keys:
            if entry.key == provided_key:
                return entry.name
        _fail("Invalid API key.")

    # disabled — allow all
    return "anonymous"


def x_require_api_key__mutmut_21(
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
            return "XXenvXX"
        _fail("Invalid API key.")

    if auth.mode == "list":
        for entry in auth.keys:
            if entry.key == provided_key:
                return entry.name
        _fail("Invalid API key.")

    # disabled — allow all
    return "anonymous"


def x_require_api_key__mutmut_22(
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
            return "ENV"
        _fail("Invalid API key.")

    if auth.mode == "list":
        for entry in auth.keys:
            if entry.key == provided_key:
                return entry.name
        _fail("Invalid API key.")

    # disabled — allow all
    return "anonymous"


def x_require_api_key__mutmut_23(
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
        _fail(None)

    if auth.mode == "list":
        for entry in auth.keys:
            if entry.key == provided_key:
                return entry.name
        _fail("Invalid API key.")

    # disabled — allow all
    return "anonymous"


def x_require_api_key__mutmut_24(
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
        _fail("XXInvalid API key.XX")

    if auth.mode == "list":
        for entry in auth.keys:
            if entry.key == provided_key:
                return entry.name
        _fail("Invalid API key.")

    # disabled — allow all
    return "anonymous"


def x_require_api_key__mutmut_25(
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
        _fail("invalid api key.")

    if auth.mode == "list":
        for entry in auth.keys:
            if entry.key == provided_key:
                return entry.name
        _fail("Invalid API key.")

    # disabled — allow all
    return "anonymous"


def x_require_api_key__mutmut_26(
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
        _fail("INVALID API KEY.")

    if auth.mode == "list":
        for entry in auth.keys:
            if entry.key == provided_key:
                return entry.name
        _fail("Invalid API key.")

    # disabled — allow all
    return "anonymous"


def x_require_api_key__mutmut_27(
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

    if auth.mode != "list":
        for entry in auth.keys:
            if entry.key == provided_key:
                return entry.name
        _fail("Invalid API key.")

    # disabled — allow all
    return "anonymous"


def x_require_api_key__mutmut_28(
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

    if auth.mode == "XXlistXX":
        for entry in auth.keys:
            if entry.key == provided_key:
                return entry.name
        _fail("Invalid API key.")

    # disabled — allow all
    return "anonymous"


def x_require_api_key__mutmut_29(
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

    if auth.mode == "LIST":
        for entry in auth.keys:
            if entry.key == provided_key:
                return entry.name
        _fail("Invalid API key.")

    # disabled — allow all
    return "anonymous"


def x_require_api_key__mutmut_30(
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
            if entry.key != provided_key:
                return entry.name
        _fail("Invalid API key.")

    # disabled — allow all
    return "anonymous"


def x_require_api_key__mutmut_31(
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
        _fail(None)

    # disabled — allow all
    return "anonymous"


def x_require_api_key__mutmut_32(
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
        _fail("XXInvalid API key.XX")

    # disabled — allow all
    return "anonymous"


def x_require_api_key__mutmut_33(
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
        _fail("invalid api key.")

    # disabled — allow all
    return "anonymous"


def x_require_api_key__mutmut_34(
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
        _fail("INVALID API KEY.")

    # disabled — allow all
    return "anonymous"


def x_require_api_key__mutmut_35(
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
    return "XXanonymousXX"


def x_require_api_key__mutmut_36(
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
    return "ANONYMOUS"

mutants_x_require_api_key__mutmut['_mutmut_orig'] = x_require_api_key__mutmut_orig # type: ignore # mutmut generated
mutants_x_require_api_key__mutmut['x_require_api_key__mutmut_1'] = x_require_api_key__mutmut_1 # type: ignore # mutmut generated
mutants_x_require_api_key__mutmut['x_require_api_key__mutmut_2'] = x_require_api_key__mutmut_2 # type: ignore # mutmut generated
mutants_x_require_api_key__mutmut['x_require_api_key__mutmut_3'] = x_require_api_key__mutmut_3 # type: ignore # mutmut generated
mutants_x_require_api_key__mutmut['x_require_api_key__mutmut_4'] = x_require_api_key__mutmut_4 # type: ignore # mutmut generated
mutants_x_require_api_key__mutmut['x_require_api_key__mutmut_5'] = x_require_api_key__mutmut_5 # type: ignore # mutmut generated
mutants_x_require_api_key__mutmut['x_require_api_key__mutmut_6'] = x_require_api_key__mutmut_6 # type: ignore # mutmut generated
mutants_x_require_api_key__mutmut['x_require_api_key__mutmut_7'] = x_require_api_key__mutmut_7 # type: ignore # mutmut generated
mutants_x_require_api_key__mutmut['x_require_api_key__mutmut_8'] = x_require_api_key__mutmut_8 # type: ignore # mutmut generated
mutants_x_require_api_key__mutmut['x_require_api_key__mutmut_9'] = x_require_api_key__mutmut_9 # type: ignore # mutmut generated
mutants_x_require_api_key__mutmut['x_require_api_key__mutmut_10'] = x_require_api_key__mutmut_10 # type: ignore # mutmut generated
mutants_x_require_api_key__mutmut['x_require_api_key__mutmut_11'] = x_require_api_key__mutmut_11 # type: ignore # mutmut generated
mutants_x_require_api_key__mutmut['x_require_api_key__mutmut_12'] = x_require_api_key__mutmut_12 # type: ignore # mutmut generated
mutants_x_require_api_key__mutmut['x_require_api_key__mutmut_13'] = x_require_api_key__mutmut_13 # type: ignore # mutmut generated
mutants_x_require_api_key__mutmut['x_require_api_key__mutmut_14'] = x_require_api_key__mutmut_14 # type: ignore # mutmut generated
mutants_x_require_api_key__mutmut['x_require_api_key__mutmut_15'] = x_require_api_key__mutmut_15 # type: ignore # mutmut generated
mutants_x_require_api_key__mutmut['x_require_api_key__mutmut_16'] = x_require_api_key__mutmut_16 # type: ignore # mutmut generated
mutants_x_require_api_key__mutmut['x_require_api_key__mutmut_17'] = x_require_api_key__mutmut_17 # type: ignore # mutmut generated
mutants_x_require_api_key__mutmut['x_require_api_key__mutmut_18'] = x_require_api_key__mutmut_18 # type: ignore # mutmut generated
mutants_x_require_api_key__mutmut['x_require_api_key__mutmut_19'] = x_require_api_key__mutmut_19 # type: ignore # mutmut generated
mutants_x_require_api_key__mutmut['x_require_api_key__mutmut_20'] = x_require_api_key__mutmut_20 # type: ignore # mutmut generated
mutants_x_require_api_key__mutmut['x_require_api_key__mutmut_21'] = x_require_api_key__mutmut_21 # type: ignore # mutmut generated
mutants_x_require_api_key__mutmut['x_require_api_key__mutmut_22'] = x_require_api_key__mutmut_22 # type: ignore # mutmut generated
mutants_x_require_api_key__mutmut['x_require_api_key__mutmut_23'] = x_require_api_key__mutmut_23 # type: ignore # mutmut generated
mutants_x_require_api_key__mutmut['x_require_api_key__mutmut_24'] = x_require_api_key__mutmut_24 # type: ignore # mutmut generated
mutants_x_require_api_key__mutmut['x_require_api_key__mutmut_25'] = x_require_api_key__mutmut_25 # type: ignore # mutmut generated
mutants_x_require_api_key__mutmut['x_require_api_key__mutmut_26'] = x_require_api_key__mutmut_26 # type: ignore # mutmut generated
mutants_x_require_api_key__mutmut['x_require_api_key__mutmut_27'] = x_require_api_key__mutmut_27 # type: ignore # mutmut generated
mutants_x_require_api_key__mutmut['x_require_api_key__mutmut_28'] = x_require_api_key__mutmut_28 # type: ignore # mutmut generated
mutants_x_require_api_key__mutmut['x_require_api_key__mutmut_29'] = x_require_api_key__mutmut_29 # type: ignore # mutmut generated
mutants_x_require_api_key__mutmut['x_require_api_key__mutmut_30'] = x_require_api_key__mutmut_30 # type: ignore # mutmut generated
mutants_x_require_api_key__mutmut['x_require_api_key__mutmut_31'] = x_require_api_key__mutmut_31 # type: ignore # mutmut generated
mutants_x_require_api_key__mutmut['x_require_api_key__mutmut_32'] = x_require_api_key__mutmut_32 # type: ignore # mutmut generated
mutants_x_require_api_key__mutmut['x_require_api_key__mutmut_33'] = x_require_api_key__mutmut_33 # type: ignore # mutmut generated
mutants_x_require_api_key__mutmut['x_require_api_key__mutmut_34'] = x_require_api_key__mutmut_34 # type: ignore # mutmut generated
mutants_x_require_api_key__mutmut['x_require_api_key__mutmut_35'] = x_require_api_key__mutmut_35 # type: ignore # mutmut generated
mutants_x_require_api_key__mutmut['x_require_api_key__mutmut_36'] = x_require_api_key__mutmut_36 # type: ignore # mutmut generated
mutants_x__extract_api_key__mutmut: MutantDict = {}  # type: ignore


@_mutmut_mutated(mutants_x__extract_api_key__mutmut)
def _extract_api_key(request: Request) -> str | None:
    """Pull an API key from the Authorization header or X-API-Key header."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:].strip()

    x_api_key = request.headers.get("X-API-Key", "")
    if x_api_key:
        return x_api_key.strip()

    return None


def x__extract_api_key__mutmut_orig(request: Request) -> str | None:
    """Pull an API key from the Authorization header or X-API-Key header."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:].strip()

    x_api_key = request.headers.get("X-API-Key", "")
    if x_api_key:
        return x_api_key.strip()

    return None


def x__extract_api_key__mutmut_1(request: Request) -> str | None:
    """Pull an API key from the Authorization header or X-API-Key header."""
    auth_header = None
    if auth_header.startswith("Bearer "):
        return auth_header[7:].strip()

    x_api_key = request.headers.get("X-API-Key", "")
    if x_api_key:
        return x_api_key.strip()

    return None


def x__extract_api_key__mutmut_2(request: Request) -> str | None:
    """Pull an API key from the Authorization header or X-API-Key header."""
    auth_header = request.headers.get(None, "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:].strip()

    x_api_key = request.headers.get("X-API-Key", "")
    if x_api_key:
        return x_api_key.strip()

    return None


def x__extract_api_key__mutmut_3(request: Request) -> str | None:
    """Pull an API key from the Authorization header or X-API-Key header."""
    auth_header = request.headers.get("Authorization", None)
    if auth_header.startswith("Bearer "):
        return auth_header[7:].strip()

    x_api_key = request.headers.get("X-API-Key", "")
    if x_api_key:
        return x_api_key.strip()

    return None


def x__extract_api_key__mutmut_4(request: Request) -> str | None:
    """Pull an API key from the Authorization header or X-API-Key header."""
    auth_header = request.headers.get("")
    if auth_header.startswith("Bearer "):
        return auth_header[7:].strip()

    x_api_key = request.headers.get("X-API-Key", "")
    if x_api_key:
        return x_api_key.strip()

    return None


def x__extract_api_key__mutmut_5(request: Request) -> str | None:
    """Pull an API key from the Authorization header or X-API-Key header."""
    auth_header = request.headers.get("Authorization", )
    if auth_header.startswith("Bearer "):
        return auth_header[7:].strip()

    x_api_key = request.headers.get("X-API-Key", "")
    if x_api_key:
        return x_api_key.strip()

    return None


def x__extract_api_key__mutmut_6(request: Request) -> str | None:
    """Pull an API key from the Authorization header or X-API-Key header."""
    auth_header = request.headers.get("XXAuthorizationXX", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:].strip()

    x_api_key = request.headers.get("X-API-Key", "")
    if x_api_key:
        return x_api_key.strip()

    return None


def x__extract_api_key__mutmut_7(request: Request) -> str | None:
    """Pull an API key from the Authorization header or X-API-Key header."""
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:].strip()

    x_api_key = request.headers.get("X-API-Key", "")
    if x_api_key:
        return x_api_key.strip()

    return None


def x__extract_api_key__mutmut_8(request: Request) -> str | None:
    """Pull an API key from the Authorization header or X-API-Key header."""
    auth_header = request.headers.get("AUTHORIZATION", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:].strip()

    x_api_key = request.headers.get("X-API-Key", "")
    if x_api_key:
        return x_api_key.strip()

    return None


def x__extract_api_key__mutmut_9(request: Request) -> str | None:
    """Pull an API key from the Authorization header or X-API-Key header."""
    auth_header = request.headers.get("Authorization", "XXXX")
    if auth_header.startswith("Bearer "):
        return auth_header[7:].strip()

    x_api_key = request.headers.get("X-API-Key", "")
    if x_api_key:
        return x_api_key.strip()

    return None


def x__extract_api_key__mutmut_10(request: Request) -> str | None:
    """Pull an API key from the Authorization header or X-API-Key header."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith(None):
        return auth_header[7:].strip()

    x_api_key = request.headers.get("X-API-Key", "")
    if x_api_key:
        return x_api_key.strip()

    return None


def x__extract_api_key__mutmut_11(request: Request) -> str | None:
    """Pull an API key from the Authorization header or X-API-Key header."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("XXBearer XX"):
        return auth_header[7:].strip()

    x_api_key = request.headers.get("X-API-Key", "")
    if x_api_key:
        return x_api_key.strip()

    return None


def x__extract_api_key__mutmut_12(request: Request) -> str | None:
    """Pull an API key from the Authorization header or X-API-Key header."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("bearer "):
        return auth_header[7:].strip()

    x_api_key = request.headers.get("X-API-Key", "")
    if x_api_key:
        return x_api_key.strip()

    return None


def x__extract_api_key__mutmut_13(request: Request) -> str | None:
    """Pull an API key from the Authorization header or X-API-Key header."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("BEARER "):
        return auth_header[7:].strip()

    x_api_key = request.headers.get("X-API-Key", "")
    if x_api_key:
        return x_api_key.strip()

    return None


def x__extract_api_key__mutmut_14(request: Request) -> str | None:
    """Pull an API key from the Authorization header or X-API-Key header."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[8:].strip()

    x_api_key = request.headers.get("X-API-Key", "")
    if x_api_key:
        return x_api_key.strip()

    return None


def x__extract_api_key__mutmut_15(request: Request) -> str | None:
    """Pull an API key from the Authorization header or X-API-Key header."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:].strip()

    x_api_key = None
    if x_api_key:
        return x_api_key.strip()

    return None


def x__extract_api_key__mutmut_16(request: Request) -> str | None:
    """Pull an API key from the Authorization header or X-API-Key header."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:].strip()

    x_api_key = request.headers.get(None, "")
    if x_api_key:
        return x_api_key.strip()

    return None


def x__extract_api_key__mutmut_17(request: Request) -> str | None:
    """Pull an API key from the Authorization header or X-API-Key header."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:].strip()

    x_api_key = request.headers.get("X-API-Key", None)
    if x_api_key:
        return x_api_key.strip()

    return None


def x__extract_api_key__mutmut_18(request: Request) -> str | None:
    """Pull an API key from the Authorization header or X-API-Key header."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:].strip()

    x_api_key = request.headers.get("")
    if x_api_key:
        return x_api_key.strip()

    return None


def x__extract_api_key__mutmut_19(request: Request) -> str | None:
    """Pull an API key from the Authorization header or X-API-Key header."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:].strip()

    x_api_key = request.headers.get("X-API-Key", )
    if x_api_key:
        return x_api_key.strip()

    return None


def x__extract_api_key__mutmut_20(request: Request) -> str | None:
    """Pull an API key from the Authorization header or X-API-Key header."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:].strip()

    x_api_key = request.headers.get("XXX-API-KeyXX", "")
    if x_api_key:
        return x_api_key.strip()

    return None


def x__extract_api_key__mutmut_21(request: Request) -> str | None:
    """Pull an API key from the Authorization header or X-API-Key header."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:].strip()

    x_api_key = request.headers.get("x-api-key", "")
    if x_api_key:
        return x_api_key.strip()

    return None


def x__extract_api_key__mutmut_22(request: Request) -> str | None:
    """Pull an API key from the Authorization header or X-API-Key header."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:].strip()

    x_api_key = request.headers.get("X-API-KEY", "")
    if x_api_key:
        return x_api_key.strip()

    return None


def x__extract_api_key__mutmut_23(request: Request) -> str | None:
    """Pull an API key from the Authorization header or X-API-Key header."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:].strip()

    x_api_key = request.headers.get("X-API-Key", "XXXX")
    if x_api_key:
        return x_api_key.strip()

    return None

mutants_x__extract_api_key__mutmut['_mutmut_orig'] = x__extract_api_key__mutmut_orig # type: ignore # mutmut generated
mutants_x__extract_api_key__mutmut['x__extract_api_key__mutmut_1'] = x__extract_api_key__mutmut_1 # type: ignore # mutmut generated
mutants_x__extract_api_key__mutmut['x__extract_api_key__mutmut_2'] = x__extract_api_key__mutmut_2 # type: ignore # mutmut generated
mutants_x__extract_api_key__mutmut['x__extract_api_key__mutmut_3'] = x__extract_api_key__mutmut_3 # type: ignore # mutmut generated
mutants_x__extract_api_key__mutmut['x__extract_api_key__mutmut_4'] = x__extract_api_key__mutmut_4 # type: ignore # mutmut generated
mutants_x__extract_api_key__mutmut['x__extract_api_key__mutmut_5'] = x__extract_api_key__mutmut_5 # type: ignore # mutmut generated
mutants_x__extract_api_key__mutmut['x__extract_api_key__mutmut_6'] = x__extract_api_key__mutmut_6 # type: ignore # mutmut generated
mutants_x__extract_api_key__mutmut['x__extract_api_key__mutmut_7'] = x__extract_api_key__mutmut_7 # type: ignore # mutmut generated
mutants_x__extract_api_key__mutmut['x__extract_api_key__mutmut_8'] = x__extract_api_key__mutmut_8 # type: ignore # mutmut generated
mutants_x__extract_api_key__mutmut['x__extract_api_key__mutmut_9'] = x__extract_api_key__mutmut_9 # type: ignore # mutmut generated
mutants_x__extract_api_key__mutmut['x__extract_api_key__mutmut_10'] = x__extract_api_key__mutmut_10 # type: ignore # mutmut generated
mutants_x__extract_api_key__mutmut['x__extract_api_key__mutmut_11'] = x__extract_api_key__mutmut_11 # type: ignore # mutmut generated
mutants_x__extract_api_key__mutmut['x__extract_api_key__mutmut_12'] = x__extract_api_key__mutmut_12 # type: ignore # mutmut generated
mutants_x__extract_api_key__mutmut['x__extract_api_key__mutmut_13'] = x__extract_api_key__mutmut_13 # type: ignore # mutmut generated
mutants_x__extract_api_key__mutmut['x__extract_api_key__mutmut_14'] = x__extract_api_key__mutmut_14 # type: ignore # mutmut generated
mutants_x__extract_api_key__mutmut['x__extract_api_key__mutmut_15'] = x__extract_api_key__mutmut_15 # type: ignore # mutmut generated
mutants_x__extract_api_key__mutmut['x__extract_api_key__mutmut_16'] = x__extract_api_key__mutmut_16 # type: ignore # mutmut generated
mutants_x__extract_api_key__mutmut['x__extract_api_key__mutmut_17'] = x__extract_api_key__mutmut_17 # type: ignore # mutmut generated
mutants_x__extract_api_key__mutmut['x__extract_api_key__mutmut_18'] = x__extract_api_key__mutmut_18 # type: ignore # mutmut generated
mutants_x__extract_api_key__mutmut['x__extract_api_key__mutmut_19'] = x__extract_api_key__mutmut_19 # type: ignore # mutmut generated
mutants_x__extract_api_key__mutmut['x__extract_api_key__mutmut_20'] = x__extract_api_key__mutmut_20 # type: ignore # mutmut generated
mutants_x__extract_api_key__mutmut['x__extract_api_key__mutmut_21'] = x__extract_api_key__mutmut_21 # type: ignore # mutmut generated
mutants_x__extract_api_key__mutmut['x__extract_api_key__mutmut_22'] = x__extract_api_key__mutmut_22 # type: ignore # mutmut generated
mutants_x__extract_api_key__mutmut['x__extract_api_key__mutmut_23'] = x__extract_api_key__mutmut_23 # type: ignore # mutmut generated
mutants_x__fail__mutmut: MutantDict = {}  # type: ignore


@_mutmut_mutated(mutants_x__fail__mutmut)
def _fail(detail: str) -> None:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"error": "unauthorized", "message": detail},
    )


def x__fail__mutmut_orig(detail: str) -> None:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"error": "unauthorized", "message": detail},
    )


def x__fail__mutmut_1(detail: str) -> None:
    raise HTTPException(
        status_code=None,
        detail={"error": "unauthorized", "message": detail},
    )


def x__fail__mutmut_2(detail: str) -> None:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=None,
    )


def x__fail__mutmut_3(detail: str) -> None:
    raise HTTPException(
        detail={"error": "unauthorized", "message": detail},
    )


def x__fail__mutmut_4(detail: str) -> None:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        )


def x__fail__mutmut_5(detail: str) -> None:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"XXerrorXX": "unauthorized", "message": detail},
    )


def x__fail__mutmut_6(detail: str) -> None:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"ERROR": "unauthorized", "message": detail},
    )


def x__fail__mutmut_7(detail: str) -> None:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"error": "XXunauthorizedXX", "message": detail},
    )


def x__fail__mutmut_8(detail: str) -> None:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"error": "UNAUTHORIZED", "message": detail},
    )


def x__fail__mutmut_9(detail: str) -> None:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"error": "unauthorized", "XXmessageXX": detail},
    )


def x__fail__mutmut_10(detail: str) -> None:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"error": "unauthorized", "MESSAGE": detail},
    )

mutants_x__fail__mutmut['_mutmut_orig'] = x__fail__mutmut_orig # type: ignore # mutmut generated
mutants_x__fail__mutmut['x__fail__mutmut_1'] = x__fail__mutmut_1 # type: ignore # mutmut generated
mutants_x__fail__mutmut['x__fail__mutmut_2'] = x__fail__mutmut_2 # type: ignore # mutmut generated
mutants_x__fail__mutmut['x__fail__mutmut_3'] = x__fail__mutmut_3 # type: ignore # mutmut generated
mutants_x__fail__mutmut['x__fail__mutmut_4'] = x__fail__mutmut_4 # type: ignore # mutmut generated
mutants_x__fail__mutmut['x__fail__mutmut_5'] = x__fail__mutmut_5 # type: ignore # mutmut generated
mutants_x__fail__mutmut['x__fail__mutmut_6'] = x__fail__mutmut_6 # type: ignore # mutmut generated
mutants_x__fail__mutmut['x__fail__mutmut_7'] = x__fail__mutmut_7 # type: ignore # mutmut generated
mutants_x__fail__mutmut['x__fail__mutmut_8'] = x__fail__mutmut_8 # type: ignore # mutmut generated
mutants_x__fail__mutmut['x__fail__mutmut_9'] = x__fail__mutmut_9 # type: ignore # mutmut generated
mutants_x__fail__mutmut['x__fail__mutmut_10'] = x__fail__mutmut_10 # type: ignore # mutmut generated
