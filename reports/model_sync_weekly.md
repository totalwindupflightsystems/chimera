# Chimera Model Sync — Weekly Report

**Date:** 2026-09-24 (cron run 17:00 UTC / 12:00 local −05)
**Run:** `scripts/model_sync_cron.py` → `model_sync.py --diff --output reports/latest.md`
**Diff result:** **2 candidates** — `reports/latest.md` line 4 reads `**Candidates:** 2 new models across 3 providers`.
**Registry source:** **task-router JSONL** (`~/task-router/data/tables/models.jsonl`, 22 provider blocks / 899 model rows) — **this is the first cron run under the new preferred source** (`load_preferred_registry`, commit `81e56fb` 2026-09-23 21:05:58 −05). See §2.
**`.seen_models.json`:** 229 entries (226 at yesterday's report; the two new ids are this run's).
**Catalog:** **42 models**, untouched by this run (recommend-only mandate). `git status` clean apart from this run's scratch files (deleted before close).
**Deployment:** `/health` reports `commit: ee8ad95` == `HEAD` (`ee8ad95`, 08:31:21 −05); unit `chimera` active since 08:32:10 −05 → **CURRENT**, no reload owed.
**Archive:** the 09-23 weekly file was copied to `reports/model_sync_weekly_20260923_archive.md` before this file replaced it.

---

## 1. The two candidates: both real models, neither is a catalogue addition

Both are live on OpenRouter and were probed with the deployment's own repo key this tick. **The verdict on each is not "new model" — one is already in the catalog, the other is strictly dominated by it.**

| Candidate | OR catalogue | Live probe (repo key) | Context | Input modality | $/1k in–out | OR `created` | Verdict |
|---|---|---|---|---|---|---|---|
| `minimax/minimax-m2.7` | present, 204 800 ctx | **HTTP 200 in 4.7 s** (content empty, `reasoning` 428 chars — reasoning-starved at `max_tokens=100`) | 204 800 | text→text | $0.000300 / $0.001200 | 2026-03-18 12:24 UTC | **SKIP** — real, but dominated |
| `minimax/minimax-m3` | present, 1 048 576 ctx | **HTTP 200 in 1.2 s**, `content='ok'` | 1 048 576 | text+image+video→text | $0.000300 / $0.001200 | 2026-05-31 16:36 UTC | **ALREADY IN CATALOG** — false candidate (§3) |

**`minimax/minimax-m3` is already admitted twice:** `openrouter/minimax/minimax-m3` (`chimera.yaml:1156`, `cost_tier: budget`) and `router9/mmx/MiniMax-M3` (`chimera.yaml:1433`). Nothing to add.

**`minimax/minimax-m2.7` is dominated at an identical price.** Same $0.30/$1.20 per M and the same $0.06/M cache-read as M3, but 204 800 vs 1 048 576 context, text-only vs multimodal, and one generation older (2026-03-18 vs 2026-05-31). The fleet's own registry agrees: the task-router row for the legacy capital id `MiniMax-M2.7` carries `disabled: true`, `disabled_reason: "superseded generation — fleet uses MiniMax-M3"`, and the duplicate reconciliation of 2026-09-19 marked the capital `MiniMax-M3` row `"duplicate of canonical lowercase minimax-m2.7/m3 — plan lanes use lowercase ids"`. Adding M2.7 to Chimera would add a lane that is strictly worse than one already present. **Recommendation: SKIP.**

Press/availability verification (not roundups): MiniMax's own release notes list the **M2.7 series** (M2.7 / M2.7-highspeed) and then **M3** as the current M-series model; M2.7 was announced **2026-03-18** with open weights on **2026-04-12** (Pandaily, aiwiki, r/LocalLLaMA all carry the same date). Both OpenRouter pages resolve and confirm pricing.

### Scoring run (`reports/model_scores_20260924_1200.yaml`)

The shipped `--score` step ran (DEEPSEEK_API_KEY resolved from `~/.hermes/.env`) and produced a scored file for both candidates. Validated against the canonical selector paths:

