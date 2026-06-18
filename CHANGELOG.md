# Changelog

All notable changes to Chimera will be documented in this file.

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
