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
        - {id: reviewer, kind: aggregator, model: zai-coding-plan/glm-5.2, depends_on: [analyzer]}
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

  zai-coding-plan/glm-5.2:
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

## First-run remedies

Two failures account for nearly every failed first run. Both messages name
the fix; this is the chain behind them.

| Symptom | The message names | Do this |
|---|---|---|
| `error: No chimera.yaml found. …` — one line, exit code 2, no traceback | `chimera config init` | Run `chimera config init`. It copies the shipped `chimera.yaml.example` into `chimera.yaml`, resolving the template from a local copy, the repo checkout, or the copy inside the installed wheel — so it works for a bare `pip install` with no repo on disk. Add `--force` to overwrite an existing config. |
| A provider rejects the call (`401`, `Missing credentials`, `invalid api key`) | the provider **and its own env var**, e.g. `provider 'deepseek' rejected the credentials or none were found: set DEEPSEEK_API_KEY` | Set that variable (or the variable your `providers.<name>.api_key_env` names) and re-run. |

Notes:

- The env var in the message is resolved from **the provider that served the
  model** — an explicit `providers.<name>.api_key_env` first, then the
  canonical name from the `api_keys` table above, then the
  `<PROVIDER>_API_KEY` convention. LiteLLM's own prose is provider-blind
  (every `base_url` provider is reached through the OpenAI SDK, so a DeepSeek
  failure mentions `OPENAI_API_KEY`); Chimera prepends its accurate remedy
  before that text, on every surface (CLI, REST body, MCP tool result, trace,
  structlog stream).
- **Keyless local endpoints are never told to set a key.** A provider whose
  `base_url` is loopback (`localhost` / `127.0.0.1` / `0.0.0.0` / `::1`) and
  that configures neither `api_key_env` nor `api_key` — `lmstudio`, `ollama`,
  a local llama.cpp/vLLM server — keeps the raw upstream error text, because
  no env var can be named for it honestly. Give it an `api_key_env` if your
  local server really does require a token.