- **32 canonical paths** from `chimera.selector.PATH_PATTERNS`; **0 unknown paths** emitted by either entry; **0 scores below 60** (the omit-below-60 policy held).
- `minimax/minimax-m2.7` — 23 paths, range 70–85, `cost_tier: standard`
- `minimax/minimax-m3` — 30 paths, range 75–92, `cost_tier: premium`

**Caveat on the scored tiers:** the `cost_tier` in the score file is the LLM's guess, not price-derived. Both models are $0.30/$1.20 per M in the registry, yet the scorer emitted `standard` for M2.7 and `premium` for M3 — while the catalog already carries M3 as `budget`. Category scores are usable; the tier labels should be overridden from the registry price at the point of any approval.

---

## 2. The larger finding: the first run on the task-router source is far narrower than models.dev

Both sources were measured this tick with the **same shipped scanner, same cache state, same process** — one call per source, nothing else changed:

| Measurement | **SOURCE A — task-router (ACTIVE)** | **SOURCE B — models.dev (fallback)** |
|---|---|---|
| provider blocks | 22 | 223 |
| model rows | 899 | 8 173 |
| **core-13 providers actually present** | **3 / 13** — `deepseek(2)`, `minimax(3)`, `stepfun(2)` | **13 / 13** — `alibaba(56)`, `anthropic(15)`, `deepseek(4)`, `google(39)`, `meta(5)`, `minimax(7)`, `mistral(35)`, `moonshotai(4)`, `openai(50)`, `stepfun(9)`, `xai(12)`, `xiaomi(9)`, `zhipuai(17)` |
| reseller-watch providers present | **1 / 5** — `openrouter(465)` | **5 / 5** — `kilo(392)`, `llmgateway(205)`, `nano-gpt(592)`, `openrouter(385)`, `vercel(388)` |
| core candidates produced | **5** | **181** |
| providers registered by discovery | **2** — `deepseek`, `openrouter` | **12** — incl. `google`, `openai`, `xai`, `zai`, `crof`, `synthetic`… |
| pricing entries returned | 835 | 7 371 |
| catalog ids with an **exact** pricing key | **24 / 42** | **35 / 42** |

**Mechanism — lane ids, not lab ids.** The task-router table names providers by *lane* (`clinepass`, `xkiro`, `commandcode`, `opencode-go`, `opencode-go-2`, `openai-codex`, `zai-glm`, `meta-model`, `grok-build`, `groq`, `sambanova`, `ollama-cloud`, `neuralwatt`, `synthetic`, `fireworks-ai`, `aws-bedrock`, `kimi-for-coding`, plus `deepseek`/`minimax`/`stepfun`/`openrouter`). `CORE_PROVIDERS` matches lab ids, so **10 of the 13 core labs now match zero rows** and the labs' models sit in the table under lane ids that the core scan never reads. The reseller watch loses 4 of 5 carriers for the same reason.

**The report header is not evidence.** `reports/latest.md` line 6 prints `IN: core providers (alibaba, anthropic, deepseek, google, meta, minimax, mistral, moonshotai, openai, stepfun, xai, xiaomi, zhipuai)` — that string is built from the `CORE_PROVIDERS` **constant**, not from the source actually loaded. Today it names ten labs with zero rows behind it. Read the scope line as intent, not as measured coverage.

**Pricing follows the same path (exact-key lookup, `config.py:1068-1074`):** `entry = config.models.get(model_id)`. Because task-router keys are lane-namespaced, these catalog ids no longer resolve: `google/gemini-3-flash-preview`, `google/gemini-3-pro-preview`, `google/gemini-3.1-flash-lite-preview`, `google/gemini-3.1-pro-preview`, `google/gemini-3.5-flash`, `anthropic/claude-haiku-4.5`, `xiaomi/mimo-v2.5`, `xiaomi/mimo-v2.5-pro`, `z-ai/glm-5`, `z-ai/glm-5-turbo`, `qwen/qwen3-coder-next` (11 ids that had exact pricing under models.dev). Measured on the **live config**: **18 of 42 models now have no explicit `cost_per_1k_*`** — exactly the 18 the active source fails to resolve (11 above + `hermes/glm-5.3-flash`, the 5 `router9/*` lanes and `openrouter/openai/gpt-5.6`, which were already unpriced under both sources). They fall back to `_model_cost_rate()` tier defaults, so cost-weighted selection is now pricing 11 lanes off a tier guess instead of the registry.

