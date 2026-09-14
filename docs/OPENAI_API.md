# OpenAI-Compatible API

Chimera implements the OpenAI chat completions API. Drop it in as a replacement
— same endpoint, same request/response format, plus Chimera's multi-model features.

## Endpoint

```
POST /v1/chat/completions
```

Base URL: `http://localhost:8765` (default, configurable in `chimera.yaml`)

## Basic Usage

```bash
curl http://localhost:8765/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "auto",
    "messages": [
      {"role": "user", "content": "Rank Rust, Go, Python for HFT systems"}
    ]
  }'
```

Response:

```json
{
  "id": "chatcmpl-a71b3f2c1234abcd",
  "object": "chat.completion",
  "created": 1781700000,
  "model": "auto",
  "choices": [{
    "index": 0,
    "message": {
      "role": "assistant",
      "content": "1. Rust — zero-cost abstractions, no GC, deterministic latency...\n2. Go — fast compilation, goroutines, but GC pauses...\n3. Python — slowest, GIL bottleneck, not suitable for HFT..."
    },
    "finish_reason": "stop"
  }],
  "usage": {
    "prompt_tokens": 800,
    "completion_tokens": 420,
    "total_tokens": 1220
  }
}
```

## Streaming

Streaming is **not supported**. Chimera deliberates synchronously and returns
the complete answer in a single JSON body. An OpenAI-compatible client that
sends `"stream": true` will not receive SSE chunks.

To fail loudly instead of silently ignoring the flag, the server rejects
`"stream": true` with HTTP 400 and an OpenAI-style error naming the field:

```json
{
  "error": {
    "message": "Streaming is not supported by this server. Omit `stream` or set it to false.",
    "type": "invalid_request_error",
    "param": "stream",
    "code": "stream_not_supported"
  }
}
```

Clients that send `"stream": false` or omit the field receive the normal
synchronous `chat.completion` response.

## Token Limits

`max_tokens` is **honored** — it caps the output of every worker and
aggregator model call in the deliberation pipeline, so a drop-in client
bounding cost with `max_tokens` gets a real bound instead of a silent no-op.
`max_completion_tokens` is accepted as its OpenAI alias and wins when both are
sent. The dispatcher's internal design call is small and structured and is not
capped.

```bash
curl http://localhost:8765/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "auto",
    "messages": [{"role": "user", "content": "Write a 10-page essay"}],
    "max_tokens": 100
  }'
```

The following standard OpenAI fields are accepted for drop-in compatibility
but are **documented no-ops** (never errors, never silently misapplied):

| Field | Status |
|---|---|
| `n` | Accepted; `n > 1` is unsupported — the response always contains a single `chat.completion` choice |
| `top_p` | Accepted; ignored — sampling temperature is fixed per stage |

## Chimera-Specific Fields

These extend the OpenAI spec. They are **optional** — omit them and Chimera
defaults to budget-friendly auto-deliberation.

