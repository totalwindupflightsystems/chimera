"""Hermetic tests for scripts/push_remotes.py — INT-MIRROR-001.

Context (measured, not assumed). ``chimera-v2`` tracks two remotes: ``origin``
(the private GitLab primary) and ``github`` (the PUBLIC mirror, reached over
HTTPS with a ``gh`` OAuth-app credential whose scopes are ``repo, read:org,
gist``). GitHub enforces the workflow permission at RECEIVE time, so a commit
that edits ``.github/workflows/`` is rejected server-side even when every local
gate passed::

    ! [remote rejected] main -> main (refusing to allow an OAuth App to create
      or update workflow .github/workflows/ci.yml without `workflow` scope)

Left to a human, that rejection silently leaves the public mirror behind — two
ticks hit it and worked around it ad hoc. ``scripts/push_remotes.py`` encodes
the pre-verified recovery (retry ONCE over the derived SSH URL, then verify
ref parity per remote); these tests pin it.

ALL tests are offline and hermetic: no network, no real remotes, no real git.
The fixture writes a scripted ``git`` stub into ``tmp_path`` and puts its
directory FIRST on ``PATH``, so the helper runs against the stub whether it is
imported as a module (monkeypatched ``PATH``) or spawned as a subprocess
(``env=`` with the stub dir first). The stub logs every invocation, so the
assertions are about the exact git commands the helper issued.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO / "scripts" / "push_remotes.py"
AGENTS_PATH = REPO / "AGENTS.md"

LOCAL_SHA = "3f2a9c1d4b5e6f708192a3b4c5d6e7f8091a2b3c"
REMOTE_SHA = "9e8d7c6b5a4938271605f4e3d2c1b0a998877665"
GITHUB_HTTPS = "https://github.com/totalwindupflightsystems/chimera.git"
GITHUB_SSH = "git@github.com:totalwindupflightsystems/chimera.git"
ORIGIN_SSH = "git@gitlab.readydedis.com:totalwindup/chimera.git"

#: The measured GitHub rejection, verbatim (Evidence item 2 of INT-MIRROR-001).
WORKFLOW_REJECTION = (
    " ! [remote rejected] main -> main (refusing to allow an OAuth App to create or update "
    "workflow .github/workflows/ci.yml without `workflow` scope)\n"
    f"error: failed to push some refs to '{GITHUB_HTTPS}'\n"
)

#: An unrelated rejection that must NEVER trigger the SSH retry.
NON_FAST_FORWARD = (
    " ! [rejected]        main -> main (non-fast-forward)\n"
    f"error: failed to push some refs to '{ORIGIN_SSH}'\n"
)

STUB_GIT_SOURCE = '''#!/usr/bin/env python3
"""Scripted `git` stub for tests/test_push_remotes.py (hermetic, no real git).

Appends one JSON line per invocation ({"argv": [...], "cwd": ...}) to the file
named by $PUSH_REMOTES_STUB_LOG, then answers from the table named by
$PUSH_REMOTES_STUB_SCRIPT: a JSON list of {"match": [...], "returncode": int,
"stdout": str, "stderr": str}. A rule matches only when its `match` list equals
the invocation's argv EXACTLY; the first match wins. An unscripted invocation
exits 1 loudly, so a stale table can never make a test pass silently.
"""
import json
import os
import sys


def main():
    argv = sys.argv[1:]
    log_path = os.environ.get("PUSH_REMOTES_STUB_LOG")
    if log_path:
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"argv": argv, "cwd": os.getcwd()}) + "\\n")
    rules = []
    script_path = os.environ.get("PUSH_REMOTES_STUB_SCRIPT")
    if script_path and os.path.exists(script_path):
        with open(script_path, encoding="utf-8") as fh:
            rules = json.load(fh)
    for rule in rules:
        if rule.get("match") == argv:
            sys.stdout.write(rule.get("stdout", ""))
            sys.stderr.write(rule.get("stderr", ""))
            return int(rule.get("returncode", 0))
    sys.stderr.write("stub git: no scripted rule for argv=%r\\n" % (argv,))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
'''


def _load_module(name: str, path: Path) -> ModuleType:
    """Load a script as a module (scripts/ is not a package)."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


push_remotes = _load_module("push_remotes", SCRIPT_PATH)


