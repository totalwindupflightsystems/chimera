# OpenAI-Compatible API

Chimera implements the OpenAI chat completions API. Drop it in as a replacement
— same endpoint, same successful request/response format, plus Chimera's
multi-model features. The request body is OpenAI-shaped and `model` is
**optional** (it selects a *formation*, and omitting it selects `"auto"`), so a
client that sends only `messages` works.

Error bodies are **not** uniformly OpenAI-shaped. Only three responses carry a
top-level OpenAI `error` object: the 404 `model_not_found`, the 400
`stream_not_supported`, and the 502 `upstream_error`. Every other failure is
rendered the way FastAPI renders it — a `detail` value (an array for schema
validation, a plain string, or an `{"error": …, "message": …}` object for
401/429). The per-status table is in
[Errors and Status Codes](#errors-and-status-codes).

## Endpoint

```
POST /v1/chat/completions
```

Base URL: `http://localhost:8765` (default, configurable in `chimera.yaml`)

## Basic Usage

The minimal documented request carries only `messages` — omit `model` and
Chimera deliberates with the `"auto"` formation:

```bash
curl http://localhost:8765/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "Rank Rust, Go, Python for HFT systems"}
    ]
  }'
```

`"model": "auto"` is the same request written explicitly; it is the only value
that may be omitted, and the response always echoes the resolved formation in
its `model` field (`"auto"` either way).

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

## Usage Reporting

The `usage` block describes the **entire deliberation**, not one provider's
call. A single `/v1/chat/completions` request fans out to the dispatcher plus
every worker, judge, and aggregator stage — each an independent upstream
model call — and the block is the aggregate over all of them:

| Field | Meaning |
|---|---|
| `prompt_tokens` | Sum of the **input** tokens of the dispatch stage plus every stage span (workers, judges, the aggregator) |
| `completion_tokens` | Sum of the **output** tokens of those same spans |
| `total_tokens` | `prompt_tokens + completion_tokens` |

So a six-word user prompt can report thousands of `prompt_tokens`: the
dispatcher's design call carries the whole model catalog (that is what makes
per-stage subtask prompting work), and it is counted like every other call.
Costing a request from `usage` therefore prices every upstream call the
deliberation made. It is **not** a single model's usage and is not comparable
field-for-field with a plain OpenAI response, where `prompt_tokens` is just
your prompt plus context.

Per-stage numbers — model, input/output tokens, latency, cost, and the full
prompt/response of each span — are on `POST /v1/deliberate`'s `trace`.

## Chimera-Specific Fields

These extend the OpenAI spec. They are **optional** — omit them and Chimera
defaults to budget-friendly auto-deliberation.

