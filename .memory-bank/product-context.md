# Product Context — Chimera

> **Current as of 2026-10-19** · `chimera-deliberation` **0.2.7**

## User experience

1. A caller sends one prompt — through the OpenAI-compatible
   `POST /v1/chat/completions`, the full-control `POST /v1/deliberate`, the
   `chimera` CLI, the `chimera-mcp` tools, or the web UI.
2. The dispatcher analyses the prompt and designs a formation: which model
   handles which scoped subtask, plus the aggregator/audit stages and the merge
   instructions.
3. Workers execute their scoped prompts, in parallel wherever the DAG allows.
4. The aggregator merges the worker outputs using the dispatcher-written
   instructions and returns one answer with a per-stage trace (model, prompt,
   response, tokens, cost, latency).

## Surfaces that ship today

- `POST /v1/chat/completions` — stateless, drop-in OpenAI-compatible. The
  `model` field selects a **formation**, not a catalog model id.
- `POST /v1/deliberate` — formation + request overrides + trace.
- `GET /v1/models` (OpenAI-shaped list plus the catalog map),
  `GET /v1/formations`, `GET /v1/health`, `/v1/health/live`,
  `/v1/health/ready`.
- `chimera` CLI — implicit prompt form and `run`, `formations`, `models`,
  `serve`, `mcp`, `config init`, `--version`, `--quiet`, `--json`,
  `--formation`.
- `chimera-mcp` stdio server exposing `chimera_deliberate`,
  `chimera_formations` and `chimera_models`, plus the `bin/chimera-mcp-hermes`
  and `bin/chimera-mcp-wrapper` shims.
- Web UI at `/web/` — multi-turn sessions (`POST /web/sessions`,
  `POST /web/sessions/{id}/chat`, `GET|DELETE /web/sessions/{id}`), live DAG and
  trace visualisation, and a Server-Sent-Events stream at `GET /web/sse/{id}`
  (replay then live frames). The `/web/*` surface requires the API key whenever
  `auth.enabled: true`.

## Stakeholders

- **Bane / totalwindupflightsystems** — primary user and design owner.
- **Hermes Agent** — drives Chimera stages over MCP; a first-class consumer.
- **Any OpenAI-compatible client** — drop-in replacement for single-model
  calls, so existing code keeps working while gaining a model team.

## Non-goals

Deliberate limits at 0.2.7. Each row names the shipped surface beside the gap, so
a reader never mistakes a boundary for a missing feature:

- **Token streaming from `/v1/chat/completions`** (OpenAI `stream: true`) — the
  compatibility endpoint answers one non-streamed JSON body and rejects
  `stream: true` with HTTP 400 `stream_not_supported` (CH-GAP-030). Live
  streaming *does* ship, on the web session surface `GET /web/sse/{id}`.
- **Conversation state on the `/v1/*` endpoints** — they are stateless by
  design. Multi-turn deliberation *does* ship, under `/web/sessions`, which
  injects prior turns as history.
- **Tool / function-calling passthrough** — no `tools` / `tool_calls`
  translation; a deliberation returns text, optionally validated against a
  caller-supplied `output_schema`.
- **Caching or memoising deliberation answers** — results are never reused
  between requests. The only caches are provider/model metadata (the models.dev
  catalog cache) and config/env resolution.

## Reader impact

An agent or developer picking up work should be able to: pick the right surface
from the list above, use only the override keys in `active-context.md`, and not
re-file a shipped feature as missing (or an intentional limit as a bug).
