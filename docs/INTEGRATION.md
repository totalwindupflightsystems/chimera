# Integrating Chimera Into Your Application

Chimera is a dynamic multi-model deliberation gateway: one API call dispatches
your prompt to a hand-picked team of LLMs and an aggregator merges their
outputs into a single answer. This guide covers everything a developer needs to
wire Chimera into an existing application: architecture, deployment, client
examples (curl and OpenAI SDKs), authentication, and health/error handling.

Companion guides:

- [CONFIG.md](CONFIG.md) — full `chimera.yaml` configuration reference
- [OPENAI_API.md](OPENAI_API.md) — OpenAI-compatible endpoint contract
- [USAGE.md](USAGE.md) — CLI, REST API, MCP, Python SDK patterns
- [SECURITY.md](SECURITY.md) — security model and credential handling

## 1. Architecture Overview

Chimera is a single Python process (FastAPI + LiteLLM) that acts as an
LLM-orchestration gateway between your application and the model providers.

```
┌──────────────┐   HTTP/JSON   ┌─────────────────────────────┐
│ Your App     │ ────────────▶ │  Chimera (chimera serve)     │
│ (SDK / curl) │ ◀──────────── │  ┌─────────┐   ┌──────────┐ │
└──────────────┘               │  │Engine   │   │Web UI    │ │
                               │  │  ├─ Dispatcher  (1 LLM call designs the DAG) │
                               │  │  ├─ Workers     (parallel, domain-scoped)    │
                               │  │  └─ Aggregator  (merges with merge rules)    │
                               │  └───────────────────────────────────┘          │
                               │  provider keys: DEEPSEEK_API_KEY, OPENROUTER_API_KEY, ... │
                               └─────────────────────────────────────────────────────┘
                                            │
                                   ┌────────▼────────┐
                                   │ Model providers │
                                   │ (DeepSeek,     │
                                   │  OpenRouter,   │
                                   │  Z.AI, ...)    │
                                   └─────────────────┘
```

Request lifecycle:

1. Your app sends one prompt to `POST /v1/chat/completions` (or `/v1/deliberate`).
2. The **dispatcher** (one model call) designs the deliberation: picks models by
   category weights, writes a custom subtask per worker, and writes the merge
   instructions for the aggregator.
3. **Workers** run in parallel, each scoped to their subtask.
4. The **aggregator** merges worker outputs using the dispatcher's instructions.
5. Chimera returns the final answer plus a full trace (per-stage tokens,
   latency, cost, model selection).

Formations (presets): `auto` (default), `simple` (2 workers), `debate`
(3 workers + merge), `audit`, or a custom DAG you define per request.

### State model — important for scaling

Chimera keeps **in-memory** rate-limit buckets and circuit-breaker state per
process. This is fine for a single instance. If you run multiple Chimera
replicas behind a load balancer, rate limiting and circuit state are per-replica
— size `rate_limit.requests_per_minute` accordingly (e.g. multiply by the
number of replicas) or accept per-replica limits.

## 2. Installation

```bash
pip install chimera-deliberation[full]   # CLI + server in a venv
pipx install chimera-deliberation[full]  # same, isolated
pip install chimera-deliberation[server] # API server only
```

Configure:

```bash
cp chimera.yaml.example chimera.yaml
# add provider API keys — at minimum DEEPSEEK_API_KEY
# (see the api_keys / providers sections of CONFIG.md)
```

Start the server:

```bash
chimera serve                      # binds host/port from chimera.yaml
CHIMERA_HOST=0.0.0.0 CHIMERA_PORT=8765 chimera serve   # env overrides
```

Default server settings (`chimera.yaml`):

```yaml
server:
  host: 0.0.0.0
  port: 8765
```

Available endpoints once running:

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/v1/chat/completions` | OpenAI-compatible deliberation (drop-in) |
| `POST` | `/v1/deliberate` | Full control: formation, overrides, trace |
| `GET` | `/v1/models` | Model catalog with category weights |
| `GET` | `/v1/formations` | Available formation presets |
| `GET` | `/v1/health` | Health check (healthy / degraded / unhealthy) |
| `GET` | `/v1/health/ready` | Readiness probe (provider connectivity) |
| `GET` | `/v1/health/live` | Liveness probe (process alive) |
| `GET` | `/docs` | OpenAPI/Swagger UI |
| `GET` | `/openapi.json` | Machine-readable OpenAPI spec |
| `GET` | `/web/` | Web UI with live DAG visualization |

## 3. Authentication (CHIMERA_API_KEY)

Enable API key auth in `chimera.yaml`:

```yaml
auth:
  enabled: true
  mode: env          # single shared key from CHIMERA_API_KEY
```

or, for multiple named keys:

```yaml
auth:
  enabled: true
  mode: list
  keys:
    - key: "sk-prod-abc123"
      name: "production-worker"
    - key: "sk-staging-xyz789"
      name: "staging-worker"
