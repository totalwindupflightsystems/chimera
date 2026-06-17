# Chimera Configuration Reference

`chimera.yaml` controls everything: model catalog, formations, providers, defaults, and observability.

## Full Example

```yaml
api_keys:
  deepseek: ${DEEPSEEK_API_KEY}
  openrouter: ${OPENROUTER_API_KEY}
  zai: ${ZAI_API_KEY}

defaults:
  dispatcher: deepseek/deepseek-v4-flash
  default_worker: deepseek/deepseek-v4-pro
  default_aggregator: deepseek/deepseek-v4-flash
  lock_dispatcher: false
  lock_aggregator: true

formations:
  auto:
    mode: auto
  simple:
    workers: 2
    aggregator: default
  my-custom-chain:
    dag:
      stages:
        - {id: analyzer, kind: worker, model: deepseek/deepseek-v4-pro}
        - {id: reviewer, kind: aggregator, model: z-ai/glm-5.2, depends_on: [analyzer]}
        - {id: finalizer, kind: merge, model: deepseek/deepseek-v4-flash, depends_on: [reviewer]}
      edges:
        - [analyzer, reviewer]
        - [reviewer, finalizer]

models:
  deepseek/deepseek-v4-flash:
    categories: {code: 0.90, analysis: 0.80, reasoning: 0.75, design: 0.35, audit: 0.55}
    cost_tier: budget
    provider: deepseek

  z-ai/glm-5.2:
    categories: {code: 0.92, analysis: 0.90, reasoning: 0.95, design: 0.85, audit: 0.88}
    cost_tier: premium
    provider: zai

providers:
  deepseek:
    base_url: https://api.deepseek.com/v1
  openrouter:
    base_url: https://openrouter.ai/api/v1
  zai:
    base_url: https://api.z.ai/api/coding/paas/v4

server:
  host: 0.0.0.0
  port: 8000

observability:
  log_level: info
  use_stdout: true
  trace_enabled: true
  langfuse:
    enabled: false
```

---

## `api_keys`

Environment-variable-backed API keys. Use `${VAR}` syntax to pull from environment.
Never hardcode keys here.

| Key | Value | Used for |
|---|---|---|
| `deepseek` | `${DEEPSEEK_API_KEY}` | Direct DeepSeek API calls |
| `openrouter` | `${OPENROUTER_API_KEY}` | All models routed through OpenRouter |
| `zai` | `${ZAI_API_KEY}` | Direct Z.AI GLM calls |

Add any key your providers need: `anthropic`, `openai`, `xai`, etc.

---

## `defaults`

| Field | Type | Default | Description |
|---|---|---|---|
| `dispatcher` | `string` | — | Model that designs the formation DAG |
| `default_worker` | `string` | — | Fallback model for worker stages |
| `default_aggregator` | `string` | — | Fallback model for aggregator/merge/audit stages |
| `lock_dispatcher` | `bool` | `false` | If `true`, dispatcher cannot override the dispatcher model |
| `lock_aggregator` | `bool` | `false` | If `true`, dispatcher cannot override the aggregator model |

**Why lock?** The dispatcher picks the "best" model for each role based on category
weights. If you want to force budget models for aggregator (e.g. DeepSeek V4 Flash
instead of GLM-5.2), set `lock_aggregator: true`.

---

## `formations`

Named formation presets. Two styles:

### Auto (dispatcher designs everything)

```yaml
auto:
  mode: auto
```

### Simple (fixed worker count)

```yaml
simple:
  workers: 2
  aggregator: default        # uses defaults.default_aggregator
```

### Debate (multiple aggregators + merge)

```yaml
debate:
  workers: 3
  aggregators:
    - default
    - openrouter/anthropic/claude-sonnet-4
  merge: best_of_n
```

### Audit (with safety review)

```yaml
audit:
  workers: 2
  aggregator: default
  audit: openrouter/anthropic/claude-haiku-4.5
```

### Custom DAG (fully defined structure)

```yaml
my-chain:
  dag:
    stages:
      - {id: step1, kind: worker, model: deepseek/deepseek-v4-pro}
      - {id: step2, kind: aggregator, model: z-ai/glm-5.2, depends_on: [step1]}
      - {id: step3, kind: worker, model: openrouter/anthropic/claude-sonnet-4, depends_on: [step2]}
      - {id: final, kind: merge, model: deepseek/deepseek-v4-flash, depends_on: [step3]}
    edges:
      - [step1, step2]
      - [step2, step3]
      - [step3, final]
```

Stage kinds: `worker`, `aggregator`, `merge`, `audit`.

---

## `models`

Each model entry:

```yaml
model-id:
  categories:           # 0.0–1.0 scores per capability category
    code: 0.90
    analysis: 0.80
    reasoning: 0.75
    design: 0.35
    audit: 0.55
  cost_tier: budget     # budget | standard | premium
  provider: deepseek    # matches a key in providers:
  # Optional overrides:
  litellm_model: openai/deepseek-v4-flash  # explicit LiteLLM model string
  cost_per_1k_input: 0.000098
  cost_per_1k_output: 0.000196
```

**Cost tiers** determine default pricing when `cost_per_1k_*` is not set:

| Tier | $/1K input | $/1K output |
|---|---|---|
| `budget` | $0.00014 | $0.00028 |
| `standard` | $0.0005 | $0.0015 |
| `premium` | $0.003 | $0.015 |

**Model ID format:** `<provider-type>/<model-name>` where `provider-type` matches a
config provider or is `openrouter` for OpenRouter-routed models:

- `deepseek/deepseek-v4-flash` → direct DeepSeek API
- `openrouter/anthropic/claude-sonnet-4` → via OpenRouter
- `z-ai/glm-5.2` → direct Z.AI API

---

## `providers`

Provider gateway configurations:

```yaml
providers:
  deepseek:
    base_url: https://api.deepseek.com/v1
  openrouter:
    base_url: https://openrouter.ai/api/v1
  zai:
    base_url: https://api.z.ai/api/coding/paas/v4
```

The `base_url` is used by LiteLLM to route calls. Provider IDs (`deepseek`,
`openrouter`, `zai`) map to the `provider` field in model entries.

---

## `observability`

| Field | Type | Default | Description |
|---|---|---|---|
| `log_level` | `string` | `info` | `debug`, `info`, `warning`, `error` |
| `use_stdout` | `bool` | `true` | Output logs to stdout (false = stderr) |
| `trace_enabled` | `bool` | `true` | Record per-stage spans with tokens/cost/latency |
| `langfuse.enabled` | `bool` | `false` | Send traces to Langfuse |
| `langfuse.host` | `string` | `cloud.langfuse.com` | Langfuse instance |
| `langfuse.public_key` | `string` | — | Langfuse public key |
| `langfuse.secret_key` | `string` | — | Langfuse secret key |

**Debug mode:** Set `log_level: debug` to see dispatcher prompts, worker prompts,
and full response payloads in logs.

---

## `server`

| Field | Default | Description |
|---|---|---|
| `host` | `0.0.0.0` | Bind address |
| `port` | `8000` | Listen port |
