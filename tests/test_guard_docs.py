"""INT-GATE-001: the guard's ``lsp`` lane must be deterministic, and its verdict
semantics documented.

The GitReins guard enables the ``lsp`` lane with ``lsp_tools: [pylsp]``
(``.gitreins/config.yaml``) and resolves that tool with
``shutil.which(binary)`` — **PATH only**. Two things follow, and both are
asserted here because neither is enforced by anything else:

1. A substantive lane that does no work is a SKIP, and with
   ``guards.allow_skips`` unset (this repo's deliberate policy: the key turns a
   missing tool into a green pass) the whole run reads red. So a contributor on a
   box without ``pylsp`` could never get a green verdict — unless the dev extra
   ships the tool (``pip install -e ".[dev]"``) and the documented guard command
   puts the repo venv first on PATH, which is the only PATH form that reaches it.
   ``AGENTS.md`` used to document ``$HOME/gitreins-poc/.venv/bin`` instead: a
   path that exists on one host, leaks an internal directory name into a public
   repo, and does not provide ``pylsp`` at all.
2. The verdict rules — a skip is not a pass, and ``gitreins task complete``
   grades the STAGED diff, so completing after a commit hands tier 1 an empty
   index (DEGRADED FAIL while tier 2 says COMPLETE) — are the ones that have
   burned foreman ticks. ``docs/GITREINS.md`` is their single home.

Hermetic by construction: paths resolve from this file (never the process cwd),
and there is no network, no provider key, and no deliberation call. ``tomllib``
is stdlib on the supported Python (>=3.11), so the declaration is parsed rather
than grepped.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PYPROJECT = REPO / "pyproject.toml"
AGENTS = REPO / "AGENTS.md"
GUARD_DOC = REPO / "docs" / "GITREINS.md"
DOCS_INDEX = REPO / "docs" / "README.md"
CONFIG = REPO / ".gitreins" / "config.yaml"

#: The LSP server the guard's ``lsp_tools`` list names, and the minimum the dev
#: extra must allow (1.12.0 is the floor the fix was provisioned against).
LSP_SERVER = "python-lsp-server"
LSP_MIN = (1, 12, 0)

#: A host-specific internal path that must never be documented in a public repo.
FORBIDDEN_IN_AGENTS = "gitreins-poc"

#: The doc must name these to be the reference it claims to be.
REQUIRED_DOC_TERMS = ("allow_skips", "DEGRADED")


def _text(path: Path) -> str:
    assert path.exists(), f"{path.relative_to(REPO)} is missing"
    return path.read_text(encoding="utf-8")


def _dev_extra() -> list[str]:
    """The ``[project.optional-dependencies].dev`` list (empty if undeclared)."""
    data = tomllib.loads(_text(PYPROJECT))
    return list(data.get("project", {}).get("optional-dependencies", {}).get("dev", []))


def _requirement_names(requirements: list[str]) -> list[str]:
    """Distribution names from PEP 508-ish requirement strings (no resolver)."""
    names = []
    for req in requirements:
        match = re.match(r"^\s*([A-Za-z0-9._-]+)", req)
        if match:
            names.append(match.group(1).lower().replace("_", "-"))
    return names


def test_dev_extra_accepts_the_python_lsp_server() -> None:
    """The dev extra must allow an LSP server that satisfies the fixed floor."""
    dev = _dev_extra()
    assert dev, "pyproject.toml has no [project.optional-dependencies].dev list"
    assert LSP_SERVER in _requirement_names(dev), (
        f"the dev extra does not declare {LSP_SERVER}: a contributor running the "
        f"documented `pip install -e \".[dev]\"` would leave the guard's lsp lane "
        f"without its tool (a skip, and a red run while allow_skips stays unset). "
        f"dev extra: {dev}"
    )

    declared = next(req for req in dev if _requirement_names([req])[0] == LSP_SERVER)
    assert "," not in declared, f"unexpected multi-specifier requirement: {declared!r}"
    floor = declared.partition(">=")[2]
    assert floor, (
        f"{declared!r} declares no `>=` lower bound — the lane's tool must be pinned "
        f"to at least {'.'.join(str(part) for part in LSP_MIN)}"
    )
    parsed = re.match(r"\d+(?:\.\d+)*", floor)
    assert parsed, f"cannot read a version out of {declared!r}"
    version = tuple(int(part) for part in parsed.group(0).split("."))
    assert version >= LSP_MIN, (
        f"{declared!r} allows a version below the required floor "
        f"{'.'.join(str(part) for part in LSP_MIN)} — raise the lower bound"
    )


def test_agents_documents_a_repo_relative_guard_on_the_repo_venv() -> None:
    """The documented guard command must put the repo venv first on PATH."""
    text = _text(AGENTS)
    assert "gitreins guard" in text, "AGENTS.md no longer documents `gitreins guard`"
    assert "git rev-parse --show-toplevel" in text, (
        "AGENTS.md's guard command is not repo-relative — it must derive the repo "
        "root with `git rev-parse --show-toplevel`, or a contributor on another "
        "checkout gets a PATH that does not exist"
    )
    assert ".venv/bin" in text, (
        "AGENTS.md's guard command does not put the repo venv on PATH — without it "
        "the lsp lane cannot find pylsp and the run is degraded"
    )


def test_agents_has_no_host_specific_internal_path() -> None:
    """No internal harness path may leak into the public repo's instructions."""
    text = _text(AGENTS)
    assert FORBIDDEN_IN_AGENTS not in text, (
        f"AGENTS.md still names {FORBIDDEN_IN_AGENTS!r} — a harness directory that "
        f"exists on one host, is meaningless to a contributor, and points the guard "
        f"at a venv that lacks the lane's tool"
    )


