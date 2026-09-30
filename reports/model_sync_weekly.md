# Chimera Model Sync — Weekly Report

**Date:** 2026-09-30 (cron run 17:00 UTC / 12:00 local −05)
**Run:** `scripts/model_sync_cron.py` → `model_sync.py --diff --output reports/latest.md` (diff json `/tmp/chimera-model-sync-diff-484517.json`)
**Diff result:** `reports/latest.md` line 4 reads `**Candidates:** 0 new models across 9 providers, plus 3 task-router lane finds` — the 3 lane rows are first appearances, and **one of them is a real OpenAI release that the new lane/core split demoted out of the core headline** (§2).
**Score step:** run by this tick — `--score-from` on a curated 2-row set (the cron wrapper skips step 3 when the headline is 0). Output `reports/model_scores_20260930_1203.yaml`, copied to `reports/model_sync_candidates_20260930.yaml`: **34 path scores, 0 unknown paths, 0 below the 60 floor, 0 above 100** (min 70, max 90).
**`.seen_models.json`:** **472 → 472 entries** — today's run recorded nothing, and none of the three printed lane ids is in the ledger (§1, §5).
**Registry input:** `source=task-router`, `data/tables/models.jsonl`, **29 provider blocks** (the log line says `providers=25` — see §4.3); provider cache hit `age_s=217`, `stale=False`; `provider_discovery_done models=5185 providers=10`.
**Catalog:** **42 models / 13 providers**, untouched by this run (recommend-only mandate; `load_config()` re-read: `models=42 enabled=42`). Nothing written to `chimera.yaml`, `chimera.yaml.example` or `chimera.yaml.docker`.
**Deployment:** HEAD `45fe276`, `/health` `commit: 958d7ca` → material diff **NON-EMPTY** ⇒ **STALE**, explicit deferral recorded in this tick (§7). No reload claimed.
**Archive:** yesterday's file copied to `reports/model_sync_weekly_20260929_archive.md` before this file replaced it.

**First run on new code:** DF-CHIMERA-V2-65 (`23cd355`, landed 2026-09-30 04:06) split lane-provider SKUs out of the core-lab sections. Its intent is right; it also introduced a false negative measured below (§2), filed as **DF-CHIMERA-V2-67** (§8).

---

## 1. Diff honesty check: 3 rows, 3 first appearances, 0 ledger entries

`--diff` filters on `_seen_match()` (exact id → basename-marker → basename resolution). All three printed rows are absent from the 472-entry ledger, and none matches a ledger entry's basename:

| Row id printed today | Provider (lane) | In ledger? | Class |
|---|---|---|---|
| `openai/gpt-6.1-sol` | `commandcode` | no (`gpt-6.1` → 0 ledger hits) | first appearance |
| `openai/openai/gpt-6.1-sol` | `xkiro` | no | first appearance (same model, second lane) |
| `deepseek/deepseek/deepseek-v4.1-flash-fast` | `commandcode` | no (ledger has `…v4-flash-fast`, not `v4.1`) | first appearance |

The only other candidate-shaped output was the `## Basename Skips` line (`openai/gpt-5.6` — already admitted as `openrouter/openai/gpt-5.6`), byte-identical to the 09-28/09-29 reports. **No DF-64-class re-reports today.**

**The ledger did not grow** (472 → 472, mtime 2026-09-30 12:00): lane rows are never written to `.seen_models.json` (§5). The row count therefore cannot be used to date a lane find — only the `_seen_match` filter can, and only for ids written by pre-`23cd355` runs.

---

## 2. What is genuinely new — and what the lane/core split hid

### 2.1 `openai/gpt-6.1-sol` is a real, day-old OpenAI release, not a lane SKU

