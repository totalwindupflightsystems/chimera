# AGENTS.md — Chimera

## Overview

Chimera is a Dynamic Multi-Model Deliberation Gateway (Python 3.11+). One API call dispatches your prompt to a hand-picked team of LLMs — each with a custom subtask scoped to their strengths — and an aggregator merges their outputs using dispatcher-written instructions.

**Repository**: https://github.com/totalwindupflightsystems/chimera
**Language**: Python
**Test framework**: pytest
**Package**: chimera-deliberation

## Project Structure

```
src/chimera/
  __init__.py       — Package init
  engine.py         — Core deliberation engine
  dispatcher.py     — Prompt-to-subtask dispatch
  aggregator.py     — Multi-model output merging
  selector.py       — Model selection logic
  config.py         — Configuration (chimera.yaml)
  gateway.py        — API gateway
  circuit_breaker.py — Rate limiting / circuit breaker
  exceptions.py     — Custom exceptions
  observability.py  — Logging/metrics
  api/              — FastAPI server
  web/              — Web UI (SSE, session, trace viz)
  cli/              — CLI entry point
tests/
  test_*.py         — Unit tests (flat in tests/, with __init__.py + conftest.py)
  integration/      — Integration tests
  compat/           — Compatibility tests
```

## Build & Test Commands

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
.venv/bin/python -m pytest -x --tb=short -q

# Run specific test file
.venv/bin/python -m pytest tests/test_engine.py -x --tb=short

# Run with coverage
.venv/bin/python -m pytest --cov=src/chimera --cov-report=term-missing
```

## Deploy / restart (supervised :8765 service)

`chimera serve` runs as a systemd system unit (`chimera.service`, User=kara,
WorkingDirectory=/home/kara/chimera-v2, Restart=always). New code is NOT
loaded until the unit restarts — `Restart=always` only recovers crashes, so
a plain `git pull` leaves the running process on the OLD code (staleness was
invisible before CH-GAP-039 added the running commit to /health).

```bash
git pull            # or switch to the target commit
sudo systemctl restart chimera
curl -s localhost:8765/health   # must show "commit": "<new HEAD>"
```

Health endpoints now expose the running git commit (`/health`,
`/v1/health/live`, `/v1/health` details) — compare it against
`git rev-parse --short HEAD` to prove the deployed process matches the
checkout. Foreman light-audits do exactly this check on every tick.

### Live config is local-only (never commit it)

`/home/kara/chimera-v2/chimera.yaml` is **untracked and gitignored**
(DF-CHIMERA-0916B-4) — the repo ships only `chimera.yaml.example`. The unit
points `Environment=CHIMERA_CONFIG` at that exact path, so the file stays on
disk here and the deploy steps above are unchanged. After pulling a tree where
it was untracked, recreate it with `chimera config init` (or restore your
backup) before restarting: a fresh clone has no live config at all, and the
service will not boot without one.

### Live smoke test (one command, end-to-end)

`/v1/health` saying "alive" does NOT prove a deliberation works — provider
billing, auth, or format regressions (INT-ZAI-001 class) only surface on a
real call. Run the live smoke test after every deploy (and any time you
suspect the deployment):

```bash
python scripts/smoke_live.py            # localhost:8765, formation=simple
python scripts/smoke_live.py --formation auto   # full dispatcher path
CHIMERA_API_KEY=... python scripts/smoke_live.py  # if auth is enabled
```

It checks liveness + running commit (warns if the deployed commit diverges
from local HEAD), probes `/v1/health`, then POSTs a real `/v1/deliberate`
and prints the merged answer. Exit 0 = merged answer received; exit 1 =
failure with an actionable message (auth/formation/busy/provider hints);
exit 2 = usage error. Stdlib-only, no extra dependencies.

### Pushing to the public mirror (workflow-touching commits)

Two remotes are configured: `origin` (the private GitLab primary) and `github`
(the PUBLIC mirror). The `github` push path is an HTTPS URL whose credential is
a `gh` OAuth app with scopes `repo, read:org, gist`, and GitHub enforces the
workflow scope at RECEIVE time — so any commit that touches
`.github/workflows/` is rejected server-side, no matter that every local gate
passed:

    ! [remote rejected] main -> main (refusing to allow an OAuth App to create
      or update workflow .github/workflows/ci.yml without `workflow` scope)

That token cannot be widened in place, so the HTTPS push can never succeed for
such a commit; the rejection is easy to miss and the mirror drifts behind. The
same account authenticates over SSH — re-push the SAME commit over the SSH URL:

```bash
git push git@github.com:totalwindupflightsystems/chimera.git main
```

`scripts/push_remotes.py` (stdlib-only) does this for every remote: it pushes,
retries ONCE over the derived SSH URL exactly on that rejection, then verifies
ref parity. Use it instead of hand-picking a remote; `--dry-run` prints the
exact commands (including the fallback) without pushing anything:

```bash
python scripts/push_remotes.py --dry-run     # plan only: no push, no ls-remote
python scripts/push_remotes.py               # every remote; exit 0 = pushed + parity
python scripts/push_remotes.py --remote github --branch main
```

Then run the parity check the helper enforces — the mirror is behind until its
`refs/heads/main` equals local `HEAD` (the read path is unaffected by the
missing workflow scope):

```bash
git ls-remote github refs/heads/main   # must equal: git rev-parse HEAD
```

---

## GitReins Quality Harness (MANDATORY)

This repo uses GitReins as its quality gate. Every commit runs static guards.
If guards fail, the commit is BLOCKED. You cannot skip this.

### Quick check before committing:

```bash
PATH="$HOME/gitreins-poc/.venv/bin:$PATH" gitreins guard
```

### What's checked:
- **secrets** — API keys, tokens, passwords (BLOCKS on fail — no exceptions)
- **lint** — ruff (WARNS on fail)
- **tests** — pytest for changed packages (BLOCKS on fail)

### Test mode: diff
Only packages with staged changes are tested. Pre-existing failures in
untouched code will NOT block your commit. If you change pyproject.toml,
Makefile, .gitreins/config.yaml, or a config file, the full suite runs
as a safety net.

### Tasks and evaluation:

```bash
# Create a task with criteria
gitreins task create fix-aggregator "Fix aggregator edge cases" \
  "Empty model list returns graceful error" \
  "Single model response passes through unmodified" \
  "Timeout responses are excluded from aggregation"

