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

These endpoints remain open regardless of auth settings:
- `GET /v1/health`
- `GET /v1/health/ready`
- `GET /v1/health/live`
- `GET /v1/models`
- `GET /v1/formations`
- `GET /docs`

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