def _python() -> str:
    """Repo venv interpreter, falling back to the one running the tests."""
    for candidate in (REPO / ".venv" / "bin" / "python", REPO / ".venv" / "Scripts" / "python.exe"):
        if candidate.exists():
            return str(candidate)
    return sys.executable


def _rule(
    match: list[str], *, returncode: int = 0, stdout: str = "", stderr: str = ""
) -> dict[str, Any]:
    return {"match": match, "returncode": returncode, "stdout": stdout, "stderr": stderr}


@dataclass
class StubGit:
    """The only ``git`` the tests may invoke, plus the log of its invocations."""

    bin_dir: Path
    log_path: Path
    script_path: Path

    @property
    def git_path(self) -> Path:
        return self.bin_dir / "git"

    def script(self, rules: list[dict[str, Any]]) -> None:
        self.script_path.write_text(json.dumps(rules, indent=0), encoding="utf-8")

    def entries(self) -> list[dict[str, Any]]:
        """Every logged invocation, in order ([] when the stub never ran)."""
        if not self.log_path.exists():
            return []
        return [
            json.loads(line)
            for line in self.log_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def argv_list(self) -> list[list[str]]:
        return [entry["argv"] for entry in self.entries()]

    def push_calls(self) -> list[list[str]]:
        return [argv for argv in self.argv_list() if argv[:1] == ["push"]]

    def ls_remote_calls(self) -> list[list[str]]:
        return [argv for argv in self.argv_list() if argv[:1] == ["ls-remote"]]

    def env(self, **extra: str) -> dict[str, str]:
        """Process env with the stub dir FIRST on PATH (stub shadows real git)."""
        env = dict(os.environ)
        env["PATH"] = os.pathsep.join([str(self.bin_dir), env.get("PATH", "")])
        env["PUSH_REMOTES_STUB_LOG"] = str(self.log_path)
        env["PUSH_REMOTES_STUB_SCRIPT"] = str(self.script_path)
        env.update(extra)
        return env


@pytest.fixture
def stub_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> StubGit:
    """A scripted ``git`` stub on PATH for both in-process and subprocess runs."""
    bin_dir = tmp_path / "stub-bin"
    bin_dir.mkdir()
    stub = StubGit(
        bin_dir=bin_dir,
        log_path=tmp_path / "git-stub-log.jsonl",
        script_path=tmp_path / "git-stub-script.json",
    )
    stub.git_path.write_text(STUB_GIT_SOURCE, encoding="utf-8")
    stub.git_path.chmod(0o755)
    monkeypatch.setenv("PATH", stub.env()["PATH"])
    monkeypatch.setenv("PUSH_REMOTES_STUB_LOG", str(stub.log_path))
    monkeypatch.setenv("PUSH_REMOTES_STUB_SCRIPT", str(stub.script_path))
    return stub


def _run_helper(stub: StubGit, *args: str) -> subprocess.CompletedProcess[str]:
    """Spawn the helper with the stub dir first on PATH."""
    return subprocess.run(
        [_python(), str(SCRIPT_PATH), *args],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
        env=stub.env(),
    )


def _github_rules(*, push_rc: int = 0, push_stderr: str = "", ls_remote_sha: str = LOCAL_SHA,
                  with_discovery: bool = False) -> list[dict[str, Any]]:
    """Scripted answers for the ``github`` remote (HTTPS URL, SSH fallback)."""
    rules = [
        _rule(["rev-parse", "HEAD"], stdout=f"{LOCAL_SHA}\n"),
        _rule(["push", "github", "main"], returncode=push_rc, stderr=push_stderr),
        _rule(["push", GITHUB_SSH, "main:refs/heads/main"]),
        _rule(["remote", "get-url", "github"], stdout=f"{GITHUB_HTTPS}\n"),
        _rule(["remote", "get-url", "origin"], stdout=f"{ORIGIN_SSH}\n"),
        _rule(["ls-remote", "github", "refs/heads/main"], stdout=f"{ls_remote_sha}\trefs/heads/main\n"),
    ]
    if with_discovery:
        rules.append(_rule(["rev-parse", "--abbrev-ref", "HEAD"], stdout="main\n"))
        rules.append(_rule(["remote"], stdout="github\norigin\n"))
    return rules


def test_stub_git_shadows_the_real_git(stub_git: StubGit) -> None:
    """The stub is the ONLY git on PATH — for us and for a spawned helper."""
    assert shutil.which("git") == str(stub_git.git_path)
    assert shutil.which("git", path=stub_git.env()["PATH"]) == str(stub_git.git_path)
    proc = subprocess.run(
        ["git", "remote"], capture_output=True, text=True, check=False, env=stub_git.env()
    )
    assert proc.returncode == 1  # unscripted invocation fails loudly by design
    assert "no scripted rule" in proc.stderr
    assert stub_git.argv_list() == [["remote"]]


# --- (a) the SSH fallback fires on the workflow-scope rejection ------------- #


def test_ssh_fallback_fires_on_workflow_scope_rejection(stub_git: StubGit) -> None:
    """HTTPS push rejected -> retry over the derived SSH URL -> parity OK, exit 0."""
    stub_git.script(_github_rules(push_rc=1, push_stderr=WORKFLOW_REJECTION))

    proc = _run_helper(stub_git, "--branch", "main", "--remote", "github")

    assert proc.returncode == 0, f"stdout={proc.stdout}\nstderr={proc.stderr}"
    assert "transport=ssh-fallback" in proc.stdout
    assert "parity=OK" in proc.stdout
    assert "PUSHED" in proc.stdout
    # The exact retry command, with the SSH form of the configured HTTPS URL.
    assert [GITHUB_SSH, "main:refs/heads/main"] in [argv[1:] for argv in stub_git.push_calls()]
    assert ["push", GITHUB_SSH, "main:refs/heads/main"] in stub_git.argv_list()
    # Parity is verified over the CONFIGURED remote NAME (read path is unaffected).
    assert ["ls-remote", "github", "refs/heads/main"] in stub_git.argv_list()
    assert proc.stdout.count("transport=") == 1


def test_ssh_fallback_honours_explicit_ssh_url_override(stub_git: StubGit) -> None:
    """--ssh-fallback-url overrides the derivation for every remote."""
    override = "git@github.com:someone-else/mirror.git"
    rules = _github_rules(push_rc=1, push_stderr=WORKFLOW_REJECTION) + [
        _rule(["push", override, "main:refs/heads/main"]),
    ]
    stub_git.script(rules)

    proc = _run_helper(
        stub_git, "--branch", "main", "--remote", "github", "--ssh-fallback-url", override
    )

    assert proc.returncode == 0, f"stdout={proc.stdout}\nstderr={proc.stderr}"
    assert ["push", override, "main:refs/heads/main"] in stub_git.argv_list()
    assert f"ssh_url={override}" in proc.stdout


def test_ssh_fallback_unavailable_fails_actionably(stub_git: StubGit) -> None:
    """A non-GitHub URL cannot be mangled into an SSH URL: fail, name both options."""
    gitlab_https = "https://gitlab.readydedis.com/totalwindup/chimera.git"
    stub_git.script([
        _rule(["rev-parse", "HEAD"], stdout=f"{LOCAL_SHA}\n"),
        _rule(["push", "origin", "main"], returncode=1, stderr=WORKFLOW_REJECTION),
        _rule(["remote", "get-url", "origin"], stdout=f"{gitlab_https}\n"),
        _rule(["ls-remote", "origin", "refs/heads/main"], stdout=f"{LOCAL_SHA}\trefs/heads/main\n"),
    ])

    proc = _run_helper(stub_git, "--branch", "main", "--remote", "origin")

    assert proc.returncode == 1
    assert "ssh-fallback-url" in proc.stdout or "ssh-fallback-url" in proc.stderr
    # No push was attempted against any derived URL.
    assert stub_git.push_calls() == [["push", "origin", "main"]]


# --- (b) parity mismatch fails loudly --------------------------------------- #


def test_parity_mismatch_exits_nonzero_and_names_both_shas(stub_git: StubGit) -> None:
    """A remote that did not receive the commit is a failure, not a warning."""
    stub_git.script(_github_rules(push_rc=1, push_stderr=WORKFLOW_REJECTION,
                                  ls_remote_sha=REMOTE_SHA))

    proc = _run_helper(stub_git, "--branch", "main", "--remote", "github")

    assert proc.returncode == 1
    assert f"remote_sha={REMOTE_SHA}" in proc.stdout
    assert f"local_sha={LOCAL_SHA}" in proc.stdout
    assert "parity=MISMATCH" in proc.stdout
    assert "github" in proc.stderr
    assert REMOTE_SHA in proc.stderr and LOCAL_SHA in proc.stderr


def test_parity_failure_on_unreadable_ref_counts_as_failure(stub_git: StubGit) -> None:
    """A failed/unreadable ls-remote is a parity failure, never a silent skip."""
    rules = _github_rules(push_rc=1, push_stderr=WORKFLOW_REJECTION)
    rules = [r for r in rules if r["match"][:1] != ["ls-remote"]]
    rules.append(_rule(["ls-remote", "github", "refs/heads/main"], returncode=128,
                       stderr="fatal: could not read from remote repository\n"))
    stub_git.script(rules)

    proc = _run_helper(stub_git, "--branch", "main", "--remote", "github")

    assert proc.returncode == 1
    assert "parity=MISMATCH" in proc.stdout
    assert "ls-remote" in (proc.stdout + proc.stderr)


# --- (c) unrelated failures never fall back --------------------------------- #


def test_unrelated_push_failure_never_falls_back(stub_git: StubGit) -> None:
    """A non-fast-forward rejection must be reported verbatim, with no SSH retry."""
    stub_git.script([
        _rule(["rev-parse", "HEAD"], stdout=f"{LOCAL_SHA}\n"),
        _rule(["push", "origin", "main"], returncode=1, stderr=NON_FAST_FORWARD),
        _rule(["ls-remote", "origin", "refs/heads/main"], stdout=f"{LOCAL_SHA}\trefs/heads/main\n"),
    ])

    proc = _run_helper(stub_git, "--branch", "main", "--remote", "origin")

    assert proc.returncode == 1
    assert "non-fast-forward" in proc.stdout  # git's own error text, quoted
    assert "transport=none" in proc.stdout
    # Exactly one push, by remote NAME — no ssh-form argv was ever logged.
    assert stub_git.push_calls() == [["push", "origin", "main"]]
    assert all("@" not in argv[1] for argv in stub_git.push_calls())


def test_unrelated_failure_does_not_match_the_ssh_markers() -> None:
    """The rejection detector fires only on the workflow-scope trap."""
    assert push_remotes.is_workflow_scope_rejection(WORKFLOW_REJECTION) is True
    assert push_remotes.is_workflow_scope_rejection(NON_FAST_FORWARD) is False
    for marker in push_remotes.WORKFLOW_SCOPE_MARKERS:
        assert push_remotes.is_workflow_scope_rejection(marker) is True


# --- (d) dry run performs nothing ------------------------------------------- #


def test_dry_run_performs_no_push_and_no_ls_remote(stub_git: StubGit) -> None:
    """--dry-run prints HEAD + the plan, and issues no push / no ls-remote.

    The brief's parenthetical read "the stub git is never invoked in dry-run";
    that cannot be reconciled with its own requirement to PRINT local HEAD and
    the per-remote plan (both need the repo's real state), so this asserts the
    substantive invariant — the dry run issues only local read-only lookups,
    never ``push``, never ``ls-remote``, and never contacts a remote.
    """
    stub_git.script(_github_rules(with_discovery=True))

    proc = _run_helper(stub_git, "--dry-run")

    assert proc.returncode == 0, f"stdout={proc.stdout}\nstderr={proc.stderr}"
    assert f"local HEAD {LOCAL_SHA}" in proc.stdout
    assert "github: plan transport=remote-url" in proc.stdout
    assert "origin: plan transport=remote-url" in proc.stdout
    # The plan names the exact commands that WOULD run, including the fallback.
    assert "git push github main" in proc.stdout
    assert f"git push {GITHUB_SSH} main:refs/heads/main" in proc.stdout
    assert "git ls-remote github refs/heads/main" in proc.stdout
    # …and none of them ran.
    assert stub_git.push_calls() == []
    assert stub_git.ls_remote_calls() == []
    read_only = [argv[0] for argv in stub_git.argv_list()]
    assert read_only, "dry run must still read local state to print the plan"
    assert set(read_only) <= {"rev-parse", "remote"}, f"unexpected git usage: {read_only}"


# --- (e) URL derivation ----------------------------------------------------- #


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://github.com/totalwindupflightsystems/chimera.git", GITHUB_SSH),
        ("https://github.com/totalwindupflightsystems/chimera", GITHUB_SSH),
        ("http://github.com/owner/repo.git", "git@github.com:owner/repo.git"),
        ("https://www.github.com/owner/repo.git", "git@github.com:owner/repo.git"),
        ("https://github.com/owner/repo/", "git@github.com:owner/repo.git"),
        (GITHUB_SSH, GITHUB_SSH),  # already scp-style SSH: unchanged
        ("ssh://git@github.com/owner/repo.git", "ssh://git@github.com/owner/repo.git"),
        (ORIGIN_SSH, ORIGIN_SSH),
        # A non-GitHub host must NOT be silently mangled into a GitHub URL.
        ("https://gitlab.readydedis.com/totalwindup/chimera.git", None),
        ("https://example.com/owner/repo.git", None),
        ("", None),
    ],
)
def test_derive_ssh_url(url: str, expected: str | None) -> None:
    """https GitHub forms derive, SSH forms pass through, everything else is None."""
    assert push_remotes.derive_ssh_url(url) == expected


