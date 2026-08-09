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
  unit/             — Unit tests
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
