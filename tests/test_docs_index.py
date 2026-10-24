"""Docs index completeness tests (CH-GAP-052).

Every tracked file under ``docs/`` must be discoverable: either linked from the
root ``README.md`` or listed in the docs index ``docs/README.md`` — and an
artifact that is not current documentation (an early PRD draft, an audit
snapshot, a dated dogfood run log) must be listed **inside** one of the
explicitly marked historical sections rather than sitting in the guide list
where a reader would take it for current documentation.

Orphan files rot silently: ``docs/LOCAL_CI.md`` was a real, current guide
(reproducing hosted CI locally with ``act``) that nothing in the repo
referenced, so it was indistinguishable from a deleted file. The tracked-file
list comes from ``git ls-files`` on purpose — a NEW file dropped into ``docs/``
fails this test until the author links it or labels it historical.

Hermetic by construction: paths resolve from this file (never the process cwd),
and there is no network access, no provider key, and no deliberation call.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
README = REPO / "README.md"
DOCS_INDEX = REPO / "docs" / "README.md"

#: Generous budget — ``git ls-files`` on this repo is a sub-second command.
GIT_TIMEOUT_S = 30

#: Heading that marks the index's historical-artifact section.
HISTORICAL_HEADING = "## Historical / archived"

#: Heading that marks the index's dogfood run-log section.
DOGFOOD_HEADING = "## Dogfood run logs"

#: The undated catch-all behind the run logs — not a dated run log itself, so the
#: same-commit rule below does not require a dated index line for it.
UNDATED_DOGFOOD_LOG = "diagnostics.md"


def _tracked_docs_files() -> list[str]:
    """Tracked paths under ``docs/`` (repo-relative, sorted), or skip the module.

    Skips rather than fails when git is unavailable or reports nothing — an
    exported tarball or a stripped clone has no index to check.
    """
    try:
        proc = subprocess.run(
            ["git", "ls-files", "docs/"],
            cwd=REPO,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:  # git missing / unrunnable
        pytest.skip(f"git unavailable: {exc}", allow_module_level=True)
    if proc.returncode != 0 or not proc.stdout.strip():
        pytest.skip(
            f"no tracked docs/ files (git exit {proc.returncode}): {proc.stderr.strip()}",
            allow_module_level=True,
        )
    return sorted(line.strip() for line in proc.stdout.splitlines() if line.strip())


TRACKED_DOCS = _tracked_docs_files()


def _section(text: str, heading: str) -> str:
    """Body of ``heading`` up to the next ``## `` heading (empty string if absent)."""
    marker = f"\n{heading}\n"
    if marker not in text:
        return ""
    body = text.split(marker, 1)[1]
    for line in body.splitlines():
        if line.startswith("## "):
            return body.split(line, 1)[0]
    return body


def _index_text() -> str:
    return README.read_text(encoding="utf-8") + "\n" + DOCS_INDEX.read_text(encoding="utf-8")


def test_readme_links_docs_index() -> None:
    """README must link the docs index, not just the individual guides."""
    assert "docs/README.md" in README.read_text(encoding="utf-8"), (
        "README.md does not link docs/README.md — readers cannot reach the full index"
    )


@pytest.mark.parametrize("rel_path", TRACKED_DOCS)
def test_tracked_docs_file_is_reachable(rel_path: str) -> None:
    """Every tracked docs/ file is named in README.md or docs/README.md."""
    text = _index_text()
    basename = Path(rel_path).name
    assert rel_path in text or basename in text, (
        f"{rel_path} is referenced nowhere: link it from README.md (if it is "
        f"current documentation) or list it in docs/README.md — in the "
        f"'{HISTORICAL_HEADING}' / '{DOGFOOD_HEADING}' section if it is historical"
    )


def _orphaned_dogfood_logs(index_text: str | None = None) -> list[str]:
    """Tracked ``docs/dogfood/*.md`` logs that no index line names, sorted.

    ``index_text`` defaults to the live README.md + docs/README.md pair. The
    pre-commit hook (``scripts/check_docs_index.sh``) passes the INDEX AS IT
    WOULD BE COMMITTED — ``git show :README.md`` plus ``git show :docs/README.md``
    — so the hook and this test agree on one implementation instead of two
    drifting copies.

    ``diagnostics.md`` is the undated catch-all, not a run log, so it is not
    required to carry a dated index line (the dogfood-section test below still
    pins it). Everything else under docs/dogfood/ is a dated run log: it exists
    to be read, so it must be reachable from the index in the same commit that
    adds it.
    """
    text = _index_text() if index_text is None else index_text
    return [
        rel
        for rel in TRACKED_DOCS
        if rel.startswith("docs/dogfood/")
        and rel.endswith(".md")
        and Path(rel).name != UNDATED_DOGFOOD_LOG
        and rel not in text
        and Path(rel).name not in text
    ]


@pytest.mark.parametrize(
    "name",
    [
        "docs/PRD.html",
        "docs/Chimera-PRD.html",
        "docs/audit-2026-08.md",
    ],
)
def test_historical_artifact_is_labeled_historical(name: str) -> None:
    """Dated artifacts live inside the historical section, not the guide list."""
    section = _section(DOCS_INDEX.read_text(encoding="utf-8"), HISTORICAL_HEADING)
    assert section, f"docs/README.md has no '{HISTORICAL_HEADING}' section"
    assert Path(name).name in section, (
        f"{name} is not listed in the '{HISTORICAL_HEADING}' section of "
        f"docs/README.md — a historical artifact must be labeled as such"
    )