| Field | Type | Default | Description |
|---|---|---|---|
| `model` | `string` | `"auto"` | **Formation selector** — `"auto"`, a preset (`"simple"`, `"debate"`, `"audit"`, `"speed"`), or `"custom"` (with a DAG). It is **not** a model ID: a key from `GET /v1/models` sent here returns HTTP 404 `model_not_found` (see [Errors](#errors-and-status-codes)). To pin a specific model, keep `model: "auto"` and use `worker_model` / `stage_models` / `allowed_models` below |
| `dispatcher_model` | `string` | config | Override the dispatcher model |
| `aggregator_model` | `string` | config | Override the aggregator model |
| `worker_model` | `string` | config | Override ALL worker models |
| `allowed_models` | `string[]` | all | Restrict to these models only |
| `disallowed_models` | `string[]` | none | Exclude these models |
| `stage_models` | `object` | — | Per-stage model overrides: `{"worker_1": "z-ai/glm-5.2"}` |
| `dag` | `object` | — | Client-defined DAG (requires `allow_custom_dag: true`) |
| `allow_custom_dag` | `bool` | `false` | Must be `true` for `dag` to be accepted |
| `response_format` | `object` | — | OpenAI-compatible structured output |

## Structured Output

```bash
curl http://localhost:8765/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "auto",
    "messages": [{"role": "user", "content": "Compare the top 3 database choices"}],
    "response_format": {
      "type": "json_schema",
      "json_schema": {
        "name": "comparison",
        "strict": true,
        "schema": {
          "type": "object",
          "properties": {
            "ranking": {"type": "array", "items": {"type": "string"}},
            "summary": {"type": "string"}
          },
          "required": ["ranking", "summary"]
        }
      }
    }
  }'
```

Chimera passes the schema through to the aggregator. If the aggregator model doesn't
support `json_schema` (e.g. DeepSeek), Chimera automatically retries with
`json_object`, then plain text as a last resort.

## Custom DAG: Full Control

```json
{
  "model": "custom",
  "allow_custom_dag": true,
  "dag": {
    "stages": [
      {"id": "researcher", "kind": "worker", "model": "openrouter/anthropic/claude-sonnet-4"},
      {"id": "critic", "kind": "aggregator", "model": "z-ai/glm-5.2", "depends_on": ["researcher"]},
      {"id": "writer", "kind": "worker", "model": "deepseek/deepseek-v4-pro", "depends_on": ["critic"]},
      {"id": "editor", "kind": "aggregator", "model": "openrouter/anthropic/claude-sonnet-4", "depends_on": ["writer"]}
    ],
    "edges": [["researcher","critic"], ["critic","writer"], ["writer","editor"]]
  },
  "messages": [{"role": "user", "content": "Write a technical blog post about WebAssembly"}]
}
```

The dispatcher writes custom prompts for each stage but uses YOUR exact structure.

## Per-Stage Model Selection

```json
{
  "model": "auto",
  "stage_models": {
    "worker_1": "z-ai/glm-5.2",
    "aggregator": "openrouter/anthropic/claude-sonnet-4"
  },
  "messages": [{"role": "user", "content": "..."}]
}
```

Unknown stage IDs warn (non-fatal): the override is skipped and the stage
keeps its dispatched model, so the request still returns 200. An unknown
**model name** inside `stage_models` (or `worker_model` / `aggregator_model`)
*is* validated against the catalog and returns HTTP 400 — see
[Errors and Status Codes](#errors-and-status-codes).

## Model Restriction

```json
{
  "model": "auto",
  "allowed_models": ["deepseek/deepseek-v4-pro", "deepseek/deepseek-v4-flash"],
  "messages": [{"role": "user", "content": "..."}]
}
```

Limits the dispatcher to budget models only.

## SDK Usage

Any OpenAI SDK works — just change `base_url`:

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8765/v1",
    api_key="not-needed"
)

response = client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "Explain quantum computing"}],
    # Chimera extras via extra_body:
    extra_body={
        "allowed_models": ["deepseek/deepseek-v4-pro", "z-ai/glm-5.2"],
        "stage_models": {"aggregator": "openrouter/anthropic/claude-sonnet-4"}
    }
)

print(response.choices[0].message.content)
```

### Forcing a specific catalog model from the OpenAI SDK

`model=` is a **formation selector**, so passing a catalog ID from
`GET /v1/models` there raises a 404 (the SDK surfaces it as
`openai.NotFoundError`). Force the model through `extra_body` instead —
`model` stays `"auto"` and the override fields carry the ID:

```python
# Same model for every worker in the deliberation:
response = client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "Explain quantum computing"}],
    extra_body={"worker_model": "deepseek/deepseek-v4-flash"},
)

# Or per stage / restricted pool — see the field table above for the full set:
response = client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "Explain quantum computing"}],
    extra_body={
        "stage_models": {"worker_1": "deepseek/deepseek-v4-pro"},
        "allowed_models": ["deepseek/deepseek-v4-pro", "deepseek/deepseek-v4-flash"],
    },
)
```

`worker_model`, `stage_models`, and `allowed_models` are the supported
specific-model controls. On `/v1/deliberate` the same overrides are plain
top-level request fields (see [/v1/deliberate](#v1deliberate) below) instead
of `extra_body` entries.

## Full API Reference

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/v1/chat/completions` | OpenAI-compatible deliberation |
| `POST` | `/v1/deliberate` | Full control (formation, overrides, trace) |
| `GET` | `/v1/models` | Model catalog with category weights |
| `GET` | `/v1/formations` | Available formation presets |
| `GET` | `/v1/health` | Health check |
| `GET` | `/docs` | OpenAPI/Swagger UI |
| `GET` | `/openapi.json` | OpenAPI spec |