This is a **side effect of a deliberate, completed design** (DF-CHIMERA-V2-39: consume the task-router JSONL instead of a second Chimera registry) — not an argument to revert it. But the scan and discovery layers need either a lane→lab mapping or a models.dev union for core-lab discovery; otherwise the weekly sync is now structurally blind to 10 of its 13 labs. **Filed as DF-CHIMERA-V2-49 (§7).**

---

## 3. The false candidate: core-path dedupe is exact-key, reseller dedupe is basename-level

The scan has two dedupe rules and they disagree:

- **Core scan** — `scripts/model_sync.py:530`: `if chimera_id in chimera_models:` → the **resolved** id must equal a catalog key *exactly*.
- **Reseller watch** — `scripts/model_sync.py:626-627`: `catalog_basenames = {cid.rsplit("/", 1)[-1] for cid in chimera_models}` → basename-level, deliberately, per its own docstring ("a namespaced reseller id never equals its resolved Chimera id").

Any model admitted under a non-bare prefix is therefore invisible to the core path. Proof from today's run: candidate `minimax/minimax-m3` (core `minimax` row) vs catalog keys `openrouter/minimax/minimax-m3` and `router9/mmx/MiniMax-M3` — all the same model, no match. Measured over the whole core candidate set: **1 of 5 candidates is already admitted by basename**, and it was **1 of the 2 entries in today's diff**. Without that, today's headline would be "1 new model", and that one is a skip.

**Fix shape:** use the same basename comparison in the core path (or reuse the prefix-strip used for reseller attribution) before a candidate is reported. **Filed as DF-CHIMERA-V2-50 (§7).**

---

## 4. The models.dev fallback cache is permanently "stale"

`~/.chimera/models-dev-cache.json` (223 provider blocks, mtime 2026-09-24 05:31) **has no `_fetched_at` key**. `provider_discovery.py:165-169` computes `age = time.time() - data.get("_fetched_at", 0)`, so with the marker missing the age is the Unix epoch distance — the live logs read `provider_cache_hit age_s=1790269581 providers=223 stale=True` (**~56.7 years**), and with `ignore_ttl=False` `_load_cache()` returns `None`, forcing a network refetch on every exercise of that path.

**Writer evidence:** `~/task-router/scripts/router_modelsdev.py:259-261` writes the very same path with a plain `json.dump(data, f)` and never adds the marker (it only *filters* `_fetched_at` when fingerprinting payloads, line 280). Yesterday's report read `age ~1 034 s, stale=False`, i.e. the marker was present then and was lost when the file was rewritten at 05:31 today.

Not blocking for this cron (it no longer reads that file), but it silently disables caching — and with it the "cache is fresh" claim — for `chimera serve` config loading whenever the task-router table is absent or invalid. Folded into DF-CHIMERA-V2-49.

---

## 5. Carried recommendations — re-verified live this tick

All seven lanes below were probed live with the repo OpenRouter key (`~/chimera-v2/.env`, sha256 `bce0faab…`). Nothing was applied to `chimera.yaml`.

| # | Recommendation | Probe today |
|---|---|---|
| 1 | **ADD** `openrouter/x-ai/grok-4.7` (premium, $0.0016/$0.0048 per 1k, 500 K ctx) | **HTTP 200 in 1.8 s**, `content='ok'` |
| 2 | **ADD** `xiaomi/mimo-v2.6-flash` (budget, $0.00014/$0.00028, 1 048 576 ctx) | **HTTP 200 in 1.8 s**, `content='ok'` |
| 3 | **ADD** `xiaomi/mimo-v2.6-pro` (standard, $0.000435/$0.00087, 1 048 576 ctx) | **HTTP 200 in 2.9 s**, `content='ok'` |
| 4 | **SKIP** `xiaomi/mimo-v2.6-pro-ultraspeed` | unchanged: 10× the pro price for latency only |
| 5 | **HOLD** `zai/glm-4.6v-flash` | OR-absent again; vision-only, and the deliberation path has no image input |
| 6 | **DECIDE** `openrouter/z-ai/glm-5.3-flashx` | **HTTP 200 in 2.6 s** at $0.37/$1.25 per MTok |
| 7 | **ADD/defer** `openrouter/openai/gpt-6-luna`, `openrouter/openai/gpt-6-sol`, `openrouter/anthropic/claude-opus-5.5` | **HTTP 200** in 1.1 s / 1.3 s / 2.3 s |