@pytest.mark.parametrize(
    "name",
    [
        "2026-08-03-integration.md",
        "2026-08-13-integration.md",
        "2026-08-23-integration.md",
        "2026-09-04-runB-integration.md",
        "2026-09-11-integration.md",
        "diagnostics.md",
    ],
)
def test_dogfood_log_is_listed_under_dogfood_section(name: str) -> None:
    """Every docs/dogfood/ file is listed under the marked run-log section."""
    section = _section(DOCS_INDEX.read_text(encoding="utf-8"), DOGFOOD_HEADING)
    assert section, f"docs/README.md has no '{DOGFOOD_HEADING}' section"
    assert name in section, (
        f"docs/dogfood/{name} is not listed under '{DOGFOOD_HEADING}' in "
        f"docs/README.md — historical run logs must be marked as such"
    )


# ── Same-commit rule (INT-CI-014-R2) ──────────────────────────────────────────
#
# test_tracked_docs_file_is_reachable above is the DETECTOR: it walks
# `git ls-files docs/`, so it fires on the push AFTER an unindexed log lands.
# That ordering is why this class recurred five times (CI-FIX-001, DOC-2,
# INT-CI-014, INT-CI-014-R2): the run log and its index line were allowed to
# travel in different commits, and main was red in between.
#
# The two tests below are the PREVENTIVE half:
#   * no stranded log at HEAD (the invariant, asserted against the live index),
#   * scripts/check_docs_index.sh blocks a commit that adds a log without its
#     index line, proven RED then GREEN through a private index file.

CHECKER = REPO / "scripts" / "check_docs_index.sh"


def test_no_dogfood_log_is_stranded_at_head() -> None:
    """The invariant: nothing tracked under docs/dogfood/ is unindexed at HEAD."""
    stranded = _orphaned_dogfood_logs()
    assert not stranded, (
        "these tracked run logs are referenced nowhere in README.md / "
        f"docs/README.md: {stranded} — list each one under '{DOGFOOD_HEADING}' "
        "in docs/README.md"
    )


def _scratch_index(tmp_path: Path) -> Path:
    """A private copy of the repository index (never the live one)."""
    git_dir = subprocess.run(
        ["git", "rev-parse", "--git-dir"],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=GIT_TIMEOUT_S,
        check=True,
    ).stdout.strip()
    source = (REPO / git_dir / "index").resolve()
    if not source.is_file():
        pytest.skip(f"no index at {source}")
    scratch = tmp_path / "index"
    scratch.write_bytes(source.read_bytes())
    return scratch


def _git(args: list[str], env: dict[str, str], stdin: str | None = None) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=REPO,
        capture_output=True,
        text=True,
        input=stdin,
        timeout=GIT_TIMEOUT_S,
        env=env,
        check=True,
    )
    return proc.stdout


def _hash(env: dict[str, str], content: str) -> str:
    return _git(["hash-object", "-w", "--stdin"], env, stdin=content).strip()


def test_checker_blocks_a_log_added_without_its_index_line(tmp_path: Path) -> None:
    """RED: an added run log with no index line is refused, through the index.

    The scratch index is a byte copy of the repo index, so the checker sees the
    real tree plus exactly one added log. Nothing is written to the worktree and
    the live index is never touched — only loose objects and a temp index.
    """
    env = {**os.environ, "GIT_INDEX_FILE": str(_scratch_index(tmp_path))}
    log_path = "docs/dogfood/2099-01-01-runZZ-integration.md"

    blob = _hash(env, "# run ZZ — scratch index arm\n")
    _git(["update-index", "--add", "--cacheinfo", f"100644,{blob},{log_path}"], env)

    red = subprocess.run(
        ["bash", str(CHECKER)], cwd=REPO, env=env, capture_output=True, text=True, timeout=GIT_TIMEOUT_S
    )
    assert red.returncode == 1, (
        "the checker PASSED a commit that adds an unindexed run log:\n"
        f"stdout={red.stdout}\nstderr={red.stderr}"
    )
    assert log_path in red.stderr, f"the refusal does not name the offending path:\n{red.stderr}"

    # GREEN: stage the index line into the SAME scratch index.
    index_md = _git(["show", ":docs/README.md"], env)
    line = f"- [dogfood/{log_path.split('/')[-1]}](dogfood/{log_path.split('/')[-1]}) — scratch arm\n"
    new_entry = index_md.replace(f"{DOGFOOD_HEADING}\n", f"{DOGFOOD_HEADING}\n{line}", 1)
    assert new_entry != index_md, "the scratch index has no dogfood section to append to"
    new_blob = _hash(env, new_entry)
    _git(["update-index", "--add", "--cacheinfo", f"100644,{new_blob},docs/README.md"], env)

    green = subprocess.run(
        ["bash", str(CHECKER)], cwd=REPO, env=env, capture_output=True, text=True, timeout=GIT_TIMEOUT_S
    )
    assert green.returncode == 0, (
        "the checker refused a commit that DOES index the log it adds:\n"
        f"stdout={green.stdout}\nstderr={green.stderr}"
    )


def test_checker_is_wired_into_the_precommit_hook() -> None:
    """The gate only prevents anything if the commit path actually runs it."""
    hook = (REPO / ".gitreins" / "pre-commit").read_text(encoding="utf-8")
    assert "scripts/check_docs_index.sh" in hook, (
        ".gitreins/pre-commit does not invoke scripts/check_docs_index.sh — the "
        "same-commit rule is inert at commit time"
    )
