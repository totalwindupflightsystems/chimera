"""Cron wrapper for litellm_pin_check.py — installed-pin freshness check.

Operator guide: ``docs/LITELLM_PIN.md`` (pin rationale, verdicts, cap-lift
checklist, cadence).

Mirrors the ``scripts/model_sync_cron.py`` precedent: a thin, idempotent,
cron-shaped wrapper whose stdout is the report. Run it from the fleet
scheduler or a user crontab (e.g. monthly) to notice when upstream litellm
fixes the stdout pollution the ``litellm>=1.50.0,<1.100`` pin guards against,
so the pin can be lifted with evidence instead of aging silently.

Every argument is forwarded verbatim to the check (``--scratch``,
``--target``), and the check's exit code is this wrapper's exit code (0 =
check completed — read the verdict; 2 = harness error). The wrapper's own
interpreter does NOT need litellm: by default the check spawns its probe in
the repo venv (``.venv/bin/python``), falling back to the wrapper's
interpreter only when the checkout has no venv.

⚠️ A schedule that runs ONLY the default mode is useless: while the cap holds,
the installed litellm is inside the pinned range, so every run reports
``INCONCLUSIVE`` (the check can only produce boundary evidence from a
``>=1.100.0`` install). Schedule it with ``--scratch`` (needs network) or
point ``--target`` at an environment holding a cap-boundary litellm. Example:

    17 4 1 * * cd <repo> && .venv/bin/python scripts/litellm_pin_check_cron.py \
        --scratch >> /var/log/chimera-litellm-pin.log 2>&1

The last stdout line is always a single JSON report
(``schema: litellm-pin-check/1``), so a cron reader can parse the verdict
unambiguously. Human-readable detail goes to stderr.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CHECK = REPO_ROOT / "scripts" / "litellm_pin_check.py"


def main(argv: list[str] | None = None) -> int:
    """Run the pin check and print its report; return the child's exit code."""
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        args = []  # installed mode by default
    proc = subprocess.run(
        [sys.executable, str(CHECK), *args],
        cwd=str(REPO_ROOT),
        check=False,
    )
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
