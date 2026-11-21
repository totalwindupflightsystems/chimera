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

Each retry draws independent ±25% jitter to spread calls within a process and
across processes, reducing thundering herds (without guaranteeing unique delays).
The exponential delay is capped before jitter, so the actual delay can reach
125% of `max_delay_ms`. Each retry is logged with attempt number, delay, and error.

### How many provider requests a logical call can cost

`retry.max_attempts` is the **only** retry budget. Chimera disables the retry
ladder that the LiteLLM client would otherwise run underneath it
(`num_retries=0` on every production call), so one Chimera attempt is exactly
one upstream HTTP request:

```
upstream requests for one model stage  =  retry.max_attempts
```

| `retry.max_attempts` | Requests one stage can cost |
|---|---|
| 1 | 1 |
| 3 (default) | 3 |
| 5 | 5 |

Worst-case provider bill for one deliberation multiplies the same way over the
model calls the run actually makes:

```
upstream requests for one deliberation  =  model calls  ×  retry.max_attempts
```

where *model calls* is the dispatcher call that plans the run, plus one call
per stage, plus a scorer call where the formation merges with `best_of_n`. A
`simple` formation (2 workers + 1 aggregator, so 1 + 3 = 4 model calls) at the
default budget costs at most `4 × 3 = 12` provider requests. Only requests that
reach the provider are billed, so a stage that succeeds on its first attempt
costs one.

Two paths are deliberately narrower than the table above:

- A health probe (`/v1/health`) makes exactly **one** upstream request per
  model, regardless of `max_attempts` (F8) — it reports what the provider says
  now instead of spending the shared health budget on retries.
- Non-retryable errors (401/403, 400, budget exhausted) stop at their first
  attempt.

Before this was made explicit (DF-CHIMERA-V2-126) the client's own default
ladder multiplied every attempt by three: `max_attempts` 1/3/5 cost 3/9/15
provider requests, i.e. a user budgeting three calls was really budgeting nine.
If you are on a build older than that fix, multiply the table by three.

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
