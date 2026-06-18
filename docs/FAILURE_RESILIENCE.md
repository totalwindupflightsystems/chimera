# Failure Resilience — Chimera v2

## Partial Worker Failures (C2)

When a worker times out or errors during a multi-worker deliberation:

1. Stage is marked `degraded: true` in the `StageResult`
2. Worker output included in aggregator prompt with `[DEGRADED]` label
3. WARNING `aggregator_partial_inputs` logged with counts
4. Aggregator still produces best-effort merged output

**Example log:**
```json
{
  "event": "aggregator_partial_inputs",
  "total_deps": 3,
  "degraded": 1,
  "healthy": 2,
  "level": "warning"
}
```

## Token Limit Handling (C3)

When a model response hits its `max_tokens` limit:

1. `GatewayResponse.finish_reason = "length"`
2. WARNING `token_limit_reached` logged with model and token counts
3. Response is still returned — downstream code can check `finish_reason`

**Example log:**
```json
{
  "event": "token_limit_reached",
  "model": "deepseek/deepseek-v4-pro",
  "tokens_input": 500,
  "tokens_output": 4096,
  "level": "warning"
}
```

## Empty/Null Response Handling (C4)

Gateway `_extract_text()` gracefully handles all edge cases:

| Scenario | Behavior |
|---|---|
| Empty `choices` array | Returns `""`, sets `is_empty=True` |
| `None` choices | Returns `""`, sets `is_empty=True` |
| Missing `message` key | Returns `""`, sets `is_empty=True` |
| `None` content | Returns `""`, sets `is_empty=True` |
| `finish_reason="stop"` with empty content | Returns `""`, sets `is_empty=True` |
| Whitespace-only content | Returns stripped string |
| `reasoning_content` present (DeepSeek) | Uses reasoning_content as fallback |
| `reasoning` field present (MiniMax/Kimi) | Uses reasoning as fallback |

No exceptions are raised for empty responses — downstream code receives `GatewayResponse` with `is_empty=True`.

## Budget Exhaustion (C7)

When a provider returns a quota or billing error:

```python
from chimera.exceptions import BudgetExhaustedError

try:
    response = await gateway.complete(messages, model)
except BudgetExhaustedError as e:
    print(f"Budget exhausted: {e.model} on {e.provider}")
    print(f"Details: {e.details}")
```

**Detection keywords (case-insensitive):**
- `insufficient_quota`
- `billing`
- `payment required`
- `quota exceeded`
- `out of credits`
- `balance insufficient`

**Example log:**
```json
{
  "event": "budget_exhausted",
  "model": "deepseek/deepseek-v4-pro",
  "provider": "openai",
  "error": "insufficient_quota: You exceeded your current quota",
  "level": "critical"
}
```

The error is NOT retried (retriable errors list excludes budget exhaustion).