# Do the work, then evaluate:
gitreins task start fix-aggregator
# ... implement ...
gitreins task complete fix-aggregator    # triggers LLM evaluation

# Or evaluate standalone:
gitreins judge fix-aggregator
```

### If guards fail:
1. READ the output — the guard tells you exactly what failed and where
2. Fix the issues. Do NOT commit with `--no-verify` unless it's a docs-only
   change or a GitReins self-upgrade.
3. Re-run `gitreins guard` until it passes
4. Then commit

### Never:
- Commit API keys or tokens — secrets guard catches these, and it's correct
- Skip guards with `--no-verify` for code changes
- Push if guards failed (let CI catch it if you must, but fix locally)
- Commit `.gitreins/tasks.yaml` — it's local task state

## Operations — model catalog refresh

`scripts/model_sync.py` scans models.dev for new chat/reasoning models and
proposes catalog additions for `chimera.yaml`. It filters to 13 core
providers, skips embeddings/speech/rerank/legacy families, tracks already-
seen candidates in `.seen_models.json` (`--diff` shows only new finds,
`--score` LLM-rates the top candidates with `DEEPSEEK_API_KEY`, `--output
reports/latest.md` writes a markdown report).

`scripts/model_sync_cron.py` is the scheduled wrapper around it: it runs
`model_sync.py --diff --output reports/latest.md` (and auto-scores when
`DEEPSEEK_API_KEY` is set), using the repo venv interpreter
(`.venv/bin/python` — the cron runner's own interpreter lacks the chimera
deps; see the `_sync_python()` fallback in the script).

**Refresh strategy (intentional — not registered as a system cron):**
catalog refreshes are ad-hoc by design. The provider cache serves stale data
(~hours) safely, and `chimera serve`/the gateway refresh on demand; a missed
or half-configured cron is worse than a manual refresh. To refresh manually:

```bash
cd ~/chimera-v2 && .venv/bin/python scripts/model_sync.py --diff --output reports/latest.md
```

If automated refreshes are ever wanted, register
`scripts/model_sync_cron.py` in the fleet scheduler or a user crontab (it is
cron-shaped and idempotent; the wrapper's stdout is the report).
