# Chimera Model Sync — Weekly Report

**Run:** 2026-10-30 17:00 UTC (sync at 12:00 UTC)
**Scope:** 13 core providers + reseller watch (kilo, llmgateway, nano-gpt, openrouter, vercel) + 22 task-router lanes
**Headline:** **1 new core-lab candidate — real, distinct, and the first genuine Mistral entry the catalog has been offered.** `mistral/mistral-large-4-0-8` is **Mistral Large 4 ("Le Chonk")**, public preview **2026-10-06**: 1T-param natively multimodal MoE, 52B active + 1.6B vision encoder, 1M context. It is not a duplicate — the catalog still has **zero** Mistral models (`grep -ic mistral chimera.yaml` = **0**), one day after the 10-29 report asked whether Mistral should be represented at all. **Recommendation: ADD — one entry, OpenRouter-routed, `cost_tier: standard`.** Nothing was applied; the catalog is untouched pending approval.

| Artifact | Path |
|---|---|
| Sync report | `reports/latest.md` (`reports/latest_20261030_1200.md`) |
| Diff candidates (raw) | `/var/tmp/hermes-scratch/chimera-model-sync-diff-3442396.json` — 1 entry, `mistral` block |
| Scores (`--score`) | `reports/model_scores_20261030_1200.yaml` — auto-scored, 31 paths, all ≥65 (min 65 / max 86) |
| Live service | `:8765` → `status=alive`, `uptime_models=43`, `commit=06639fa`, `version=0.2.8` |
| Deploy parity | **CODE-CURRENT** — running `06639fa` resolves, is an ancestor of HEAD `5bf227e`, and the material diff (`src/ scripts/ tests/ pyproject.toml`) is **empty**. The 5 changed files are board/wave state + `reports/deps-refresh-20261029.md`: bookkeeping only, no reload owed, none claimed. |

---

## 1. What the scan reported

- `--diff`: **1 new model across 13 core providers**, **0** task-router lane promotions
- basename skips: 3 standing (`openai/gpt-5.6`, `-luna`, `-sol`, reported as already admitted under `openrouter/` prefixes — see §3, the first of those is now bogus)
- registry: task-router `data/tables/models.jsonl` (25 providers); provider cache stale at start (age 13,818 s) then refetched — **235 providers** fetched, **234** served from cache at age 0-1 s afterwards; `provider_discovery_done models=8713 providers=9 unattributed=5480`
- reseller watch: large standing set (batch / quantized / `-uncensored` / `-latest` variants). Informational, not recorded in `.seen_models.json`, re-reported every run
- pending ledger: **511** seen-but-uncatalogued keys vs **43** catalog models (see §4.3)

## 2. Verification — the four gates

| Gate | Result | Evidence |
|---|---|---|
| Provider model card | **PASS** | models.dev `mistral` block carries both `mistral-large-4` and `mistral-large-4-0-8`, **identical**: `release_date 2026-10-06`, `cost {input 0.7, output 2.1, cache_read 0.07}`, `limit.context 1048576` |
| Release announcement | **PASS** | `mistral.ai/news/mistral-large-4/` — *"Introducing Mistral Large 4"* (independent coverage pins public preview to **Oct 6 2026**, 1T params / 52B active / 1.6B vision encoder); follow-up `mistral.ai/news/mistral-large-4-oss/` (weights opened later in October, modified-MIT) |
| Pricing available | **PASS** | Live OpenRouter `/api/v1/models` this run (HTTP 200, authenticated, 424 ids): `mistralai/mistral-large-4-0` → prompt `0.0000007`, completion `0.0000021`, ctx `1048576` = **$0.70 / $2.10 per MTok** |
| Distinct from existing entries | **PASS** | No Mistral model in the catalog at all; no existing row shares this price point or its 1M-context multimodal profile |

**Wire-id trap, recorded — three ids, one model. Do not add all three:**

| Surface | Id |
|---|---|
| Mistral API, canonical versioned | `mistral-large-4-0-8` ← what the sync reported |
| Mistral API, friendly alias | `mistral-large-4` |
| OpenRouter slug (live-verified) | `mistralai/mistral-large-4-0` |

