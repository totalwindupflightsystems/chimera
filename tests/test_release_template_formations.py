"""The release gate's probed formations must exist in the config it provisions.

DF-CHIMERA-V2-100 (DF-CHIMERA-0917-6 class): the MCP purity probe legs in the
``release-verify`` job (step 9) only run on a TAG push, so no main-branch job
catches a drift between the formations the gate probes and the formations the
shipped template declares. v0.2.8 shipped exactly that way: the probe generates
its config with ``chimera config init`` (``scripts/probe_mcp_stdio.py``
``config_init_command`` -> ``chimera.config.find_example_config_path``), but
``chimera.yaml.example`` had been trimmed to a minimal budget WITHOUT the
``speed`` formation — the ``--formation=speed`` leg answered
``unknown_formation`` and the gate failed AFTER publish, leaving a released
wheel with an unverified gate.

This module pins the missing invariant OFFLINE (no network, no provider keys):

1. parse the formation names the release-verify job ACTUALLY probes out of
   ``.github/workflows/ci.yml`` (``probe_mcp_stdio.py --formation=<name>``
   legs) — not a hardcoded list, so a future third leg is covered
   automatically;
2. generate a config exactly the way the probe does — the probe module's own
   ``config_init_command`` against this interpreter's installed ``chimera``
   (the repo checkout's template wins under the editable dev install; a wheel
   install resolves the shipped copy — the same content, force-included) — and
   assert the generated ``formations`` keys are a SUPERSET of the probed names.
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import yaml

REPO = Path(__file__).resolve().parent.parent
WORKFLOW_PATH = REPO / ".github" / "workflows" / "ci.yml"
PROBE_PATH = REPO / "scripts" / "probe_mcp_stdio.py"


def _load_module(name: str, path: Path) -> ModuleType:
    """Load a script as a module (scripts/ is not a package)."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


probe = _load_module("probe_mcp_stdio_template_formations", PROBE_PATH)


def _release_verify_run_blocks() -> str:
    """All ``run:`` blocks of the release-verify job, concatenated."""
    with WORKFLOW_PATH.open(encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)
    job = doc["jobs"]["release-verify"]
    assert "refs/tags/v" in job["if"], "premise broken: release-verify is not tag-triggered"
    return "\n".join(step.get("run", "") for step in job["steps"])


def _probed_formations(run_blocks: str) -> set[str]:
    """Formation names the gate drives via ``--formation=<name>``."""
    names = set(re.findall(r"probe_mcp_stdio\.py --formation=([A-Za-z0-9_-]+)", run_blocks))
    assert names, "premise broken: release-verify declares no probe_mcp_stdio --formation legs"
    return names


def _config_init_formations(tmp_dir: Path) -> tuple[set[str], str]:
    """Run ``chimera config init`` the way the probe provisions, return (names, source).

    Uses the probe's own ``config_init_command`` so the test exercises the SAME
    provisioning path as the gate (sibling-CLI detection, template resolution
    through ``chimera.config.find_example_config_path``). This checkout's
    ``chimera.yaml.example`` is staged INTO the generate dir first, so template
    resolution step 1 (walk up from cwd) deterministically picks THIS tree's
    template — no dependence on how the dev install resolves its fallbacks,
    and a pre-fix tree's template is what actually gets copied. The source
    template path is recovered from the command output for the failure message.
    """
    staged = tmp_dir / "chimera.yaml.example"
    staged.write_text((REPO / "chimera.yaml.example").read_text(encoding="utf-8"), encoding="utf-8")
    child_cmd = [sys.executable, "-m", "chimera"]
    command = probe.config_init_command(child_cmd)
    proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
        command,
        cwd=tmp_dir,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert proc.returncode == 0, (
        f"`{' '.join(command)}` failed in {tmp_dir} (rc={proc.returncode}): "
        f"{(proc.stderr or proc.stdout).strip()[:600]}"
    )
    generated = tmp_dir / "chimera.yaml"
    assert generated.is_file(), f"`{' '.join(command)}` wrote no chimera.yaml in {tmp_dir}"
    source = str(staged)
    match = re.search(r"from (.+)\.\s*$", proc.stdout.strip(), re.MULTILINE)
    if match:
        source = match.group(1).strip()
    raw = yaml.safe_load(generated.read_text(encoding="utf-8"))
    assert isinstance(raw, dict), f"generated config is not a mapping: {generated}"
    return set(raw.get("formations") or {}), source


def test_gate_probes_are_a_subset_of_the_generated_config_formations(tmp_path: Path) -> None:
    """Every formation the release gate probes must survive ``chimera config init``.

    Fails when the shipped template lacks a probed formation — the v0.2.8
    escape (speed probed at depth but absent from chimera.yaml.example) now
    trips on every main-branch push, not only on the tag push.
    """
    probed = _probed_formations(_release_verify_run_blocks())
    generated_names, source = _config_init_formations(tmp_path)
    missing = probed - generated_names
    assert not missing, (
        f"the release gate probes formation(s) {sorted(missing)} that the generated "
        f"config does not declare (template: {source}). The MCP gate provisions its "
        f"config via `chimera config init`, so a probed-but-undeclared formation fails "
        f"the release-verify job only AFTER publish (DF-CHIMERA-V2-100). Restore the "
        f"formation to chimera.yaml.example."
    )
