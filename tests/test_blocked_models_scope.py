"""Repo-scoped blocked-models state (CHIMERA-V2-REVIEW-03).

``blocked_models.DEFAULT_STATE_PATH`` used to be home-scoped
(``~/.chimera/blocked-models.json``), so a fresh clone inherited every block
ever recorded by any chimera process on the machine — a brand-new checkout
with a mock-only config printed ``provider key rejected`` warnings for
deepseek/openrouter models it had never called (the exact evidence on this
task). The fix resolves the state file from the CURRENT INSTALL: the
``CHIMERA_BLOCKED_MODELS_PATH`` env override, else the repo root found by
walking up to the nearest ``pyproject.toml`` (the same convention
``scripts/model_sync.py`` uses for ``.seen_models.json``), else the legacy
home path with a warning. A fresh clone therefore starts with an EMPTY
registry even when the developer's home file is full of stale blocks, while
blocks still persist across restarts within one checkout, and two checkouts
never see each other's blocks.

The CLI renders the registry's ACTUAL path (previously it hardcoded the home
string), so ``chimera models`` never points an operator at a file the
process does not read.
"""

from __future__ import annotations

import json
import time

import pytest

from chimera import blocked_models
from chimera.blocked_models import ModelBlockRegistry, set_shared_registry


@pytest.fixture(autouse=True)
def _fresh_registry():
    """Isolate the process-wide registry per test (and restore it after)."""
    original = blocked_models.shared_registry
    set_shared_registry(ModelBlockRegistry(state_path=None))
    yield
    set_shared_registry(original)