Same weights, same price, same 1M context. A models.dev issue (`anomalyco/models.dev#11980`) tracks `mistral-large-4-0-8` as the remote id being backfilled from Mistral's own catalog — the `-0-8` suffix is the pinned API version (4.0.8), not a separate tier.

### Scored block (ready if approved — NOT applied)

`reports/model_scores_20261030_1200.yaml`: 31 paths, all ≥65 — python 86, tool_use/code_execution 84, reasoning/explanation 84, multi_step_planning 82, sql 82, error_analysis 82, javascript 82, fact_retrieval/definitions 82; 76-80 across unit_tests, shell, json, architecture, abstractive summarization, translation; 65-74 on legal analysis, storytelling, interface copy.

**One correction to the auto-score:** it assigned `cost_tier: premium`. Average ($0.0007 + $0.0021) / 2 = **$0.0014 per 1k**, which lands on the selector's `standard` default ($0.001), not `premium` ($0.009). Recommend **`standard`** — as scored, price-weighting would under-rate it ~6x.

```yaml
  openrouter/mistralai/mistral-large-4-0:
    categories:
      technology_code/code_generation/python: 86
      technology_code/code_generation/javascript: 82
      technology_code/code_generation/sql: 82
      technology_code/code_generation/shell: 76
      technology_code/testing_debugging/unit_tests: 76
      technology_code/testing_debugging/error_analysis: 82
      technology_code/data_science/analysis: 78
      technology_code/data_science/modeling: 72
      technology_code/data_interaction/database/sql: 82
      technology_code/data_interaction/file_based/json: 80
      technology_code/system_design/architecture: 78
      technology_code/system_design/devops: 70
      complex_reasoning_agency/multi_step_planning/task_decomposition: 82
      complex_reasoning_agency/tool_use/code_execution: 84
      complex_reasoning_agency/self_correction/debugging: 80
      academic_scientific/formal_writing/research_paper: 68
      academic_scientific/mathematics/algebra: 78
      academic_scientific/mathematics/calculus: 76
      academic_scientific/mathematics/statistics: 74
      general_knowledge/reasoning/explanation: 84
      general_knowledge/reasoning/logic_puzzle: 78
      general_knowledge/fact_retrieval/definitions: 82
      general_knowledge/fact_retrieval/historical_events: 76
      language_translation/summarization/abstractive: 80
      language_translation/translation/language_to_language: 80
      language_translation/linguistic_analysis/sentiment: 78
      business_finance/legal_document/analysis: 65
      business_finance/marketing/copywriting: 72
      creative_conversational/creative_writing/storytelling: 74
      creative_conversational/ux_writing/interface_copy: 68
      multimedia_processing/image/analysis: 72
    cost_tier: standard
    provider: openrouter
    cost_per_1k_input: 0.0007
    cost_per_1k_output: 0.0021
    enabled: true
```

**Why OpenRouter rather than native `mistral`:** `chimera.yaml`'s `api_keys` block has no `mistral` entry and there is no `MISTRAL_API_KEY` in the process env or `~/.hermes/.env` — a native stage would register no credential, get excluded from auto-selection, and fail the call. OpenRouter is already keyed (verified live this run) and serves the same model at the same sticker. If Bane prefers the native lab route: add `api_keys.mistral: ${MISTRAL_API_KEY}`, provision the key, then `mistral/mistral-large-4-0-8` with `provider: mistral` — a strictly larger change (new provider block + secret) for identical capability.

## 3. Consequential side-finding — one catalog id no longer resolves on OpenRouter

Every `openrouter/*` catalog id was checked against the live OR model list this run (424 ids):

| Catalog id | Live OR status |
|---|---|
| `openrouter/openai/gpt-5.5`, `-5.5-pro`, `gpt-5.6-luna`, `-sol`, `-terra`, `qwen/qwen3.7-{max,plus}`, `qwen/qwen3-coder`, `anthropic/claude-fable-5`, `x-ai/grok-4.{3,5,20,20-multi-agent}`, `moonshotai/kimi-k2.{6,7-code}`, `minimax/minimax-m3` | **resolves** — 16/17 |
| **`openrouter/openai/gpt-5.6`** | **ABSENT** — bare `openai/gpt-5.6` is gone; only tiered ids remain (`-luna`, `-sol`, `-terra`, each also `-pro`, plus `:batch`) |