- **A custom `base_url` provider names its own variable.** The remedy follows
  `providers.<name>.api_key_env`, so a failure from the Hermes gateway reads
  `set API_SERVER_KEY` — not LiteLLM's `OPENAI_API_KEY` prose, even though the
  call is served through the OpenAI SDK. Note that a keyless custom provider
  cannot be called at all: LiteLLM's OpenAI path requires a key value, so pair
  a custom `base_url` with an `api_key_env` (see
  [Custom OpenAI-compatible endpoints](#custom-openai-compatible-endpoints)).
- A *present but invalid* key blocks the model for the block cooldown
  (`~/.chimera/blocked-models.json`, 7 days by default); the CLI prints the
  same variable in its `credential failure` hint, and `chimera models` lists
  the blocked models with their remedy. The block self-clears when the key
  changes.

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
    - anthropic/claude-sonnet-4.6
  merge: best_of_n
```

### Audit (with safety review)

```yaml
audit:
  workers: 2
  aggregator: default
  audit: anthropic/claude-haiku-4.5
```

### Custom DAG (fully defined structure)

```yaml
my-chain:
  dag:
    stages:
      - {id: step1, kind: worker, model: deepseek/deepseek-v4-pro}
      - {id: step2, kind: aggregator, model: zai-coding-plan/glm-5.2, depends_on: [step1]}
      - {id: step3, kind: worker, model: anthropic/claude-sonnet-4.6, depends_on: [step2]}
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
  categories:           # 0-100 percent scores per category path (leaf or prefix)
    technology_code/code_generation/python: 90
    technology_code/data_science/analysis: 80
    general_knowledge/reasoning/explanation: 75
    creative_conversational/ux_writing/interface_copy: 35
    technology_code/testing_debugging/error_analysis: 55
  cost_tier: budget     # budget | standard | premium
  provider: deepseek    # matches a key in providers:
  # Optional overrides:
  litellm_model: openai/deepseek-v4-flash  # explicit LiteLLM model string
  cost_per_1k_input: 0.000098
  cost_per_1k_output: 0.000196
```

**Score scale — percent, 0–100.** The shipped templates
(`chimera.yaml.example`, `chimera.yaml.docker`), the live catalog and the
`categories` map served by `GET /v1/models` all use percent, and the selector
multiplies a score by its task weight with no further rescale — so percent is
the canonical scale. There is exactly **one scale per catalog**, enforced at
load:

- a catalog whose values are all ≤ 1.0 is read as **0.0–1.0** (the historical
  docs scale) and rescaled ×100 on load, with one warning naming how many
  models were rescaled — so a catalog written from this page competes instead
  of being silently starved;
- a 0.0–1.0 value inside an otherwise percent catalog is rescaled per entry,
  with one warning per affected model + path (`0.9 → 90.0`);
- an already-percent value is never touched (byte-identical on load);
- a value outside 0–100, a non-numeric value, or `NaN`/`Infinity` **fails the
  load** with one actionable line naming the model id, the category path, the
  value and the accepted range — no traceback, CLI exit code 2.

**Category keys** are slash-delimited hierarchical paths from the selector's
`PATH_PATTERNS` tree (see `src/chimera/selector.py`), e.g.
`technology_code/code_generation/python`. A score on a parent path (e.g.
`technology_code`) applies to every descendant path via prefix fallback, so
scoring a few broad paths is enough to cover a whole area.

Short-form aliases are also accepted and resolve to the long-form targets
below — a model configured with `{code: 90}` scores on every path under
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

**`GET /v1/models` serves the EFFECTIVE rate — the same number the engine
bills.** For each model the `cost_per_1k_input` / `cost_per_1k_output` fields of
both the `data[]` entries and the `catalog` map carry the resolved rate an
explicit `cost_per_1k_*` declaration wins over, otherwise the `cost_tier`
default from the table above (an unrecognised or absent tier resolves to
`standard`, the same fallback the biller uses). These are the values returned by
`ModelEntry.cost_rate_input()` / `ModelEntry.cost_rate_output()`, which is the
code path `engine._stage_cost` charges through, so the served catalog and the
billed cost cannot drift. A model the engine genuinely cannot price has no
catalog entry to serve, so the fields are never `null` for an entry the engine
bills. The field names, JSON types and the rest of the envelope are unchanged —
a client that read the raw declared rates sees the effective rate instead of
`null` for tier-priced ids.

**Model ID format:** `<provider-type>/<model-name>` where `provider-type` matches a
config provider or is `openrouter` for OpenRouter-routed models:

- `deepseek/deepseek-v4-flash` → direct DeepSeek API
- `openrouter/anthropic/claude-fable-5` → via OpenRouter
- `zai-coding-plan/glm-5.2` → direct Z.AI API

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
  hermes:
    base_url: http://127.0.0.1:8642/v1
    api_key_env: API_SERVER_KEY
  router9:
    base_url: http://master001:20128/v1
    api_key_env: ROUTER9_API_KEY
```

The `base_url` is used by LiteLLM to route calls. Provider IDs (`deepseek`,
`openrouter`, `zai`, `hermes`, `router9`) map to the `provider` field in model
entries.

Two optional credential fields per provider:

| Field | Meaning |
|---|---|
| `api_key_env` | Name of the environment variable holding this provider's key. **Overrides** the canonical name from `api_keys` (`google` → `GEMINI_API_KEY`) and the `<PROVIDER>_API_KEY` convention. Set it when your key lives under a non-standard name. |
| `api_key` | Literal key value, or a `${VAR}` token (never hardcode a real key). |

A provider with a **loopback** `base_url` and neither field set is treated as
keyless (a local `lmstudio`/`ollama`/llama.cpp/vLLM endpoint): credential
errors from it keep their raw upstream text instead of naming an env var that
does not exist, and no key is required for it to run.

### Custom OpenAI-compatible endpoints

`deepseek`, `openrouter`, `zai`, `anthropic`, `google` and `openai` have
native routing built into the gateway. Any **other** provider is routed by its
own `base_url`: the call goes to that URL through the OpenAI-compatible SDK,
authenticated with the provider's resolved key (see `api_key_env` above), and
the **model id sent upstream is the catalog id with exactly ONE leading
`<provider>/` segment stripped** — or the part after the last `/` when the
catalog id does not carry the provider prefix, exactly as the `zai` provider
works. A catalog entry `hermes/glm-5.3-flash` therefore reaches
`http://127.0.0.1:8642/v1` as `glm-5.3-flash`.

Endpoints that serve **namespaced** model ids of their own keep their inner
slashes — only the one catalog prefix goes:
`router9/ds/deepseek-v4-flash` reaches 9router as `ds/deepseek-v4-flash`, and
`router9/openrouter/x-ai/grok-4.6` as `openrouter/x-ai/grok-4.6`.

That is what makes a local, non-LiteLLM-prefixed service usable as a
first-class provider. The shipped example config wires the **Hermes gateway**
(OpenAI-compatible on `:8642`) that way:

```yaml
models:
  hermes/glm-5.3-flash:
    provider: hermes
    cost_tier: budget
    categories:
      general_knowledge/reasoning/explanation: 80

providers:
  hermes:
    base_url: http://127.0.0.1:8642/v1
    api_key_env: API_SERVER_KEY
```

The same seam carries the **9router fleet gateway**: one OpenAI-compatible
endpoint in front of a large multi-prefix catalog (~269 models across 15
upstream prefixes — `ds/`, `mmx/`, `minimax/`, `kimi/`, `openrouter/`, `xai/`,
`ollama/`, …). It answers on `http://master001:20128/v1` (the host is
`master001` on the tailnet, and the same name resolves from the LAN hosts):

```yaml
models:
  router9/ds/deepseek-v4-flash:
    provider: router9
    cost_tier: budget
    categories:
      technology_code/code_generation/python: 88

providers:
  router9:
    base_url: http://master001:20128/v1
    api_key_env: ROUTER9_API_KEY   # var name in ~/.hermes/.env — never inline the key
```

Notes for this shape of provider:

- **The key still has to resolve to a value.** LiteLLM's OpenAI-SDK path
  refuses to call without one (`Missing credentials`), even against loopback,
  so give the provider an `api_key_env` — `API_SERVER_KEY` lives in
  `~/.hermes/.env` and is read through the usual resolution chain (process env
  → repo `.env` → `~/.hermes/.env`).
- **The gateway injects its own system prompt** — a ~41k-token prompt is added
  to every request, billed as input tokens. Treat the effective budget as the
  model's context window minus that: a 200k-token model has roughly 159k
  tokens left for the deliberation prompt and worker outputs.
- **`/v1/health` runs a real completion** against a model of every configured
  provider, bounded by `server.health_timeout_s` (default `10.0` s). A gateway
  that takes longer than that to answer a 1-token probe is reported
  `degraded`; keep `health_timeout_s` above the gateway's own latency. A probe
  still outstanding at the deadline gets `server.health_probe_grace_s` extra
  seconds (default `1.0`) to land before it is reported `timeout`
  (DF-CHIMERA-V2-17).
- **A lane behind a routing gateway can be out of quota.** 9router serves each
  upstream prefix from its own account, so one exhausted lane answers
  `429`/`403` for every model behind it while the gateway itself is healthy and
  other prefixes keep working. That is a provider-side condition, not a Chimera
  defect: point the formation at another prefix's model instead of
  re-dispatching at the same one.

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