```

Start the server with the key:

```bash
CHIMERA_API_KEY="sk-prod-abc123" chimera serve
```

Clients authenticate with either header:

```bash
# Authorization header
curl -H "Authorization: Bearer sk-prod-abc123" http://localhost:8765/v1/chat/completions ...

# X-API-Key header (useful behind proxies that strip Authorization)
curl -H "X-API-Key: sk-prod-abc123" http://localhost:8765/v1/chat/completions ...
```

When auth is disabled, requests pass through unauthenticated. The following
endpoints are always open regardless of auth settings (safe for load-balancer
health checks): `/v1/health`, `/v1/health/ready`, `/v1/health/live`,
`/v1/models`, `/v1/formations`, `/docs`.

## 4. Client Examples

### curl — OpenAI-compatible endpoint

```bash
curl -X POST http://localhost:8765/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-prod-abc123" \
  -d '{
    "model": "auto",
    "messages": [{"role": "user", "content": "Compare Rust and Go for a low-latency trading system"}]
  }'
```

### Python — official openai SDK

Any OpenAI SDK works; just change `base_url` and add Chimera extras via
`extra_body`:

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8765/v1",
    api_key="sk-prod-abc123",          # any non-empty value when auth is off
)

response = client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "Explain quantum computing simply"}],
    extra_body={
        # Chimera-specific fields (optional):
        "allowed_models": ["deepseek/deepseek-v4-pro", "z-ai/glm-5.2"],
        "stage_models": {"aggregator": "openrouter/anthropic/claude-sonnet-4"},
    },
)
print(response.choices[0].message.content)
```

### Node.js — openai SDK

```javascript
import OpenAI from "openai";

const client = new OpenAI({
  baseURL: "http://localhost:8765/v1",
  apiKey: "sk-prod-abc123",
});

const response = await client.chat.completions.create({
  model: "auto",
  messages: [{ role: "user", content: "Summarize this diff" }],
});
console.log(response.choices[0].message.content);
```

### curl — /v1/deliberate with full trace

Use `/v1/deliberate` when you need the complete trace (per-stage tokens,
latency, cost, model selection, and all prompts/responses):

```bash
curl -X POST http://localhost:8765/v1/deliberate \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-prod-abc123" \
  -d '{
    "prompt": "Design a rate limiter for a distributed system",
    "formation": "debate",
    "allowed_models": ["deepseek/deepseek-v4-pro", "z-ai/glm-5.2"]
  }'
```

The response includes a `trace` object; the final answer is in `answer` (or
`choices[0].message.content` on the OpenAI-compatible endpoint).

### Custom DAGs

For full control of the deliberation structure, send your own DAG:

```json
{
  "model": "custom",
  "allow_custom_dag": true,
  "dag": {
    "stages": [
      {"id": "researcher", "kind": "worker", "model": "openrouter/anthropic/claude-sonnet-4"},
      {"id": "critic", "kind": "aggregator", "model": "z-ai/glm-5.2", "depends_on": ["researcher"]},
      {"id": "writer", "kind": "worker", "model": "deepseek/deepseek-v4-pro", "depends_on": ["critic"]}
    ],
    "edges": [["researcher", "critic"], ["critic", "writer"]]
  },
  "messages": [{"role": "user", "content": "Write a blog post about WebAssembly"}]
}
```

The dispatcher writes custom prompts for each stage but uses your exact
structure. Unknown stage IDs warn (non-fatal); unknown model names return 400.

### Structured output

Request JSON-schema output via `response_format` (OpenAI-compatible). Chimera
passes the schema to the aggregator, and automatically falls back through
`json_object` → plain text if the aggregator model does not support
`json_schema`:

```python
response = client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "Compare the top 3 databases"}],
    response_format={
        "type": "json_schema",
        "json_schema": {
            "name": "comparison",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {"ranking": {"type": "array", "items": {"type": "string"}}},
                "required": ["ranking"],
            },
        },
    },
)
```

### MCP (AI agents)

`chimera-mcp` exposes Chimera as an MCP server over stdio — Hermes, Claude
Code, and other MCP-capable agents can call `chimera_deliberate` directly.
It reads the same `chimera.yaml`.

## 5. Deployment Patterns

### 5.1 systemd (single host)

