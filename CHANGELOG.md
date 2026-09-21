# Changelog

All notable changes to Chimera will be documented in this file.

## [Unreleased]

## [0.2.7] — 2026-09-21

### Fixed

- **A provider that cannot answer inside the probe budget is reported `slow`
  instead of permanently degrading `/v1/health`** (DF-CHIMERA-V2-27). Measured
  live: the `hermes` gateway injects a ~43.6k-token system prompt, so a
  `max_tokens=1` probe took 108.3s against the 10.0s budget while the gateway
  answered `/v1/models` in 0.33s and the same model called directly upstream
  answered in 1.9s — a bare `timeout` verdict made `status` read `degraded`
  forever, which made a REAL hermes outage indistinguishable from the standing
  condition. A probe that never lands now reports `error_class: "slow"` with
  the measured wait (`latency_s`, plus the wait in the `error` text) and is
  named in the new top-level `slow_providers` array; it does NOT degrade
  `status` and is NOT in `unhealthy_providers`, because nothing about that
  provider was measured beyond its latency. Every other failure — connection
  refused, HTTP 5xx, auth, quota — keeps its class and still reads
  `healthy: false` / `degraded` exactly as before. `slow_providers` and
  `probe_skipped_providers` are additive fields, so existing consumers are
  unaffected; the class-aware smoke report prints `slow` and `probe_skipped`
  providers as INFO rather than as a degradation warning.

### Added

- **`providers.<name>.health_probe: false`** (DF-CHIMERA-V2-27) skips the live
  connectivity probe for that provider entirely (no upstream call, no tokens);
  it is reported `probe_skipped`, named in the top-level
  `probe_skipped_providers`, and does not satisfy `/v1/health/ready` — the
  omission stays visible rather than reading as healthy.

## [0.2.6] — 2026-09-17

### Added

- **`chimera --version`** (and `python -m chimera --version`) now report the
  installed version, which the README quickstart documents (DF-CHIMERA-V2-4).

### Fixed

- **An unknown formation is rejected at the user-facing edge** instead of
  silently falling back to `auto`: the CLI and MCP surfaces exit 2 / return an
  error before any provider call (DF-CHIMERA-V2-7), and the `/web` session chat
  surface returns HTTP 422 (DF-CHIMERA-0917-2), matching the REST
  `/v1/deliberate` behaviour (422).
- **Models whose provider credential fails auth are blocked from selection**
  with an actionable remedy instead of surfacing as an opaque provider error
  (DF-CHIMERA-V2-6).
- **`bin/chimera-mcp-hermes` is venv-agnostic** (QA-CHIMERA-V2-12): the wrapper
  execs the repo-local `.venv/bin/chimera-mcp` only when that interpreter is
  live, falls back to a `chimera-mcp` found on `PATH` when the repo venv is
  missing or dead (fresh install), and exits 1 naming both attempted paths when
  neither exists.
- **The drop-in `/v1/chat/completions` 404 explains that the `model` field
  selects a FORMATION**, not a catalog model id (DF-CHIMERA-0911-3).
- **The dogfood run log for 2026-09-16 is indexed**, restoring the docs index
  test at HEAD (DF-CHIMERA-0917-1).

### Changed

- **The live `chimera.yaml` is no longer tracked in the public repo** (the repo
  ships `chimera.yaml.example` only), so fresh clones can run
  `chimera config init` (DF-CHIMERA-0916B-4).
- **Local CI (`act`) pins the runner image and the ruff version** so local runs
  reproduce hosted CI, and the docs state the local-vs-hosted job boundary
  (QA-CHIMERA-V2-7).
- **Every `docs/` file is indexed from the README/docs index**, and that index
  is enforced by a test (CH-GAP-052); the `python -m chimera` module entry point
  is documented (DOC-1).
- **The release gate asserts the README quickstart CLI surface against the
  PUBLISHED pinned wheel** in `release-verify`, so a wheel that cannot run a
  documented command fails CI (DF-CHIMERA-0916B-3).

### Security

- **Private host addresses were scrubbed from published content** and a leak
  guard (with an explicit CIDR allowance) now blocks recurrence (INT-CI-005).

## [0.2.5] — 2026-09-11

### Fixed

