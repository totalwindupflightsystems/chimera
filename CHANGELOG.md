# Changelog

All notable changes to Chimera will be documented in this file.

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