Note on #1-#3, #6, #7 under the new source: all are `openrouter/*` rides, and `openrouter` is the one reseller row the active table carries (465 rows), so these remain visible to the watch list. Their catalogue keys would be `openrouter/*` ids, which is also the convention that keeps pricing resolvable (§2).

---

## 6. Action items

1. **Accept the §1 verdicts** — this week's honest headline is **0 new catalogue additions**: `minimax-m3` is already admitted, `minimax-m2.7` is dominated by it. No catalogue edit made.
2. **Decide the carried adds** (grok-4.7, mimo-v2.6-flash, mimo-v2.6-pro, glm-5.3-flashx, gpt-6-sol/-luna, claude-opus-5.5) — all re-verified live today; none will reappear in a `--diff` report once seen.
3. **DF-CHIMERA-V2-49** — decide how the sync restores core-lab coverage under the task-router source (lane→lab mapping vs models.dev union for core discovery), and whether the 11 catalog ids that lost exact pricing get explicit `cost_per_1k_*` or keep tier defaults.
4. **DF-CHIMERA-V2-50** — basename-level dedupe in the core scan path, so already-admitted models stop reporting as new finds.
5. Unrelated, still open: `DF-CHIMERA-V2-28` (StepFun native key vs OR), `INT-GW-RESTART-001` (Hermes gateway restart), `INT-CI-010` (full-suite flake class).

---

## 7. Board rows filed this run

| Row | Priority | Finding |
|---|---|---|
| **DF-CHIMERA-V2-49** | P2 | The task-router registry is now the preferred source and the sync lost 10 of its 13 core labs: core providers present 3/13 vs 13/13 on models.dev, core candidates 5 vs 181, registered providers 2 vs 12, catalog ids with an exact pricing key 24/42 vs 35/42 — and 18/42 live catalog models now have no explicit `cost_per_1k_*` because lane-namespaced keys (`xkiro/…`, `commandcode/…`) cannot match bare catalog ids at `config.py:1068-1074`. Same row carries the always-stale models.dev cache (`_fetched_at` never written by `router_modelsdev.py:259-261`, so `provider_discovery.py:165-169` reads age ≈ 56.7 years). |
| **DF-CHIMERA-V2-50** | P3 | Core-scan catalog dedupe is exact-key (`model_sync.py:530`) while the reseller watch is basename-level (`:626-627`), so a model admitted under any prefix re-reports as a new find: measured today, 1 of 5 core candidates and 1 of 2 diff entries (`minimax/minimax-m3` vs catalog `openrouter/minimax/minimax-m3` + `router9/mmx/MiniMax-M3`). |

---

## 8. Method / reproducibility

- Diff report: `reports/latest.md` (+ timestamped copy `latest_20260924_1200.md`), diff payload `/tmp/chimera-model-sync-diff-2603947.json`, score file `reports/model_scores_20260924_1200.yaml`.
- Both-source comparison: same process, `scan_models_dev()` per source (`load_preferred_registry()` vs `_load_cache(ignore_ttl=True)`), and `discover_providers()` with the source loader patched for each run.
- Live evidence: OpenRouter catalogue (458 ids) + one `chat/completions` probe per model with the repo key; `/health` cross-checked against `git rev-parse --short HEAD`.
- Nothing in this run wrote to `chimera.yaml`, `chimera.yaml.example` or `chimera.yaml.docker`; `.seen_models.json` was updated only by the sync's own `--diff` run.
