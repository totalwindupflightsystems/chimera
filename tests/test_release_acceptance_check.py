"""Offline regression tests for the acceptance-evidence SHA gate — RELEASE-FINDING-2026-11-21-006.

v0.3.0's artifact-acceptance evidence
(``​.coding-hermes/evidence/RELEASE-PARITY-2026-11-16/artifact-acceptance-0.3.0.md``)
graded the wheel at worktree HEAD ``f7cf034``, while the pushed ``v0.3.0`` tag peeled
to ``57e298c`` — 72 commits later, 11 touching product source. The acceptance record
certified a tree no user receives, and nothing in the cut pipeline compared the two.

These tests pin the fix OFFLINE — no GitHub runner, no PyPI, no provider keys:

* scripts/release_acceptance_check.py extracts the graded SHA from the evidence
  file (priority: a ``graded-sha: <sha>`` line, the ``at HEAD `<sha>``` form the
  0.3.0 file used, then any backtick-quoted SHA; >1 distinct candidates refuse;
  64-hex sha256 artifact digests can never be mistaken for a git SHA), resolves
  the tag target with ``git rev-parse <tag>{}``, and exits 0 ONLY on EXACT
  equality;
* the incident shape — graded commit an ANCESTOR of the tag with commits between
  — is REFUSED with both SHAs printed on one loud line (f7cf034/57e298c replay);
* the refusal contract covers every abnormal input: missing evidence file, >1
  glob matches, missing/ambiguous graded SHA, unresolvable tag;
* the SCOPE-WAIVER escape is honored only when the line names THIS graded
  SHA/tag pair AND the packaged-path delta verifies empty; a packaged-path
  change or a mismatched waiver refuses;
* the gate is wired into the tag-gated ``release-verify`` job as a cheap keyless
  step that runs BEFORE the 5-minute PyPI install retry, invoking the script via
  the triggering tag — and a workflow copy with the step removed fails the pin.
"""

from __future__ import annotations

import importlib.util
import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
WORKFLOW_PATH = REPO / ".github" / "workflows" / "ci.yml"
CHECK_PATH = REPO / "scripts" / "release_acceptance_check.py"