def test_agents_points_at_the_guard_reference_doc() -> None:
    """AGENTS.md keeps the short form; the detail lives in docs/GITREINS.md."""
    assert "docs/GITREINS.md" in _text(AGENTS), (
        "AGENTS.md does not reference docs/GITREINS.md — the DEGRADED-PASS and "
        "verdict-ordering rules have nowhere to live"
    )


def test_guard_doc_states_the_verdict_semantics() -> None:
    """docs/GITREINS.md must carry the load-bearing verdict rules verbatim."""
    text = _text(GUARD_DOC)
    assert len(text) > 1500, f"docs/GITREINS.md is only {len(text)} bytes — too thin to be the reference"

    missing = [term for term in REQUIRED_DOC_TERMS if term not in text]
    assert not missing, f"docs/GITREINS.md does not mention {missing}"

    # The DEGRADED-PASS rule: a zero-work lane is a skip, not a pass.
    assert re.search(r"skip\w*", text, re.IGNORECASE), "docs/GITREINS.md never says what a skipped lane is"

    # The ordering trap: tier 1 grades the STAGED diff, so `task complete` after a
    # commit grades an empty index. Both halves of that sentence must be present.
    assert isinstance(re.search(r"task complete", text), re.Match), (
        "docs/GITREINS.md does not document `gitreins task complete` — the ordering "
        "trap it must warn about"
    )
    assert re.search(r"staged", text, re.IGNORECASE), (
        "docs/GITREINS.md does not say that tier 1 grades the STAGED diff, which is "
        "the whole reason the ordering trap happens"
    )


@pytest.mark.parametrize("basename", ["GITREINS.md"])
def test_guard_doc_is_linked_from_the_docs_index(basename: str) -> None:
    """tests/test_docs_index.py fails on any unlinked docs/ file — link it here."""
    assert basename in _text(DOCS_INDEX), (
        f"docs/README.md does not link {basename} — a tracked docs/ file that no "
        f"index references fails test_docs_index.py, and a reader never finds it"
    )


def test_lsp_lane_is_still_enabled_in_the_guard_config() -> None:
    """Premise guard: the lane these docs are about is configured and enabled.

    Without this, the whole module could stay green after someone disabled the
    lane — the docs would describe a gate that no longer exists.
    """
    text = _text(CONFIG)
    assert re.search(r"^\s*lsp:\s*true\s*$", text, re.MULTILINE), (
        ".gitreins/config.yaml no longer enables the lsp lane — docs/GITREINS.md and "
        "the dev-extra declaration exist to make that lane run"
    )
    assert re.search(r"^\s*-\s*pylsp\s*$", text, re.MULTILINE), (
        ".gitreins/config.yaml does not list pylsp in lsp_tools"
    )
    assert not re.search(r"^\s*allow_skips:\s*true\s*$", text, re.MULTILINE), (
        "guards.allow_skips is enabled — that converts a missing tool into a green "
        "pass, which is the policy this repo deliberately opts out of"
    )
