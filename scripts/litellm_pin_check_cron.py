"""Cron wrapper for litellm_pin_check.py — installed-pin freshness check.

Mirrors the ``scripts/model_sync_cron.py`` precedent: a thin, idempotent,
cron-shaped wrapper whose stdout is the report. Run it from the fleet
scheduler or a user crontab (e.g. monthly) to notice when upstream litellm
fixes the stdout pollution the ``litellm>=1.50.0,<1.100`` pin guards against,
so the pin can be lifted with evidence instead of aging silently.

By default it probes the REPO VENV's installed litellm (fast, offline,
exit 0, JSON verdict SAFE_TO_TEST / STAY_PINNED / INCONCLUSIVE). Pass
``--scratch`` to pip-install ``litellm>=1.100.0`` into a temporary venv for
cap-boundary evidence (needs network; degrades to INCONCLUSIVE offline).

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