- **LiteLLM's stdout debug banners are suppressed on every deliberation path**
  (DF-CHIMERA-0911-1). A real `formation=speed` deliberation on the published
  0.2.4 wheel emitted three ANSI
  `Provider List: https://docs.litellm.ai/docs/providers` lines straight onto
  stdout — i.e. into the MCP JSON-RPC wire — while `formation=simple` stayed
  clean, which is why the 0.2.4 gate (simple only) missed it. Both LiteLLM
  print paths are gated on the process-global `litellm.suppress_debug_info`,
  which defaults to `False` and which Chimera never set:
  `litellm_core_utils/get_llm_provider_logic.py` (the ANSI banner, reached via
  LiteLLM's own internal provider lookups — e.g. OpenRouter's
  `get_supported_openai_params` → `utils.supports_reasoning` — so it fires even
  on a *successful* call) and `litellm_core_utils/exception_mapping_utils.py`
  (the `Give Feedback / Get Help` block printed for every mapped provider
  error).

  `chimera.gateway` — the single module that calls LiteLLM — now sets
  `suppress_debug_info = True` (and `set_verbose = False`) through
  `ensure_litellm_quiet()` immediately before **every** completion, in the
  async path and the sync fallback. That covers MCP, CLI and HTTP-API callers
  without patching site-packages or redirecting process stdout globally, and it
  runs before the exception-mapping path, which executes inside
  `completion()`/`acompletion()`. Regression coverage:
  `tests/test_litellm_stdout_suppression.py` (ordering with an injected litellm
  module, exception-path ordering, and a behavioural test that drives the real
  gateway against an unroutable model and asserts no banner reaches stdout).

### Changed

- **The release probe can drive any formation** (DF-CHIMERA-0911-1):
  `scripts/probe_mcp_stdio.py` now accepts `--formation=NAME` (a single
  probe-owned token that is stripped from the child command, so it can never be
  confused with the server argv) or the `CHIMERA_PROBE_FORMATION` environment
  variable; the default stays `simple`. The release gate verifies **both**
  `simple` and `speed` — the leak was formation-dependent. Offline contract
  tests: `tests/test_probe_mcp_stdio.py`.
- The `litellm>=1.50.0,<1.100` cap stays: it and the suppression above guard
  two *different* regressions (see the corrected 0.2.4 entry).

## [0.2.4] — 2026-09-11

### Fixed

- **First published artifact carrying the CLI/MCP stderr pin** (fix 27f0b35,
  DF-CHIMERA-V2-3): the two-phase `configure_logging(..., force_stderr=True)`
  pin on the CLI path — which stops provider auto-discovery / structlog lines
  from polluting stdout ahead of real output — shipped in-repo after the
  0.2.3 upload, so no published wheel contained it. 0.2.4 is the first PyPI
  release whose `chimera` / `chimera-mcp` entry points are stdout-clean.

- **`litellm` capped below 1.100** (found by the strengthened probe,
  DF-CHIMERA-0911-1): the first fresh-venv run of the probe against the 0.2.4
  wheel failed with 8 non-JSON-RPC stdout lines. `litellm>=1.50.0` let a clean
  install resolve **1.100.1**, which replaced its stderr
  `logging.StreamHandler()` with `LevelRoutingStreamHandler` (routes every
  record *below* WARNING to `sys.stdout`). `force_stderr` only pins chimera's
  own sinks, so the first real `completion()` re-polluted the MCP JSON-RPC
  wire for any consumer — the exact failure the release probe exists to catch.
  The requirement is now `litellm>=1.50.0,<1.100`; regression tests pin both
  the range and the lockfile version.

  **Correction (0.2.5):** this entry originally claimed 1.99.0 was "verified
  stderr-only". That is false, and the 0.2.5 gate proved it: the cap only
  removes the 1.100+ *logging-handler* regression, while 1.99.0 keeps the
  separate, always-on `suppress_debug_info=False` bare-`print()` banner path
  that leaked three ANSI lines onto the MCP stdout wire on `formation=speed`.
  Both guards are needed — the cap **and** the suppression added in 0.2.5.

### Changed

- **Release probe reaches a real deliberation call** (DF-CHIMERA-0911-1):
  `scripts/probe_mcp_stdio.py` now drives its depth call against
  `chimera_deliberate` (deterministic `17 * 23` prompt, formation=simple)
  instead of the catalog-only `chimera_models` call. A handshake/catalog
  call never triggers the lazy LiteLLM import, so the published 0.2.3 wheel
  passed the old probe while still polluting stdout on a real deliberation.
  The probe now fails unless the call returns JSON with a non-empty merged
  answer; offline contract tests live in `tests/test_probe_mcp_stdio.py`.

## [0.2.3] — 2026-09-08