### `/v1/deliberate`

```bash
curl -X POST http://localhost:8765/v1/deliberate \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "...",
    "formation": "auto",
    "allowed_models": ["deepseek/deepseek-v4-pro"],
    "output_schema": {"type": "object", "properties": {"answer": {"type": "string"}}}
  }'
```

Response includes full trace with per-stage tokens, latency, cost, model selection,
and all prompts/responses.

### `/v1/models`

```json
{
  "deepseek/deepseek-v4-pro": {
    "categories": {"code": 0.95, "analysis": 0.85, "reasoning": 0.80, "design": 0.40, "audit": 0.60},
    "cost_tier": "budget",
    "provider": "deepseek"
  },
  "z-ai/glm-5.2": {
    "categories": {"code": 0.92, "analysis": 0.90, "reasoning": 0.95, "design": 0.85, "audit": 0.88},
    "cost_tier": "premium",
    "provider": "zai"
  }
}
```

### `/v1/formations`

```json
{
  "auto": {"mode": "auto"},
  "simple": {"workers": 2, "aggregator": "default"},
  "debate": {"workers": 3, "aggregators": ["default", "openrouter/anthropic/claude-sonnet-4"], "merge": "best_of_n"}
}
```

## Errors and Status Codes

Chimera distinguishes **which** field carried the bad value — the top-level
`model` is a formation selector, while the override fields name catalog
models — so the two failures have different status codes and body shapes.

### Top-level `model` is not a formation → HTTP 404

A `model` value that is not `"auto"`, a configured formation preset, or
`"custom"` (with `allow_custom_dag` + a `dag`) is a hard 404 with the
OpenAI-style error object. **A valid `GET /v1/models` catalog ID lands here
too** — the catalog is not addressable through `model`:

```json
{
  "error": {
    "message": "The model `deepseek/deepseek-v4-flash` does not exist. `model` selects a FORMATION (a deliberation preset), not a catalog model ID — use GET /v1/formations for the valid names, or GET /v1/models for the catalog. Valid values: 'auto', a formation preset, or 'custom' with a DAG via allow_custom_dag. To force a specific catalog model, send model='auto' with one of the Chimera override fields: `worker_model` (every worker), `stage_models` (per stage), or `allowed_models` (restrict the pool) — OpenAI SDK callers pass these through extra_body. See docs/OPENAI_API.md.",
    "type": "invalid_request_error",
    "param": "model",
    "code": "model_not_found"
  }
}
```

This is a deliberate contract (CH-GAP-027): an unknown `model` is never
silently substituted, because a silent fall back to `auto` would return a
200 answer from a model the caller did not ask for. Nothing is dispatched and
nothing is billed. Valid formation requests are unaffected.

### Unknown model name inside an override field → HTTP 400

`worker_model`, `aggregator_model`, and `stage_models` values *are* validated
against the catalog (`GET /v1/models`). An unknown name there returns HTTP
400 carrying FastAPI's validation body (note: `detail`, **not** the
OpenAI-style `error` object):

```json
{"detail": "Unknown model/formation: worker_model references unknown model 'bogus/nonexistent-model-xyz'"}
```

Two asymmetric cases are worth knowing:

- `stage_models` with an unknown **stage id** (rather than an unknown model)
  only logs a warning; the request proceeds with the dispatched model and
  returns 200.
- `allowed_models` entries and `dispatcher_model` are **not** catalog-validated
  on this path — `allowed_models` remaps worker stages to its first entry, and
  `dispatcher_model` is passed through to the dispatcher. A typo there is not
  rejected up front; it surfaces as an upstream provider error (or as a
  worker-failure trace) rather than as a 400.

### Other status codes

| Status | `code` | Cause |
|---|---|---|
| 400 | `stream_not_supported` | `"stream": true` — see [Streaming](#streaming) |
| 401 | — | Missing/invalid API key (when auth is enabled) |
| 503 | — | Request queue full (`Retry-After` header set) |
| 502 | — | Deliberation produced no usable answer (upstream failures) |
