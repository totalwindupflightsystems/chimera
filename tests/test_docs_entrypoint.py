"""Docs + entry-point regression tests for ``python -m chimera`` (DOC-1).

CH-GAP-034/035/036 made ``python -m chimera`` work (``src/chimera/__main__.py``
delegating to ``chimera.cli.main:main``), but it was documented nowhere and
tested nowhere — so the escape hatch for a fresh clone, a non-activated venv,
or a bare wheel without scripts could rot silently.

These tests pin both halves: the docs mention (README + docs/USAGE.md) and the
real module entry point, spawned as a subprocess so the assertion is about the
shipped behaviour rather than an import. All paths resolve from this file's
location, never from the process cwd.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
README = REPO / "README.md"
USAGE = REPO / "docs" / "USAGE.md"
MAIN_MODULE = REPO / "src" / "chimera" / "__main__.py"

#: The escape hatch that must stay documented and working.
ENTRYPOINT = "python -m chimera"

#: Generous subprocess budget — the CLI is measured in seconds, not minutes.
SUBPROCESS_TIMEOUT_S = 45


def _venv_python() -> Path:
    """Repo venv interpreter, falling back to the one running the tests."""
    for candidate in (REPO / ".venv" / "bin" / "python", REPO / ".venv" / "Scripts" / "python.exe"):
        if candidate.exists():
            return candidate
    return Path(sys.executable)


def test_readme_documents_module_entrypoint() -> None:
    """README Quickstart must mention the module entry point."""
    assert ENTRYPOINT in README.read_text(encoding="utf-8")


def test_usage_documents_module_entrypoint() -> None:
    """docs/USAGE.md must document the module entry point."""
    assert ENTRYPOINT in USAGE.read_text(encoding="utf-8")


def test_main_module_delegates_to_cli_main() -> None:
    """``src/chimera/__main__.py`` exists and runs the click CLI's entry point."""
    assert MAIN_MODULE.is_file(), f"missing module entry point: {MAIN_MODULE}"
    source = MAIN_MODULE.read_text(encoding="utf-8")
    assert "chimera.cli.main" in source, "module entry point must import chimera.cli.main"
    assert "main()" in source, "module entry point must call main()"


@pytest.mark.timeout(60)
def test_module_entrypoint_reports_version() -> None:
    """``python -m chimera --version`` exits 0 and prints the package version."""
    import chimera

    proc = subprocess.run(
        [_venv_python(), "-m", "chimera", "--version"],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=SUBPROCESS_TIMEOUT_S,
        check=False,
    )
    assert proc.returncode == 0, f"exit {proc.returncode}\nstdout: {proc.stdout}\nstderr: {proc.stderr}"
    assert chimera.__version__ in proc.stdout, f"version missing from stdout: {proc.stdout!r}"
