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
