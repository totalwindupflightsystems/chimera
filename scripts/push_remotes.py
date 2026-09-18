#!/usr/bin/env python3
"""Dual-remote push helper: retry over SSH when GitHub rejects a workflow edit.

``chimera-v2`` tracks two remotes: ``origin`` (private GitLab primary) and
``github`` (the PUBLIC mirror). The mirror's push path is an HTTPS URL
authenticated by a ``gh`` OAuth app with scopes ``repo, read:org, gist``, and
GitHub enforces the workflow permission at RECEIVE time, so a commit touching
``.github/workflows/`` is rejected server-side even when every local gate
passed::

    ! [remote rejected] main -> main (refusing to allow an OAuth App to create
      or update workflow .github/workflows/ci.yml without `workflow` scope)

That credential cannot be widened in place, so the HTTPS push can never succeed
for such a commit and the mirror drifts behind silently. The same account
authenticates over SSH, so re-pushing the same commit over the SSH URL works
(``git push git@github.com:totalwindupflightsystems/chimera.git main``).

This script encodes that recovery: push each remote, retry ONCE over the
derived SSH URL only on that exact rejection, then verify that every remote's
``refs/heads/<branch>`` really points at the pushed commit (the read path is
unaffected by the missing scope). Exit code 0 requires every remote pushed AND
in parity. ``--dry-run`` pushes nothing and runs no ``ls-remote`` — it uses only
local read-only lookups (``rev-parse`` / ``remote``) to print HEAD and the plan.

Stdlib only; argv lists only (never ``shell=True``).
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

#: Where a git command runs (``None`` = the process's own cwd).
Cwd = str | Path | None

#: Any of these in git's failure text is the missing-workflow-scope trap — the
#: only failure for which an SSH retry is warranted.
WORKFLOW_SCOPE_MARKERS: tuple[str, ...] = (
    "workflow scope",
    "refusing to allow an OAuth App",
    "without `workflow`",
)

#: scp-style (``git@host:owner/repo``) and ``ssh://`` URLs are already SSH.
_SSH_SHAPED_RE = re.compile(r"^(?:[^/@\s]+@[^/:\s]+:|ssh://)")
#: ``https://github.com/<owner>/<repo>``, with or without a trailing ``.git``.
_GITHUB_HTTPS_RE = re.compile(
    r"^https?://(?:www\.)?github\.com/(?P<owner>[^/\s]+)/(?P<repo>[^/\s]+?)(?:\.git)?/?$"
)


def _run_git(args: Sequence[str], cwd: Cwd = None) -> subprocess.CompletedProcess[str]:
    """Run ``git <args>`` with captured text output. Never uses a shell."""
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)


def _git_text(args: Sequence[str], cwd: Cwd = None) -> str | None:
    """Stripped stdout of a read-only git command, or ``None`` when it fails."""
    proc = _run_git(args, cwd)
    return proc.stdout.strip() if proc.returncode == 0 else None


def list_remotes(cwd: Cwd = None) -> list[str]:
    """Every configured remote name (``git remote``)."""
    return [ln.strip() for ln in (_git_text(["remote"], cwd) or "").splitlines() if ln.strip()]


def remote_url(name: str, cwd: Cwd = None) -> str | None:
    """The configured URL of ``name``, or ``None`` when it cannot be read."""
    return _git_text(["remote", "get-url", name], cwd)


def local_head(cwd: Cwd = None) -> str | None:
    """The full sha of local ``HEAD``."""
    return _git_text(["rev-parse", "HEAD"], cwd)


def current_branch(cwd: Cwd = None) -> str | None:
    """The current branch name (``git rev-parse --abbrev-ref HEAD``)."""
    return _git_text(["rev-parse", "--abbrev-ref", "HEAD"], cwd)


def derive_ssh_url(url: str) -> str | None:
    """SSH form of a remote URL, or ``None`` when it cannot be derived safely.

    ``https://github.com/<owner>/<repo>[.git]`` becomes
    ``git@github.com:<owner>/<repo>.git``; an already SSH-shaped URL
    (``git@host:owner/repo`` or ``ssh://...``) is returned unchanged. Anything
    else — notably a non-GitHub HTTPS URL — is ``None``: inventing a GitHub SSH
    URL for an unknown host would push to the wrong place, so the caller must
    fail loudly and ask for ``--ssh-fallback-url`` instead.
    """
    candidate = (url or "").strip()
    if not candidate:
        return None
    if _SSH_SHAPED_RE.match(candidate):
        return candidate
    match = _GITHUB_HTTPS_RE.match(candidate)
    if match is None:
        return None
    return f"git@github.com:{match.group('owner')}/{match.group('repo')}.git"


def is_workflow_scope_rejection(text: str) -> bool:
    """True when git's output carries GitHub's workflow-scope rejection."""
    lowered = (text or "").lower()
    return any(marker.lower() in lowered for marker in WORKFLOW_SCOPE_MARKERS)


def _first_marker_line(text: str) -> str | None:
    """The first output line that triggered the fallback (recorded for the log)."""
    return next(
        (ln.strip() for ln in (text or "").splitlines() if is_workflow_scope_rejection(ln)), None
    )


def _combined_output(proc: subprocess.CompletedProcess[str]) -> str:
    """stdout+stderr of a failed git call, trimmed for reporting."""
    return f"{proc.stdout}\n{proc.stderr}".strip()


@dataclass
class RemoteResult:
    """What happened to one remote: push outcome, transport, and parity."""

    name: str
    branch: str
    pushed: bool = False
    transport: str = "none"  # remote-url | ssh-fallback | none
    ssh_url: str | None = None
    rejection: str | None = None
    error: str | None = None
    remote_sha: str | None = None
    local_sha: str | None = None
    parity: bool | None = None  # None = not checked (dry run)
    commands: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.pushed and self.parity is True

    def reason(self, message: str) -> None:
        """Append an actionable reason, keeping git's own text intact."""
        self.error = "\n".join(part for part in (self.error, message) if part)


def push_one(
    name: str, branch: str, *, ssh_fallback_url: str | None = None, cwd: Cwd = None
) -> RemoteResult:
    """Push ``branch`` to one remote, recovering from the workflow-scope trap.

    Exactly one retry is allowed, and only when git's failure text carries a
    workflow-scope rejection; every other failure is reported verbatim.
    """
    result = RemoteResult(name=name, branch=branch)
    refspec = f"{branch}:refs/heads/{branch}"
    result.commands.append(f"git push {name} {branch}")

    proc = _run_git(["push", name, branch], cwd)
    if proc.returncode == 0:
        result.pushed = True
        result.transport = "remote-url"
        return result

    failure = _combined_output(proc)
    if not is_workflow_scope_rejection(failure):
        result.reason(failure or "git push failed with no output")  # never fall back
        return result

    result.rejection = _first_marker_line(failure)
    configured_url = remote_url(name, cwd)
    ssh_url = ssh_fallback_url or derive_ssh_url(configured_url or "")
    if not ssh_url:
        result.reason(
            f"remote '{name}' was rejected for the missing workflow scope and no SSH fallback "
            f"URL could be derived from its configured URL ({configured_url or 'unreadable'}). "
            "Pass --ssh-fallback-url git@github.com:<owner>/<repo>.git (the same account "
            "authenticates over SSH) or fix the remote's URL."
        )
        return result

    result.ssh_url = ssh_url
    result.commands.append(f"git push {ssh_url} {refspec}")
    retry = _run_git(["push", ssh_url, refspec], cwd)
    result.transport = "ssh-fallback"
    if retry.returncode != 0:
        result.reason(
            f"SSH fallback push also failed (git push {ssh_url} {refspec}):\n"
            f"{_combined_output(retry)}"
        )
        return result
    result.pushed = True
    return result


def verify_parity(result: RemoteResult, cwd: Cwd = None) -> None:
    """Check ``git ls-remote <remote> refs/heads/<branch>`` against local HEAD.

    Read over the CONFIGURED remote name — the read path is unaffected by the
    missing workflow scope. An unreadable ref counts as a failure, exactly like
    a sha mismatch.
    """
    result.commands.append(f"git ls-remote {result.name} refs/heads/{result.branch}")
    out = _git_text(["ls-remote", result.name, f"refs/heads/{result.branch}"], cwd)
    if not out:
        result.parity = False
        result.reason(
            f"parity check failed on remote '{result.name}': git ls-remote {result.name} "
            f"refs/heads/{result.branch} returned no ref (remote unreachable, branch missing, "
            "or read credentials broken)."
        )
        return
    result.remote_sha = out.split()[0]
    result.parity = result.remote_sha == result.local_sha
    if not result.parity:
        result.reason(
            f"parity mismatch on remote '{result.name}': remote refs/heads/{result.branch}="
            f"{result.remote_sha} but local HEAD={result.local_sha}"
        )


def format_result_line(result: RemoteResult) -> str:
    """One human-readable line per remote: name, transport, status, shas, parity."""
    parts = [
        f"{result.name}:",
        "PUSHED" if result.pushed else "FAILED",
        f"transport={result.transport}",
    ]
    if result.ssh_url:
        parts.append(f"ssh_url={result.ssh_url}")
    parts.append(f"remote_sha={result.remote_sha or 'unknown'}")
    parts.append(f"local_sha={result.local_sha or 'unknown'}")
    if result.parity is None:
        parts.append("parity=SKIPPED")
    else:
        parts.append("parity=OK" if result.parity else "parity=MISMATCH")
    return " ".join(parts)


def format_details(result: RemoteResult) -> list[str]:
    """Indented, actionable detail lines for a remote that did not come out clean."""
    lines = [f"  rejection: {result.rejection}"] if result.rejection else []
    if result.ssh_url:
        lines.append(f"  fallback: {result.ssh_url}")
    lines.extend(f"  reason: {line}" for line in (result.error or "").splitlines())
    return lines


def print_plan(head: str | None, branch: str, remotes: Sequence[str],
               ssh_fallback_url: str | None, cwd: Cwd) -> None:
    """Dry-run output: local HEAD plus the exact commands that would run, per remote."""
    print(f"local HEAD {head or 'unknown'} (branch {branch})")
    for name in remotes:
        url = remote_url(name, cwd)
        ssh_url = ssh_fallback_url or derive_ssh_url(url or "")
        print(f"{name}: plan transport=remote-url cmd: git push {name} {branch}")
        print(f"  configured url: {url or 'unreadable'}")
        if ssh_url:
            print(
                f"  on workflow-scope rejection: transport=ssh-fallback cmd: "
                f"git push {ssh_url} {branch}:refs/heads/{branch}"
            )
        else:
            print(
                "  on workflow-scope rejection: no SSH URL derivable — a real run would fail "
                "and ask for --ssh-fallback-url"
            )
        print(f"  parity check: git ls-remote {name} refs/heads/{branch}")


def push_remotes(
    remotes: Sequence[str],
    branch: str,
    *,
    ssh_fallback_url: str | None = None,
    dry_run: bool = False,
    cwd: Cwd = None,
) -> int:
    """Push ``branch`` to every remote in ``remotes``, verify parity, return an exit code."""
    head = local_head(cwd)
    if dry_run:
        print_plan(head, branch, remotes, ssh_fallback_url, cwd)
        return 0
    if not head:
        print("FATAL: could not read local HEAD (not a git repository?)", file=sys.stderr)
        return 1

    results: list[RemoteResult] = []
    for name in remotes:
        result = push_one(name, branch, ssh_fallback_url=ssh_fallback_url, cwd=cwd)
        result.local_sha = head
        verify_parity(result, cwd)
        results.append(result)

    for result in results:
        print(format_result_line(result))
        for line in format_details(result):
            print(line)

    failures = [r for r in results if not r.ok]
    if failures:
        print(
            "FAILED: "
            + ", ".join(
                f"{r.name} ({'push failed' if not r.pushed else 'parity mismatch'} "
                f"remote_sha={r.remote_sha or 'unknown'} local_sha={r.local_sha or 'unknown'})"
                for r in failures
            ),
            file=sys.stderr,
        )
        return 1
    print(f"OK: {len(results)}/{len(remotes)} remotes pushed and in parity with {head[:12]}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="push_remotes.py",
        description=(
            "Push the current branch to every remote, retrying over the derived SSH URL "
            "exactly when GitHub rejects the push for a missing workflow scope, then verify "
            "refs/heads/<branch> parity on every remote."
        ),
    )
    parser.add_argument("--branch", default=None, help="branch to push (default: current branch)")
    parser.add_argument(
        "--remote",
        action="append",
        default=None,
        metavar="REMOTE",
        help="restrict to this remote (repeatable; default: every remote from git remote)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print local HEAD and the commands that would run; pushes nothing, runs no ls-remote",
    )
    parser.add_argument(
        "--ssh-fallback-url",
        default=None,
        metavar="URL",
        help="SSH URL to retry with, overriding the derivation from the remote's URL",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    branch = args.branch or current_branch()
    if not branch:
        print("FATAL: could not resolve the branch to push (pass --branch)", file=sys.stderr)
        return 1
    remotes = list(args.remote) if args.remote else list_remotes()
    if not remotes:
        print("FATAL: no remotes to push (git remote is empty; pass --remote)", file=sys.stderr)
        return 1
    return push_remotes(
        remotes, branch, ssh_fallback_url=args.ssh_fallback_url, dry_run=args.dry_run
    )


if __name__ == "__main__":
    raise SystemExit(main())