# --- module API (the helper is importable, not just a script) --------------- #


def test_push_one_and_verify_parity_in_process(stub_git: StubGit) -> None:
    """The imported module recovers the same way the spawned script does."""
    stub_git.script(_github_rules(push_rc=1, push_stderr=WORKFLOW_REJECTION))

    result = push_remotes.push_one("github", "main")
    assert result.pushed is True
    assert result.transport == "ssh-fallback"
    assert result.ssh_url == GITHUB_SSH
    assert result.rejection is not None
    assert push_remotes.is_workflow_scope_rejection(result.rejection) is True
    assert "refusing to allow an OAuth App" in result.rejection

    result.local_sha = LOCAL_SHA
    push_remotes.verify_parity(result)
    assert result.parity is True
    assert result.ok is True
    assert "transport=ssh-fallback" in push_remotes.format_result_line(result)


def test_script_never_uses_a_shell() -> None:
    """Every git call is an argv list — proven from the source's AST, not a grep.

    A text grep for ``shell=True`` would trip on the module docstring (which
    names the rule), so this parses the file: no ``subprocess`` call may pass a
    truthy ``shell`` keyword, and every ``subprocess.run`` must take a LIST
    whose first element is the ``git`` literal.
    """
    tree = ast.parse(SCRIPT_PATH.read_text(encoding="utf-8"))
    shell_offenders: list[str] = []
    argv_offenders: list[str] = []
    seen_run = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in {"run", "Popen", "call", "check_call", "check_output"}:
            continue
        for keyword in node.keywords:
            if keyword.arg == "shell" and not (
                isinstance(keyword.value, ast.Constant) and keyword.value.value is False
            ):
                shell_offenders.append(ast.unparse(node)[:120])
        if node.func.attr == "run":
            seen_run += 1
            first = node.args[0] if node.args else None
            is_argv_list = (
                isinstance(first, ast.List)
                and bool(first.elts)
                and isinstance(first.elts[0], ast.Constant)
                and first.elts[0].value == "git"
            )
            if not is_argv_list:
                argv_offenders.append(ast.unparse(node)[:120])

    assert seen_run >= 1, "the helper must shell out via subprocess.run"
    assert not shell_offenders, f"shell invocation found: {shell_offenders}"
    assert not argv_offenders, f"subprocess.run without an argv list: {argv_offenders}"


# --- machine-checkable documentation criterion ------------------------------ #


def test_agents_md_documents_the_working_mirror_push() -> None:
    """AGENTS.md carries the trap, the working command, the helper, and the parity check."""
    text = AGENTS_PATH.read_text(encoding="utf-8")
    assert GITHUB_SSH in text, "AGENTS.md must name the SSH mirror URL"
    assert "workflow scope" in text, "AGENTS.md must name the missing workflow scope"
    assert f"git push {GITHUB_SSH} main" in text, "AGENTS.md must carry the working command"
    assert "scripts/push_remotes.py" in text, "AGENTS.md must point at the helper"
    assert "git ls-remote github refs/heads/main" in text, "AGENTS.md must document the parity check"
    assert "--dry-run" in text