A stage pinned to `openrouter/openai/gpt-5.6` 404s at call time. Fixes (neither applied, both need approval): repoint to `openrouter/openai/gpt-5.6-sol` (nearest non-Luna tier, $2.00/$10.00 per MTok) or drop the row. Note the sync's own basename-skip line still describes `openai/gpt-5.6` as *"already admitted as `openrouter/openai/gpt-5.6`"* — the skip logic inherits the stale id and will keep masking this breakage until the catalog is corrected.

## 4. Catalog aging — 40 core-lab chat models released since 2026-08-01 are absent

Measured against the same models.dev cache the sync used (13 core providers, chat/reasoning only, priced, text output, released ≥ 2026-08-01, basename-deduped against the catalog). Live OR availability and pricing re-verified for every row below.

The catalog's newest rows are the GPT-5.6 generation, Claude 4.x, Gemini 3.x, Kimi k2.x, MiniMax M3, Grok 4.5/4.6. Core labs have moved on:

| Lab | Model | OR id (live-verified) | $/MTok in / out | Released |
|---|---|---|---|---|
| OpenAI | GPT-6.1 Terra | `openai/gpt-6.1-terra` | 1.00 / 5.00 | 10-26 |
| OpenAI | GPT-6.1 Sol | `openai/gpt-6.1-sol` | 2.00 / 10.00 | 09-29 |
| Anthropic | Claude Opus 5.5 | `anthropic/claude-opus-5.5` | 4.00 / 20.00 | 09-22 |
| Anthropic | Claude Sonnet 5.5 | `anthropic/claude-sonnet-5.5` | 2.00 / 10.00 | 09-28 |
| Anthropic | Claude Haiku 5.5 | `anthropic/claude-haiku-5.5` | 0.10 / 0.50 | 10-07 |
| Google | Gemini 4 Argon | `google/gemini-4-argon` | 2.00 / 10.00 | 10-13 |
| Moonshot | Kimi K3.1 Pro | `moonshotai/kimi-k3.1-pro` | 2.00 / 10.00 | 10-23 |
| MiniMax | M3.1 Flash | `minimax/minimax-m3.1-flash` | 0.075 / 0.30 | 10-19 |
| xAI | Grok 4.7 | `x-ai/grok-4.7` | 2.00 / 6.00 | 09-21 |
| StepFun | Step-5 Preview | `stepfun/step-5-preview` | 1.00 / 2.70 | 09-16 |
| Meta | Muse Wonder 1.0 | `meta/muse-wonder` | 4.00 / 20.00 | 10-12 |
| Xiaomi | MiMo v2.6 Flash | `xiaomi/mimo-v2.6-flash` | 0.14 / 0.28 | 09-22 |
| Alibaba | Qwen3.8 Flash | `qwen/qwen3.8-flash` | 0.15 / 0.47 | 08-26 |
| Z.ai | GLM-5.3 (native) | `z-ai/glm-5.3` | 0.08 / 3.60 — asymmetric, verify before adopting | 08-14 |

Deliberately **not** proposed: `-pro` / `-fast` / `-highspeed` / `-ultraspeed` / `-contributor` / `-latest` / `:batch` / `:thinking` variants (same weights, premium or promotional stickers); `mistral/deepseek-v4-1-flash-1017` and `mistral/zai-glm-5-3*` (Mistral now hosts third-party models — the DeepSeek one was already declined yesterday as a duplicate of `deepseek/deepseek-v4-flash`); `gpt-daybreak-*` and `gemini-flash-latest` (alias rows).

### 4.3 The seen-file trap is live and large

`.seen_models.json` holds **511** keys; the catalog holds **43** models. Every discovery not admitted is "seen" forever and therefore invisible to `--diff` on later runs. That is how a 40-model generational gap coexists with a "1 new model" headline: the scan reports **novelty relative to its ledger**, not **gap relative to the catalog**. The scan is not malfunctioning — the ledger records everything it ever saw. Two consequences: (a) the weekly headline must always be read beside §4's catalog-relative scan; (b) re-baselining the ledger (prune keys declined by decision, keep the rest) would restore `--diff` as a change detector. Not done here — it is Bane's call whether the file is a "have I seen this" or a "did I decline this" register.

