# Active Context — Chimera

> **Current as of 2026-10-19** · `chimera-deliberation` **0.2.7**
> (released 2026-09-21) · private GitLab primary, public GitHub mirror.
>
> These files describe the repository AS IT IS NOW. Anything historical lives in
> the *History* section of `progress.md` and is labelled as history.
> **Maintenance rule:** a release that changes the shipped surface, the version,
> or a measured count refreshes the affected file in the same wave. A stale
> `.memory-bank/` is a defect, not a snapshot.

## Where the project is

Chimera is past scaffolding and past its first public release:

- **Version** `0.2.7`, published on PyPI as `chimera-deliberation`.
- **Tests** 2190 collected — re-derive with
  `.venv/bin/python -m pytest --collect-only -q`.
- **Live service** a supervised `chimera.service` on `:8765`; `/health` reports
  the running commit (compare it to `git rev-parse --short HEAD`).
- **Dogfood** runs are recorded under `docs/dogfood/`; the latest is run 24
  (2026-10-15).

Current work is hardening and repair: dogfood rotations, dependency refresh,
documentation-rot fixes, and quality-gate upkeep.

## What we're building

A dispatcher-first deliberation gateway. **One** dispatcher model call reads the
user prompt plus the model catalog and designs the entire deliberation as a DAG —
which models take which scoped subtask, the aggregator/audit stages, and the
merge instructions — then the engine executes it and returns one merged answer
with a full trace.

## Key decisions (all still standing)

- **No SpecLang, no code-generation pipeline** — plain Python package.
- **Config-driven from day one** — `chimera.yaml` carries the catalog, providers,
  formations, timeouts and defaults; no model ids are hardcoded in code.
- **Budget-first defaults** — `chimera.yaml.example` defaults to DeepSeek:
  `deepseek/deepseek-v4-flash` for dispatcher and aggregator,
  `deepseek/deepseek-v4-pro` for the default worker. Premium models are opt-in
  per formation or per request.
- **Category-weighted selection** — every model carries 0–100 scores against
  slash-delimited category paths (e.g.
  `technology_code/code_generation/python`); the selector maps a task onto those
  paths and scores candidates, and `selector.price_sensitivity` (0.0 = quality
  only, 1.0 = cheapest-that-works) trades quality against cost.
- **Credential-aware auto formation** — `auto.restrict_to_credentialed_providers`
  (default `true`) limits the dispatcher's catalog to providers whose
  credentials resolve, so a fresh install cannot burn calls on models it has no
  key for. Named presets and custom DAGs are unaffected.
- **Failure is degraded, not fatal** — one slow or failing worker becomes a
  degraded placeholder recorded in the trace; the deliberation still returns.

## Request-level overrides (exact, current)

`DeliberationOverrides` in `src/chimera/config.py` is the single source of truth.
The API and CLI accept exactly these keys — anything else is not supported:

`allowed_models`, `disallowed_models`, `dispatcher_model`, `aggregator_model`,
`worker_model`, `output_schema`, `stage_models`, `timeout_total_s`,
`timeout_per_stage_s`, `progressive`, `wait_messages`, `trigger`, `max_tokens`.

The merge role is the **aggregator** (`aggregator_model`, plus
`stage_models[stage_id]` for per-stage control). A caller that wants a different
merge model sets `aggregator_model`; there is no separate merge-role key
outside this list.

## Operator state

- **Deploy** `git pull` then `sudo systemctl restart chimera`, and prove it with
  `curl -s localhost:8765/health` showing the new commit plus a passing
  `python scripts/smoke_live.py`. `Restart=always` recovers crashes only — it
  never reloads code after a pull.
- **Config** the live `chimera.yaml` is untracked and gitignored; a fresh clone
  has none and needs `chimera config init`. The repo ships
  `chimera.yaml.example` (minimal, wheel-shipped) and `chimera.yaml.fleet` (full
  operator reference, checkout-only, never wheel-shipped).
- **Blocked models** a provider whose credential fails auth has its models
  recorded in a repo-scoped, gitignored `.chimera/blocked-models.json`
  (`$CHIMERA_BLOCKED_MODELS_PATH` overrides the path).

## Blockers

None.

## Open work

The authoritative queue is `.coding-hermes/board/tasks.jsonl`. This file
deliberately does **not** duplicate a next-steps list: a copied roadmap goes
stale within one tick, which is exactly the failure this file was rewritten to
remove.
