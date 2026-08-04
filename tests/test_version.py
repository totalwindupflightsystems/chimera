"""Version consistency tests — pyproject.toml is the single source of truth.

Offline only: parses pyproject.toml with stdlib tomllib, no network calls.
Catches the dogfood-version-drift class of bug where __version__ or the
FastAPI app version was a stale hardcoded string.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

import chimera

_PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def _pyproject_version() -> str:
    """Read the project version straight from pyproject.toml."""
    with open(_PYPROJECT, "rb") as f:
        data = tomllib.load(f)
    return str(data["project"]["version"])


def test_version_matches_pyproject() -> None:
    """chimera.__version__ must equal the version declared in pyproject.toml."""
    assert chimera.__version__ == _pyproject_version()


def test_version_fallback_matches_pyproject() -> None:
    """The source-tree fallback constant must also match pyproject.toml."""
    assert _pyproject_version() == chimera._FALLBACK_VERSION


def test_fastapi_app_version_matches_package() -> None:
    """The REST API must report the package version — no separate hardcode."""
    pytest.importorskip("fastapi")  # api extra may be absent
    from chimera.api.server import create_app

    app = create_app()
    assert app.version == chimera.__version__
