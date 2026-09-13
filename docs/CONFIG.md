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
    categories:
      technology_code/code_generation/python: 0.90
      technology_code/data_science/analysis: 0.80
      general_knowledge/reasoning/explanation: 0.75
      creative_conversational/ux_writing/interface_copy: 0.35
      technology_code/testing_debugging/error_analysis: 0.55
    cost_tier: budget
    provider: deepseek

  z-ai/glm-5.2:
    categories:
      technology_code/code_generation/python: 0.92
      technology_code/data_science/analysis: 0.90
      general_knowledge/reasoning/explanation: 0.95
      creative_conversational/ux_writing/interface_copy: 0.85
      technology_code/testing_debugging/error_analysis: 0.88
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
  port: 8765

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

## `auto_formation`

Controls how the **default `auto` formation** (dispatcher-designed DAGs) picks
worker models.

| Field | Type | Default | Description |
|---|---|---|---|
| `restrict_to_credentialed_providers` | `bool` | `true` | Limit the dispatcher's catalog — and the auto worker stages that result — to enabled models whose provider has resolved credentials |

```yaml
auto_formation:
  restrict_to_credentialed_providers: true   # default
```

**Default routing by configured provider.** With the default `true`, the auto
dispatcher only sees (and the engine only executes) worker models whose
provider key is configured — resolved from `api_keys:` (`${VAR}` substitution
or the `*_API_KEY` env shortcuts) or a provider's `api_key` / `api_key_env`.
A fresh install with only `DEEPSEEK_API_KEY` set will therefore design
DeepSeek-only formations instead of picking OpenRouter models that fail with
guardrail/auth errors (`model_blocked_guardrail` → dropped workers →
`aggregator_partial_inputs` degraded merges). Anthropic models count as
usable when an OpenRouter key exists, matching the gateway's
Anthropic→OpenRouter fallback.

**Explicit all-catalog opt-in.** Set the flag to `false` (or export
`CHIMERA_AUTO_ALLOW_ALL_CATALOG=true`) to give the auto dispatcher the full
enabled catalog — the pre-restriction behavior.

**Scope.** Only dispatcher-generated `auto` formations are restricted:

- Named presets and custom DAGs are never rewritten — their structure is
  explicit configuration and is honored verbatim.
- Request-level overrides remain authoritative:
  `allowed_models`, `worker_model`, `stage_models`, `dispatcher_model`, and
  `aggregator_model` behave exactly as documented and can force any catalog
  model, credentialed or not.

**Guardrail-blocked model registry.** When a worker call fails with a
guardrail/privacy/endpoint-availability error
(`No endpoints available matching your guardrail restrictions…`), the model
is recorded in a blocked-model registry and excluded from the auto
dispatcher catalog and the category selector. Blocks are **long-lived (7
days)** and **persisted to `~/.chimera/blocked-models.json`**, so a fresh
process never re-picks a known guardrail-blocked model and the block is not
silently re-admitted after a short cooldown. Only guardrail-class failures
are recorded — timeouts, 5xx, and auth errors never block a model. Expired
entries are pruned automatically; to clear a block manually, delete the
state file (or remove the entry from it).
- `defaults.dispatcher` / `defaults.default_worker` /
  `defaults.default_aggregator` are operator choices and are not filtered
  (a failed aggregator stage still retries with `default_aggregator`).
- If *no* provider has resolved credentials, the restriction is skipped with
  an actionable warning so the failure surface stays the real provider auth
  error rather than an empty catalog.

---

## `models`

Each model entry:

```yaml
model-id:
  categories:           # 0.0–1.0 scores per category path (leaf or prefix)
    technology_code/code_generation/python: 0.90
    technology_code/data_science/analysis: 0.80
    general_knowledge/reasoning/explanation: 0.75
    creative_conversational/ux_writing/interface_copy: 0.35
    technology_code/testing_debugging/error_analysis: 0.55
  cost_tier: budget     # budget | standard | premium
  provider: deepseek    # matches a key in providers:
  # Optional overrides:
  litellm_model: openai/deepseek-v4-flash  # explicit LiteLLM model string
  cost_per_1k_input: 0.000098
  cost_per_1k_output: 0.000196
```

**Category keys** are slash-delimited hierarchical paths from the selector's
`PATH_PATTERNS` tree (see `src/chimera/selector.py`), e.g.
`technology_code/code_generation/python`. A score on a parent path (e.g.
`technology_code`) applies to every descendant path via prefix fallback, so
scoring a few broad paths is enough to cover a whole area.

Short-form aliases are also accepted and resolve to the long-form targets
below — a model configured with `{code: 0.90}` scores on every path under
`technology_code`:

| Alias | Resolves to |
|---|---|
| `code` | `technology_code` |
| `analysis` | `technology_code/data_science`, `academic_scientific/mathematics/statistics` |
| `reasoning` | `general_knowledge/reasoning`, `complex_reasoning_agency` |
| `design` | `creative_conversational/ux_writing/interface_copy`, `technology_code/system_design` |
| `audit` | `technology_code/testing_debugging/error_analysis`, `business_finance/legal_document/analysis` |

Prefer long-form paths for precise control; aliases are a convenience and
apply the same score to every path under their target subtree.

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
| `port` | `8765` | Listen port |
