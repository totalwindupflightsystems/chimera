"""INT-GATE-002: the shipped pre-commit hook must delegate to ``gitreins guard``.

Measured at INT-GATE-002 open time: ``.gitreins/pre-commit`` was byte-identical
to ``.git/hooks/pre-commit`` (md5 ``367f204ff6f5087d22b6589cad9c25f3``, 2663
bytes) and ended in an unconditional ``exit 0``. Its lint arm printed
``GitReins Tier 1: Lint — ISSUES FOUND (non-blocking)`` and its tests arm
printed ``GitReins Tier 1: Tests — FAILED`` — neither could stop a commit —
while ``AGENTS.md`` promised "Every commit runs static guards. If guards fail,
the commit is BLOCKED." and ``gitreins guard`` itself DOES block on a lint
failure (exit 1, reproduced live). The two gate surfaces disagreed and only the
advisory one ran at commit time.

These tests pin the fixed contract on **real process output and exit codes** — a
stub engine on the child's PATH and a throwaway git repo per case, never this
checkout's index:

* rc 1 from ``gitreins guard`` (a graded FAIL) BLOCKS the commit;
* rc 0 (PASS) commits;
* rc 2 (DEGRADED — a lane did no work) warns LOUDLY by name and still commits;
* a missing engine warns that the harness did not run and still commits;
* the built-in secrets scan still blocks with no engine at all;
* ``scripts/install_hooks.sh`` installs a byte-identical copy, is idempotent,
  and reports parity drift.

Hermetic by construction: no network, no real ``gitreins``, no remote, no
provider key, no deliberation call. Paths resolve from this file (never the
process cwd), and the child PATH is a temp dir of symlinks to the host's own
tools — which is what makes "no engine on PATH" a real state rather than a wish.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HOOK_SOURCE = REPO / ".gitreins" / "pre-commit"
INSTALLER = REPO / "scripts" / "install_hooks.sh"
AGENTS = REPO / "AGENTS.md"
GUARD_DOC = REPO / "docs" / "GITREINS.md"

#: Everything the hook and the installer shell out to, besides the engine under
#: test. The child PATH is built ONLY from these symlinks + a stub dir, so a
#: real ``gitreins`` (in ``~/.local/bin`` or ``/usr/local/bin``) can never leak
#: into a case that asserts the engine is absent.
HOOK_TOOLS = (
    "bash",
    "env",
    "git",
    "grep",
    "tee",
    "mktemp",
    "rm",
    "cp",
    "mv",
    "chmod",
    "cat",
    "ls",
    "tr",
    "wc",
    "cmp",
    "dirname",
    "stat",
)

#: Representative engine output (the shape ``gitreins guard`` prints), so the
#: assertions read like the real verdict a contributor sees.
PASS_LINES = ("Tier 1 Guards: PASS  (test mode: diff)", "  ✓ secrets — clean", "  ✓ lint")
FAIL_LINES = (
    "Tier 1 Guards: FAIL  (test mode: diff)",
    "  ✓ secrets — clean",
    "  ✗ lint — [*] 2 fixable with the `--fix` option.",
)
FAIL_TAIL = ("Fix the issues above and re-run: gitreins guard",)
#: The measured DEGRADED summary + skip line from docs/GITREINS.md, verbatim.
DEGRADED_LINES = (
    "Tier 1: DEGRADED PASS (skips: lsp)",
    "~ lsp — skipped (no LSP tool on PATH (pylsp not installed))",
)

#: A fake credential the hook's own built-in pattern must catch.
FAKE_SECRET = "OPENROUTER_API_KEY=sk-abcdefghijklmnopqrstuvwxyz0123456789"

TIMEOUT_S = 120

#: Appends ``<cwd>|<argv>`` for every invocation, so a test can prove the hook
#: really EXECUTED the engine with the ``guard`` subcommand.
STUB_PREAMBLE = r"""
if [ -n "${STUB_LOG:-}" ]; then
  printf '%s|%s\n' "$PWD" "$*" >> "$STUB_LOG"
fi
"""


@dataclass(frozen=True)
class Run:
    """A finished child process, with the hook's two output streams kept apart."""

    rc: int
    stdout: str
    stderr: str

    @property
    def output(self) -> str:
        return self.stdout + self.stderr


# ── fixtures ────────────────────────────────────────────────────────────────