```ini
# /etc/systemd/system/chimera.service
[Unit]
Description=Chimera deliberation gateway
After=network.target

[Service]
User=chimera
WorkingDirectory=/opt/chimera
EnvironmentFile=/etc/chimera.env
ExecStart=/opt/chimera/.venv/bin/chimera serve
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

`/etc/chimera.env` holds secrets (never commit it):

```
CHIMERA_API_KEY=<your shared auth key>
# provider credentials — see the providers/api_keys sections of CONFIG.md
```

### 5.2 Behind nginx (TLS termination)

```nginx
server {
    listen 443 ssl;
    server_name chimera.example.com;

    ssl_certificate     /etc/letsencrypt/live/chimera.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/chimera.example.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8765;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;   # deliberations can take minutes
    }
}
```

Notes:

- Long deliberations: raise `proxy_read_timeout` (default 60s is too short).
- If your proxy strips the `Authorization` header (some CDNs do), clients can
  use `X-API-Key` instead — both are accepted.
- Health checks for your load balancer should target `/v1/health/live`
  (liveness) and `/v1/health/ready` (readiness); both are unauthenticated.
- The web UI (`/web/`) and `/docs` are served by the same process; if you do
  not want them public, restrict those paths in the proxy.

### 5.3 Environment variables

| Variable | Purpose |
|---|---|
| `CHIMERA_API_KEY` | Shared auth key when `auth.mode: env` |
| `CHIMERA_HOST` / `CHIMERA_PORT` | Bind address/port overrides |
| `DEEPSEEK_API_KEY`, `OPENROUTER_API_KEY`, ... | Provider credentials (see CONFIG.md) |

## 6. Health Checks

Three probes, all unauthenticated, all return HTTP 200 with a JSON body:

| Endpoint | Meaning | Use for |
|---|---|---|
| `GET /v1/health/live` | Process is alive | Liveness (restart if 5xx) |
| `GET /v1/health/ready` | Provider connectivity | Readiness (drain if failing) |
| `GET /v1/health` | Overall status | Dashboards / operators |

`/v1/health` returns:

```json
{
  "status": "healthy",
  "details": {
    "config_loaded": true,
    "models_configured": 42,
    "providers_configured": 5,
    "providers": { "deepseek": {"healthy": true} }
  }
}
```

Status semantics:

- `healthy` — config loaded, all configured providers reachable.
- `degraded` — config loaded, at least one provider reachable (or the
  connectivity probe itself failed). Deliberations may still succeed via the
  healthy providers.
- `unhealthy` — no provider reachable. Expect failures (or circuit-open
  fast-fails) on deliberate calls.

`/v1/health` always returns HTTP 200 with the status in the body — do not gate
on the HTTP status code alone; parse `status`.

## 7. Error Handling

All errors are JSON. The OpenAI-compatible endpoint returns conventional HTTP
status codes; body shape follows the FastAPI/OpenAI conventions.

| Status | Condition | Response shape | Action |
|---|---|---|---|
| `400` | Unknown model name, malformed DAG, invalid `response_format` | `{"detail": {...}}` | Fix the request; log the detail |
| `401` | Missing/invalid API key (auth enabled) | `{"detail": {"error": "unauthorized", "message": "Missing API key..."}}` | Add `Authorization: Bearer` or `X-API-Key` |
| `429` | Rate limit exceeded | `{"detail": {"error": "rate_limited", ...}}` + `Retry-After` header | Back off by `Retry-After` seconds |
| `5xx` | Server error | `{"detail": ...}` | Retry with backoff; check health |

### Circuit breakers

Provider-level circuit breakers prevent cascading failures. When a provider's
circuit is OPEN, Chimera fast-fails that provider without calling it:

```yaml
circuit_breakers:
  enabled: true
  defaults:
    failure_threshold: 5       # consecutive failures to open
    recovery_timeout_s: 30     # before testing recovery
    half_open_max_requests: 1  # probe requests in half-open state
```

The deliberation result may contain `[circuit open: <provider> is temporarily
unavailable]` — treat this as a retryable provider failure, not an app bug.

### Provider failures inside a deliberation

Chimera degrades gracefully: a failed worker is dropped from the aggregation
and the response trace records what happened. If every worker fails, the
response carries the error(s) in the trace; check `trace` before surfacing the
answer to end users.

### Retry guidance

- `429`: honor `Retry-After` (seconds). Do not hammer.
- `5xx` and circuit-open markers: retry with exponential backoff (e.g.
  1s → 2s → 4s, max 3 retries), or fall back to a single-model provider.
- Deliberations are not idempotent by default — each call costs tokens.
  Design retries around your budget; Chimera returns `usage` per response so
  you can meter cost.

## 8. Versioning & Support

- Package: `chimera-deliberation` (PyPI). Python 3.11+.
- Server version is reported in `/v1/health` details and `chimera --version`.
- Release notes: [CHANGELOG.md](../CHANGELOG.md).
- Security issues: see [SECURITY.md](SECURITY.md) for the reporting process
  and the full security model (auth modes, rate limiting, circuit breakers).

## 9. Quick Checklist

- [ ] `chimera.yaml` present with provider keys; `chimera serve` starts clean
- [ ] Auth enabled and `CHIMERA_API_KEY` set; `401` returned without a key
- [ ] `curl` chat completion works end-to-end
- [ ] Load balancer health checks point at `/v1/health/live` + `/v1/health/ready`
- [ ] Reverse proxy timeouts raised for long deliberations
- [ ] `429`/`Retry-After` honored in client retry logic
- [ ] Monitoring parses `status` from `/v1/health` (not just the HTTP code)