@pytest.fixture()
def home_state(tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    """A home directory whose legacy state file carries the stale blocks
    from the task evidence — the leak a fresh clone must not inherit."""
    home = tmp_path / "home"
    state = home / ".chimera"
    state.mkdir(parents=True)
    epoch = time.time() + 7 * 24 * 3600.0
    leaked = (
        "deepseek/deepseek-v4-flash",
        "deepseek/deepseek-v4-pro",
        "openrouter/qwen/qwen3-coder",
    )
    (state / "blocked-models.json").write_text(
        json.dumps(
            {
                "blocked_until_epoch": dict.fromkeys(leaked, epoch),
                "reasons": dict.fromkeys(leaked, "credential"),
                "credential_fingerprints": dict.fromkeys(leaked, "no-credential"),
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(home))
    return home


@pytest.fixture()
def fresh_clone(tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    """A scratch checkout shaped like a real clone: pyproject.toml at the
    root, no prior .chimera/ state, process cwd inside it."""
    clone = tmp_path / "clone"
    clone.mkdir()
    (clone / "pyproject.toml").write_text('[project]\nname = "x"\n', encoding="utf-8")
    (clone / "src").mkdir()
    monkeypatch.chdir(clone / "src")  # walk-up must find the clone root
    return clone


# ---------------------------------------------------------------------------
# AC1: a fresh clone with no prior state shows NO blocked models
# ---------------------------------------------------------------------------


def test_fresh_clone_does_not_inherit_home_blocks(home_state, fresh_clone) -> None:
    """The leak from the task evidence: a stale home state file full of
    credential blocks must be invisible to a fresh clone's default registry
    (the exact shape production builds at import: ``ModelBlockRegistry()``)."""
    reg = ModelBlockRegistry()
    assert reg.blocked() == set()
    assert not reg.is_blocked("deepseek/deepseek-v4-flash")
    assert not reg.is_blocked("deepseek/deepseek-v4-pro")
    assert not reg.is_blocked("openrouter/qwen/qwen3-coder")


def test_default_resolution_prefers_the_repo_state_file(fresh_clone) -> None:
    """The default path lands at <repo>/.chimera/blocked-models.json."""
    from chimera.blocked_models import default_state_path

    resolved = default_state_path()
    assert str(resolved).startswith(str(fresh_clone))
    assert resolved == fresh_clone / ".chimera" / "blocked-models.json"


# ---------------------------------------------------------------------------
# AC2: blocks persist within the same repo/install across restarts
# ---------------------------------------------------------------------------


def test_block_persists_within_the_same_repo(fresh_clone) -> None:
    """Record, then 'restart' (new registry, same resolution) — still blocked."""
    reg = ModelBlockRegistry()
    assert reg.record_failure(
        "openrouter/qwen/qwen3-coder", "401 Unauthorized", credential_fingerprint="fp-dead"
    )
    assert (fresh_clone / ".chimera" / "blocked-models.json").is_file()
    reg2 = ModelBlockRegistry()
    assert reg2.is_blocked("openrouter/qwen/qwen3-coder")
    assert reg2.block_reason("openrouter/qwen/qwen3-coder") == "credential"


# ---------------------------------------------------------------------------
# AC3: different repos/checkouts have independent state
# ---------------------------------------------------------------------------


def test_two_checkouts_have_independent_state(tmp_path, monkeypatch) -> None:
    """A block recorded in checkout A must not appear in checkout B."""
    a = tmp_path / "checkout-a"
    b = tmp_path / "checkout-b"
    for repo in (a, b):
        repo.mkdir()
        (repo / "pyproject.toml").write_text('[project]\nname = "x"\n', encoding="utf-8")

    monkeypatch.chdir(a)
    reg_a = ModelBlockRegistry()
    assert reg_a.record_failure("model/only-in-a", "401 Unauthorized")
    assert (a / ".chimera" / "blocked-models.json").is_file()

    monkeypatch.chdir(b)
    reg_b = ModelBlockRegistry()
    assert reg_b.blocked() == set()
    assert not (b / ".chimera").exists()


def test_repo_state_does_not_shadow_a_different_env_override(fresh_clone, monkeypatch, tmp_path) -> None:
    """CHIMERA_BLOCKED_MODELS_PATH wins over repo resolution, so a deploy can
    pin one shared state file explicitly."""
    custom = tmp_path / "pinned" / "state.json"
    monkeypatch.setenv("CHIMERA_BLOCKED_MODELS_PATH", str(custom))
    reg = ModelBlockRegistry()
    assert reg.record_failure("model/x", "401 Unauthorized")
    assert custom.is_file()
    assert not (fresh_clone / ".chimera").exists()


def test_resolution_falls_back_home_with_no_marker(tmp_path, monkeypatch) -> None:
    """Outside any repo marker (and with no env override) the legacy home
    path is kept — pip installs keep working — but the registry WARN."""
    empty = tmp_path / "nowhere"
    empty.mkdir()
    monkeypatch.chdir(empty)
    monkeypatch.delenv("CHIMERA_BLOCKED_MODELS_PATH", raising=False)

    from chimera.blocked_models import default_state_path

    resolved = default_state_path()
    assert str(resolved).startswith("~")  # still expanded against HOME later

    with pytest.warns(UserWarning, match="blocked-models"):
        ModelBlockRegistry()


# ---------------------------------------------------------------------------
# AC4: the repo-local state directory is gitignored
# ---------------------------------------------------------------------------


def test_repo_local_state_dir_is_gitignored() -> None:
    """``.chimera/blocked-models.json`` must never be committable (it is
    per-install runtime state). Asserted like test_repo_hygiene does."""
    import shutil
    import subprocess

    repo = _repo_root()
    if (
        shutil.which("git") is None
        or subprocess.run(["git", "rev-parse", "--git-dir"], cwd=repo, capture_output=True).returncode != 0
    ):
        pytest.skip("not a git checkout")
    artifact = ".chimera/blocked-models.json"
    probe = subprocess.run(["git", "check-ignore", "--quiet", artifact], cwd=repo, capture_output=True)
    assert probe.returncode == 0, f"{artifact} is not gitignored — add the .chimera/ class rule"


def _repo_root():  # type: ignore[no-untyped-def]
    from pathlib import Path

    return Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# AC5 (CLI): `chimera models` renders the ACTUAL state path
# ---------------------------------------------------------------------------


def test_models_command_shows_the_real_state_file(fresh_clone) -> None:
    """The blocked section must not hardcode the legacy home string: an
    operator following the printed path must find the file being read."""
    import yaml
    from click.testing import CliRunner

    from chimera.cli.main import main
    from tests.conftest import CONFIG_DICT

    config_file = fresh_clone / "chimera.yaml"
    config_file.write_text(yaml.safe_dump(CONFIG_DICT), encoding="utf-8")

    reg = ModelBlockRegistry()
    assert reg.record_failure("openrouter/qwen/qwen3-coder", "401 Unauthorized")
    set_shared_registry(reg)

    result = CliRunner().invoke(main, ["-c", str(config_file), "models"])
    assert result.exit_code == 0, result.output
    assert "Blocked models" in result.output
    assert str(fresh_clone / ".chimera" / "blocked-models.json") in result.output
    assert "~/.chimera/blocked-models.json" not in result.output