def _tool_bin(tmp_path: Path) -> Path:
    """A PATH holding the real tools the hook needs — and no engine."""
    bin_dir = tmp_path / "tools-bin"
    bin_dir.mkdir()
    for tool in HOOK_TOOLS:
        found = shutil.which(tool)
        assert found is not None, f"the host has no `{tool}`; these tests need it"
        (bin_dir / tool).symlink_to(found)
    assert shutil.which("gitreins", path=str(bin_dir)) is None, (
        "the sandbox PATH must not resolve an engine — case 4 is vacuous otherwise"
    )
    return bin_dir


def _stub_engine(
    bin_dir: Path,
    rc: int,
    stdout_lines: tuple[str, ...] = (),
    stderr_lines: tuple[str, ...] = (),
) -> Path:
    """A fake ``gitreins`` that prints representative output and exits ``rc``."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    body = ["#!/usr/bin/env bash", STUB_PREAMBLE.strip()]
    body += [f"printf '%s\\n' {shlex.quote(text)}" for text in stdout_lines]
    body += [f"printf '%s\\n' {shlex.quote(text)} >&2" for text in stderr_lines]
    body.append(f"exit {rc}")
    engine = bin_dir / "gitreins"
    engine.write_text("\n".join(body) + "\n", encoding="utf-8")
    engine.chmod(0o755)
    return bin_dir


def _child_env(home: Path, *path_dirs: Path) -> dict[str, str]:
    """A fully-specified child environment (never inherited PATH)."""
    tmpdir = home / "tmp"
    tmpdir.mkdir(parents=True, exist_ok=True)
    return {
        "PATH": os.pathsep.join(str(entry) for entry in path_dirs),
        "HOME": str(home),
        "TMPDIR": str(tmpdir),
        "STUB_LOG": str(home / "stub-invocations.log"),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_TERMINAL_PROMPT": "0",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
    }


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=TIMEOUT_S,
        check=False,
        env={
            **os.environ,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
        },
    )


def _repo(tmp_path: Path, *, install_hook: bool, name: str = "repo") -> Path:
    """A throwaway git repo carrying a copy of the tracked hook."""
    repo = tmp_path / name
    (repo / ".gitreins").mkdir(parents=True)
    init = _git(repo, "init", "-q", "-b", "main")
    if init.returncode != 0:  # git < 2.28 has no -b
        init = _git(repo, "init", "-q")
    assert init.returncode == 0, f"git init failed: {init.stderr}"

    (repo / ".gitreins" / "pre-commit").write_bytes(HOOK_SOURCE.read_bytes())
    if install_hook:
        dest = repo / ".git" / "hooks" / "pre-commit"
        dest.write_bytes(HOOK_SOURCE.read_bytes())
        dest.chmod(0o755)
    return repo


def _stage(repo: Path, name: str, content: str = "VALUE = 1\n") -> None:
    (repo / name).write_text(content, encoding="utf-8")
    added = _git(repo, "add", "--", name)
    assert added.returncode == 0, f"git add failed: {added.stderr}"


def _run(script: Path, repo: Path, env: dict[str, str], *args: str) -> Run:
    proc = subprocess.run(
        [str(script), *args],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=TIMEOUT_S,
        check=False,
    )
    return Run(rc=proc.returncode, stdout=proc.stdout, stderr=proc.stderr)


def _hook(repo: Path, env: dict[str, str]) -> Run:
    hook = repo / ".git" / "hooks" / "pre-commit"
    assert hook.is_file(), "the test repo has no installed hook to run"
    return _run(hook, repo, env)


def _stub_calls(env: dict[str, str]) -> list[str]:
    log = Path(env["STUB_LOG"])
    if not log.is_file():
        return []
    return [line for line in log.read_text(encoding="utf-8").splitlines() if line]


# ── the commit-time contract ────────────────────────────────────────────────


def test_guard_fail_blocks_the_commit(tmp_path: Path) -> None:
    """A graded lint FAIL (engine rc 1) must abort the commit, not warn."""
    repo = _repo(tmp_path, install_hook=True)
    _stage(repo, "fixture.py")
    env = _child_env(
        tmp_path,
        _stub_engine(tmp_path / "engine", 1, FAIL_LINES, FAIL_TAIL),
        _tool_bin(tmp_path),
    )

    run = _hook(repo, env)

    assert run.rc != 0, f"a FAILing guard must block the commit, got rc=0:\n{run.output}"
    assert "COMMIT BLOCKED" in run.stderr, run.output
    assert "lint" in run.output, f"the guard's verdict was swallowed:\n{run.output}"
    assert _stub_calls(env) and _stub_calls(env)[0].endswith("|guard"), (
        f"the hook did not execute `gitreins guard`: {_stub_calls(env)}"
    )


def test_passing_guard_lets_the_commit_through(tmp_path: Path) -> None:
    """A green harness run (engine rc 0) must not block anything."""
    repo = _repo(tmp_path, install_hook=True)
    _stage(repo, "fixture.py")
    env = _child_env(
        tmp_path,
        _stub_engine(tmp_path / "engine", 0, PASS_LINES),
        _tool_bin(tmp_path),
    )

    run = _hook(repo, env)

    assert run.rc == 0, f"a PASSing guard blocked the commit:\n{run.output}"
    assert "Tier 1 Guards: PASS" in run.output, run.output
    assert "PASS (gitreins guard)" in run.stdout, run.output


def test_degraded_run_warns_by_name_and_still_commits(tmp_path: Path) -> None:
    """rc 2 is a SKIP, not a FAIL: name the lane and let the commit proceed.

    The assertion is on the lane NAME, so a hook that silently swallows the
    degraded state (the pre-fix behaviour) cannot pass this test.
    """
    repo = _repo(tmp_path, install_hook=True)
    _stage(repo, "fixture.py")
    env = _child_env(
        tmp_path,
        _stub_engine(tmp_path / "engine", 2, DEGRADED_LINES),
        _tool_bin(tmp_path),
    )

    run = _hook(repo, env)

    assert run.rc == 0, f"a DEGRADED run must not block the commit:\n{run.output}"
    assert "DEGRADED" in run.stderr, run.output
    assert "no LSP tool on PATH" in run.stderr, (
        f"the warning does not name the skipped lane:\n{run.stderr}"
    )
    assert "lsp" in run.stderr, run.output


def test_missing_engine_warns_and_still_commits(tmp_path: Path) -> None:
    """No engine on PATH: say so loudly — lint/tests/lsp did not grade this one."""
    repo = _repo(tmp_path, install_hook=True)
    _stage(repo, "fixture.py")
    env = _child_env(tmp_path, _tool_bin(tmp_path))  # tools, deliberately no engine

    run = _hook(repo, env)

    assert run.rc == 0, f"a missing engine must not block the commit:\n{run.output}"
    assert "engine not found" in run.stderr.lower(), run.output
    assert "did NOT run" in run.stderr, (
        f"the warning does not say the harness was skipped:\n{run.stderr}"
    )
    assert _stub_calls(env) == [], "no engine was on PATH, so nothing should have run"


def test_unwritable_tmpdir_does_not_disable_the_gate(tmp_path: Path) -> None:
    """A broken TMPDIR must not turn a graded FAIL into a silent pass."""
    repo = _repo(tmp_path, install_hook=True)
    _stage(repo, "fixture.py")
    env = _child_env(
        tmp_path,
        _stub_engine(tmp_path / "engine", 1, FAIL_LINES, FAIL_TAIL),
        _tool_bin(tmp_path),
    )
    env["TMPDIR"] = str(tmp_path / "no-such-tmpdir")  # mktemp cannot write here

    run = _hook(repo, env)

    assert run.rc != 0, f"the gate was disabled by a broken TMPDIR:\n{run.output}"
    assert "COMMIT BLOCKED" in run.stderr, run.output


def test_secrets_still_block_without_the_engine(tmp_path: Path) -> None:
    """The built-in secrets scan stays load-bearing where no engine exists."""
    repo = _repo(tmp_path, install_hook=True)
    _stage(repo, "leaky.py", f"{FAKE_SECRET}\n")
    env = _child_env(tmp_path, _tool_bin(tmp_path))

    run = _hook(repo, env)

    assert run.rc != 0, f"a staged secret must block even without an engine:\n{run.output}"
    assert "COMMIT BLOCKED: secrets found" in run.stderr, run.output


# ── the installer ───────────────────────────────────────────────────────────


def test_installer_installs_a_byte_identical_hook(tmp_path: Path) -> None:
    """`--check` proves parity; the installer closes the gap and is idempotent."""
    repo = _repo(tmp_path, install_hook=False)
    env = _child_env(tmp_path, _tool_bin(tmp_path))
    dest = repo / ".git" / "hooks" / "pre-commit"

    missing = _run(INSTALLER, repo, env, "--check")
    assert missing.rc != 0, "`--check` must fail when the hook is not installed"
    assert "not installed" in missing.stderr, missing.output

    installed = _run(INSTALLER, repo, env)
    assert installed.rc == 0, installed.output
    assert dest.is_file(), f"the installer did not create {dest}"
    assert dest.read_bytes() == HOOK_SOURCE.read_bytes(), (
        "the installed hook is not byte-identical to .gitreins/pre-commit"
    )
    assert os.access(dest, os.X_OK), "the installed hook is not executable"

    ok = _run(INSTALLER, repo, env, "--check")
    assert ok.rc == 0, ok.output
    assert "byte-identical" in ok.stdout, ok.output

    again = _run(INSTALLER, repo, env)
    assert again.rc == 0, again.output
    assert "Already installed" in again.stdout, (
        f"re-running the installer is not a no-op:\n{again.stdout}"
    )
    assert dest.read_bytes() == HOOK_SOURCE.read_bytes()

    # The installer must never hijack git's hook lookup: core.hooksPath would
    # shadow the fleet `prepare-commit-msg` trailer hook.
    hooks_path = _git(repo, "config", "--get", "core.hooksPath")
    assert hooks_path.returncode != 0, (
        f"the installer set core.hooksPath={hooks_path.stdout.strip()!r} — that "
        f"shadows the co-author trailer hook in .git/hooks/"
    )


def test_installer_check_detects_drift_and_dry_run_writes_nothing(tmp_path: Path) -> None:
    """A drifted installed hook is reported (non-zero) and repaired, not ignored."""
    repo = _repo(tmp_path, install_hook=False)
    env = _child_env(tmp_path, _tool_bin(tmp_path))
    dest = repo / ".git" / "hooks" / "pre-commit"

    assert _run(INSTALLER, repo, env).rc == 0
    good = dest.read_bytes()

    dry = _run(INSTALLER, repo, env, "--dry-run")
    assert dry.rc == 0, dry.output
    assert "DRY RUN" in dry.stdout, dry.output
    assert dest.read_bytes() == good, "--dry-run modified the installed hook"

    dest.write_bytes(good + b"\n# drift\n")
    drifted = dest.read_bytes()
    check = _run(INSTALLER, repo, env, "--check")
    assert check.rc != 0, "`--check` must fail on a drifted hook"
    assert "differs" in check.stderr, check.output

    repaired = _run(INSTALLER, repo, env)
    assert repaired.rc == 0, repaired.output
    assert "Installed" in repaired.stdout or "restored" in repaired.stdout, repaired.output
    assert dest.read_bytes() == HOOK_SOURCE.read_bytes(), (
        "the installer did not restore the drifted hook"
    )
    assert drifted != HOOK_SOURCE.read_bytes()
    assert _run(INSTALLER, repo, env, "--check").rc == 0


# ── premise guards (documentation and the tracked script) ───────────────────


def test_tracked_hook_delegates_to_the_guard() -> None:
    """Premise: the TRACKED hook is the delegating one, not the advisory one.

    Without this, reverting ``.gitreins/pre-commit`` to the pre-fix advisory
    script would leave the rest of the suite describing a gate that is gone.
    """
    text = HOOK_SOURCE.read_text(encoding="utf-8")

    assert "gitreins guard" in text, (
        ".gitreins/pre-commit never invokes `gitreins guard` — the commit-time "
        "gate cannot block on a graded FAIL without it"
    )
    assert "COMMIT BLOCKED: gitreins guard reported FAIL" in text, (
        "the hook does not block on a graded FAIL"
    )
    for advisory in ("ISSUES FOUND (non-blocking)", "Tests — FAILED"):
        assert advisory not in text, (
            f"the advisory arm {advisory!r} is back in .gitreins/pre-commit — "
            f"lint/tests can no longer block a commit"
        )


def test_docs_state_the_commit_time_policy() -> None:
    """AGENTS.md and docs/GITREINS.md must describe what now blocks a commit."""
    agents = AGENTS.read_text(encoding="utf-8")
    doc = GUARD_DOC.read_text(encoding="utf-8")

    assert "scripts/install_hooks.sh" in agents, (
        "AGENTS.md does not tell a contributor how the pre-commit hook is installed"
    )
    assert "scripts/install_hooks.sh" in doc, (
        "docs/GITREINS.md does not document the installer"
    )
    assert "## The pre-commit hook" in doc, (
        "docs/GITREINS.md has no `## The pre-commit hook` section"
    )
    assert "--no-verify" in doc, (
        "docs/GITREINS.md does not name the only bypass (`git commit --no-verify`)"
    )
    assert "core.hooksPath" in doc, (
        "docs/GITREINS.md does not explain why the hook is copied rather than "
        "installed through core.hooksPath"
    )
