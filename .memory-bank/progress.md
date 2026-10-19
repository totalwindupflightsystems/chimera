# Progress — Chimera

> **Current as of 2026-10-19** · `chimera-deliberation` **0.2.7**
>
> Status first, history last. Measurement commands are given so every number
> here can be re-derived instead of trusted.

## Current status

| Field | Value | Re-derive with |
|-------|-------|----------------|
| Version | 0.2.7 (PyPI, released 2026-09-21) | `grep -m1 '^version' pyproject.toml` |
| Tests | 2190 collected | `.venv/bin/python -m pytest --collect-only -q` |
| Suite | green at HEAD (CI: Python 3.11 / 3.12 / 3.13) | `.venv/bin/python -m pytest -x -q` |
| Live service | `chimera.service` on `:8765`, `/health` reports the running commit | `curl -s localhost:8765/health` |
| Dogfood | latest run 24 (2026-10-15), recorded in `docs/dogfood/` | `ls docs/dogfood/` |
| Open work | `.coding-hermes/board/tasks.jsonl` | — |

Any count above that does not match a fresh measurement is a bug in this file:
fix the number, do not re-measure to fit the file.

## Release history

Headlines only; the authoritative log is `CHANGELOG.md`.

| Version | Date | Headline |
|---------|------|----------|
| 0.2.7 | 2026-09-21 | Providers that exceed the probe budget are classed `slow` instead of permanently degrading `/v1/health`; `providers.<name>.health_probe: false` |
| 0.2.6 | 2026-09-17 | `chimera --version`; unknown formation rejected at every edge; auth-failing models blocked from selection |
| 0.2.5 | 2026-09-11 | LiteLLM stdout debug banners suppressed on every deliberation path (MCP stdio wire stays clean) |
| 0.2.4 | 2026-09-11 | First published artifact carrying the CLI/MCP stderr pin |
| 0.2.3 | 2026-09-08 | `chimera config init` — first run without a config is no longer a dead end |
| 0.2.1 | 2026-08-23 | Bare install works again (lazy web imports) |
| 0.1.0 | 2026-06-18 | Core engine: dispatcher-designed DAG, parallel workers, aggregator merge; `auto` formation |

## History (explicitly not current state)

- **2026-06-17** — architecture spec (`specs/architecture.md`) and package
  scaffolding. This is the origin of the repository, kept here so the timeline is
  complete; nothing in this section describes today's architecture.
- **2026-06-18** — 0.1.0 published.

## Validation gate

```bash
.venv/bin/python -m pytest -x -q
```

The repo venv is load-bearing: `AGENTS.md` mandates `.venv/bin/python`, and a
bare `python -m pytest` can resolve a different interpreter with a different
dependency set. Before any commit, also run the guard with the venv first on
PATH:

```bash
PATH="$(git rev-parse --show-toplevel)/.venv/bin:$PATH" gitreins guard
```
