"""Cron wrapper for model_sync.py — diff-only with auto-scoring.

Called by the chimera-model-sync cron job (Mondays 12:00 CT).
Outputs a report suitable for the cron agent's context.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _sync_python() -> str:
    """Return the Python interpreter that has the chimera deps installed.

    The cron runner's interpreter (sys.executable, e.g. the Hermes venv) does
    NOT have structlog/chimera installed — model_sync.py imports
    chimera.provider_discovery at module load, which fails with
    ModuleNotFoundError when run under the wrong interpreter (observed
    2026-08-04, cron run 17:00 UTC). Prefer the repo venv; fall back to
    sys.executable if the venv is missing so manual runs still work.
    """
    venv_py = REPO_ROOT / ".venv" / "bin" / "python"
    if venv_py.exists():
        return str(venv_py)
    return sys.executable


def main() -> None:
    print("=== Chimera Model Sync Cron ===")
    print(f"Run: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}")
    print()

    sync_python = _sync_python()

    # Step 1: Run model_sync.py --diff
    sync_script = REPO_ROOT / "scripts" / "model_sync.py"
    result = subprocess.run(
        [sync_python, str(sync_script), "--diff", "--output",
         str(REPO_ROOT / "reports" / "latest.md")],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")},
    )
    print(result.stdout)
    if result.returncode != 0:
        print(f"ERROR (model_sync): {result.stderr}")
        sys.exit(1)

    # Step 2: Check if there are new candidates
    output_path = REPO_ROOT / "reports" / "latest.md"
    if output_path.exists():
        content = output_path.read_text()
        if "Candidates: 0 new models" in content:
            print("No new models found. Done.")
            return

        # Step 3: Auto-score if DEEPSEEK_API_KEY is available
        if os.environ.get("DEEPSEEK_API_KEY"):
            print("\n=== Auto-scoring new candidates ===")
            score_result = subprocess.run(
                [sync_python, str(sync_script), "--diff", "--score"],
                capture_output=True, text=True, cwd=str(REPO_ROOT),
                env={**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")},
            )
            print(score_result.stdout)
            if score_result.returncode != 0:
                print(f"WARNING (scoring): {score_result.stderr}")
        else:
            print("\n⚠️  DEEPSEEK_API_KEY not set — skipping auto-score.")

    print("\n=== Done ===")


if __name__ == "__main__":
    main()