## 5. Carry-forward queue (unchanged, re-verified live)

No approval landed since yesterday, so the six-item queue was re-checked against this run's OpenRouter pull. All six still live, prices unchanged, still zero grep hits in `chimera.yaml`:

| # | Proposed id | OR | $/1k in | $/1k out | ctx | Waiting since |
|---|---|---|---|---|---|---|
| 1 | `openrouter/openai/gpt-6.1-terra` | LIVE | 0.00100 | 0.00500 | 1,050,000 | 10-25 |
| 2 | `openrouter/minimax/minimax-m3.1-flash` | LIVE | 0.000075 | 0.000300 | 1,048,576 | 10-29 |
| 3 | `openrouter/anthropic/claude-opus-5.5` | LIVE | 0.00400 | 0.02000 | 1,000,000 | 10-25 |
| 4 | `openrouter/openai/gpt-6.1-sol` | LIVE | 0.00200 | 0.01000 | 1,050,000 | 10-29 |
| 5 | `openrouter/google/gemini-4-argon` | LIVE | 0.00200 | 0.01000 | 1,048,576 | 10-25 |
| 6 | `openrouter/moonshotai/kimi-k3.1-pro` | LIVE | 0.00200 | 0.01000 | 1,048,576 | 10-29 |

## 6. Observations

1. **Yesterday's Mistral question now has an answer with a model attached.** The 10-29 report closed with *"if Mistral should be represented, the candidates worth scoring are Mistral Large 4 and Devstral, not a hosted DeepSeek."* The sync delivered exactly Mistral Large 4 today and it clears all four gates — the lab gap and the model gap close with one row.
2. **A catalog id silently rotted (§3).** OR slugs are not stable across generations, and the sync's skip logic keyed off the stale id keeps hiding it. A "catalog ids vs live OR" check is one GET (424 ids) and worth wiring next to the sync.
3. **The headline number is not the gap number (§4.3).** 511 seen / 43 catalogued / 40 core releases missing. Treat `--diff: 0 new` as "nothing *novel to the ledger*", never as "catalog current".
4. **Attribution backlog unchanged:** 5,480 of 8,713 discovered models unattributed. Standing, not a regression.
5. **Deploy parity is bookkeeping-only** — `:8765` runs current code; no reload performed or claimed.

## 7. Action items (approval required — nothing applied)

1. **ADD** `openrouter/mistralai/mistral-large-4-0` (block in §2). First real Mistral coverage; model, price and OR availability all verified live. Use `cost_tier: standard`, not the auto-scorer's `premium`.
2. **FIX** `openrouter/openai/gpt-5.6` — dangling OR id that will 404; repoint to `-sol` or drop.
3. **DECIDE** the generational gap in §4 — 14 candidates named and price-verified; highest-leverage picks under Bane's "newest live generation" rule are GPT-6.1 Terra, Claude Opus/Sonnet 5.5, Gemini 4 Argon, Kimi K3.1 Pro, Grok 4.7, MiniMax M3.1 Flash.
4. **DECIDE** the `.seen_models.json` re-baseline (§4.3).

If any row is approved the sequence is unchanged: edit `chimera.yaml` → `cp chimera.yaml chimera.yaml.example && cp chimera.yaml chimera.yaml.docker` → offline suite green (`pytest tests/ --ignore=tests/integration --ignore=tests/compat -q`) → `sudo systemctl restart chimera` → `/health` shows the new commit → `/v1/models` count check (43 → 44 for one row) → `python scripts/smoke_live.py` (exit 0).

---

*Source of record for this run: `reports/latest.md`, `reports/latest_20261030_1200.md`, `/var/tmp/hermes-scratch/chimera-model-sync-diff-3442396.json`, `reports/model_scores_20261030_1200.yaml`, `~/.chimera/models-dev-cache.json` (refetched this run, 235→234 providers), `openrouter.ai/api/v1/models` (fetched 2026-10-30, 424 ids), `mistral.ai/news/mistral-large-4/` + `mistral.ai/news/mistral-large-4-oss/`, `.seen_models.json` (511 keys), catalog-relative gap scan (13 core providers, release_date ≥ 2026-08-01), live `/health` at commit `06639fa`, HEAD `5bf227e`. No catalog file, config template, or service was modified by this run.*