| Evidence | Content |
|---|---|
| OpenRouter `/api/v1/models` | `openai/gpt-6.1-sol`, name **"OpenAI: GPT-6.1 Sol"**, created `1790702882` = **2026-09-29 17:28 UTC**, ctx **1,050,000**, **$2/M in, $10/M out**, plus `openai/gpt-6.1-sol-pro` (created 17:28:06) and `:batch` forms |
| OR description | "GPT-6.1 Sol is an upgrade to GPT-6 Sol from OpenAI, positioned below the flagship GPT-6 Astra in the GPT-6 series. It is suited for agentic coding, computer use, document-heavy professional…" |
| models.dev cache, **core `openai` block** | row `gpt-6.1-sol` present (also azure, azure-cognitive-services, github-copilot, opencode, requesty, cortecs, edenai, llmgateway, merge-gateway) |
| task-router registry | `{provider: openai-codex, model: gpt-6.1-sol, release_date: 2026-09-29, price_evidence: "…official $2 in / $0.10 cached / $10 out per 1M, DevDay release 09-29; upgrade of gpt-6-sol at the SAME official sticker with cache rate halved $0.20→$0.10"}` |
| **paid route proof** | `POST /chat/completions`, `max_tokens=4`, wire id `openai/gpt-6.1-sol` → **HTTP 200**, served as `openai/gpt-6.1-sol`, billed **1.6e-05 for 8 prompt tokens (= $2/M)** and **5e-05 for 5 completion tokens (= $10/M)** |

The sticker price is confirmed by the actual bill, not inferred from a table. Catalogue state: **no GPT-6 entry of any kind** — the newest catalogued sol is `openrouter/openai/gpt-5.6-sol`.

### 2.2 Root cause: a core-lab candidate now needs a core-lab block in the scan source

`format_report()` splits per **candidate** — `provider` in `CORE_PROVIDERS` → core section, else lane section (`model_sync.py:1223-1230`), and the headline counts core only (`:1383-1389`). Correct for lane SKUs. But the core scan can only see labs that have **their own provider block in the task-router registry**, and the registry has no `openai` block:

```
registry blocks (29): aws-bedrock clinepass commandcode commandcode-2 crof deepseek
  deepseek-duckbrain-sync deepseek-foreman fireworks-ai grok-build groq gw-deepseek
  kimi-for-coding meta-model minimax muse-code myrouter:zai-glm neuralwatt ollama-cloud
  openai-codex opencode-go opencode-go-2 openrouter sambanova stepfun synthetic xkiro xkiro-2 zai-glm
```

No `openai`, `anthropic`, `google` or `alibaba` block exists — so every OpenAI/Anthropic/Google/Alibaba release can arrive **only** through a lane row, and post-`23cd355` every lane row is excluded from the headline. The measured consequence: the very model the tick should have headlined sat in the lane section while line 4 read "0 new models".

Which registry rows carry it: `clinepass` ×4, `commandcode` ×2, `openai-codex` ×1, `openrouter` ×4, `xkiro`, `xkiro-2` — every one of them lane- or reseller-class.

---

## 3. Recommendation: **1 ADD**

Scored artifact: `reports/model_sync_candidates_20260930.yaml`. Scores are DeepSeek-generated against the canonical path list read from the code (`{p for p, _ in chimera.selector.PATH_PATTERNS}` = **32**), then validated: 0 unknown, 0 out of bounds, 0 under the 60 floor.

| Proposed key | ← predecessor | tier | $/1k in–out | paths | status |
|---|---|---|---:|---:|---|
| `openrouter/openai/gpt-6.1-sol` | `openrouter/openai/gpt-5.6-sol` | **premium** | 0.002 / 0.010 | 19 (70–90) | **recommend-add** |

Top paths: `technology_code/code_generation/python` 90, `complex_reasoning_agency/tool_use/code_execution` 88, `complex_reasoning_agency/multi_step_planning/task_decomposition` 87, `technology_code/code_generation/javascript` 86, `technology_code/testing_debugging/error_analysis` 85, `…/self_correction/debugging` 84.

