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

## Chimera-Specific Fields

These extend the OpenAI spec. They are **optional** — omit them and Chimera
defaults to budget-friendly auto-deliberation.

| Field | Type | Default | Description |
|---|---|---|---|
| `model` | `string` | `"auto"` | Formation name: `"auto"`, `"simple"`, `"debate"`, `"audit"`, or a custom preset name |
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

Unknown stage IDs warn (non-fatal). Unknown model names return 400.

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
