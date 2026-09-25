# Chimera Model Sync — Weekly Report

**Date:** 2026-09-25 (cron run 17:00 UTC / 12:00 local −05)
**Run:** `scripts/model_sync_cron.py` → `model_sync.py --diff --diff-json /tmp/chimera-model-sync-diff-2647034.json --output reports/latest.md`, then step 3 `--score-from`
**Diff result:** `reports/latest.md` line 4 reads `**Candidates:** 225 new models across 13 providers`
**Score step:** **FAILED** — `❌ LLM scoring failed: Extra data: line 2 column 1 (char 24) (model=deepseek-v4-flash, finish_reason=stop, max_tokens=8192)`. **No `reports/model_scores_20260925_*.yaml` was written** (last score file on disk is `model_scores_20260924_1200.yaml`). Root cause in §4; a substitute scored file was produced by hand this tick (§3).
**`.seen_models.json`:** **229 → 457 entries** (+228 = this run's 225 diff ids + 3) — the single fact that explains the whole report (§1).
**Catalog:** **42 models**, untouched by this run (recommend-only mandate).
**Deployment:** HEAD `f5fee48` == `/health` `commit: f5fee48` → **CURRENT** (identical commits: no diff run, no reload owed). Unit `chimera` active since 11:44:06 −05.
**Archive:** yesterday's file copied to `reports/model_sync_weekly_20260924_archive.md` before this file replaced it.

---

## 1. The honest headline: this is not 225 new models — it is 5 newly-appeared registry lanes

The count is real and the diff filter is behaving exactly as written (`chimera_id not in seen`). What changed is the **input**: the task-router registry table grew rows for five lanes that were not in `.seen_models.json` before, and the core path dedupes by **exact id**, not by model (DF-CHIMERA-V2-50, filed yesterday). Every model behind a newly-seen lane is therefore a "new candidate" — 225 of them, in one tick.

**Where the 225 come from (`provider` field of each diff row):**

| Registry lane | diff rows | share |
|---|---:|---:|
| `xkiro` | 70 | 31% |
| `aws-bedrock` | 41 | 18% |
| `fireworks-ai` | 40 | 18% |
| `commandcode` | 37 | 16% |
| `neuralwatt` | 21 | 9% |
| `synthetic` / `groq` / `ollama-cloud` / `clinepass` / `kimi-for-coding` | 5 / 4 / 3 / 2 / 2 | 7% |
| **top 5 lanes** | **209** | **93%** |

**Collapsing ids to models:** 225 candidate ids → **179 distinct basename strings**, of which 24 match a catalog basename outright (an undercount — see §1.1), 99 fall into mechanical variant/namespace classes (`:free` 43, `:batch` 72, `:thinking` 91, dotted Bedrock/regional ids 16, `accounts/fireworks/*` 29, `hf:` mirrors, `TEE/*`, `*-latest` aliases), and the residual 92 ids resolve to ~61 model families.

### 1.1 Why `aws-bedrock` inflates the count twice over

Bedrock's 41 rows arrive as dotted namespaces (`anthropic.claude-opus-5`, `qwen.qwen3-32b-v1:0`, `jp.anthropic.claude-sonnet-5`, `us-gov.openai.gpt-oss-20b-1:0`). These are the **same models** as their bare counterparts — `anthropic.claude-opus-4.8` is `anthropic/claude-opus-4.8`, already in the catalogue — but the id never matches, so basename dedupe reports them "not in catalogue". Regional duplicates (`jp.` ×7, `us-gov.` ×2, plus a `-v1:0` suffix) triple some entries again. Treated correctly, Bedrock contributes **0 new models**, only new ids.

### 1.2 The flood should not repeat next tick

All 225 ids are now in `.seen_models.json` (457 entries). Tomorrow's diff should collapse back to a handful — the prediction to hold this report to.

---

## 2. What is genuinely new — 14 models, all live-verified

Each candidate was probed this tick with the repo OpenRouter key (`~/chimera-v2/.env`, read at runtime, never printed): `POST /api/v1/chat/completions`, `max_tokens=200`, one "reply with exactly: ok" prompt. **14 of 15 returned HTTP 200 with `content='ok'`.** Pricing/context are the authoritative OpenRouter `/api/v1/models` values (per 1k tokens).

| # | OR id | ctx | $/1k in–out | probe | tier |
|---|---|---:|---|---|---|
| 1 | `anthropic/claude-opus-5` | 1 000 000 | 0.005 / 0.025 | 200 in 2.3 s | premium |
| 2 | `anthropic/claude-sonnet-5` | 1 000 000 | 0.002 / 0.010 | 200 in 3.4 s | standard |
| 3 | `openai/gpt-6-astra` | 1 050 000 | 0.010 / 0.050 | 200 in 2.1 s | premium |
| 4 | `openai/gpt-5.4` | 1 050 000 | 0.0025 / 0.015 | OR catalogue | standard |
| 5 | `google/gemini-3.8-flash` | 1 048 576 | 0.00075 / 0.00375 | 200 in 2.7 s | standard |
| 6 | `google/gemini-3.6-flash` | 1 048 576 | 0.00075 / 0.00375 | 200 in 1.8 s | standard |
| 7 | `google/gemini-3.5-flash-lite` | 1 048 576 | 0.0003 / 0.0025 | OR catalogue | budget |
| 8 | `moonshotai/kimi-k3` | 1 048 576 | 0.003 / 0.015 | 200 in 1.3 s | premium |
| 9 | `z-ai/glm-5.3` | 1 310 720 | 0.0014 / 0.0044 | 200 in 0.4 s | standard |
| 10 | `z-ai/glm-5.3-flash` | 1 310 720 | 0.000045 / 0.00014 | 200 in 2.6 s | budget |
| 11 | `x-ai/grok-build-0.1` | 256 000 | 0.001 / 0.002 | 200 in 1.9 s | standard |
| 12 | `qwen/qwen3.8-max-0902` | 1 000 000 | 0.002 / 0.006 | 200 in 1.9 s | premium |
| 13 | `qwen/qwen3.8-27b` | 1 000 000 | 0.00042 / 0.003 | 200 in 1.0 s | standard |
| 14 | `deepseek/deepseek-v4.1-flash` | 1 048 576 | 0.000075 / 0.0003 | 200 in 2.9 s | budget |
| 15 | `stepfun/step-3.5-flash` | 262 144 | 0.0001 / 0.0003 | 200 in 1.4 s | budget |

Availability was confirmed against the OpenRouter catalogue itself (458 ids) plus the live chat probe — not against roundups. `anthropic/claude-opus-5` is billed as Anthropic's flagship for long-horizon agentic work; `google/gemini-3.8-flash` is described by OpenRouter as Google's most intelligent Flash, with gains over 3.7 Flash; `x-ai/grok-build-0.1` is an early-access coding-agent model (256 K, no text output limit); `moonshotai/kimi-k3` is a 2.8 T-parameter open-weight multimodal reasoning model.

### 2.1 Skip / hold

- **SKIP `minimax/minimax-m2.7`** (and `m2.5`) — yesterday's verdict stands and was re-confirmed: same $0.30/$1.20 per M as M3, 204 800 vs 1 048 576 context, text-only vs multimodal, one generation older. `openrouter/minimax/minimax-m3` + `router9/mmx/MiniMax-M3` are already in the catalogue.
- **HOLD `mistral-large-3`** — `mistralai/mistral-large-3` returned **HTTP 400 "not a valid model ID"**; it appears only via `ollama-cloud` (`mistral-large-3:675b`) and an `xkiro` `mistralai/*` set with **no pricing at all** (in and out both `None`).
- **HOLD `anthropic/claude-opus-4.6`, `claude-fable-5-1`, `kimi-k2.5`** — intermediate generations superseded within their own line by entries above (`claude-opus-5`, and catalogue `claude-fable-5`); no reason to spend catalogue slots.
- **CAUTION `deepseek/deepseek-v4.1-flash`** — a real OR model (probe 200, 1 M ctx, $0.075/$0.30), **but** the fleet's own dispatch doctrine records that DeepSeek's direct API rejects the `v4.1` / `-0731` names and serves the legacy id *as* V4.1-Flash. If approved, admit it as `openrouter/…` only, never as a native `deepseek/…` lane, or it will be a phantom duplicate of `deepseek/deepseek-v4-flash`.
- **Note `qwen3.8-max`** — the bare id is **absent** from OpenRouter; only the `-0902` snapshot exists. Recommend the snapshot id.

---

## 3. Recommendation: 14 ADD, all as `openrouter/*` keys

Scored entries are in **`reports/model_sync_candidates_20260925.yaml`** (14 entries, 378 path scores, validated: **0 unknown paths**, **0 scores below 60**). Lineage is stated explicitly in that file's header and is not LLM output (§4): each entry is **templated from its in-catalogue predecessor plus an explicit per-path delta** — the pattern the catalogue itself uses across generations (e.g. GPT-5.6 from 5.5, budget variants dropped). Pricing is the OpenRouter API value, not the scorer's guess.

| Proposed key | ← predecessor | Δ | tier |
|---|---|---:|---|
| `openrouter/anthropic/claude-opus-5` | `anthropic/claude-opus-4.8` | +1 | premium |
| `openrouter/anthropic/claude-sonnet-5` | `anthropic/claude-sonnet-4.6` | +1 | standard |
| `openrouter/openai/gpt-6-astra` | `openrouter/openai/gpt-5.6-sol` | +1 | premium |
| `openrouter/openai/gpt-5.4` | `openrouter/openai/gpt-5.6-terra` | 0 | standard |
| `openrouter/google/gemini-3.8-flash` | `google/gemini-3.5-flash` | +2 | standard |
| `openrouter/google/gemini-3.5-flash-lite` | `google/gemini-3.1-flash-lite-preview` | +2 | budget |
| `openrouter/moonshotai/kimi-k3` | `openrouter/moonshotai/kimi-k2.6` | +2 | premium |
| `openrouter/z-ai/glm-5.3` | `z-ai/glm-5` | +4 | standard |
| `openrouter/z-ai/glm-5.3-flash` | `hermes/glm-5.3-flash` | +3 | budget |
| `openrouter/x-ai/grok-build-0.1` | `openrouter/x-ai/grok-4.3` | 0 | standard |
| `openrouter/qwen/qwen3.8-max-0902` | `openrouter/qwen/qwen3.7-max` | +2 | premium |
| `openrouter/qwen/qwen3.8-27b` | `openrouter/qwen/qwen3.7-plus` | +1 | standard |
| `openrouter/deepseek/deepseek-v4.1-flash` | `deepseek/deepseek-v4-flash` | +1 | budget |
| `openrouter/stepfun/step-3.5-flash` | `stepfun/step-3.7-flash` | −2 | budget |

**Why `openrouter/*`:** under the task-router source, `openrouter` is the one reseller row the table carries, so these keys stay visible to the watch list — and the `/health`-visible catalogue keeps pricing resolvable (§5.1). The deliberation-side reason: three of these (opus-5, gpt-6-astra, kimi-k3) are new **flagship** seats, and the cheapest useful addition is `z-ai/glm-5.3-flash` at **$0.045/M in** — an order of magnitude below anything plan-priced currently in the catalogue.

Nothing was written to `chimera.yaml`, `chimera.yaml.example` or `chimera.yaml.docker`.

---

## 4. NEW defect: the `--score` step crashed on the oversized diff, and the retry ladder could not catch it

The failure is mechanical, not provider trouble. Two things line up:

1. **The model returned two JSON objects.** `Extra data: line 2 column 1 (char 24)` means a first JSON value of 23 characters followed by more content on line 2 — i.e. concatenated objects, not one object with prose around it.
2. **The fallback only strips prose around a *single* object.** `_extract_json_object` (`scripts/model_sync.py:1297-1303`) tries `json.loads(stripped)`, then falls back to `json.loads(stripped[first"{" : last"}"])`. With two objects, the slice is *still* invalid JSON — and because `JSONDecodeError` subclasses `ValueError`, the second failure propagates as a "not truncated" error.
3. **The retry ladder is gated on `finish_reason == "length"`.** `_score_llm_reply` (`:1367-1373`) raises immediately unless the reply was truncated. This reply was `finish_reason=stop`, so no retry, up to `SCORE_MAX_TOKENS_CEILING=32768`, ever fired.

**Why now:** yesterday's diff was **2 candidates**; today's was **225**. This is the first oversized payload the scorer has been handed, and the scorer's prompt embeds the candidate set. Plausible mechanism (hypothesis, not measured): with a large payload the model emits a partial object and then continues with another. Whatever the trigger, a *parse* failure that is not a *truncation* failure is unrecoverable by design today.

**Fix shape (three independent, cheap):**
- Parse with `json.JSONDecoder().raw_decode()` at the first `{` so a trailing second object is ignored rather than fatal; or split on newlines and take the first object that parses.
- Send `response_format={"type": "json_object"}` on the scoring call (DeepSeek supports it — see the gateway provider-classification note in the skill; `json_object` also removes the fences/prose case entirely).
- Cap the payload: score the top-N by recency rather than the whole diff set, so the scoring call never scales with a lane-namespace flood.

Filed as **DF-CHIMERA-V2-57** (§7).

---

## 5. Measured corrections to yesterday's carried numbers

Reported as corrections, not as regressions — two of yesterday's findings do not reproduce today, and one skill reference does not exist.

| Yesterday's claim | Measured today | Status |
|---|---|---|
| `references/category-paths.md` is the scoring authority (`references/category-paths.md` cited throughout the skill) | **file does not exist** in the repo | **STALE DOC** — the real 32-path authority is `chimera.selector.PATH_PATTERNS` (extracted live: 32 paths). Every score in §3 was validated against that, not against a doc. |
| 18 of 42 live catalog models have no explicit `cost_per_1k_*` | **35 / 42 priced, 7 unpriced** (`hermes/glm-5.3-flash`, `openrouter/openai/gpt-5.6`, and the 5 `router9/*` lanes). Measured on `load_config()`, not raw YAML — raw YAML stores 0/42 by design, which would have been a false finding | **DOES NOT REPRODUCE** (coverage is better, not worse) |
| models.dev fallback cache is permanently "stale" (`_fetched_at` never written; age ≈ 56.7 years) | live logs today read `provider_cache_hit age_s=1617 providers=223 stale=False`; also `provider_discovery_done models=5197 providers=10`, `registry_source=task-router` | **DOES NOT REPRODUCE this run** — the marker is present |

### 5.1 What the scope line means

`reports/latest.md` line 6 still prints `IN: core providers (alibaba, anthropic, deepseek, google, …)` — that string is built from the `CORE_PROVIDERS` **constant**, while the rows actually scanned came from lane ids (`xkiro`, `aws-bedrock`, …). Read the scope line as *intent*, never as measured coverage. Unchanged from yesterday (DF-CHIMERA-V2-49).

---

## 6. Action items

1. **Decide §3's 14 ADDs** — all live-verified today; none will reappear in a `--diff` report once seen, so the decision has to be taken from this file. Suggested batch: the three new flagships (opus-5, gpt-6-astra, kimi-k3), the value seats (gemini-3.8-flash, glm-5.3-flash, grok-build-0.1) and the 1 M-context budget seat (deepseek-v4.1-flash as `openrouter/*` only).
2. **Accept the §2.1 verdicts** — 0 additions for `minimax-m2.7`/`m2.5` (dominated), `mistral-large-3` (not a valid OR id), and the superseded intermediates.
3. **DF-CHIMERA-V2-57** — fix the scorer before the next oversized diff (§4), or the weekly score artifact will keep silently not being produced.
4. **Still open from yesterday:** DF-CHIMERA-V2-49 (core-lab coverage under the task-router source), DF-CHIMERA-V2-50 (basename dedupe in the core path — the defect that produced 225 rows today), plus `DF-CHIMERA-V2-28` (StepFun native key vs OR), `INT-GW-RESTART-001`, `INT-CI-010`.
5. **Skill hygiene:** the `chimera-development` skill cites `references/category-paths.md`, which is absent. Repoint it at `chimera.selector.PATH_PATTERNS`.

---

## 7. Board row filed this run

| Row | Priority | Finding |
|---|---|---|
| **DF-CHIMERA-V2-57** | P2 | `--score` is unrecoverable on a non-truncated unparsable reply: two concatenated JSON objects (`Extra data: line 2 column 1 (char 24)`, first object 23 chars) defeat `_extract_json_object`'s prose-stripping fallback (`model_sync.py:1297-1303`) and, because `JSONDecodeError` subclasses `ValueError` and the retry ladder is gated on `finish_reason == "length"` (`:1367-1373`), the run aborts with `finish_reason=stop` and **writes no score file**. First occurrence on an oversized diff (2026-09-25: 225 candidates vs 2 the day before). Fix: `raw_decode` at the first `{` / `response_format: json_object` / cap the payload to top-N by recency. |

Board census before append: **222 rows, 222 unique ids, 0 duplicates, max `DF-CHIMERA-V2-56`**.

---

## 8. Method / reproducibility

- Diff report: `reports/latest.md` + `latest_20260925_1200.md`; diff payload `/tmp/chimera-model-sync-diff-2647034.json` (10 lab keys, 225 rows).
- Lane attribution and id→model collapsing: one-off reduction over the diff payload; classes counted on the id basename only (dotted namespace, `:free`, `:batch`, `:thinking`, `:size`, `hf:`, `TEE/`, `jp.`, `us-gov`, `accounts/fireworks/`, `-latest`).
- Availability evidence: OpenRouter `GET /api/v1/models` (458 ids) for pricing/context + one live `chat/completions` probe per candidate (15 probes, 14 × HTTP 200).
- Config measurement: `load_config()` for pricing coverage (not raw YAML), `chimera.selector.PATH_PATTERNS` for the canonical 32 paths.
- Deployment parity: `/health` `commit` vs `git rev-parse --short HEAD` (identical → CURRENT, no diff run).
- Nothing in this run wrote to `chimera.yaml`, `chimera.yaml.example` or `chimera.yaml.docker`. `.seen_models.json` was updated only by the sync's own `--diff` run. Scratch diagnostic scripts were temporary and have been removed.