**Why this one.** It is the same $2/$10 sticker as the catalogued `gpt-5.6-sol` with a cheaper cache-read rate, twice the context (1.05M vs the 5.6 series' entry), and it is the current OpenAI agentic-coding tier at DevDay pricing — a straight successor add, not a new cost line. The key shape is `openrouter/…` because that is the route the catalogue already uses for the whole GPT-5.6 family (the explicit `openrouter` branch in `gateway.py` returns the id verbatim, and the probe above proves the wire id resolves).

**Open question, named not resolved:** the `-pro` and `:batch` siblings exist and are not recommended separately — batch ids have never been admitted to this catalogue, and `-pro` needs its own benchmark story rather than a copy of the base model's scores.

---

## 4. Verified this tick, not carried

1. **`deepseek/deepseek-v4.1-flash`** — real and uncatalogued, but **not a new find**: OpenRouter-live since **2026-09-10** (ctx 1,048,576, first DeepSeek model on the CED architecture, 8B/16B activated), and it has been in the ledger since at least 09-21, so no `--diff` run will ever print it again (DF-66 class). Scored anyway this tick for a future decision: tier **budget**, 15 paths (70–84; strongest `academic_scientific/mathematics/algebra` 84, `technology_code/code_generation/python` 82).
   **Pricing is unresolved and must be checked before any entry:** earlier ticks' reseller tables show $0.15/M in / $0.60/M out, OpenRouter's current `/models` payload advertises **$0.0198/M in / $0.396/M out**, and the paid probe billed `upstream_inference_prompt_cost` 3.648e-06 for 32 tokens = **$0.114/M**. Three different numbers from three sources — do not admit on any of them without a pricing pass.
2. **`deepseek/deepseek-v4.1-flash-fast`** (the lane row) — **not a candidate**: no OpenRouter id exists (`-fast` → 0 OR rows); it is a reseller speed variant (models.dev carries `baseten/…DeepSeek-V4.1-Flash-Fast` and `coralbricks/deepseek-v4.1-flash-fast-fp4`).
3. **Registry provider count.** The log says `providers=25`; the file holds **29 blocks**. The scope line lists only the lane blocks it printed (22); the count in the log and the count in the file disagree — recorded here, not chased.

---

## 5. The lane half of the ledger problem (measured, filed with DF-67)

`.seen_models.json` is written from `new_seen`, which is updated **only** in the core loop (`:1254`) and by basename-skip markers (`:1344`). The lane section filters with the same `_seen_match()` (`:1292`) but nothing records lane ids — so for any id no pre-`23cd355` run happened to record, that filter is inert and the row re-reports **every run**.

Measured today: ledger **472 entries before and after** the run (16,565 bytes), 3 lane rows printed, **all three ids absent** from the ledger. And the report's own tracking-policy footnote names only *Reseller Watch / Blind Spot* — so a reader cannot tell a lane row's first appearance from its fifth.

**Input for the pending DF-CHIMERA-V2-66 fix:** a naive "seen but not catalogued" section (ledger ∩ live catalogue, basename-normalised) yields **430 rows** on today's ledger — overwhelmingly registry lane SKUs and `:free`/`:batch` variants. That section needs the provider-class filter or it will be unreadable.

---

## 6. Coverage behind the recommendation (re-measured this tick)

OpenRouter 464 ids; per-lab, excluding `:batch`/`:…` variants, catalogue lab resolved from the key's second-to-last segment:

| lab | OR-live | catalogued | missing | new non-batch since 2026-08-01 | newest uncatalogued |
|---|---:|---:|---:|---:|---|
| `openai` | 65 | 6 | 59 | **8** | `gpt-6.1-sol-pro`, `gpt-6.1-sol` (09-29) |
| `qwen` | 53 | 4 | 49 | **6** | `qwen3.8-max-prime`, `qwen3.8-omni-flash` |
| `google` | 28 | 5 | 23 | **2** | `gemini-3.8-flash`, `gemini-3.7-flash` |
| `mistralai` | 19 | **0** | 19 | 0 | — |
| `z-ai` | 16 | 2 | 14 | **4** | `glm-5.3-prime`, `glm-5.3-flashx` |
| `anthropic` | 15 | 5 | 10 | **3** | `claude-sonnet-5.5`, `claude-opus-5.5` |
| `deepseek` | 14 | 2 | 12 | **3** | `deepseek-v4.1-flash` |
| `minimax` | 8 | 1 | 7 | 0 | — |
| `moonshotai` | 7 | 2 | 5 | 0 | — |
| `x-ai` | 7 | 5 | 2 | **2** | `grok-4.7`, `grok-4.6` |
| `tencent` | 7 | 1 | 6 | **4** | `hy4-preview`, `hy-mt2-*` |
| `meta` | 6 | 0 | 6 | **5** | `muse-spark-1.3*`, `muse-glimmer-30b` |
| `nvidia` | 5 | 0 | 5 | 1 | `nemotron-3.5-lightning` |
| `cohere` | 5 | 0 | 5 | 1 | `command-a-plus` |
| **totals** | **255** | **33** | **222** | **39** | |

The honest reading is unchanged: most of the 222 are batch variants, `:free` tiers, superseded point releases and legacy ids — that is what a curated catalogue is *for*. The sharp number is **39 non-batch ids released since 2026-08-01 that are live and uncatalogued** — and 6 of them are already-verified, already-recommended adds that the `--diff` ledger can no longer surface.

### 6.1 The decision backlog (unchanged for the 6th consecutive tick)

| Verified add | First recommended | Today's state |
|---|---|---|
| `openrouter/openai/gpt-6-sol`, `…/gpt-6-luna` | 2026-09-24 | uncatalogued (OR-created 2026-09-21) |
| `openrouter/anthropic/claude-opus-5.5` | 2026-09-24 | uncatalogued (OR-created 2026-09-22, $4/$20 — undercuts `claude-opus-4.8` $5/$25) |
| `openrouter/x-ai/grok-4.7` | 2026-09-24 | uncatalogued (OR-created 2026-09-21, $2/$6) |
| `openrouter/z-ai/glm-5.3-flashx` | 2026-09-24 | uncatalogued (OR-created 2026-09-18) |
| `openrouter/qwen/qwen3.7-flash` | 2026-09-28 | uncatalogued |
| `openrouter/anthropic/claude-sonnet-5.5` | 2026-09-29 | uncatalogued (OR-created 2026-09-28) |
| **`openrouter/openai/gpt-6.1-sol`** | **today** | uncatalogued (OR-created 2026-09-29) |

Catalogue has stayed at **42 models across six consecutive ticks**. Value order if only part is approved: `gpt-6.1-sol` (newest, same sticker as the catalogued sol) → `gpt-6-sol` → `gpt-6-luna` → `claude-opus-5.5` (price cut on a flagship seat) → `claude-sonnet-5.5` (newer *and* cheaper than the sonnet 4.6 it would replace) → `grok-4.7` → `glm-5.3-flashx`.

---

## 7. Deployment check — **STALE**, explicit deferral recorded

| Field | Value |
|---|---|
| `/health` running commit | `958d7ca` |
| HEAD | `45fe276` |
| ancestry | `958d7ca` **is** an ancestor of HEAD |
| material diff (`src/ scripts/ tests/ pyproject.toml`) | **`scripts/model_sync.py`, `tests/test_model_sync_provider_class.py`** — NON-EMPTY |
| classification | **STALE** |
| `/health` `version` / `uptime_models` | `0.2.7` / `42` (= the 42 models on disk) |
| service start | 2026-09-29 23:19:26 −05 (predates `23cd355`, 04:06) |

**Explicit deferral, with the reason.** The only material change since the running commit is the standalone model-sync script and its test — `grep -rn model_sync src/` returns nothing, so `chimera serve` does not import or execute either; the served API surface is byte-identical to the running process. The cron path this job owns already executed the new code from disk (it runs `.venv/bin/python scripts/model_sync.py` as a fresh process). A restart would interrupt any in-flight deliberation to load code the server never runs, so this tick **defers the reload** rather than claiming a deployment: the next foreman tick on this repo should reload (`sudo systemctl restart chimera`) or record its own deferral, and until then the deployment is **not** current.

---

## 8. Board row filed this run

| Row | Priority | Finding |
|---|---|---|
| **DF-CHIMERA-V2-67** | P2 | The DF-65 lane/core split demotes a genuine core-lab release: `openai/gpt-6.1-sol` (OpenAI DevDay, 2026-09-29) reaches the scan only via `xkiro`/`commandcode`/`openai-codex` lane rows, so the 2026-09-30 run headlined "0 new models" while a day-old real OpenAI model sat in the lane section. Fix direction: promote a candidate whose id resolves to a core-lab models.dev block into the core section (counter-verified by the paid probe + OR row), keep block-less lane SKUs where they are, and record promoted ids in the ledger so they cannot re-report. |

Board census before append: **274 rows, 274 unique ids, 0 duplicates, max `DF-CHIMERA-V2-66`** (parsed line-wise, not grep-counted). Appended with `~/.hermes/scripts/board_append.py` (single-line compact JSON — a pretty-printed row is rejected as "not valid JSON" because the writer splits argv words on newlines). After: **275 rows, 275 unique, 0 dups; 33 pending.**

Related, still open: **DF-CHIMERA-V2-66** (ledger cannot distinguish admitted from ignored) — §5 supplies its missing filter requirement; DF-65 **complete** this morning (`23cd355`, tier-2 3/3).

---

## 9. Method / reproducibility

```bash
# the run (cron wrapper did step 1)
cd ~/chimera-v2 && .venv/bin/python scripts/model_sync_cron.py
#   -> reports/latest.md (+ latest_20260930_1200.md), /tmp/chimera-model-sync-diff-484517.json

# this tick (read-only unless stated; no catalogue writes anywhere):
#   candidate truth   OR GET https://openrouter.ai/api/v1/models   (464 ids, key from .env at runtime)
#   route proof       POST /chat/completions max_tokens=4 for wire id 'openai/gpt-6.1-sol' (200; $2/M/$10/M billed)
#                     and 'deepseek/deepseek-v4.1-flash' (200)
#   core-row proof    models.dev cache -> core `openai` block row `gpt-6.1-sol`
#   registry proof    grep '"model": "gpt-6.1-sol"' task-router/data/tables/models.jsonl (clinepass/commandcode/
#                     openai-codex/openrouter/xkiro/xkiro-2 rows; no `openai` block in the file)
#   scoring           set -a; . ./.env; . ~/.hermes/.env; set +a
#                     .venv/bin/python scripts/model_sync.py --score-from /tmp/chimera-curated-diff-20260930.json
#   score validation  against {p for p, _ in chimera.selector.PATH_PATTERNS}  (32 canonical paths)
#   ledger proof      472 entries before/after; none of the 3 printed ids present
#   deployment        /health commit vs HEAD + git diff --name-only <running>..HEAD -- src/ scripts/ tests/ pyproject.toml
```

Artifacts: `reports/latest.md` (+ `latest_20260930_1200.md`), `/tmp/chimera-model-sync-diff-484517.json`, `/tmp/chimera-curated-diff-20260930.json`, `reports/model_scores_20260930_1203.yaml`, `reports/model_sync_candidates_20260930.yaml`, this file, `reports/model_sync_weekly_20260929_archive.md`. Throwaway diagnostics (`/tmp/_diag_*.py`) removed.

**Skill hygiene, still open (third tick):** `chimera-development` cites `references/category-paths.md`, which does not exist in the repo. Repoint it at `chimera.selector.PATH_PATTERNS` **and** record the tuple-unpacking step (`{p for p, _ in PATH_PATTERNS}` — unpacking wrong makes every score read as an unknown path).

---

## 10. Action items

1. **Decide today's ADD:** `openrouter/openai/gpt-6.1-sol` (tier premium per the scorer; the sibling `gpt-5.6-sol` is premium too, so no tier question this time).
2. **Decide the backlog (§6.1):** 7 verified adds spanning seven ticks, the last five invisible to future `--diff` runs.
3. **DF-CHIMERA-V2-67** (§2/§8) — the lane split now hides real core-lab releases; P2, this is the first run affected.
4. **DF-CHIMERA-V2-66** — still pending; §5 gives the filter requirement so its "pending" section is usable.
5. **Reload owed** (§7) — `scripts/model_sync.py` is in the material diff while `chimera serve` runs the pre-fix tree; next tick reload or re-defer explicitly.
6. **Still open from previous ticks:** DF-61, -62, -63 (`pending`); DF-28 (StepFun native key vs OR); `mistralai/` 19-live / 0-catalogued; `deepseek-v4.1-flash` pricing needs three-way reconciliation before it can ever be admitted.