| Field | Type | Default | Description |
|---|---|---|---|
| `model` | `string` | `"auto"` | **Optional** — omitted entirely is the same as `"auto"`. An explicitly empty string (`""`) is a schema validation error (422, see [Invalid request body](#invalid-request-body--http-422-fastapi-validation-not-openai-shaped)). **Formation selector** — `"auto"`, a preset (`"simple"`, `"debate"`, `"audit"`, `"speed"`), or `"custom"` (with a DAG). It is **not** a model ID: a key from `GET /v1/models` sent here returns HTTP 404 `model_not_found` (see [Errors](#errors-and-status-codes)). To pin a specific model, keep `model: "auto"` and use `worker_model` / `stage_models` / `allowed_models` below |
| `dispatcher_model` | `string` | config | Override the dispatcher model |
| `aggregator_model` | `string` | config | Override the aggregator model |
| `worker_model` | `string` | config | Override ALL worker models |
| `allowed_models` | `string[]` | all | Restrict to these models only |
| `disallowed_models` | `string[]` | none | Exclude these models |
| `stage_models` | `object` | — | Per-stage model overrides: `{"worker_1": "zai-coding-plan/glm-5.2"}` |
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

Chimera passes the schema through to the aggregator **when the aggregator's
provider supports it**. If it does not, the format is negotiated down (or
stripped) before the call rather than retried afterwards — see below for exactly
what goes on the wire, and for the log events that record the loss.

### When the format cannot be honored (and the log events that say so)

Format support is decided **before** the call, per resolved provider, from a
capability table (`chimera.gateway.negotiate_response_format`) — not by
trial-and-error retries:

| Provider capability | You asked for | What is actually sent |
|---|---|---|
| `json_schema` — `openai`, `anthropic`, `google`, `zai` | anything | passed through unchanged |
| `json_object` — `moonshot` | `json_schema` | downgraded to `{"type": "json_object"}` (schema dropped) |
| `json_object` | `json_object` | passed through unchanged |
| none — any provider **not** in the table (e.g. `deepseek`, `openrouter`, a `base_url` provider) | any format | **removed** — the call goes out as plain text |

Two structured log events (INFO, on the `chimera.gateway` logger) mark the
lossy paths, and each one means the response is **less constrained than you
asked for**:

- `gateway_format_downgrade` — fields `from_format=json_schema`,
  `to_format=json_object`, `provider`. The provider can return generic JSON but
  not a schema, so your schema is discarded. Expect JSON; do not expect your
  shape or `required` fields.
- `gateway_format_removed` — fields `requested_type`, `provider`. The resolved
  provider is not in the capability table, so the `response_format` field is
  stripped entirely and the model answers as plain text.

What to do as a caller: either pin a schema-capable provider for the stage
(`aggregator_model` / `stage_models`, or `worker_model` for every worker) or
treat a logged event as a signal to validate and repair the JSON in your own
code. Chimera does not retry with a weaker format after the fact: the
negotiation happens once, before the call. Note the table keys on the
**resolved** provider — a model routed through a generic provider (including
the automatic Anthropic→OpenRouter credential fallback, which logs
`gateway_anthropic_fallback`) loses the requested format, and an
`openrouter`-facing aggregator is therefore a common source of
`gateway_format_removed` on real requests.

## Custom DAG: Full Control

```json
{
  "model": "custom",
  "allow_custom_dag": true,
  "dag": {
    "stages": [
      {"id": "researcher", "kind": "worker", "model": "anthropic/claude-sonnet-4.6"},
      {"id": "critic", "kind": "aggregator", "model": "zai-coding-plan/glm-5.2", "depends_on": ["researcher"]},
      {"id": "writer", "kind": "worker", "model": "deepseek/deepseek-v4-pro", "depends_on": ["critic"]},
      {"id": "editor", "kind": "aggregator", "model": "anthropic/claude-sonnet-4.6", "depends_on": ["writer"]}
    ],
    "edges": [["researcher","critic"], ["critic","writer"], ["writer","editor"]]
  },
  "messages": [{"role": "user", "content": "Write a technical blog post about WebAssembly"}]
}
```

The dispatcher writes custom prompts for each stage but uses YOUR exact structure.
Sending `dag` without `allow_custom_dag: true` is rejected with HTTP 400 —
`{"detail": "Custom DAG requires allow_custom_dag=true"}` (a `detail` string,
not the OpenAI-style `error` object).

## Per-Stage Model Selection

```json
{
  "model": "auto",
  "stage_models": {
    "worker_1": "zai-coding-plan/glm-5.2",
    "aggregator": "anthropic/claude-sonnet-4.6"
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
        "allowed_models": ["deepseek/deepseek-v4-pro", "zai-coding-plan/glm-5.2"],
        "stage_models": {"aggregator": "anthropic/claude-sonnet-4.6"}
    }
)

print(response.choices[0].message.content)
```

The endpoint accepts a body without `model`, but the official SDK's own
`create()` signature requires the argument, so SDK callers keep passing
`model="auto"` — omitting it is a raw-HTTP convenience (a hand-rolled
`curl`/`httpx` client that does not know about formations).

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
| `GET` | `/v1/models` | OpenAI `ListModelsResponse` envelope + chimera `catalog` map |
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

An **OpenAI `ListModelsResponse`**, so `client.models.list()` works through the
official SDK. The per-model chimera payload is unchanged; it is served twice —
once per entry in the spec-shaped `data[]`, and once in the `catalog` map that
is a **chimera extension** (the pre-envelope response shape, kept so keyed
lookups by model id keep working).

```json
{
  "object": "list",
  "data": [
    {
      "id": "deepseek/deepseek-v4-pro",
      "object": "model",
      "created": 0,
      "owned_by": "deepseek",
      "categories": {"code": 95, "analysis": 85, "reasoning": 80, "design": 40, "audit": 60},
      "cost_tier": "budget",
      "provider": "deepseek",
      "enabled": true,
      "cost_per_1k_input": 0.00055,
      "cost_per_1k_output": 0.00219
    }
  ],
  "catalog": {
    "deepseek/deepseek-v4-pro": {
      "categories": {"code": 95, "analysis": 85, "reasoning": 80, "design": 40, "audit": 60},
      "cost_tier": "budget",
      "provider": "deepseek",
      "enabled": true,
      "cost_per_1k_input": 0.00055,
      "cost_per_1k_output": 0.00219
    }
  }
}
```

Field semantics:

| Field | Type | Meaning |
|---|---|---|
| `id` | `string` | Catalog model id — the same key `catalog` uses |
| `object` | `string` | Always `"model"` (OpenAI object type) |
| `created` | `int` | Always `0`: the catalog carries no per-model creation time, so a real epoch value is not invented |
| `owned_by` | `string` | The model's configured provider (mirrors `provider`) |
| `categories` | `object` | Weighted category scores, **percent 0–100** (see the `GET /v1/models` catalog columns) |
| `cost_tier` | `string` | `budget` / `standard` / `premium` |
| `provider` | `string` | Provider key from `chimera.yaml` |
| `enabled` | `bool` | Whether the catalog entry is selectable |
| `cost_per_1k_*` | `float \| null` | Explicit rate when the entry declares one, else `null` (the tier default is applied at billing time — this route reports the configured value, not the derived one) |

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8765/v1", api_key="not-needed")

page = client.models.list()
print(len(page.data), page.data[0].id)   # -> 42 deepseek/deepseek-v4-pro

# Chimera extension: the keyed catalog map, same payloads as data[].
import httpx
catalog = httpx.get("http://localhost:8765/v1/models").json()["catalog"]
```

The route is keyless (see [docs/SECURITY.md](SECURITY.md) for the open-endpoint
list) and stays that way.

**Not implemented** — the deviation is deliberate; these are unauthenticated,
served as-is, and a caller should not expect OpenAI semantics from them:

- `GET /v1/models/{model}` (`client.models.retrieve(...)`) — **404**. Read the
  entry out of `data[]` / `catalog` instead.
- Pagination (`limit` / `after` query parameters) — ignored. The catalog is
  small and returned in full.
- `GET /v1/models` is **read-only discovery**: it lists what `chimera.yaml`
  configures. It does not imply every listed model is reachable — unused
  credentials for a provider surface at call time (see
  [Errors and Status Codes](#errors-and-status-codes)).
- Passing a listed `id` as the top-level `model` on
  `/v1/chat/completions` is still a 404: `model` selects a **formation**, not
  a catalog model — see
  [Forcing a specific catalog model from the OpenAI SDK](#forcing-a-specific-catalog-model-from-the-openai-sdk).

### `/v1/formations`

```json
{
  "auto": {"mode": "auto"},
  "simple": {"workers": 2, "aggregator": "default"},
  "debate": {"workers": 3, "aggregators": ["default", "anthropic/claude-sonnet-4.6"], "merge": "best_of_n"}
}
```

## Errors and Status Codes

Chimera is OpenAI-compatible in its request and response *shape*, not in every
error body, and the bodies are **not** uniform. Every status this endpoint can
emit, with the body it actually returns:

| Status | Body shape | Cause |
|---|---|---|
| 400 | OpenAI `error` (code `stream_not_supported`) | `"stream": true` — see [Streaming](#streaming) |
| 400 | FastAPI `detail` **string** | `dag` sent without `allow_custom_dag: true` |
| 400 | FastAPI `detail` **string** | Unknown catalog model in `worker_model` / `aggregator_model` / `stage_models` |
| 401 | FastAPI `detail` **object** — `{"error": "unauthorized", "message": …}` | Missing/invalid API key, when auth is enabled |
| 404 | OpenAI `error` (code `model_not_found`) | `model` is not a formation — see below |
| 422 | FastAPI `detail` **array** | Request body failed schema validation — see below |
| 429 | FastAPI `detail` **object** — `{"error": "rate_limited", "message": …}` + `Retry-After` | Rate limit exhausted for the key |
| 502 | JSON body with an `error` object (`upstream_error` + `request_id`) | Deliberation produced no usable answer |
| 503 | FastAPI `detail` **string** + `Retry-After: 5` | Request queue full |

Only three of those bodies are OpenAI-shaped — the 400 `stream_not_supported`,
the 404 `model_not_found`, and the 502 `upstream_error`. Everything else is
FastAPI's own error rendering (`detail`), so a client that only understands
`{"error": {...}}` will misread most failures. The two `detail` cases with their
own subsections follow; the remaining bodies are given verbatim below.

### Invalid request body → HTTP 422 (FastAPI validation, NOT OpenAI-shaped)

The request *schema* is enforced before any handler runs, and its failures are
returned by FastAPI exactly as FastAPI renders them: a `detail` array of
per-field errors (Pydantic's `loc` / `msg` / `type` / `input`). There is **no**
`error` object, no `type` / `param` / `code` keys. `messages` is required and
must be a non-empty list; `model` is optional, **but must be non-empty when
present** — `"model": ""` lands here instead of on the `"auto"` default:

```json
{
  "detail": [
    {
      "type": "string_too_short",
      "loc": ["body", "model"],
      "msg": "String should have at least 1 character",
      "input": "",
      "ctx": {"min_length": 1}
    }
  ]
}
```

Same shape, other members of this class: `{}` (no `messages` at all) →
`loc: ["body", "messages"]` with `"type": "missing"`; `{"messages": []}` →
`loc: ["body", "messages"]` with `"type": "too_short"`. An OpenAI SDK client
maps the status to a distinct 4xx error type of its own, so a client that
parses the body as an OpenAI `error` object must handle this shape too — it is
this endpoint's one non-OpenAI error surface, and it is deliberate: the schema
lives in the OpenAPI document, so `/openapi.json` (and `/docs`) is the
authoritative contract for rejected request bodies.

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

### Other status codes — the bodies verbatim

| Status | When | Body |
|---|---|---|
| 400 | `"stream": true` | OpenAI `error`, `code: "stream_not_supported"` — see [Streaming](#streaming) |
| 400 | `dag` without `allow_custom_dag: true` | `{"detail": "Custom DAG requires allow_custom_dag=true"}` |
| 400 | unknown model in an override field | `{"detail": "Unknown model/formation: …"}` — see [above](#unknown-model-name-inside-an-override-field--http-400) |
| 401 | auth enabled, missing/invalid key | `{"detail": {"error": "unauthorized", "message": "…"}}` |
| 422 | body failed schema validation | `{"detail": [ … ]}` — see [Invalid request body](#invalid-request-body--http-422-fastapi-validation-not-openai-shaped) |
| 429 | rate limit exhausted for the key | `{"detail": {"error": "rate_limited", "message": "…"}}` + `Retry-After` |
| 502 | deliberation produced no usable answer | `{"error": {"message": "…", "type": "upstream_error", "request_id": "…"}}` |
| 503 | request queue full | `{"detail": "Server busy — queue full. Retry later."}` + `Retry-After: 5` |

Note the 401 and 429 shape: `error` and `message` are nested **inside**
`detail`, they are not the top-level OpenAI `error` object. Only the `stream`
400, the 404 `model_not_found`, and the 502 `upstream_error` carry that
top-level object — and the 502's `type` is `upstream_error`, which OpenAI does
not define. Dispatch on the status code first; treat `body.error` as
OpenAI-shaped only for those three.
