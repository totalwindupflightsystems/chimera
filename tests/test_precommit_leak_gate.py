"""DF-CHIMERA-V2-24: the commit gate must catch private-host leaks BEFORE commit.

The INT-CI-005 suite guard (``tests/test_no_private_host_leaks.py``) only ran
inside pytest, so a dogfood doc carrying a bunker tailnet address passed its
own commit and surfaced on the NEXT full-suite run — after the public mirror
already had it. The fix moves the same pattern set (one shared module,
``tests.private_host_scan`` — never a second hand-rolled copy) into a new
pre-commit arm in ``.gitreins/pre-commit``: every staged text file is scanned,
and any private/CGNAT/tailnet hit BLOCKS the commit with the fix ("publish the
host NAME, never its address").

Pinned here, hermetically:

* the pure function flags every range class the old guard covered
  (10/8, 192.168/16, 172.16-31, 100.64-127/10 CGNAT) plus tailnet hostnames,
  and passes hostnames like ``bunker3`` / ``bunker-las-03``;
* the same exclusions as the suite guard survive in the shared module
  (allowlisted addresses, CIDR-notation prose, binary files);
* on a REAL hook run in a throwaway git repo, a staged document carrying a
  private-range address is BLOCKED, and the same document carrying the host
  name instead commits cleanly — the write path itself, not a mock of it.

No network, no real ``gitreins`` engine, no provider key. Forbidden addresses
in this file are assembled from parts — the whole-tree suite guard would flag
a literal one.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.private_host_scan import (
    ALLOWED_ADDRESSES,
    find_private_hosts,
    iter_line_hits,
    scan_file,
)

REPO = Path(__file__).resolve().parents[1]
HOOK_SOURCE = REPO / ".gitreins" / "pre-commit"
SCANNER_SOURCE = REPO / "tests" / "private_host_scan.py"

TIMEOUT_S = 120

#: Every range class the original hand-rolled guard covered, assembled from
#: parts so this tracked test file never contains a literal forbidden address.
_OCTETS = ["7", "33", "201", "16"]
_RANGE_CLASSES = {
    "10/8": ".".join(["10", _OCTETS[0], _OCTETS[1], _OCTETS[2]]),
    "192.168/16": ".".join(["192", "168", _OCTETS[2], _OCTETS[3]]),
    "172.16-31": ".".join(["172", "28", _OCTETS[1], _OCTETS[3]]),
    "100.64-127/10 (CGNAT/tailnet)": ".".join(["100", "115", _OCTETS[1], _OCTETS[3]]),
}


def _addr(cls: str) -> str:
    return _RANGE_CLASSES[cls]


def test_every_range_class_is_flagged() -> None:
    """Each covered range class yields exactly its own address as a hit."""
    for label, addr in _RANGE_CLASSES.items():
        hits = find_private_hosts(f"contact {addr} for details\n")
        assert hits == [addr], f"the {label} class was not flagged: {hits}"


def test_tailnet_hostname_is_flagged() -> None:
    """MagicDNS tailnet hostnames are private too — matching stays case-insensitive.

    The pattern anchors at a word boundary, so a hyphenated host prefix is not
    part of the match: the reported shape is the MagicDNS label + ``.ts.net``
    (this is the original guard's behaviour, now pinned).

    The hostname itself is assembled from parts — a literal one here would put
    this tracked file on the wrong side of the guard it exercises.
    """
    magic = "-".join(["tail", "48c"])  # the MagicDNS label
    suffix = ".".join(["ts", "net"])  # the tailnet domain
    host = "box-bunker7." + magic + "." + suffix
    hits = find_private_hosts("ssh into " + host + " and check\n")
    assert hits == [magic + "." + suffix], hits
    upper = (magic + "." + suffix).upper()
    assert find_private_hosts("the portal at BOX-7." + upper + "\n") == [upper], (
        "the original guard matched tailnet names case-insensitively"
    )


def test_hostnames_pass_and_are_not_flagged() -> None:
    text = (
        "bunker3 is down; see bunker-las-03 and vault-bunker-12 for the same role.\n"
        "ts.net is the suffix domain — bare, it is not a hostname.\n"
    )
    assert find_private_hosts(text) == [], "hostnames must never be flagged"


def test_suite_guard_exclusions_survive_in_the_shared_module() -> None:
    """Allowlist, CIDR prose and line scoping behave exactly as the old guard."""
    # Allowlisted documentation addresses are not leaks.
    for allowed in sorted(ALLOWED_ADDRESSES):
        assert find_private_hosts(f"probe {allowed} locally\n") == [], allowed
    # CIDR notation documents a range, not a host.
    cgnat = _addr("100.64-127/10 (CGNAT/tailnet)")
    assert find_private_hosts("the pool is " + cgnat + "/10\n") == []
    # But the same address WITHOUT the suffix is a hit — the exclusion is the slash.
    assert find_private_hosts("the pool is " + cgnat + "\n") == [cgnat]


def test_line_numbers_and_multi_line_ordering() -> None:
    text = "fine line\n" + f"leak of {_addr('10/8')} here\n" + f"and {_addr('192.168/16')} there\n"
    assert list(iter_line_hits(text)) == [(2, _addr("10/8")), (3, _addr("192.168/16"))]


def test_scan_file_skips_binary(tmp_path: Path) -> None:
    """A non-UTF-8 (binary-looking) file yields no hits and never raises."""
    binary = tmp_path / "blob.bin"
    binary.write_bytes(b"\xff\xfe\x00" + _addr("10/8").encode() + b"\x00\x80")
    assert scan_file(binary) == []
    texty = tmp_path / "notes.md"
    texty.write_text("reachable at " + _addr("172.16-31") + "\n", encoding="utf-8")
    assert scan_file(texty) == [(1, _addr("172.16-31"))]


def test_patterns_are_shared_not_duplicated() -> None:
    """The hook scans through the SAME module the suite guard imports."""
    hook = HOOK_SOURCE.read_text(encoding="utf-8")
    assert 'LEAK_SCANNER="tests/private_host_scan.py"' in hook, (
        ".gitreins/pre-commit does not consume tests/private_host_scan — a second "
        "hand-rolled pattern copy would drift from the suite guard's set"
    )
    assert "--scan" in hook, "the hook never invokes the shared scanner"


def test_hook_script_is_bash_clean() -> None:
    """The hook stays syntactically valid bash (the gate itself runs bash -n)."""
    bash = shutil.which("bash")
    assert bash is not None, "bash is required to lint the hook"
    proc = subprocess.run(
        [bash, "-n", str(HOOK_SOURCE)],
        capture_output=True,
        text=True,
        timeout=TIMEOUT_S,
        check=False,
    )
    assert proc.returncode == 0, f"bash -n failed:\n{proc.stderr}"


# ── the write path, end to end ───────────────────────────────────────────────


def _git_env() -> dict[str, str]:
    """Child env for hook runs: real tools, deliberately NO gitreins engine.

    The engine must stay absent so the leak arm (like the built-in secrets
    scan) is proven to block ON ITS OWN, where no quality harness is installed.
    PATH is built from the directories of the tools the hook needs — never the
    inherited PATH, which could resolve a real ``gitreins``.
    """
    dirs: list[str] = []
    for tool in ("git", "python3", "bash", "basename", "grep", "mktemp", "tee", "rm", "cat"):
        found = shutil.which(tool)
        assert found is not None, f"the host has no `{tool}`; these tests need it"
        if (parent := str(Path(found).parent)) not in dirs:
            dirs.append(parent)
    path = os.pathsep.join([*dirs, "/usr/bin", "/bin"])
    assert shutil.which("gitreins", path=path) is None, (
        "the child PATH must not resolve a gitreins engine — the leak arm is supposed to block without one"
    )
    return {
        **os.environ,
        "PATH": path,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_TERMINAL_PROMPT": "0",
    }


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=TIMEOUT_S,
        check=False,
        env={**_git_env()},
    )


def _commit(repo: Path, name: str, content: str, message: str) -> subprocess.CompletedProcess[str]:
    """Stage ``name`` and let the installed hook decide the commit's fate."""
    (repo / name).write_text(content, encoding="utf-8")
    added = _git(repo, "add", "--", name)
    assert added.returncode == 0, added.stderr
    return _git(repo, "commit", "-m", message)


@pytest.fixture()
def hook_repo(tmp_path: Path) -> Path:
    """A throwaway repo with one seed commit and the tracked hook installed."""
    repo = tmp_path / "repo"
    repo.mkdir()
    assert _git(repo, "init", "-q", "-b", "main").returncode == 0
    # A throwaway repo still needs an author identity to commit.
    assert _git(repo, "config", "user.email", "leak-gate-test@example.invalid").returncode == 0
    assert _git(repo, "config", "user.name", "Leak Gate Test").returncode == 0
    hook = repo / ".git" / "hooks" / "pre-commit"
    hook.parent.mkdir(parents=True, exist_ok=True)  # git init already creates .git/hooks
    hook.write_bytes(HOOK_SOURCE.read_bytes())
    hook.chmod(0o755)
    # A real checkout always carries the tracked scanner the hook resolves at
    # $ROOT/tests/ — mirror that, or the arm would (correctly) loud-SKIP.
    scanner = repo / "tests" / "private_host_scan.py"
    scanner.parent.mkdir(exist_ok=True)
    scanner.write_bytes(SCANNER_SOURCE.read_bytes())
    seed = _commit(repo, "README.md", "seed\n", "seed")
    assert seed.returncode == 0, f"seed commit failed:\n{seed.stdout}{seed.stderr}"
    return repo


def test_staged_leak_document_is_blocked(hook_repo: Path) -> None:
    """A staged doc carrying a private address must not reach a commit."""
    cgnat = _addr("100.64-127/10 (CGNAT/tailnet)")
    result = _commit(
        hook_repo,
        "run-10.md",
        "# integration run\n\nthe bunker node is at " + cgnat + "\n",
        "docs: run 10 notes",
    )
    output = result.stdout + result.stderr
    assert result.returncode != 0, f"a staged private address must block the commit:\n{output}"
    assert "COMMIT BLOCKED: private host address" in result.stderr, result.stderr
    assert "run-10.md" in output, "the block must name the offending file"
    assert cgnat in output, "the block must show the matched address shape"
    assert "Publish the host NAME" in output, "the block must name the fix"
    count = _git(hook_repo, "rev-list", "--count", "HEAD")
    assert count.returncode == 0 and count.stdout.strip() == "1", (
        f"the commit went through despite the block: {count.stdout}"
    )


def test_same_document_with_the_host_name_commits(hook_repo: Path) -> None:
    """The same doc referencing the host by NAME commits cleanly."""
    result = _commit(
        hook_repo,
        "run-10.md",
        "# integration run\n\nthe bunker node bunker-las-03 answered in 210ms\n",
        "docs: run 10 notes",
    )
    assert result.returncode == 0, f"a hostname-only doc must commit:\n{result.stdout}{result.stderr}"
    count = _git(hook_repo, "rev-list", "--count", "HEAD")
    assert count.stdout.strip() == "2", count.stdout
