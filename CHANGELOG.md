# Changelog

All notable changes to Chimera will be documented in this file.

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
