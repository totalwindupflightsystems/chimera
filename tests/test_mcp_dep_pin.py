"""Dependency pin regression tests — the mcp extras must stay below 2.0.

Offline only: parses pyproject.toml with stdlib tomllib, no network calls.

mcp 2.0.0 removed ``mcp.server.fastmcp`` (the v1 API that
``chimera.mcp.server`` imports). An unbounded ``mcp>=1.0.0`` spec lets fresh
``pip install .[mcp]`` / ``.[full]`` resolve to 2.0.0 and breaks both the
``chimera-mcp`` console script and the ``chimera mcp`` CLI subcommand with
ModuleNotFoundError. These tests pin the packaging contract (CH-GAP-005).
"""

from __future__ import annotations

import tomllib
from pathlib import Path

_PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"

_MCP_PIN = "mcp>=1.0.0,<2.0"


def _optional_dependencies() -> dict[str, list[str]]:
    """Read [project.optional-dependencies] straight from pyproject.toml."""
    with open(_PYPROJECT, "rb") as f:
        data = tomllib.load(f)
    return data["project"]["optional-dependencies"]


def _mcp_specs(extra: str) -> list[str]:
    """Return every requirement string in ``extra`` that targets the mcp package."""
    deps = _optional_dependencies()[extra]
    return [spec for spec in deps if spec == "mcp" or spec.startswith("mcp<") or spec.startswith("mcp>")
            or spec.startswith("mcp=") or spec.startswith("mcp!") or spec.startswith("mcp[")]


def test_mcp_extra_pins_below_2() -> None:
    """The ``mcp`` extra must carry the exact ``mcp>=1.0.0,<2.0`` pin."""
    assert _MCP_PIN in _optional_dependencies()["mcp"]


def test_full_extra_pins_below_2() -> None:
    """The ``full`` extra must carry the exact ``mcp>=1.0.0,<2.0`` pin."""
    assert _MCP_PIN in _optional_dependencies()["full"]


def test_no_extra_allows_mcp_2() -> None:
    """Neither extra may permit mcp 2.x — every mcp spec needs a <2.0 upper bound."""
    for extra in ("mcp", "full"):
        specs = _mcp_specs(extra)
        assert specs, f"extra {extra!r} has no mcp requirement at all"
        for spec in specs:
            assert "<2.0" in spec.replace(" ", ""), f"extra {extra!r} allows mcp>=2.0 via {spec!r}"
