"""Tests for the ``python -m chimera`` entry point (src/chimera/__main__.py).

The module is a thin delegate to the click CLI: run it as a real subprocess
so the ``__main__`` module itself is the code under test (import-time behavior
plus the ``if __name__ == "__main__"`` guard), not a mock of it.
"""

import subprocess
import sys

import pytest

import chimera


@pytest.mark.parametrize(
    "cmd",
    [
        [sys.executable, "-m", "chimera", "--version"],
        [sys.executable, "-m", "chimera", "--help"],
    ],
)
def test_python_m_chimera_exits_zero(cmd):
    """``python -m chimera --version`` / ``--help`` behave like the console script."""
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=False)
    assert proc.returncode == 0, proc.stderr


def test_python_m_chimera_version_matches_package():
    """The printed version equals chimera.__version__ (same CLI delegate)."""
    proc = subprocess.run(
        [sys.executable, "-m", "chimera", "--version"],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert chimera.__version__ in proc.stdout + proc.stderr


def test_main_module_imports_cli_main():
    """Importing the entry module exposes the same ``main`` the CLI uses."""
    from chimera.__main__ import main as entry_main
    from chimera.cli.main import main as cli_main

    assert entry_main is cli_main
