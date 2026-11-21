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
      technology_code/code_generation/python: 90
      technology_code/data_science/analysis: 80
      general_knowledge/reasoning/explanation: 75
      creative_conversational/ux_writing/interface_copy: 35
      technology_code/testing_debugging/error_analysis: 55
    cost_tier: budget
    provider: deepseek

  zai-coding-plan/glm-5.2:
    categories:
      technology_code/code_generation/python: 92
      technology_code/data_science/analysis: 90
      general_knowledge/reasoning/explanation: 95
      creative_conversational/ux_writing/interface_copy: 85
      technology_code/testing_debugging/error_analysis: 88
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
  (state file: `.chimera/blocked-models.json` in the repo checkout — see
  [Blocked-models state file](#blocked-models-state-file), 7 days by
  default); the CLI prints the same variable in its `credential failure`
  hint, and `chimera models` lists the blocked models with their remedy.
  The block self-clears when the key changes.

---

## `defaults`

| Field | Type | Default | Description |
|---|---|---|---|
| `dispatcher` | `string` | — | Model that designs the formation DAG |
| `default_worker` | `string` | — | Fallback model for worker stages |
| `default_aggregator` | `string` | — | Fallback model for aggregator/merge/audit stages |
| `lock_dispatcher` | `bool` | `false` | If `true`, the dispatcher role keeps its configured model: a request's `dispatcher_model` is discarded (and reported — see [`lock_dispatcher` / `lock_aggregator`](#lock_dispatcher--lock_aggregator-what-a-locked-config-absorbs)) |
| `lock_aggregator` | `bool` | `false` | If `true`, aggregator/merge/audit stages keep their configured model: a request's `aggregator_model` is discarded (and reported — see below) |
| `aggregator_fallbacks` | `list[string]` | `[]` | Ordered merge fallback chain, tried when the aggregator model's own call fails |

**Why lock?** The dispatcher picks the "best" model for each role based on category
weights. If you want to force budget models for aggregator (e.g. DeepSeek V4 Flash
instead of GLM-5.2), set `lock_aggregator: true`.

### `lock_dispatcher` / `lock_aggregator` — what a locked config absorbs

Both locks guard the same seam: a **global, role-level request override** is
ignored and the configured model keeps the role (DF-CHIMERA-V2-131).

| Lock | Absorbs this request field | Role that keeps its configured model |
|---|---|---|
| `lock_aggregator: true` | `aggregator_model` | every `aggregator` / `merge` / `audit` stage |
| `lock_dispatcher: true` | `dispatcher_model` | the dispatcher call that designs the DAG |

What a lock does **not** absorb:

* `worker_model` — neither lock covers worker stages.
* `stage_models` — per-stage overrides are applied *after* the lock decision, so
  `stage_models: {aggregator: <model>}` still selects that model under
  `lock_aggregator: true`. This is the per-request escape hatch that survives a
  lock.
* `allowed_models` / `models` — pool restrictions, not role assignments.
* `defaults.aggregator_fallbacks` — the merge fallback chain stays armed under the
  lock (see below).

**A discard is never silent.** Before DF-CHIMERA-V2-131 the locked model simply
won: the request validated, returned `200`, and nothing in the body said the
override had been thrown away — so a caller whose configured aggregator was dead
(quota-exhausted, bad key) could not escape it through the API and never learned
why. Every surface now carries a first-class `discarded_overrides` field — one
`{field, requested, locked_by, reason}` record per discarded override:

| Surface | Where the discard appears |
|---|---|
| `POST /v1/deliberate` success | top-level `discarded_overrides` (absent when nothing was discarded) **and** `trace.discarded_overrides` |
| `POST /v1/chat/completions` success | `chimera_discarded_overrides` (absent when nothing was discarded); the chat surface serves no `trace` body |
| `502` no-usable-answer | `error.discarded_overrides` + the same clause appended to `error.message`, plus `error.dispatch_note` |
| `503` no-healthy-candidate / `lane_unreachable` | `error.discarded_overrides` + the same clause in `error.message` |

`trace.discarded_overrides` is the authoritative carrier: `dispatch_note` is a
single prose string, and a run that also collapsed to the generic formation has
its note replaced by the fallback reason, which would hide the discard in prose.
The structured list is never overwritten.

To *honour* the override, turn the lock off (`lock_aggregator: false`) or name the
stage explicitly with `stage_models`. To route around a dead aggregator while
keeping the lock, use `defaults.aggregator_fallbacks`.

### `aggregator_fallbacks` — the merge must not be a single point of failure

Measured (DF-CHIMERA-V2-120): 3 of 4 live deliberations exited rc=2 with no answer
after 83-187 s while all three workers had already succeeded and been billed — the
single configured aggregator model failed with `Insufficient Balance` and there was
nothing else to try. The fallback chain fixes exactly that:

```yaml
defaults:
  default_aggregator: deepseek/deepseek-v4-flash
  aggregator_fallbacks:
    - deepseek/deepseek-v4-pro     # tried first when the aggregator call fails
    - openrouter/anthropic/claude-sonnet-4.6
    - "default"                    # alias for defaults.default_aggregator
```

Semantics:

* **Ordered.** The first entry that can serve produces the merge; the run exits 0
  and `trace.aggregator_model` names the model that actually answered, while
  `trace.aggregator_fallbacks` lists every entry in order with `served` / `failed`
  / `skipped` **and the skip reason** (unknown or disabled model, provider without a
  credential, quota-dead account, the failed model itself, attempt budget).
* **Skipped, not called.** An entry that provably cannot help costs no provider
  latency. At most 4 ordinary fallback candidates are called per merge. After
  the configured and implicit candidates, one additional call is reserved for
  a model that successfully served a worker or dispatcher stage in this run;
  it skips credential checks but remains subject to quota and model checks.
  Its trace entry has `source: "this_run_survivor"`.
* **`lock_aggregator` does not disable the chain.** The lock forbids ad-hoc
  per-request `aggregator_model` overrides, not resilience.
* **Formations override.** A named formation may set its own
  `aggregator_fallbacks`; that list REPLACES the defaults for that formation. An
  explicit empty list (`aggregator_fallbacks: []`) disables the chain for that
  formation; omitting the key inherits `defaults.aggregator_fallbacks`.
* **Empty list keeps implicit resilience.** With no configured chain, the default
  aggregator, implicit replacement and this-run survivor tail remain available.
* **Still no usable answer?** If no chain entry can serve the merge while at least
  one worker succeeded, the run exits non-zero but the paid worker outputs are
  preserved on the `--json` payload (`worker_outputs`, with
  `answer_degraded_reason: "workers_preserved"`) instead of being discarded.

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

### Rank-then-fuse: `rank` / `kappa` / `rank_model`

Optional pre-merge ranking (LLM-Blender PairRanker class, DF-CHIMERA-V2-102).
When a formation sets `rank: true`, one cheap **scorer call** scores every
upstream output *before* the merge, the candidates are sorted by score, and only
the top `kappa` of them reach the aggregator prompt:

```yaml
ranked-fanout:
  workers: 5
  aggregator: default
  rank: true          # default false → pre-merge behaviour is unchanged
  kappa: 2            # default 3 — how many candidates reach the merge prompt
  rank_model: deepseek/deepseek-v4-flash   # optional; default = the aggregator's model
```

| key | default | meaning |
| --- | --- | --- |
| `rank` | `false` | Rank the upstream outputs before the merge. `false` feeds every output straight to the aggregator, exactly as before. |
| `kappa` | `3` | How many candidates reach the merge prompt (must be `>= 1`). Only applies when there are **more** candidates than `kappa` — with 3 or fewer outputs nothing is dropped and no scorer call is made. |
| `rank_model` | `null` | Model alias for the scorer call. `null` scores with the aggregator stage's own model. Point it at a budget model to keep the extra call cheap; an unknown or disabled alias falls back to the stage model with a `rank_model_unusable` warning instead of failing the run. |

The scorer is one bounded call over all candidates (each output capped at
~6k characters), asked for a single JSON object
`{"scores": {"<stage id>": <number>}}`. Answers in other shapes — a bare
`{id: score}` map, numbers as strings, prose with `id: 5` — are all accepted.

**Ranking is best-effort, never lossy.** If the scorer call fails (provider
error, budget) or answers with no recoverable score, the merge falls back to
feeding **every** upstream output, and the failure is recorded on the
aggregator's trace span as `rank_error`. A candidate with no score of its own
sorts after every scored candidate — an absent score is never treated as a good
one.

**What the trace records** (aggregator span):

| field | meaning |
| --- | --- |
| `ranked_candidates` | every scored candidate, in rank order, with `stage_id`, `model`, `score`, `rank` (1-based) and `kept` (whether it reached the merge prompt). Dropped candidates are traced too, so the decision is auditable. |
| `rank_kappa` | the `kappa` that applied (`null` when no ranking ran) |
| `rank_model` | model that served the scorer call (`""` when no ranking ran) |
| `rank_tokens_input` / `rank_tokens_output` / `rank_cost` | the scorer call's real spend — kept separate from the merge call's own `tokens_*`/`cost`, and included in the run's `total_tokens`/`total_cost` |
| `rank_error` | why ranking did not take effect (`null` on success or when no ranking was attempted) |

A ranked aggregator span's `prompt` is the merge prompt that was actually sent
(the top-`kappa` outputs only, each tagged `[rank i/n, score s]`, plus a note
naming how many candidates were omitted) — so a trace is direct evidence of
what was fed. Un-ranked runs keep their compact prompt summary unchanged.

#### The dispatcher call: skipped for explicit formations (PERF-2)

A custom DAG or any named non-auto preset is **executed without a dispatcher
model call**. The config already fixes the full structure and every model, so
Chimera synthesizes the plan deterministically instead of paying a provider
round-trip to restate it:

- workers receive the templated task prompt (`You are worker '<id>'. Solve the
  user's request as completely as you can.` — the same text the
  dispatcher-failure fallback has always used);
- `aggregator` / `merge` / `audit` stages receive the aggregator module's
  built-in per-kind instructions;
- `trace.dispatch` is `null` in the JSON trace (not a zeroed span), and the
  run's `total_cost` / `total_tokens` cover the stage calls alone.

Measured on the run-30 budget panel (two stub workers + one merge, dispatcher
on a real DeepSeek model): the explicit formation used to pay **14.5 s of a
22.5 s wall — 64 % — and 100 % of the run's cost ($0.001387, 1070 prompt +
2044 completion tokens)** for that one call. With the skip, the same command
runs in ~8.1 s at $0.00 (stub stages only).

