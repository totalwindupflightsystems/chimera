# Security — Chimera v2

## F1 — Authentication ✅

Chimera supports API key authentication via two modes:

### Mode: `env` (single shared key)

Set the `CHIMERA_API_KEY` environment variable:
```bash
export CHIMERA_API_KEY="your-secret-key"
```

Configure in `chimera.yaml`:
```yaml
auth:
  enabled: true
  mode: env
```

Clients must include the key in every request:
```bash
# Authorization header
curl -H "Authorization: Bearer your-secret-key" http://localhost:8765/v1/deliberate \
  -d '{"prompt": "hello"}'

# X-API-Key header
curl -H "X-API-Key: your-secret-key" http://localhost:8765/v1/deliberate \
  -d '{"prompt": "hello"}'
```

### Mode: `list` (multiple named keys)

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

Each key is independent; all share the same rate limit pool by default.

### Unauthenticated Endpoints

These are the only paths served without credentials when `auth.enabled: true`
(measured against a live server — re-verify with `curl -o /dev/null -w '%{http_code}'`
against your own deployment, and see `GET /openapi.json` for the routed surface):

- `GET /health` — alias of `/v1/health`
- `GET /v1/health`
- `GET /v1/health/ready`
- `GET /v1/health/live`
- `GET /v1/models`
- `GET /v1/formations`
- `GET /docs` and `GET /docs/oauth2-redirect` — Swagger UI
- `GET /redoc` — ReDoc UI
- `GET /openapi.json` — machine-readable spec

Everything else requires the key: `POST /v1/deliberate`,
`POST /v1/chat/completions`, and the **entire** `/web/*` surface —
`POST /web/sessions`, `POST /web/sessions/{id}/chat`, `GET /web/sessions/{id}`,
`GET /web/sse/{id}`, and the SPA shell at `GET /web/`.
The web surface runs deliberations through the same engine as `/v1/deliberate`,
so leaving it open would be a keyless, billable equivalent of the protected API.
An anonymous request is refused by the auth layer before any handler, session or
provider call runs (401, never 404).

Because the auth dependency is attached to the router, gating covers `/web/*`
as a whole — including the SPA shell. The bundled browser UI therefore targets
auth-disabled deployments; with auth enabled the UI's own requests have nowhere
to put a header, so drive `/web/*` from an API client that sends
`Authorization: Bearer <key>` or `X-API-Key: <key>` (or keep the UI behind your
own authenticating reverse proxy).

#### `POST /web/debug/reset` — dev/test only, disabled by default

This one path is **not** part of the keyed surface: it is disabled by default
and returns **404** (never a session-destroying 200) unless the SERVER process
was started with the dev switch `CHIMERA_WEB_DEBUG_RESET=1` (also accepts
`true`). With `auth.enabled: true` the router-level auth layer still answers
first, so an anonymous caller there sees 401 and learns nothing about the route.

**Blast radius when enabled:** the handler rebinds the process-global session
manager and SSE broadcaster, so **every** live session — and the conversation
history of every concurrent user on that server — is destroyed in one request,
and every open SSE stream loses its subscribers. It is a test hook: enable it
only on a throwaway local/CI server nobody else is using (the integration suite
starts its own server with the switch set for exactly this reason). Do not set
`CHIMERA_WEB_DEBUG_RESET` on a shared or public deployment, and do not put this
path behind anything that could forward an anonymous request to it.

Enabling it logs a `web_debug_reset_fired` warning (with the session count
being dropped) each time the reset actually runs.

### Error Response (401)

```json
{
  "detail": {
    "error": "unauthorized",
    "message": "Missing API key. Provide via Authorization: Bearer <key> or X-API-Key header."
  }
}
```

## F2 — Rate Limiting ✅

In-memory token bucket rate limiter. No external dependencies (no Redis required).

```yaml
rate_limit:
  enabled: true
  requests_per_minute: 60     # sustained rate
  burst_size: 10              # allowed burst above sustained rate
```

- Per-API-key buckets (each key gets independent limits)
- `TokenBucket` implementation: tokens replenish at `requests_per_minute / 60` per second
- Bucket depth = `burst_size`

### Error Response (429)

```json
{
  "detail": {
    "error": "rate_limited",
    "message": "Too many requests. Please wait before retrying."
  }
}
```

Response includes `Retry-After` header (seconds).

## F3 — Circuit Breakers ✅

Provider-level circuit breakers prevent cascading failures when a provider is down.

```yaml
circuit_breakers:
  enabled: true
  defaults:
    failure_threshold: 5       # consecutive failures to open circuit
    recovery_timeout_s: 30     # seconds before testing recovery
    half_open_max_requests: 1  # test requests allowed in half-open state
```

### States

| State | Behavior |
|---|---|
| **CLOSED** | Normal operation — requests pass through |
| **OPEN** | Fast-fail — returns `[circuit open]` response without calling provider |
| **HALF_OPEN** | Testing — allows 1 probe request to check if provider recovered |

### Per-Provider Override

```yaml
circuit_breakers:
  providers:
    deepseek:
      failure_threshold: 3     # open faster for less reliable providers
      recovery_timeout_s: 60   # wait longer before retrying
```

### Fast-Fail Response

When circuit is OPEN, gateway returns:
```python
GatewayResponse(
    text="[circuit open: deepseek is temporarily unavailable]",
    is_circuit_open=True,
    ...
)
```

WARNING `circuit_open_fast_fail` logged with provider name.
