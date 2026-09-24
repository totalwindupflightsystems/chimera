"""Health identity tests (DF-CHIMERA-V2-48).

* every health surface carries an additive ``version`` field — the package
  version — so a wheel/container install (no git metadata) still reports an
  identity alongside ``commit``,
* ``commit`` prefers the short git commit and falls back to ``v<version>``
  when the process has no git metadata: the ``'unknown'`` sentinel of
  ``_running_commit`` must never leak onto a health surface (the fallback is
  version-shaped, never commit-shaped, so scripts/smoke_live.py keeps
  classifying it UNVERIFIABLE),
* a resolvable commit is reported unchanged.
"""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

import chimera  # noqa: E402
from chimera.api import server as api_server  # noqa: E402
from chimera.engine import Engine  # noqa: E402
from tests.conftest import FakeGateway  # noqa: E402

#: Liveness surfaces (same shape) plus the detailed health endpoint.
HEALTH_PATHS = ("/v1/health/live", "/health", "/v1/health")


def _client(config):  # type: ignore[no-untyped-def]
    app = api_server.create_app(config=config, engine=Engine(config, FakeGateway()))
    return TestClient(app)


def _identity(data: dict, path: str) -> dict:
    """:path's identity dict — the response body, except /v1/health whose
    identity fields (commit, version) live inside ``details``."""
    return data["details"] if path == "/v1/health" else data


def test_every_health_surface_reports_package_version(config) -> None:  # type: ignore[no-untyped-def]
    """Additive identity: ``version`` == chimera.__version__ on all surfaces."""
    client = _client(config)
    for path in HEALTH_PATHS:
        r = client.get(path)
        assert r.status_code == 200
        assert _identity(r.json(), path)["version"] == chimera.__version__


def test_commit_falls_back_to_version_when_git_metadata_missing(
    config,  # type: ignore[no-untyped-def]
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No git metadata (wheel/container install): commit = v<version>.

    ``_running_commit`` keeps returning its ``'unknown'`` sentinel; the
    health surfaces must translate it into the version fallback instead of
    publishing a bare ``unknown``.
    """
    monkeypatch.setattr(api_server, "_running_commit", lambda: "unknown")
    client = _client(config)
    expected = f"v{chimera.__version__}"
    for path in HEALTH_PATHS:
        data = _identity(client.get(path).json(), path)
        assert data["commit"] == expected
        assert data["commit"] != "unknown"


def test_resolvable_commit_is_reported_unchanged(
    config,  # type: ignore[no-untyped-def]
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Normal path: a real short sha passes through without fallback."""
    monkeypatch.setattr(api_server, "_running_commit", lambda: "abc1234")
    client = _client(config)
    for path in HEALTH_PATHS:
        assert _identity(client.get(path).json(), path)["commit"] == "abc1234"