def _load_module(name: str, path: Path) -> ModuleType:
    """Load a script as a module (scripts/ is not a package)."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


check = _load_module("release_acceptance_check", CHECK_PATH)


def _load_workflow(path: Path = WORKFLOW_PATH) -> dict:
    """Parse a workflow file (by default the real ci.yml) as a mapping."""
    with path.open(encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)
    assert isinstance(doc, dict), f"{path} must parse as a mapping"
    return doc


def _write_workflow_copy(tmp_path: Path, doc: dict) -> Path:
    """Serialize a mutated workflow to tmp_path — the real ci.yml is never edited."""
    out = tmp_path / "ci-mutated.yml"
    out.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    return out


# --- scratch git repos: the f7cf034/57e298c incident shape, replayed ------------- #


@dataclass
class ScratchRepo:
    """A repo whose graded commit is an ANCESTOR of the tagged commit."""

    path: Path
    graded: str  # full SHA of the commit the evidence grades
    tagged: str  # full SHA the tag certifies


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, f"git {args} failed: {proc.stderr}"
    return proc.stdout.strip()


def _make_scratch_repo(tmp_path: Path, *, drift: str = "board") -> ScratchRepo:
    """A repo where the graded commit precedes the tag.

    ``drift`` controls what the commits between grading and tagging touch:
    ``board`` — non-packaged board/state files only (the 0.3.0 scope-note shape,
    so a SCOPE-WAIVER can legitimately apply); ``product`` — the drift also
    changes packaged source (src/); ``none`` — the tag sits ON the graded commit.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.name", "test")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "commit.gpgsign", "false")
    (repo / "src").mkdir()
    (repo / "src" / "pkg.py").write_text("one\n", encoding="utf-8")
    (repo / "board").mkdir()
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "graded commit")
    graded = _git(repo, "rev-parse", "HEAD")
    if drift != "none":
        (repo / "board" / "events.jsonl").write_text("tick\n", encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-qm", "board-only drift")
    if drift == "product":
        (repo / "src" / "pkg.py").write_text("two\n", encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-qm", "product drift")
    _git(repo, "tag", "-a", "v1.2.3", "-m", "release v1.2.3")
    tagged = _git(repo, "rev-parse", "v1.2.3^{}")
    return ScratchRepo(path=repo, graded=graded, tagged=tagged)


def _write_evidence(
    repo: ScratchRepo | Path, graded_short: str, *, version: str = "1.2.3", body: str | None = None
) -> Path:
    """An evidence file in the tracked convention, shaped like the real 0.3.0 one."""
    repo_path = repo.path if isinstance(repo, ScratchRepo) else repo
    directory = repo_path / ".coding-hermes" / "evidence" / "RELEASE-PARITY-2026-11-16"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"artifact-acceptance-{version}.md"
    path.write_text(
        body
        if body is not None
        else (
            "# acceptance evidence\n\nVERDICT: PASS\n\nWheel (sha256 `<64-hex-digest>`) built "
            f"from worktree `wt/RELEASE-PARITY` at HEAD `{graded_short}`.\n"
        ),
        encoding="utf-8",
    )
    return path


def _run_check(
    *args: str, repo: Path | None = None, github_ref_name: str | None = None
) -> subprocess.CompletedProcess:
    """Run the check as a real process — its exit codes ARE the contract.

    ``GITHUB_REF_NAME`` is stripped from the ambient env unless explicitly set,
    so a developer's shell can never mask the CLI-argument contract.
    """
    cmd = [sys.executable, str(CHECK_PATH)]
    if repo is not None:
        cmd += ["--repo", str(repo)]
    cmd += list(args)
    env = dict(os.environ)
    env.pop("GITHUB_REF_NAME", None)
    if github_ref_name is not None:
        env["GITHUB_REF_NAME"] = github_ref_name
    return subprocess.run(cmd, capture_output=True, text=True, timeout=120, cwd=str(REPO), env=env)


# --- the incident shape: ancestor-only must REFUSE, naming both SHAs ------------- #


def test_ancestor_only_incident_shape_refuses_and_prints_both_shas(tmp_path: Path) -> None:
    """The f7cf034/57e298c replay: graded commit IS an ancestor — still refused.

    72 commits landed between the grading run and the v0.3.0 tag; the check must
    never silently accept that relationship, and the refusal must print BOTH
    SHAs plainly on the loud line.
    """
    repo = _make_scratch_repo(tmp_path, drift="board")
    _write_evidence(repo, repo.graded[:7])
    proc = _run_check("v1.2.3", repo=repo.path)
    assert proc.returncode == 2, f"ancestor-only must refuse:\n{proc.stdout}\n{proc.stderr}"
    assert "REFUSING to certify v1.2.3" in proc.stdout
    assert f"graded={repo.graded}" in proc.stdout, "the graded SHA must be printed plainly"
    assert f"tag={repo.tagged}" in proc.stdout, "the tag target must be printed plainly"
    assert "the acceptance evidence grades a different tree" in proc.stdout
    assert "ancestor-only" in proc.stdout
    assert "ancestry is not certification" in proc.stdout


def test_exact_graded_tree_passes(tmp_path: Path) -> None:
    """GREEN control: the tag sits on the graded commit — exit 0, both SHAs equal."""
    repo = _make_scratch_repo(tmp_path, drift="none")
    _write_evidence(repo, repo.graded[:7])
    proc = _run_check("v1.2.3", repo=repo.path)
    assert proc.returncode == 0, f"exact grade must pass:\n{proc.stdout}\n{proc.stderr}"
    assert f"graded={repo.tagged}" in proc.stdout
    assert f"tag={repo.tagged}" in proc.stdout
    assert "OK" in proc.stdout


def test_graded_sha_line_form_passes(tmp_path: Path) -> None:
    """The recommended machine-checkable line is honored as the graded SHA."""
    repo = _make_scratch_repo(tmp_path, drift="none")
    _write_evidence(repo, repo.graded[:7], body=f"graded-sha: {repo.tagged}\n")
    proc = _run_check("v1.2.3", repo=repo.path)
    assert proc.returncode == 0, f"graded-sha: line must pass:\n{proc.stdout}\n{proc.stderr}"


def test_github_ref_name_env_is_honored(tmp_path: Path) -> None:
    """The CI env form (no positional tag) works — that is how the workflow calls it."""
    repo = _make_scratch_repo(tmp_path, drift="none")
    _write_evidence(repo, repo.graded[:7])
    proc = _run_check(repo=repo.path, github_ref_name="v1.2.3")
    assert proc.returncode == 0, f"env tag form must pass:\n{proc.stdout}\n{proc.stderr}"


# --- the SHA extractor's documented robustness ----------------------------------- #


@pytest.mark.parametrize(
    "bad_tag",
    ["0.2.5", "v", "v*star", "v../escape", "va/b", "v0.2.5[!]", "", "v0.2.5; rm -rf /"],
)
def test_derive_version_rejects_glob_unsafe_tags(bad_tag: str) -> None:
    """The version interpolated into the evidence glob can never escape the pattern."""
    with pytest.raises(ValueError):
        check.derive_version(bad_tag)


def test_sha256_digest_never_counts_as_the_graded_sha(tmp_path: Path) -> None:
    """A 64-hex wheel sha256 digest in backticks is not a git SHA — HEAD form wins."""
    repo = _make_scratch_repo(tmp_path, drift="none")
    digest = "c80cd2c9f67e65aea3439e2b741e783fe7bf4ed8dd33cc12468622f7ba5491a3"
    body = (
        "# acceptance\n\nVERDICT: PASS\n\n"
        f"Artifact sha256 `{digest}` (1,224,866 bytes), built from worktree at HEAD `{repo.graded[:7]}`.\n"
    )
    _write_evidence(repo, repo.graded[:7], body=body)
    proc = _run_check("v1.2.3", repo=repo.path)
    assert proc.returncode == 0, (
        f"the digest must not derail the HEAD-form SHA:\n{proc.stdout}\n{proc.stderr}"
    )
    assert proc.stdout.startswith(f"graded={repo.tagged}"), proc.stdout


def test_ambiguous_backtick_evidence_refuses(tmp_path: Path) -> None:
    """Several distinct backtick SHAs (the incident file's scope-note shape) refuse."""
    repo = _make_scratch_repo(tmp_path, drift="board")
    body = (
        "# acceptance\n\nScope note: HEAD tree `aaaaaaaaaaaaaaa`, origin/main `bbbbbbbbbbbbbbb`, "
        "a tag cut at `ccccccccccccccc` would build.\n"
    )
    _write_evidence(repo, repo.graded[:7], body=body)
    proc = _run_check("v1.2.3", repo=repo.path)
    assert proc.returncode == 2, f"ambiguous evidence must refuse:\n{proc.stdout}\n{proc.stderr}"
    assert "ambiguous graded SHA" in proc.stdout
    assert "aaaaaaaaaaaaaaa" in proc.stdout and "bbbbbbbbbbbbbbb" in proc.stdout


def test_evidence_without_any_sha_refuses(tmp_path: Path) -> None:
    """An evidence file that never states the graded tree cannot certify anything."""
    repo = _make_scratch_repo(tmp_path, drift="none")
    _write_evidence(repo, repo.graded[:7], body="# acceptance\n\nVERDICT: PASS, trust me.\n")
    proc = _run_check("v1.2.3", repo=repo.path)
    assert proc.returncode == 2, proc.stdout
    assert "no graded HEAD SHA found" in proc.stdout
    assert "graded-sha:" in proc.stdout, "the refusal must teach the documented form"


# --- the refusal contract for every abnormal input ------------------------------- #


def test_missing_evidence_refuses(tmp_path: Path) -> None:
    """No evidence file at the convention — refuse loudly naming the convention."""
    repo = _make_scratch_repo(tmp_path, drift="none")
    proc = _run_check("v1.2.3", repo=repo.path)
    assert proc.returncode == 2, proc.stdout
    assert "no acceptance-evidence file" in proc.stdout
    assert "artifact-acceptance-1.2.3.md" in proc.stdout


def test_multiple_glob_matches_refuse_without_an_explicit_path(tmp_path: Path) -> None:
    """>1 convention matches refuse — the gate must not guess which record counts."""
    repo = _make_scratch_repo(tmp_path, drift="none")
    _write_evidence(repo, repo.graded[:7])
    other = repo.path / ".coding-hermes" / "evidence" / "other-run"
    other.mkdir(parents=True, exist_ok=True)
    (other / "artifact-acceptance-1.2.3.md").write_text(f"graded-sha: {repo.tagged}\n", encoding="utf-8")
    proc = _run_check("v1.2.3", repo=repo.path)
    assert proc.returncode == 2, proc.stdout
    assert "2 evidence files match" in proc.stdout


def test_explicit_evidence_path_overrides_the_glob(tmp_path: Path) -> None:
    """``--evidence`` names the file — the >1-match refusal does not apply."""
    repo = _make_scratch_repo(tmp_path, drift="none")
    evidence = _write_evidence(repo, repo.graded[:7])
    proc = _run_check("v1.2.3", "--evidence", str(evidence), repo=repo.path)
    assert proc.returncode == 0, f"explicit path must pass:\n{proc.stdout}\n{proc.stderr}"


def test_unresolvable_tag_refuses(tmp_path: Path) -> None:
    """A tag that does not resolve — refusal names the tag unresolvable."""
    repo = _make_scratch_repo(tmp_path, drift="none")
    _write_evidence(repo, repo.graded[:7], version="9.9.9")
    proc = _run_check("v9.9.9", repo=repo.path)
    assert proc.returncode == 2, proc.stdout
    assert "unresolvable" in proc.stdout
    assert "REFUSING to certify v9.9.9" in proc.stdout


def test_usage_error_without_any_tag_refuses() -> None:
    """No positional tag and no GITHUB_REF_NAME — usage exit 2, never a traceback."""
    proc = _run_check()
    assert proc.returncode == 2, proc.stdout
    assert "usage error" in proc.stderr
    assert "Traceback" not in proc.stderr


# --- the SCOPE-WAIVER escape: simple, loud, verified ------------------------------ #


def test_scope_waiver_honored_when_only_nonpackaged_paths_changed(tmp_path: Path) -> None:
    """Waiver + verified empty packaged-path delta: exit 0, loudly justified."""
    repo = _make_scratch_repo(tmp_path, drift="board")
    waiver = (
        f"SCOPE-WAIVER: {repo.graded[:7]} -> v1.2.3 board/state files only, never packaged into the wheel"
    )
    body = f"# acceptance\n\nbuilt at HEAD `{repo.graded[:7]}`.\n\n{waiver}\n"
    _write_evidence(repo, repo.graded[:7], body=body)
    proc = _run_check("v1.2.3", repo=repo.path)
    assert proc.returncode == 0, (
        f"waiver must pass with an empty packaged delta:\n{proc.stdout}\n{proc.stderr}"
    )
    assert "SCOPE-WAIVER honored" in proc.stdout
    assert waiver in proc.stdout, "the waiver line itself must be echoed"
    assert "board/state files only" in proc.stdout
    assert "board/events.jsonl" in proc.stdout, "every changed path must be listed"


def test_scope_waiver_refused_when_a_packaged_path_changed(tmp_path: Path) -> None:
    """A waiver cannot cover packaged-path drift — the delta verification refuses."""
    repo = _make_scratch_repo(tmp_path, drift="product")
    body = (
        f"# acceptance\n\nbuilt at HEAD `{repo.graded[:7]}`.\n\n"
        f"SCOPE-WAIVER: {repo.graded[:7]} -> v1.2.3 board/state files only, never packaged\n"
    )
    _write_evidence(repo, repo.graded[:7], body=body)
    proc = _run_check("v1.2.3", repo=repo.path)
    assert proc.returncode == 2, f"packaged drift must refuse:\n{proc.stdout}\n{proc.stderr}"
    assert "packaged paths changed" in proc.stdout
    assert "src/pkg.py" in proc.stdout


def test_scope_waiver_with_wrong_sha_refuses(tmp_path: Path) -> None:
    """A waiver naming another SHA/tag pair cannot apply — loud refusal explains why."""
    repo = _make_scratch_repo(tmp_path, drift="board")
    body = (
        f"# acceptance\n\nbuilt at HEAD `{repo.graded[:7]}`.\n\n"
        "SCOPE-WAIVER: deadbee -> v1.2.3 board/state files only, never packaged into the wheel\n"
    )
    _write_evidence(repo, repo.graded[:7], body=body)
    proc = _run_check("v1.2.3", repo=repo.path)
    assert proc.returncode == 2, proc.stdout
    assert "not this graded SHA/tag pair" in proc.stdout


# --- workflow wiring: the gate is a real, cheap, keyless release-verify step ------ #


@pytest.fixture(scope="module")
def workflow() -> dict:
    return _load_workflow()


ACCEPTANCE_COMMAND = ["python", "scripts/release_acceptance_check.py", "${GITHUB_REF_NAME}"]


def _acceptance_gate_steps(job: dict) -> list[dict]:
    return [s for s in job["steps"] if "release_acceptance_check.py" in s.get("run", "")]


def _assert_release_verify_runs_the_acceptance_gate(job: dict) -> dict:
    """Assert the acceptance-gate contract; return the step it pinned.

    The whole contract lives in this one helper so the mutation test judges a
    mutated COPY by exactly the assertions the real workflow passes.
    """
    assert job["needs"] == "publish", "release-verify must keep running after publish"
    assert "refs/tags/v" in job["if"], "release-verify must stay tag-gated"
    steps = _acceptance_gate_steps(job)
    assert len(steps) == 1, (
        f"release-verify must declare exactly one acceptance-SHA-gate step, found {len(steps)}"
    )
    step = steps[0]
    run = step["run"]
    invocations = [
        line.strip()
        for line in run.splitlines()
        if "release_acceptance_check.py" in line and not line.strip().startswith("#")
    ]
    assert len(invocations) == 1, f"expected exactly one invocation, got {invocations}"
    assert shlex.split(invocations[0]) == ACCEPTANCE_COMMAND, (
        f"the gate must run against the triggering tag, got {invocations[0]!r}"
    )
    assert "RELEASE-FINDING-2026-11-21-006" in step["name"], step["name"]
    assert not step.get("env"), f"the SHA gate is keyless, got env={step.get('env')}"
    assert "secrets." not in yaml.safe_dump(step), f"the gate is keyless, got {step}"
    all_steps = job["steps"]
    gate_index = all_steps.index(step)
    install_index = next(
        i for i, s in enumerate(all_steps) if "chimera-deliberation[full]==${VERSION}" in s.get("run", "")
    )
    assert gate_index < install_index, (
        f"the cheap SHA gate ({gate_index}) must fail BEFORE the 5-minute PyPI install "
        f"retry ({install_index})"
    )
    return step


def test_release_verify_runs_the_acceptance_sha_gate(workflow: dict) -> None:
    """The gate is wired into the tag-gated release-verify job."""
    _assert_release_verify_runs_the_acceptance_gate(workflow["jobs"]["release-verify"])


def test_removing_the_acceptance_gate_fails_the_pin(tmp_path: Path) -> None:
    """NEGATIVE: a workflow copy without the step must FAIL the contract."""
    doc = _load_workflow()
    job = doc["jobs"]["release-verify"]
    before = len(_acceptance_gate_steps(job))
    job["steps"] = [s for s in job["steps"] if "release_acceptance_check.py" not in s.get("run", "")]
    assert (before, len(_acceptance_gate_steps(job))) == (1, 0), "premise broken: step not removed"
    mutated = _load_workflow(_write_workflow_copy(tmp_path, doc))
    with pytest.raises(AssertionError, match="exactly one acceptance-SHA-gate step"):
        _assert_release_verify_runs_the_acceptance_gate(mutated["jobs"]["release-verify"])