To restore the dispatcher-authored fill-in pass (task-specific per-worker
prompts and merge instructions, at the latency/cost above), set
`dispatch_prompts: true` on the formation:

```yaml
my-chain:
  dispatch_prompts: true   # one extra dispatcher call per run (opt-in)
  dag:
    stages: ...
```

`dispatch_prompts` only ever adds the call back for an explicit formation;
`auto` formations always keep the dispatcher, unchanged.

### Per-formation merge fallback: `aggregator_fallbacks`

A formation may carry its own merge fallback chain (same semantics as
`defaults.aggregator_fallbacks`); when present it REPLACES the defaults for that
formation:

```yaml
review:
  workers: 3
  aggregator: default
  aggregator_fallbacks:            # replaces defaults.aggregator_fallbacks here
    - openrouter/anthropic/claude-sonnet-4.6

paper-only:
  workers: 2
  aggregator: default
  aggregator_fallbacks: []         # explicit: no chain for this formation
```

Omitting the key inherits `defaults.aggregator_fallbacks`. `lock_aggregator`
never disables the chain.

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
  explicit configuration and is honored verbatim. Since PERF-2 they also skip
  the dispatcher call entirely (see
  [Custom DAG](#custom-dag-fully-defined-structure)); `dispatch_prompts: true`
  on a formation opts back into it.
- Request-level overrides remain authoritative:
  `allowed_models`, `worker_model`, `stage_models`, `dispatcher_model`, and
  `aggregator_model` behave exactly as documented and can force any catalog
  model, credentialed or not.

**Blocked-model registry (three classes).** When a call fails with a
*permanent-for-this-key* or *funding* error, the model is recorded in a
blocked-model registry and excluded from the auto dispatcher catalog, the
category selector, and engine stage selection:

| Class | Trigger | Block TTL |
|---|---|---|
| `guardrail` | guardrail/privacy/endpoint-availability rejection (`No endpoints available matching your guardrail restrictions…`) | 7 days |
| `credential` | `401` / `AuthenticationError` / "invalid api key" — present-but-invalid key | 7 days (self-clears when the key changes) |
| `quota` | `402` / `insufficient_quota` / "Insufficient balance … recharge" — empty account balance | 15 minutes (`DEFAULT_QUOTA_BLOCK_COOLDOWN_S`) |

Blocks are **persisted to a state file scoped to the current install**
(see [Blocked-models state file](#blocked-models-state-file)), so a fresh
process never re-picks a known-blocked model. Timeouts, `429` rate limits and
`5xx` are transient and **never** block a model — a `5xx` or a timeout is
refused structurally, no matter what its message says.

The `quota` class is deliberately short-lived and separate from `credential`:
an empty balance is fixed by a top-up, not by rotating a perfectly good key.
Quota exhaustion is an **account-level** condition, so a verdict or block on
one model covers every model of that provider. Selection consults two
TTL-bounded signals **at the start of every run**: the live `/v1/health`
provider snapshot (`error_class: quota`) and the recorded blocks. Neither is
cached across runs in the engine.

- A stage whose model is quota-excluded is remapped to the next healthy
  candidate (`defaults.default_worker` / `defaults.default_aggregator` when
  healthy, else the first healthy catalog model) — for **workers and
  aggregator/merge/audit alike**. This is the one exception to "operator
  choices are not filtered": a call to an account with no budget cannot
  succeed. A failed aggregator stage retries on a healthy model too.
- When *nothing* healthy is left, the run fails with a machine-readable
  `503` (`error.type: no_healthy_candidate`) listing every skipped candidate
  with its provider, model and failure class — `POST /v1/deliberate` and
  `POST /v1/chat/completions`. The CLI prints the same message and exits `2`.
  No provider call is spent discovering that.
- `/v1/health` keeps reporting `status: degraded` / `error_class: quota` for
  the dead provider while deliberations succeed on another one — the snapshot
  is consulted, never masked.
- `defaults.dispatcher` is not remapped (a named preset skips the dispatcher
  call entirely; `auto` still uses the configured dispatcher).
- If *no* provider has resolved credentials, the restriction is skipped with
  an actionable warning so the failure surface stays the real provider auth
  error rather than an empty catalog — and the no-candidate error is NOT
  raised, because absent keys are not quota evidence.

### Blocked-models state file

The registry persists to a state file resolved **per install, not per
machine** (CHIMERA-V2-REVIEW-03 — the old machine-wide
`~/.chimera/blocked-models.json` made a fresh clone inherit every block ever
recorded on the host, including credential blocks for providers the new
install had never configured). Resolution order, applied when the registry
is constructed:

1. `$CHIMERA_BLOCKED_MODELS_PATH` when set — pin one explicit file (deploys,
   tests);
2. else `<repo>/.chimera/blocked-models.json` for the nearest enclosing
   checkout (walks up from the working directory to the first
   `pyproject.toml`) — a fresh clone starts with an empty registry, two
   checkouts never see each other's blocks, and `.chimera/` is gitignored;
3. else the legacy `~/.chimera/blocked-models.json` (bare pip installs
   outside any checkout) — kept for compatibility and announced with a
   `UserWarning` because that location is shared by every chimera process
   on the machine.

`chimera models` renders the actual state file in its `Blocked models`
header, and the per-failure `credential failure` hint names it too — follow
the printed path, never an assumed one. Blocks recorded before this change
remain in the legacy home file and are simply no longer read; delete that
file when nothing on the host still runs an old chimera.

---

## `timeout`

Wall-clock budgets, in seconds — the first thing to look at when a run reports a
dropped stage. A stage that exceeds its budget is **not** fatal: the deliberation
continues without it (the resilience contract), the trace records it in
`worker_failures`, and the CLI prints a `warning:` line naming the dropped stage
(see [USAGE.md](USAGE.md)).

```yaml
timeout:
  per_stage_s: 120        # one worker/aggregator/merge/audit stage
  total_s: 300            # the whole deliberation
  idle_s: 30              # inter-token stall, only with min_tokens_per_second
  min_tokens_per_second: 0    # >0 lets a productive stage run past per_stage_s
  connect_s: 10           # TCP/HTTP connect
  read_s: 30              # socket read
  retry_s: 60             # retry budget inside one stage
```

- `per_stage_s` — **the knob to raise first.** The default is 120 s, which is
  what a slow reasoning model on a large prompt hits first; a run that answers
  "from 1 of 2 reviewers" was almost always this budget. `0` (or a negative
  value) disables the per-stage budget entirely.
- `total_s` — end-to-end cap for one deliberation; a per-stage budget is clamped
  to it.
- The same budget is available per request on the REST surface
  (`X-Chimera-Timeout`), and a request can only *lower* the configured ceiling.
  The header's grammar is `total=<seconds>,per_stage=<seconds>` — either pair
  may be omitted, and `0` disables that override for the request. A part that
  cannot be parsed, is missing its `=`, or names a key other than `total` /
  `per_stage` is rejected with HTTP 400 naming the offending pair rather than
  being ignored, and no part of such a header is applied.

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
(`chimera.yaml.fleet`, `chimera.yaml.docker`, and the minimal
`chimera.yaml.example`), the live catalog and the
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

The examples on this page are already percent-correct (plain 0–100 integers),
so a catalog copied from them loads with no rescale warnings.

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

### Learning category scores from stored traces

`scripts/bandit_lite.py` turns the traces Chimera already stores into bounded
score corrections, so a catalog does not have to be hand-tuned forever. It reads
the `{"answer", "trace"}` documents written from `chimera --json run` (a file, a
directory of them, or JSONL) and scores one observation per worker/aggregator
stage: an accept when the stage produced an answer, a reject when the trace shows
a degraded placeholder, an empty or truncated (`finish_reason: "length"`)
response, a `degraded` flag, or a `worker_failures` entry naming that stage. The
category is the stage's own `category` field when a trace carries one, otherwise
the selector's keyword path for the stage prompt — resolved to the catalog key
with the same exact / parent / alias precedence the selector uses, so the number
adjusted is the number actually scored.

For one `(model, category)` pair with `a` accepts and `r` rejects:

```text
delta = clamp(step * (a - r) / n, -step, +step)
new   = clamp(score + delta, floor, ceiling)
```

A pair therefore moves at most `--step` points per run (default 2), never leaves
`--floor`/`--ceiling` (default 1 / 99), and never moves at all below
`--min-samples` observations (default 5) — a no-op on insufficient evidence
rather than a drift on noise.

**Dry run is the default**: the script prints the proposed table and writes
nothing. `--write` applies the deltas, rewriting only the matched score lines
(comments and ordering survive); a match it cannot locate unambiguously aborts
the run with nothing written, and shipped templates are never write targets.

```bash
.venv/bin/python scripts/bandit_lite.py --traces traces/            # dry run
.venv/bin/python scripts/bandit_lite.py --traces traces/ --write    # apply
```

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

### Model catalog source: the task-router registry (env overrides)

`chimera models`, provider discovery and `scripts/model_sync.py` read the model
catalog from task-router's generated JSONL registry. Two environment variables
control where that registry is found:

| Env var | Meaning |
|---|---|
| `CHIMERA_TASK_ROUTER_MODELS_PATH` | Explicit path to a `models.jsonl` table. Authoritative — it wins even when it points at a missing file, so a wrong path produces a clear diagnostic instead of silently reading a different checkout. |
| `TASK_ROUTER_HOME` | Path to a task-router checkout. The registry is read from `<home>/data/tables/models.jsonl`. |

Default discovery order when neither is set: `~/task-router/data/tables/models.jsonl`
(the home checkout), then a `task-router` checkout sibling to the installed package.
The chimera adapter depends only on the JSONL wire format — the task-router Python
package or checkout is never imported, so wheels stay portable. Registry selection
is logged at startup (`registry_source_selected`); `chimera models` refreshes and
probes the resolved source. When `model_sync.py` cannot find a registry, its error
remedy names `CHIMERA_TASK_ROUTER_MODELS_PATH` (or running `chimera models`) as the fix.

#### How a discovered price is resolved (per provider)

Every registry block publishes prices for the models it serves, and several
blocks routinely carry the **same** model id (a lab's own row plus the rows of
any gateway reselling that model). A discovered price is therefore keyed by
`(provider, model id)` — the provider being the block that published it — and a
catalog entry is priced through **its own `provider` label first**:

| Resolution | Source | Notes |
|---|---|---|
| `provider` | The block named by the entry's `provider` field. | Authoritative. Another provider's row for the same model id cannot price the entry. |
| `unattributed` | The provider-agnostic winner across all blocks. | Only when the entry's provider publishes no row for that id. Kept for coverage; the block it came from is recorded, so the fallback is never silent. |
| `catalog` | The entry's own `cost_per_1k_*` declaration. | Always wins; discovery never overwrites it. |
| *(none)* | Nothing discovered and nothing declared. | The `cost_tier` default from the table above applies. |

`load_config()` records the outcome per model in the internal
`ChimeraConfig.cost_provenance` map (`{"tier", "registry", "source_provider",
"source_model"}`) — load-time bookkeeping, excluded from every serialization —
so a rate in a trace can be traced back to the registry row that produced it.
An alias table (`MODEL_ID_MAP`) canonicalizes model **ids** (e.g. DeepSeek's own
`deepseek-flash` and the catalog's `deepseek/deepseek-v4-flash` are the same
SKU); it never merges two providers' rows for the same id.

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
keyless **for credential-error diagnostics**: errors keep their raw upstream
text instead of naming an env var that does not exist. This does not guarantee
that the OpenAI-compatible SDK can run without a key. For a reproducible local
fixture, explicitly pass a dummy key as in the example below.

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

#### Minimal local fixture

This smoke test needs no real provider, model download, task-router registry,
or real credential. Run from the root of a fresh clone. Install the dev extra
because the fixture reuses the repository's pytest-backed loopback helper:

```bash
uv venv
UV_LINK_MODE=copy uv pip install -e '.[dev]'
```

Save the following complete config as `local-fixture.yaml` in that checkout;
do not merge in the shipped template's `api_keys` or defaults:

```yaml
provider_discovery: false
providers:
  mock:
    base_url: http://127.0.0.1:18081/v1
    api_key_env: CHIMERA_LOCAL_FIXTURE_KEY
models:
  mock/m1:
    provider: mock
    cost_tier: budget
    categories:
      code: 90
defaults:
  dispatcher: mock/m1
  default_worker: mock/m1
  default_aggregator: mock/m1
formations:
  simple:
    workers: 1
    aggregator: default
```

In terminal 1, start the existing hermetic OpenAI-compatible test fixture:

```bash
.venv/bin/python -u -c 'from threading import Event; from tests.test_gateway_custom_base_url import _compat_stub; exec("with _compat_stub(port=18081) as (url, seen):\n    print(url, flush=True)\n    Event().wait()")'
```

Wait for `http://127.0.0.1:18081/v1` to print. The fixture binds only to loopback,
returns `STUB-OK`, and is not a production server or an authentication validator.
If either demo port is occupied, stop the demo and choose unused ports, updating
the config/fixture port together and the serve/curl port together; do not probe
an unrelated service already listening there.

In terminal 2 (also at the checkout root), export the **value** of the dummy
credential in the same shell that launches Chimera, then start the REST server:

```bash
export CHIMERA_LOCAL_FIXTURE_KEY=local-fixture-only
.venv/bin/chimera --config local-fixture.yaml serve --host 127.0.0.1 --port 18082
```

After server startup, in terminal 3:

```bash
curl --noproxy '*' -sS -i http://127.0.0.1:18082/v1/deliberate \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"hello","formation":"simple"}'
```

Expected: HTTP **200**, `answer: "STUB-OK"`, and
`trace.credential_sources.mock: "process_env"`. Every upstream request goes to
`/v1/chat/completions` with model `m1` and `Authorization: Bearer local-fixture-only`.
The `simple` formation uses the configured default worker/aggregator; this is a
transport/config smoke test, not a demonstration of multi-model answer quality.
Use Ctrl-C in terminals 1 and 2 to stop both servers.

**Credential shape matters, including on loopback.** `api_key_env` is the
variable's **name**; exporting that variable supplies its value at config load
(process env first, then `.env` beside the config, then `~/.hermes/.env`). A
variable name alone is not a credential. No top-level `api_keys` is needed for
the example. Alternatively, remove `api_key_env` and add
`api_keys: {mock: "${CHIMERA_LOCAL_FIXTURE_KEY}"}` at the top level, keeping the
same export. `api_keys.mock` is checked first: an empty string (including an
unresolved `${VAR}`) shadows the provider-entry key; omit the shortcut rather
than leaving an empty one. A dummy literal `providers.mock.api_key:
local-fixture-only` also works for this fixture, but never inline real secrets.
These details match `load_config()` / `_resolve_provider_api_keys()` in
`src/chimera/config.py` and `LiteLLMGateway.complete()` in `src/chimera/gateway.py`.

**Negative control:** stop terminal 2, run `unset CHIMERA_LOCAL_FIXTURE_KEY`, and
restart the same serve command without exporting a key. On a fresh clone with
no matching dotenv entry or ambient OpenAI SDK key, the same POST returns HTTP
**502** with `error.type: "upstream_error"` and a message naming
`CHIMERA_LOCAL_FIXTURE_KEY`. `GET /v1/health` additionally reports
`details.providers.mock.error_class: "missing_credentials"`. A reachable
loopback address does not make this SDK path keyless. The recipe deliberately
passes a dummy key instead of depending on SDK-global credentials or implicit
keyless behavior. The hermetic regression strips those ambient credentials and
tests both copies of this YAML:

```bash
.venv/bin/python -m pytest tests/test_credential_source.py -k documented_local_fixture -q
```

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
endpoint in front of a large multi-prefix catalog (323 models across 16
upstream prefixes, measured 2026-10-19 — `ds/`, `mmx/`, `minimax/`, `kimi/`,
`openrouter/`, `xai/`, `ollama/`, …). It answers on
`http://master001:20128/v1` (the host is
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

### Catalog entries are required for dispatch

Adding `providers.<name>` wires up *routing* — it does not by itself make any
model reachable. A model id is dispatchable only when it has its own
`models.<id>` catalog entry: formations, client DAGs and every per-request
override (`worker_model`, `stage_models`, `aggregator_model`) validate against
the catalog, so an id missing from `models:` is rejected with an HTTP 400
"unknown model" even though its provider is fully configured. For a gateway
serving hundreds of models behind one `base_url`, that means each id you
actually want to dispatch needs an explicit entry — deliberately, so cost
tier, category scores and `enabled` stay per-model decisions instead of
inheriting whatever the gateway happens to list (GET /v1/models shows exactly
which ids the catalog knows):

```yaml
providers:
  router9:
    base_url: http://master001:20128/v1
    api_key_env: ROUTER9_API_KEY

models:
  router9/ds/deepseek-v4-flash:      # dispatchable: has a catalog entry
    provider: router9
    cost_tier: budget
    categories:
      technology_code/code_generation/python: 88
  # router9/ds/deepseek-v4-pro is NOT dispatchable yet — the provider can
  # route it, but until a `models:` entry exists it fails with 400
  # "unknown model"; add the entry (provider + cost_tier + categories).
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
  `error_class: "slow"` with the measured latency and named in the top-level
  `slow_providers` array — NOT as a degradation, because nothing about that
  provider was measured beyond its latency (DF-CHIMERA-V2-27: the `hermes`
  gateway injects a ~43.6k-token system prompt and needs ~108 s for a 1-token
  probe, which used to make `/v1/health` read `degraded` permanently and hid a
  real outage). Keep `health_timeout_s` above the gateway's own latency if you
  want the probe to actually wait for it. A probe still outstanding at the
  deadline gets `server.health_probe_grace_s` extra seconds (default `1.0`) to
  land before it is classified `slow` (DF-CHIMERA-V2-17). To stop probing such
  a provider entirely, set `health_probe: false` on its `providers.<name>`
  entry: it is then reported `probe_skipped`, named in
  `probe_skipped_providers`, and does not satisfy `/v1/health/ready` — keep at
  least one live-probed provider.
- **A lane behind a routing gateway can be out of quota.** 9router serves each
  upstream prefix from its own account, so one exhausted lane answers
  `429`/`403` for every model behind it while the gateway itself is healthy and
  other prefixes keep working. That is a provider-side condition, not a Chimera
  defect: point the formation at another prefix's model instead of
  re-dispatching at the same one.

---

## Credential Sources

Chimera records **where each provider's API key came from** at config-load
time, and publishes that map on every deliberation trace and on `/v1/health`
(DF-CHIMERA-V2-90). It exists to make one situation visible: a deliberation
that succeeds only because a host-level `~/.hermes/.env` quietly supplied the
key is otherwise indistinguishable from a properly configured install. The
call works, so nothing tells you the key was never configured where you
thought it was.

Only source **labels** travel — key values are never recorded, logged, traced
or served.

### Resolution chain (recorded, not changed)

The order a provider key is resolved in is unchanged; the source label only
records which step succeeded:

| # | Source | Label | Meaning |
|---|---|---|---|
| 0 | `api_keys.<provider>` holding a literal key | `api_keys` | The gateway consults the shortcut first, so a non-empty literal **is** the credential it uses (CHIMERA-V2-REVIEW-08 — previously mislabeled `missing`). |
| 0 | `api_keys.<provider>` = `` `${VAR}` `` | rows 2-4, or `missing` | A token is judged by the provenance of the env var it names, never by the entry name. |
| 1 | `providers.<name>.api_key` (literal key) | `provider.api_key` | An inline key wins and the env resolver never runs for that provider (applies when no `api_keys` entry covers it). |
| 2 | Process environment (`api_key_env` first, then the canonical name, then `<PROVIDER>_API_KEY`) | `process_env` | Exported in the environment that launched Chimera — systemd `Environment=`/`EnvironmentFile=`, shell export, container env. |
| 3 | Repo-level `.env` beside `chimera.yaml` | `repo_dotenv` | Injected into the process env at load time, and only for variables the real environment did **not** already set, so row 2 keeps precedence. |
| 4 | `~/.hermes/.env` | `hermes_dotenv_fallback` | Host-specific Hermes dotenv, consulted only when the variable is absent from the process env. **The one source a user would not expect.** |
| — | none of the above | `missing` | Nothing satisfied the key; the provider is unusable until something does. |

Both credential shapes are covered: `providers.<name>.api_key_env` (explicit)
and the shipped-template `api_keys: {deepseek: ${DEEPSEEK_API_KEY}}` shortcut.
For an `api_keys` entry the provenance is read from the `${VAR}` token itself,
so `acme: ${ACME_TOKEN}` is judged by `ACME_TOKEN`'s origin rather than a
guessed `ACME_API_KEY` name; a **literal** value in the shortcut is labeled
`api_keys` directly, because that exact value is what the gateway consults
first.

A provider with **no entry at all** is one the resolver never looked at — a
provider added by auto-discovery, or a config object built
programmatically. Absent means *unknown*, not `missing`: never read absence as
either success or failure. A config built in code records no provenance, so
the trace field is an empty object there — the field is additive and never
fabricated.

### Where to read it

| Surface | Path | Notes |
|---|---|---|
| Deliberation trace | `trace.credential_sources` | On `POST /v1/deliberate`, the OpenAI-compatible response, and `chimera --json run`. |
| Health | `GET /v1/health` → `details.credential_sources` | Operator/dashboard view of the loaded config. |
| Config object | `ChimeraConfig.credential_sources` | Load-time bookkeeping; `exclude=True`, so it is not part of the config's own YAML/JSON serialization. |

```json
{
  "trace": {
    "request_id": "…",
    "credential_sources": {
      "deepseek": "process_env",
      "openrouter": "repo_dotenv",
      "zai": "hermes_dotenv_fallback",
      "anthropic": "missing"
    }
  }
}
```

```bash
# operator check: which source satisfied each key on the running service?
curl -s localhost:8765/v1/health | jq '.details.credential_sources'
```

### The `api_key_source_fallback` warning

When a key resolves from `~/.hermes/.env`, the config loader emits exactly one
WARNING per provider per config load through the structlog pipeline
(`chimera.config` logger):

```json
{"provider": "deepseek", "env_var": "DEEPSEEK_API_KEY", "source": "hermes_dotenv_fallback", "path": "~/.hermes/.env", "event": "api_key_source_fallback", "level": "warning", "timestamp": "2026-10-16T04:24:49.123456Z"}
```

The CLI and the MCP stdio transport pin that stream to **stderr** (so a
machine-mode `--json` stdout stays exactly one JSON object); the API server
follows `observability.use_stdout` (stdout by default), so there the line
lands in the server's normal log stream.

It names the provider, the env var and the file — never the value. `source` is
always `hermes_dotenv_fallback`, `path` is the display path of the fallback
file, and `env_var` is the variable the provider actually reads (`api_key_env`
when set, else the token from an `api_keys` entry).

Read it as a **portability warning**, not an error: the install works on this
host and will not work on one without that file. The remedy is to set the
variable where the deployment actually reads credentials — the unit's
`Environment=`/`EnvironmentFile=`, the container environment, or the repo
`.env` next to `chimera.yaml` — not to change the resolution order, which
already prefers both of those. The operator checklist (including the
`missing` case) is in
[INTEGRATION.md → `api_key_source_fallback`](INTEGRATION.md#api_key_source_fallback-what-operators-should-do).

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

| Field | Type | Default | Description |
|---|---|---|---|
| `host` | `string` | `0.0.0.0` | Bind address |
| `port` | `int` | `8765` | Listen port |
| `health_timeout_s` | `float` | `10.0` | Wall-clock budget, in seconds, for the provider connectivity probe behind `/v1/health` and `/v1/health/ready`. All provider probes run concurrently under this one budget; a provider that has not answered inside it is reported `timeout` (probes still outstanding at the deadline then get `health_probe_grace_s` extra seconds — see below), and one that answers later than this budget is classified `slow` with its measured latency and named in `slow_providers` rather than counted as a degradation (DF-CHIMERA-V2-27). Raise it above a routing gateway's own latency — e.g. the `hermes` gateway injects a ~43.6k-token system prompt and needs ~108 s for a 1-token probe — if you want the probe to actually wait for that provider. |
| `health_probe_grace_s` | `float` | `1.0` | Extra patience, in seconds, for probes still outstanding when the shared `health_timeout_s` budget expires (DF-CHIMERA-V2-17). A probe that lands inside the grace reports its real verdict (`quota` / `auth` / `api` plus `model_tested`) instead of a fabricated `timeout` — this keeps the first `/v1/health` after a process restart honest while LiteLLM's one-off client/TLS/provider-discovery warm-up (measured ~10.3 s cold vs ~2.8-3.2 s warm) briefly exceeds the budget. `0` disables the grace and reproduces the previous cancel-at-deadline behaviour exactly. |
| `litellm_prewarm` | `bool` | `true` | Fire a non-blocking LiteLLM warm-up when the API server starts (CHIMERA-V2-REVIEW-04). The first deliberation on a cold process pays a one-off LiteLLM initialization cost inside its dispatch stage (~2.6s measured; ~1.5s of it is the lazy `import litellm`). With the default `true`, the server's lifespan schedules that same one-time initialization at startup in the background, so the first real request arrives on a warm module. The warm-up runs offline (an instant `mock_response` completion — no network, no credentials) and never delays startup or raises into the app. Set to `false` to restore exact cold-start behaviour: no startup warm-up, and the first deliberation pays the initialization cost itself. |

### Auto-discovered providers and the health report

Provider auto-discovery registers every registry provider whose API key resolves,
so the in-memory `providers` map can hold names this file never declared.
`/v1/health` keeps them out of its verdict and names them in the top-level
`discovered_not_configured` array: providers that exist on the host (a key
resolved) but that no `models:` entry references, so there is nothing to probe
and nothing to conclude about their reachability. The array is informational —
a non-empty value on a deployment you never configured is expected, not a fault:

```json
"discovered_not_configured": ["openai", "xai"]
```

- **To use one of them**, add a `models:` entry for one of its ids. It becomes
  probe-able, leaves the array, and joins the `status` / `unhealthy_providers`
  math (see [Catalog entries are required for dispatch](#catalog-entries-are-required-for-dispatch)).
- **To make one disappear**, remove its key from the resolved environment
  (process env → repo `.env` → `~/.hermes/.env`); discovery only registers a
  provider whose key resolved.
- **A declared provider is never in this array.** A provider you configured but
  left without models still degrades `status`, exactly as it did before
  auto-discovery existed.

Full response schema, the sibling arrays (`unhealthy_providers`,
`slow_providers`, `probe_skipped_providers`) and the cache/`age_s` semantics are
in [docs/OPENAI_API.md](OPENAI_API.md#v1health).

---

## `retry`

Exponential backoff retry policy for provider calls (the F7 policy in
`gateway._complete_with_retry`). A transient provider failure is retried with
a delay that starts at `base_delay_ms` and is multiplied by
`backoff_multiplier` after each attempt, capped at `max_delay_ms`, until
`max_attempts` tries have been made.

| Field | Type | Default | Description |
|---|---|---|---|
| `max_attempts` | `int` | `3` | Total tries for one provider call, including the first |
| `base_delay_ms` | `int` | `500` | Delay before the first retry, in milliseconds |
| `max_delay_ms` | `int` | `10000` | Upper bound for any single backoff delay, in milliseconds |
| `backoff_multiplier` | `float` | `2.0` | Factor each successive delay is multiplied by |

```yaml
retry:
  max_attempts: 3
  base_delay_ms: 500
  max_delay_ms: 10000
  backoff_multiplier: 2.0
```

With the defaults the retry delays are 500 ms then 1000 ms — a provider call
is attempted at most 3 times over roughly 1.5 s of backoff before the failure
is surfaced (and recorded against the provider's circuit breaker, when one is
configured).

---

## `queue`

In-memory request queue / backpressure configuration (F5) for the REST API.

| Field | Type | Default | Description |
|---|---|---|---|
| `max_concurrent` | `int` | `10` | Maximum requests processed at the same time |
| `max_queue_depth` | `int` | `100` | Maximum requests held waiting once `max_concurrent` are in flight |

```yaml
queue:
  max_concurrent: 10
  max_queue_depth: 100
```

Requests beyond `max_concurrent` wait in the queue; once the queue itself is
full (`max_queue_depth` waiting), further requests are refused rather than
buffered, so load sheds at the edge instead of growing memory unboundedly.

### Queue feedback

A queued request used to be silent: under concurrency, `POST /v1/deliberate`
(and the `POST /v1/chat/completions` drop-in, which shares the same queue)
returned no per-request signal, so four simultaneous deliberations came back
with 18.9-49.4 s of wall-time variance and the client could not tell it had
waited behind other work at all.

Every deliberation response now carries:

| Header | Value |
|---|---|
| `X-Chimera-Queue-Position` | The request's **1-based arrival rank**: how many requests, including itself, were inside the queue when it entered. `1` means nothing else was queued at entry. |

The rank is an ordering signal, **not** a wait-time estimate and **not** a
promise of a slot. With the default `max_concurrent: 10`, four simultaneous
requests all enter immediately (ranks `1`-`4`) and none of them waits on this
queue — their wall-time spread is model/provider bound upstream. A rank above
`max_concurrent` is the one that means the request genuinely parked behind
busy slots. The header is absent on the `503` refusal path, because a refused
request never entered the queue.

---

## `auth`

Authentication configuration for the REST API. Disabled by default — every
request is then served as `anonymous` with no credential check.

| Field | Type | Default | Description |
|---|---|---|---|
| `enabled` | `bool` | `false` | Master switch; `false` serves every request without a key |
| `mode` | `string` | `env` | Key source: `env` (one shared key) or `list` (named keys from config) |
| `keys` | `list` | `[]` | `AuthKeyEntry` items used by `list` mode (see below) |

Clients pass the key in the `Authorization: Bearer <key>` header or the
`X-API-Key` header. A missing key is answered `401 Missing API key`, a wrong
one `401 Invalid API key`.

**`env` mode** — one shared key read from the `CHIMERA_API_KEY` environment
variable (never from the YAML file):

```yaml
auth:
  enabled: true
  mode: env
```

Set `CHIMERA_AUTH_ENABLED=true` to flip `enabled` on without editing the
file. If `enabled: true` with `mode: env` but `CHIMERA_API_KEY` is not set,
the server still starts but prints a loud startup warning — every
authenticated call would be rejected with `401 Invalid API key` — telling you
to export `CHIMERA_API_KEY` and restart.

**`list` mode** — any number of named keys declared in the config; each
request is matched against the list and served under that entry's `name`:

```yaml
auth:
  enabled: true
  mode: list
  keys:
    - key: ${CHIMERA_KEY_ALICE}   # ${VAR} substitution — never inline a real key
      name: alice
    - key: ${CHIMERA_KEY_CI}
      name: ci-runner
```

Each `keys` entry is an `AuthKeyEntry`:

| Field | Type | Default | Description |
|---|---|---|---|
| `key` | `string` | — (required) | The credential value; use `${VAR}` substitution, never a literal key |
| `name` | `string` | `default` | Label the request is served under when this key matches |

Use `list` mode when callers should be distinguishable (per-user or
per-integration keys); use `env` mode for a single shared deployment key.
Never commit real key values — `${VAR}` tokens resolve from the process
environment, the repo `.env`, or `~/.hermes/.env` at load time.

---

## `rate_limit`

In-memory token-bucket rate limiting for the REST API. Disabled by default;
`CHIMERA_RATE_LIMIT_ENABLED=true` flips it on without editing the file.

| Field | Type | Default | Description |
|---|---|---|---|
| `enabled` | `bool` | `false` | Master switch; `false` allows every request |
| `requests_per_minute` | `int` | `60` | Sustained rate per client — tokens refill at this many per minute |
| `burst_size` | `int` | `10` | Bucket capacity per client — the maximum burst above the sustained rate |

```yaml
rate_limit:
  enabled: true
  requests_per_minute: 60
  burst_size: 10
```

Each client gets its own bucket, created full at `burst_size` tokens and
refilled steadily at `requests_per_minute / 60` tokens per second. A request
consumes one token; when the bucket is empty the request is rejected and the
response carries the estimated seconds until the next token
(`retry_after`). Buckets are in-memory only — a restart resets every client's
allowance.

---

## `circuit_breakers`

Per-provider circuit breakers, protecting a deliberation from cascading
failures when a provider is consistently erroring. The value is a **mapping
from provider name to a `CircuitBreakerConfig`**; a provider with no entry
gets no breaker unless a `default` entry is configured, in which case the
`default` settings are used to create a breaker for it on first use.

```yaml
circuit_breakers:
  default:                    # applied to any provider without its own entry
    failure_threshold: 5
    recovery_timeout_s: 30
    half_open_max_requests: 1
  deepseek:                   # per-provider override
    failure_threshold: 3
    recovery_timeout_s: 60
    half_open_max_requests: 1
```

Each entry:

| Field | Type | Default | Description |
|---|---|---|---|
| `failure_threshold` | `int` | `5` | Consecutive failures that trip the breaker OPEN |
| `recovery_timeout_s` | `int` | `30` | Seconds an OPEN breaker waits before allowing a trial request |
| `half_open_max_requests` | `int` | `1` | Trial requests allowed through while testing recovery |

The breaker is a three-state machine per provider:

- **CLOSED** — normal operation; calls proceed and failures are counted.
- **OPEN** — after `failure_threshold` consecutive failures; calls fail fast
  without touching the provider.
- **HALF_OPEN** — after `recovery_timeout_s`; up to `half_open_max_requests`
  trial calls are let through. A success closes the breaker; a failure
  re-opens it for another recovery window.

---

## `selector`

Model selection strategy — how the category-weighted selector balances
quality against cost when it scores models for a task.

| Field | Type | Default | Description |
|---|---|---|---|
| `price_sensitivity` | `float` | `0.0` | How much cost influences selection; range `0.0`–`1.0` (enforced at load) |

```yaml
selector:
  price_sensitivity: 0.0      # default — matches chimera.yaml.example
```

- `0.0` — **pure quality**: cost is ignored; the highest category-scored
  model wins.
- `0.5` — **balanced**: quality and cost weigh equally.
- `1.0` — **pure cheapest-that-works**: the cheapest adequate model wins.

Values outside `0.0`–`1.0` are rejected by config validation. Cost figures
come from the model's `cost_per_1k_*` overrides or its `cost_tier` default
(see [`models`](#models)).

### `max_aggregator_context_tokens`

Top-level `ChimeraConfig` field (not a subsection): an optional soft cap on the
**aggregator** prompt size, in estimated tokens (~4 chars/token).

```yaml
# top level of chimera.yaml, next to api_keys / selector:
max_aggregator_context_tokens: 100000   # omit or null = no cap (default)
```

When the natural merge prompt would exceed the cap, the aggregator truncates
the **longest** worker outputs (preserving shorter ones) until the prompt
fits. `null`/absent = no cap, backward compatible. Typical use: a deliberation
with many large-output workers feeding an aggregator model with a small
context window. The engine passes the cap to every aggregator call
(`max_prompt_tokens`), so it applies to merge, audit and aggregator-style
stages alike.

---

## Provider twins: one vendor, two separate accounts

Some vendors expose the same model families from two different hosted
endpoints — the model names look identical, but the endpoints are **separate
accounts** with separate billing, separate quotas and separate keys. A key
registered on one endpoint does not exist on the other: an endpoint rejecting
it with `401 Incorrect API key provided` is the *endpoint mirror telling you
you knocked on the wrong door*, NOT a credential defect. Measured example
(DF-CHIMERA-V2-28, 2026-09-20, key redacted): `api.stepfun.ai/v1` (StepFun
Global) accepted the key and listed 16 models, while
`api.stepfun.com/v1` (StepFun China) rejected the same key with 401 — so wire
`api.stepfun.ai` for that key, and never assume the other mirror works.

When a vendor's native endpoint answers `402 quota_exceeded` on every chat
call — account-wide, not model-specific — the fix is billing (top up or
consciously leave the key unused), not configuration. **Do not add a native
provider entry against an unfunded account while routing stays healthy
elsewhere**: it would put a permanently failing provider into the
auto-selection path and into the `/v1/health` provider map. Route the models
through an existing healthy provider (e.g. OpenRouter) until the account is
funded, then follow [Custom OpenAI-compatible endpoints](#custom-openai-compatible-endpoints)
and remember the catalog-entry requirement — wiring `providers.<name>` alone
does not make a model dispatchable.
