"""DF-CHIMERA-0916B-4: the live ``chimera.yaml`` must never be a tracked file.

The repo ships ``chimera.yaml.example`` — and nothing else. Tracking the live
config both leaked internal tuning (SIMON SAYS section-spec prompts, category
weights, fleet settings) onto the public mirror and dead-ended the documented
first run: on a fresh clone ``chimera config init`` exited 2 with
"chimera.yaml already exists. Use --force to overwrite it.", so CH-GAP-050's
first-run fix could never fire for a new user.

Nothing reads the repo-root ``chimera.yaml`` by path from inside the repo:
packaging force-includes only ``chimera.yaml.example`` / ``chimera.yaml.docker``
into the wheel, and CI writes its own config under ``/tmp``. The running systemd
service reads the live file through ``Environment=CHIMERA_CONFIG``, so the file
must stay on disk at that path — these tests pin its *tracking* state only,
never its existence in a working tree. A fresh CI checkout legitimately has no
``chimera.yaml`` at all, which is why nothing here asserts one exists.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

pytest.importorskip("click")
from click.testing import CliRunner  # noqa: E402

from chimera.cli.main import main  # noqa: E402
from chimera.config import (  # noqa: E402
    ChimeraConfig,
    find_example_config_path,
    load_config,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
LIVE_CONFIG = "chimera.yaml"
TEMPLATE = "chimera.yaml.example"


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    """Run git in the repo root; a non-zero exit is data, not an exception."""
    return subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=False
    )


def _require_git_checkout() -> None:
    """Skip cleanly (never fail) where git or a git checkout is unavailable."""
    if shutil.which("git") is None:
        pytest.skip("git is not available")
    if _git("rev-parse", "--git-dir").returncode != 0:
        pytest.skip("not a git checkout — the tracking guard does not apply")


def _removal_is_staged() -> bool:
    """True when the live config's deletion is staged but not yet committed."""
    out = _git("diff", "--cached", "--name-status", "--diff-filter=D", "--", LIVE_CONFIG)
    return any(
        line.split("\t")[-1] == LIVE_CONFIG
        for line in out.stdout.splitlines()
        if line.strip()
    )


def test_chimera_yaml_is_not_tracked() -> None:
    """The live config is absent from the index, and must leave HEAD too."""
    _require_git_checkout()
    tracked = _git("ls-files", "--error-unmatch", LIVE_CONFIG)
    assert tracked.returncode != 0, (
        f"{LIVE_CONFIG} is tracked again — it must stay local-only and gitignored "
        f"(git ls-files printed: {tracked.stdout.strip()!r})"
    )
    in_head = _git("ls-tree", "HEAD", "--", LIVE_CONFIG).stdout.strip()
    # A deletion cannot be staged and reflected in HEAD at the same time: while
    # the untracking change is staged, HEAD still lists the file. That window is
    # legitimate only when the staged change really removes it.
    assert not in_head or _removal_is_staged(), (
        f"{LIVE_CONFIG} is still present in HEAD and its removal is not staged "
        f"(git ls-tree HEAD printed: {in_head!r})"
    )


def test_chimera_yaml_is_gitignored() -> None:
    """``chimera.yaml`` is ignored, so a live copy can never be re-added."""
    _require_git_checkout()
    result = _git("check-ignore", "-q", LIVE_CONFIG)
    assert result.returncode == 0, (
        f"{LIVE_CONFIG} is not gitignored (git check-ignore -q exited "
        f"{result.returncode}) — a local live config could be committed by accident"
    )


def test_config_init_on_fresh_tree(tmp_path, monkeypatch) -> None:
    """The fresh-clone contract in miniature: template only → init succeeds."""
    template = REPO_ROOT / TEMPLATE
    assert template.is_file(), f"missing shipped template: {template}"
    shutil.copyfile(template, tmp_path / TEMPLATE)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("CHIMERA_CONFIG", raising=False)
    monkeypatch.chdir(tmp_path)

    # The tree's OWN template must be what resolves — not a repo-checkout or
    # wheel copy found further up the search path.
    assert find_example_config_path(tmp_path) == (tmp_path / TEMPLATE).resolve()

    result = CliRunner().invoke(main, ["config", "init"])
    assert result.exit_code == 0, result.output
    written = tmp_path / LIVE_CONFIG
    assert written.is_file(), f"{LIVE_CONFIG} was not created in the fresh tree"
    config = load_config(written)
    assert isinstance(config, ChimeraConfig)
    assert "simple" in config.formations


def test_example_template_is_still_shipped() -> None:
    """Untracking the live file must not take the shipped template with it."""
    template = REPO_ROOT / TEMPLATE
    assert template.is_file(), f"missing shipped template: {template}"
    raw = yaml.safe_load(template.read_text(encoding="utf-8"))
    assert isinstance(raw, dict) and raw, "template must be a non-empty YAML mapping"
    config = load_config(template)
    assert isinstance(config, ChimeraConfig)
    assert "simple" in config.formations
