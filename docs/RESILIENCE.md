# Resilience — Chimera v2

## F5 — Request Queue / Backpressure ✅

In-memory request queue prevents overload under traffic spikes.

```yaml
queue:
  max_concurrent: 10     # simultaneous deliberations
  max_queue_depth: 100   # pending requests before 503
```

- Uses `asyncio.Semaphore` for concurrency limiting
- When `max_queue_depth` is exceeded, returns HTTP 503 with `Retry-After: 5`
- Both `/v1/deliberate` and `/v1/chat/completions` acquire/release slots

## F6 — Provider-Aware Format Negotiation ✅

Different providers support different response format capabilities. Chimera auto-negotiates.

| Provider | json_schema | json_object | Fallback |
|---|---|---|---|
| OpenAI, Anthropic, Google, Z.AI | ✅ | ✅ | — |
| DeepSeek, Moonshot | ❌ | ✅ | json_object |
| Unknown/Other | ❌ | ❌ | plain text |

The gateway downgrades automatically before sending the request, avoiding provider errors.

## F7 — Retry with Exponential Backoff ✅

```yaml
retry:
  max_attempts: 3
  base_delay_ms: 500
  max_delay_ms: 10000
  backoff_multiplier: 2.0
```

### Retryable Errors
- Rate limit (HTTP 429)
- Server errors (HTTP 5xx)
- Network errors (timeout, connection refused)

### Non-Retryable Errors
- Authentication (401, 403)
- Bad request (400)
- Budget exhausted (detected via error message keywords)

Retries include ±25% jitter to avoid thundering herd. Each attempt logged with attempt number, delay, and error.

## F8 — Health Check Verification ✅

### Endpoints

| Endpoint | Purpose | Response |
|---|---|---|
| `GET /v1/health` | Overall health | `{"status": "healthy"\|"degraded"\|"unhealthy"}` |
| `GET /v1/health/ready` | Readiness probe | 200 or 503 |
| `GET /v1/health/live` | Liveness probe | Always 200 |

### Health Status

```json
{
  "status": "healthy",
  "details": {
    "config_loaded": true,
    "models_configured": 4,
    "providers": {
      "deepseek": {"healthy": true, "error": null},
      "openrouter": {"healthy": true, "error": null}
    }
  }
}
```

- **healthy**: config loaded, all providers reachable
- **degraded**: config loaded, some providers unreachable
- **unhealthy**: config failed to load

Readiness probe (`/v1/health/ready`) returns 503 when no providers are reachable — signals the load balancer to stop routing traffic.