### Added

- **`chimera config init`** (CH-GAP-050): first-run without a config is no
  longer a dead-end raw traceback — the CLI prints a friendly remedy and
  `chimera config init` scaffolds a working `chimera.yaml` from the shipped
  template.
- **`chimera.yaml.example` ships inside the wheel** (CH-GAP-049,
  force-include) so the README Quickstart `cp chimera.yaml.example
  chimera.yaml` works for every pip/pipx consumer.
- **MCP stdio purity** (DF-CHIMERA-0906-2): the `chimera-mcp` entry point
  forces every log sink to stderr, so stdout carries ONLY JSON-RPC frames —
  real MCP clients no longer die on structlog lines before the initialize
  response. Regression-covered by `tests/test_mcp_stdio_purity.py`
  (subprocess handshake against the real console scripts).
- **Durable MCP wrapper** (DF-CHIMERA-V2-1): `bin/chimera-mcp-hermes` execs
  the repo venv binary instead of dead-exec'ing a missing one.

### Fixed

- **README Quickstart is live again for pip consumers** (DF-CHIMERA-0906-1):
  fresh venv + `pip install chimera-deliberation[full]` → `chimera config
  init` → bare `chimera run` with only `DEEPSEEK_API_KEY` returns a merged
  answer.

## [0.2.1] — 2026-08-23

### Fixed

- **Bare install works again** (CH-GAP-026/041): `from chimera import Engine`
  no longer crashes with `ModuleNotFoundError: fastapi` (lazy web imports),
  and the `chimera` / `chimera-mcp` console scripts work on a bare wheel
  install (click/rich/mcp moved into base dependencies).
- **`stream:true` is rejected with HTTP 400 `stream_not_supported`**
  (CH-GAP-030) instead of silently returning a non-stream completion.
- **`max_tokens` is honored** (CH-GAP-031) — no more 3548-token essays when
  `max_tokens:1` is requested.
- **Unknown models return HTTP 404 `model_not_found`** (CH-GAP-027) instead
  of silently substituting another model.
- **Server default port is 8765** (CH-GAP-038).
- **Health endpoints expose the running git commit** (CH-GAP-039) so a
  stale deployment is visible (`/v1/health` → `details.commit`).
- **CI packaging smoke gate** (CH-GAP-041): fresh venv + bare wheel install
  → import + `chimera --help` + `chimera-mcp` initialize handshake.

## [0.1.0] — 2026-06-18

### Added

- **Core engine**: Dynamic DAG deliberation — dispatcher designs formation, workers execute in parallel, aggregator merges
- **Auto formation**: Dispatcher auto-designs custom DAGs based on prompt complexity and model catalog
- **Preset formations**: `simple` (2 workers), `debate` (3 workers), `audit` (worker + reviewer)
- **Custom formations**: Define arbitrary DAG presets in `chimera.yaml`
- **Category-weighted model selection**: Models scored by category with configurable bandwidth offsets
- **Budget-first defaults**: All roles default to budget models; overridable per-request
- **Client-defined custom DAG**: `dag` + `allow_custom_dag` — clients send full DAG definitions
- **Per-stage model overrides**: `stage_models` field forces models per stage
- **Structured output**: `output_schema` with provider-aware `json_schema → json_object → text` negotiation
- **Web UI**: Session-backed multi-turn chat with live Mermaid DAG rendering via SSE
- **MCP server**: 3 tools (`chimera_deliberate`, `chimera_formations`, `chimera_models`)
- **OpenAI-compatible endpoint**: `POST /v1/chat/completions`
- **Resilience**: Circuit breakers, retry with exponential backoff, request queue with backpressure, rate limiting, API key auth
- **Observability**: `structlog` JSON logging, `RequestId`, `StageSpan`, `DeliberationTrace`, optional Langfuse tracing
- **CI/CD**: GitHub Actions (3.11/3.12/3.13 matrix), auto-publish to PyPI on version tags
- **Pre-commit**: GitReins Tier 1 (secrets scan, lint, tests)
- **Packaging**: `pipx install chimera-deliberation[full]`, extras: `[server]`, `[cli]`, `[mcp]`, `[web]`

### Supported Providers

- DeepSeek (V4 Flash, V4 Pro) — budget defaults
- OpenRouter (Claude Sonnet 4, Gemini 2.5 Flash, Kimi K2.7, MiniMax M3)
- Z.AI Coding Plan (GLM-5.2)
- Any OpenAI-compatible provider via LiteLLM
