# System Patterns — Chimera

> **Current as of 2026-10-19** · `chimera-deliberation` **0.2.7**
> Verified against `src/chimera/` at HEAD, not carried forward from earlier notes.

## Dispatcher-first architecture

All the planning intelligence lives in the dispatcher. Workers and aggregators
are executors following dispatcher-written instructions. The dispatcher reads the
prompt plus the config's model catalog and designs the whole formation in one
call: stage list, model assignment per stage, each worker's scoped prompt, and
the aggregator's merge instructions.

Consequence a reader must internalise: quality problems are usually *dispatch*
problems (bad stage decomposition, bad model assignment, vague worker prompt),
not worker problems.

## Category-weighted domain routing

Models carry 0–100 scores against slash-delimited category paths
(`technology_code/code_generation/python`,
`complex_reasoning_agency/multi_step_planning/task_decomposition`, …). The
selector maps the task onto those paths, scores candidates, and can trade quality
for cost through `selector.price_sensitivity`. Short-form capability aliases
(`code`, `analysis`, `reasoning`, `design`, `audit`) expand to the hierarchical
paths they stand for, so a model configured the short way still scores on
matching task paths.

## Formations (DAGs, not pipelines)

A formation is a DAG, not a fixed chain:

- `auto` — the dispatcher designs the DAG itself (the CLI default).
- named presets — `simple` (N workers + aggregator), `debate` (multiple
  aggregators, `merge: best_of_n`), `audit` (post-hoc auditor stage before the
  aggregator), plus whatever an operator declares in `chimera.yaml`.
- request-level `stage_models` / `worker_model` / `dispatcher_model` /
  `aggregator_model` overrides layer on top of a preset.

An unknown formation name is an error at every edge (CLI exit 2, REST 422), never
a silent fallback to `auto`.

## Provider gateway

One uniform interface over providers: LiteLLM for protocol translation, plus a
generic OpenAI-compatible `base_url` branch for anything else — including a
**local CLI proxy** such as `claude-code-router`, `one-api` or `new-api` fronting
vendors on loopback (`docs/CLI_PROXY.md`). Credentials resolve per provider from
env/`.env`; a provider whose credential fails auth has its models blocked in a
repo-scoped `.chimera/blocked-models.json` instead of failing opaquely on every
call.

## Resilience patterns

- **Per-stage timeout ladder** — code default, admin ceiling in
  `timeout` config, per-request `X-Chimera-Timeout` that cannot exceed the
  ceiling.
- **Degraded stage, not a failed deliberation** — a stage that times out or
  errors becomes a degraded placeholder recorded in the trace; the rest of the
  DAG continues and the caller can see which stages degraded.
- **Retry + per-provider circuit breaker** (`circuit_breaker` config) and an
  in-memory token-bucket rate limiter (`rate_limit` config).
- **Health with named error classes** — `/v1/health` distinguishes a provider
  that is unreachable / unauthorised / out of quota from one that simply exceeds
  the probe budget (`slow`), which does not degrade status. `health_probe: false`
  skips a probe and reports `probe_skipped` rather than reading healthy.

## Sessions and streaming

`/v1/*` is stateless. Multi-turn state lives in the web session layer
(`src/chimera/web/session.py`): a session accumulates turns, injects prior turns
as history into the next deliberation, and exposes an SSE stream
(`GET /web/sse/{id}`) that replays then follows live events for the DAG/trace
visualisation. OpenAI-compatible `stream: true` on `/v1/chat/completions` is
explicitly rejected (400) — the two streaming stories are separate on purpose.

## Observability

structlog JSON for logs (stdout for the CLI, forcibly pinned to stderr for the
MCP stdio transport so the JSON-RPC wire can never be polluted), a per-stage
trace in every response (model, prompt, response, tokens, cost, latency), and
optional Langfuse tracing when configured and importable.

## Config lifecycle

`chimera.yaml` is the single config surface, loaded once at startup with
`${ENV_VAR}` references resolved from the environment or a `.env` beside the
config. Live config is local-only and gitignored; the repo tracks
`chimera.yaml.example` (minimal, wheel-shipped) and `chimera.yaml.fleet` (full
operator reference, never shipped).
