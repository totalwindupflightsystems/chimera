"""Cron wrapper for model_sync.py — diff-only with auto-scoring.

Called by the chimera-model-sync cron job (daily 12:00 local — the live Hermes
job uses the cron expr ``0 12 * * *``; the previous "Mondays 12:00 CT" line
was stale).
Outputs a report suitable for the cron agent's context.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Env var holding the DeepSeek key used by ``model_sync.py --score``.
SCORE_KEY_ENV = "DEEPSEEK_API_KEY"

#: Env override pointing at an alternative Hermes dotenv file, so tests never
#: depend on the developer's real ``~/.hermes/.env``.
HERMES_DOTENV_ENV = "CHIMERA_HERMES_DOTENV"

#: Source label reported when the key came from the process environment.
PROCESS_ENV_SOURCE = "process env"


def _hermes_dotenv_path() -> Path:
    """Path of the Hermes dotenv file that holds the fleet's API keys.

    Defaults to ``~/.hermes/.env`` (resolved from the user's home, never a
    hardcoded absolute path) and can be redirected with
    ``CHIMERA_HERMES_DOTENV``.
    """
    override = os.environ.get(HERMES_DOTENV_ENV, "").strip()
    if override:
        return Path(override).expanduser()
    return Path("~/.hermes/.env").expanduser()


def _parse_dotenv(path: Path) -> dict[str, str]:
    """Parse a dotenv file into ``{name: value}`` (stdlib only).

    Mirrors ``chimera.config._load_hermes_dotenv``: blank and ``#`` lines are
    skipped, the key is split on the FIRST ``=``, surrounding quotes are
    stripped and whitespace is tolerated. Implemented locally on purpose —
    this wrapper runs under the cron runner's interpreter, which has no
    chimera/structlog deps installed (see ``_sync_python()``).
    """
    values: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return values
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
            val = val[1:-1]
        values[key] = val
    return values


def _resolve_score_key() -> tuple[str, str]:
    """Resolve ``DEEPSEEK_API_KEY`` and report which source supplied it.

    Precedence matches ``chimera.config.load_config()``:
    process env > repo ``.env`` (next to ``REPO_ROOT``) > ``~/.hermes/.env``
    (redirectable via ``CHIMERA_HERMES_DOTENV``). The scheduled runner's
    process environment does NOT carry the key — it only exists in the Hermes
    dotenv file — so gating on ``os.environ`` alone skipped the auto-score
    step on every scheduled run (observed 2026-09-17).

    Returns ``(key, source)``, or ``("", "")`` when the key resolves nowhere.
    Callers must report *source*, never the key value.
    """
    value = os.environ.get(SCORE_KEY_ENV, "").strip()
    if value:
        return value, PROCESS_ENV_SOURCE

    for path in (REPO_ROOT / ".env", _hermes_dotenv_path()):
        if not path.is_file():
            continue
        value = _parse_dotenv(path).get(SCORE_KEY_ENV, "").strip()
        if value:
            return value, str(path)

    return "", ""


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
        [sync_python, str(sync_script), "--diff", "--output", str(REPO_ROOT / "reports" / "latest.md")],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
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
        # NB: the file is markdown ("**Candidates:** 0 new models ..."), so
        # match the shared "0 new models" fragment — the plain-text marker
        # "Candidates: 0 new models" never appears in the file and let the
        # auto-score step run on an empty diff (wasted API call + confusing
        # error output; observed 2026-08-17).
        if "0 new models" in content:
            print("No new models found. Done.")
            return

        # Step 3: Auto-score when the key resolves (process env, repo .env or
        # ~/.hermes/.env). The scheduled runner's process environment carries
        # no DEEPSEEK_API_KEY — it lives in the Hermes dotenv file — so a bare
        # os.environ check skipped scoring on every scheduled run.
        score_key, key_source = _resolve_score_key()
        if score_key:
            print("\n=== Auto-scoring new candidates ===")
            print(f"{SCORE_KEY_ENV} resolved from {key_source}")
            score_result = subprocess.run(
                [sync_python, str(sync_script), "--diff", "--score"],
                capture_output=True,
                text=True,
                cwd=str(REPO_ROOT),
                env={
                    **os.environ,
                    SCORE_KEY_ENV: score_key,
                    "PYTHONPATH": str(REPO_ROOT / "src"),
                },
            )
            print(score_result.stdout)
            if score_result.returncode != 0:
                print(f"WARNING (scoring): {score_result.stderr}")
        else:
            print(f"\n⚠️  {SCORE_KEY_ENV} not set — skipping auto-score.")

    print("\n=== Done ===")


if __name__ == "__main__":
    main()
