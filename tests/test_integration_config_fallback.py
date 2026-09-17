"""Hermetic tests for the integration suite's config-path resolver (INT-CI-007).

``tests/integration/conftest.py`` resolves the YAML its live servers run against
instead of hard-coding ``<repo>/chimera.yaml``: that file is untracked and
gitignored (DF-CHIMERA-0916B-4), so the CI ``integration`` job died with
``FileNotFoundError`` at fixture setup on every push while every hermetic job
stayed green.

The resolver is imported straight from the integration conftest module (it is not
a test module) and driven against a throwaway project root so all four arms are
covered without a real config.  These tests are hermetic — no network, no
``--run-integration`` flag, no server, no live config — and they run in the
DEFAULT suite; the integration job is the only place the bug ever showed, so a
test that hides behind the flag would not have caught it.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
import yaml

_CONFTEST_PATH = Path(__file__).resolve().parent / "integration" / "conftest.py"

_spec = importlib.util.spec_from_file_location(
    "chimera_integration_conftest_under_test", _CONFTEST_PATH,
)
if _spec is None or _spec.loader is None:  # pragma: no cover - defensive
    raise RuntimeError(f"cannot load the integration conftest from {_CONFTEST_PATH}")
it_conftest = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(it_conftest)

resolve_config_path = it_conftest._resolve_config_path

#: Minimal but realistic config body — parsed by ``yaml.safe_load`` in the tests.
EXAMPLE_TEXT = (
    "server:\n"
    "  host: 127.0.0.1\n"
    "  port: 8810\n"
    "auth:\n"
    "  enabled: false\n"
)


def _fake_root(tmp_path: Path) -> Path:
    """A throwaway stand-in for the project root (no live config by default)."""
    root = tmp_path / "fake-project"
    root.mkdir()
    return root


def _cached_roots() -> list[str]:
    """Snapshot the module-level materialization cache (order-insensitive)."""
    return sorted(it_conftest._MATERIALIZED_CONFIGS)


# ── arm (a): CHIMERA_CONFIG ────────────────────────────────────────────────


def test_env_var_wins_when_the_file_exists(tmp_path: Path) -> None:
    """A valid ``CHIMERA_CONFIG`` is returned verbatim, even if the repo also has one."""
    root = _fake_root(tmp_path)
    (root / "chimera.yaml").write_text(EXAMPLE_TEXT)
    env_file = tmp_path / "explicit" / "custom.yaml"
    env_file.parent.mkdir()
    env_file.write_text("explicit: true\n")

    resolved = resolve_config_path(
        project_root=root, env={"CHIMERA_CONFIG": str(env_file)},
    )

    assert resolved == env_file
    assert resolved.read_text() == "explicit: true\n"
    assert resolved != root / "chimera.yaml"


def test_env_var_pointing_at_a_missing_file_falls_through(tmp_path: Path) -> None:
    """A set-but-missing ``CHIMERA_CONFIG`` is not an error — resolution continues.

    Chosen semantics: the env var is an *optional* override (arm 1 requires the
    file to exist), so a stale pointer cannot take the suite down on a fresh
    checkout — it falls through to the live config / example template / clear
    error.  Bypassing a stale path silently is the point: the fallback arms all
    end somewhere real.
    """
    root = _fake_root(tmp_path)
    live = root / "chimera.yaml"
    live.write_text(EXAMPLE_TEXT)

    resolved = resolve_config_path(
        project_root=root,
        env={"CHIMERA_CONFIG": str(tmp_path / "does-not-exist" / "chimera.yaml")},
    )

    assert resolved == live
    assert resolved.read_text() == EXAMPLE_TEXT


# ── arm (b): the live repo-root config ──────────────────────────────────────


def test_live_config_is_used_unchanged_and_no_temp_copy_is_made(tmp_path: Path) -> None:
    """Local behaviour stays byte-identical: same file, no temp file written."""
    root = _fake_root(tmp_path)
    live = root / "chimera.yaml"
    live.write_text(EXAMPLE_TEXT)
    # The template sits right next to it and must NOT be preferred.
    (root / "chimera.yaml.example").write_text(EXAMPLE_TEXT + "# template\n")

    before = _cached_roots()
    resolved = resolve_config_path(project_root=root, env={})

    assert resolved == live
    assert resolved.read_text() == EXAMPLE_TEXT
    assert _cached_roots() == before, "arm (b) must not materialize anything"
    assert str(root.resolve()) not in it_conftest._MATERIALIZED_CONFIGS


# ── arm (c): the tracked example template ──────────────────────────────────


def test_example_template_is_materialized_outside_the_repo(tmp_path: Path) -> None:
    """A fresh checkout (only the template) still resolves, without polluting the repo."""
    root = _fake_root(tmp_path)
    example = root / "chimera.yaml.example"
    example.write_text(EXAMPLE_TEXT)

    resolved = resolve_config_path(project_root=root, env={})

    assert resolved.exists() and resolved.is_file()
    assert resolved != example
    # Content is the template's, byte for byte, and it really parses as YAML.
    assert resolved.read_text() == example.read_text()
    assert yaml.safe_load(resolved.read_text()) == yaml.safe_load(EXAMPLE_TEXT)
    # ...and it lives outside the (fake) project root.
    assert root.resolve() not in resolved.resolve().parents
    # The fallback must NOT fabricate a live config in the checkout.
    assert not (root / "chimera.yaml").exists()
    assert sorted(p.name for p in root.iterdir()) == ["chimera.yaml.example"]


def test_materialized_copy_is_cached_per_project_root(tmp_path: Path) -> None:
    """Both session fixtures share ONE copy (module-level cache, not per call)."""
    root = _fake_root(tmp_path)
    (root / "chimera.yaml.example").write_text(EXAMPLE_TEXT)

    first = resolve_config_path(project_root=root, env={})
    second = resolve_config_path(project_root=root, env={})

    assert first == second
    assert first.read_text() == EXAMPLE_TEXT


# ── arm (d): nowhere to look ───────────────────────────────────────────────


def test_missing_config_everywhere_raises_with_the_remedy(tmp_path: Path) -> None:
    """No config at all → an actionable error, not a bare FileNotFoundError."""
    root = _fake_root(tmp_path)

    with pytest.raises(RuntimeError) as excinfo:
        resolve_config_path(project_root=root, env={})

    message = str(excinfo.value)
    assert "chimera config init" in message
    assert "CHIMERA_CONFIG" in message
    assert str(root / "chimera.yaml") in message


# ── env plumbing ───────────────────────────────────────────────────────────


def test_env_defaults_to_the_process_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``env=None`` reads ``os.environ``; passing *env* overrides it."""
    root = _fake_root(tmp_path)
    live = root / "chimera.yaml"
    live.write_text(EXAMPLE_TEXT)
    other = tmp_path / "other.yaml"
    other.write_text("other: true\n")

    monkeypatch.delenv("CHIMERA_CONFIG", raising=False)
    assert resolve_config_path(project_root=root) == live

    monkeypatch.setenv("CHIMERA_CONFIG", str(other))
    assert resolve_config_path(project_root=root) == other
    assert resolve_config_path(project_root=root, env={}) == live


def test_this_module_is_not_gated_behind_run_integration() -> None:
    """INT-CI-007: the regression test for a CI-only defect must run by default."""
    module = sys.modules[__name__]
    assert not hasattr(module, "pytestmark"), (
        "these tests are hermetic — do not mark them integration/slow, or the "
        "default suite stops covering the fallback"
    )
