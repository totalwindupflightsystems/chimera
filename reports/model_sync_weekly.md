# Chimera Model Sync — Weekly Report

**Date:** 2026-10-01 (cron run 17:00 UTC / 12:00 local −05)
**Run:** `scripts/model_sync_cron.py` → `model_sync.py --diff --output reports/latest.md` (diff json `/mnt/bulk/scratch/chimera-model-sync-diff-2813229.json`)
**Diff result:** `reports/latest.md` line 4 reads `**Candidates:** 1 new models across 13 providers, plus 1 task-router lane find` — and for the first time since DF-65/DF-67 the single core row is the real one (§1, §2).
**Score step:** the cron wrapper's auto-score ran (`DEEPSEEK_API_KEY resolved from /home/kara/.hermes/.env`) → `reports/model_scores_20261001_1200.yaml`, 2 model entries. Re-validated this tick against `{p for p, _ in chimera.selector.PATH_PATTERNS}` = **32 canonical paths**: 0 unknown, 0 below the 60 floor, 0 above 100 (§3).
**`.seen_models.json`:** **472 → 474 entries** (474 unique, 0 dups, sorted) — the run appended exactly the two ids it printed, and both are present (§5). Yesterday's archived report recorded 472 pre- and post-run.
**Registry input:** `source=task-router`, `data/tables/models.jsonl` (1,877 rows, mtime 2026-10-01 11:45), **29 provider blocks**; provider cache hit `age_s=1020`, `stale=False`; `provider_discovery_done models=5196 providers=10`. The log's `providers=25` still disagrees with the file's 29 (§6).
**Catalog:** **42 models / 42 enabled / 13 providers**, untouched by this run (recommend-only mandate; `load_config()` re-read after the reload).
**Deployment:** HEAD `897dbd0`, running commit at tick start `628fc2d`, material diff **NON-EMPTY** ⇒ **STALE** ⇒ **reloaded this tick** and verified — post-restart `/health` = `897dbd0` and `smoke_live.py` exit 0 (§7).
**Archive:** yesterday's file copied to `reports/model_sync_weekly_20260930_archive.md` before this file replaced it.

**DF-CHIMERA-V2-67 verified fixed.** The lane/core split that demoted yesterday's model now promotes it: the diff json carries `"core_lab_member": true`, the row renders in the **OpenAI** core section, and the headline counts it. Both halves of the fix are confirmed by observation, not by the commit message (§1, §5).

---

## 1. Diff honesty check: 1 core row + 1 lane row, both first appearances

`--diff` filters on `_seen_match()` (exact → basename-marker → basename). Both printed rows were absent from the 472-entry ledger at run time and both are in it now:

| Row id printed today | Provider | Ledger before | Class |
|---|---|---|---|
| `openai/gpt-6.1-sol` | `xkiro` (lane-carried, `core_lab_member: true`) | no | **first appearance — promoted to the OpenAI core section** |
| `deepseek/deepseek-v4.1-flash-fast` | `commandcode` (lane) | no | first appearance, lane SKU — not a catalog candidate (§2.2) |

The only other candidate-shaped output was the standing basename skip (`openai/gpt-5.6` — already admitted as `openrouter/openai/gpt-5.6`), byte-identical to recent runs. **No DF-64-class re-reports.**

---

## 2. Candidate verification

### 2.1 `openai/gpt-6.1-sol` — VERIFIED, recommend adding

| Evidence | Content |
|---|---|
| OpenRouter `/api/v1/models` (re-fetched this tick, 463 ids) | `openai/gpt-6.1-sol`, name **"OpenAI: GPT-6.1 Sol"**, `created` `1790702882` = **2026-09-29 17:28:02 UTC**, ctx **1,050,000**, pricing `0.000002`/`0.00001` per token = **$2/M in, $10/M out**, cache-read **$0.10/M** |
| Sibling | `openai/gpt-6.1-sol-pro` live (`created` 1790702886) — same price (see §3 open question) |
| models.dev cache, core `openai` block | row `gpt-6.1-sol` present: `{input 2, output 10, cache_read 0.1, cache_write 2.5}`, with a >272k-context tier at 4/15 |
| OpenAI official | `openai.com/index/introducing-gpt-6-1-sol/`; TechCrunch + Gizmodo 2026-09-29 (DevDay; Astra scrapped, 6.1 Sol shipped instead) |
| Paid route proof | yesterday's tick (`20260930_1200`) POSTed wire id `openai/gpt-6.1-sol` → **HTTP 200**, billed $2/M in / $10/M out |
| Catalogue state | **no GPT-6 entry of any kind** — the newest catalogued sol is `openrouter/openai/gpt-5.6-sol` |

### 2.2 `deepseek/deepseek-v4.1-flash-fast` — NOT a candidate (lane SKU)

Absent from OpenRouter: the `v4.1-flash` needle returns exactly `deepseek/deepseek-v4.1-flash` and `…:batch`. It is a reseller speed variant carried by the `commandcode` lane (commandcode.ai prices it $0.16/M in, $0.58/M out). Unchanged from yesterday's §4.2 — reported in the lane section, never counted in the headline, **no recommendation**.

### 2.3 Reseller-watch rows reviewed, not recommended

`gpt-6.1-sol-pro`, `gpt-6-sol{,-fast,-pro}`, `gpt-6-luna{,-fast,-pro}`, `gpt-6-astra{,-fast,-pro}`, all `:batch` forms. `-pro`/`-fast` need their own benchmark story rather than a copy of the base scores, and batch ids have never been admitted to this catalogue. The Astra rows also contradict the launch reporting (Astra was pulled), so they should not be admitted on reseller rows alone.

---

## 3. Recommendation: **1 ADD**

Scored artifact: `reports/model_scores_20261001_1200.yaml`. Scores are DeepSeek-generated against the 32 canonical paths, then validated this tick.

| Proposed catalog key | ← predecessor | tier | $/1k in–out | paths | status |
|---|---|---|---:|---:|---|
| `openrouter/openai/gpt-6.1-sol` | `openrouter/openai/gpt-5.6-sol` | **premium** | 0.002 / 0.010 | 31 (78–90) | **recommend-add** |

Top paths: `general_knowledge/reasoning/explanation` 90, `technology_code/code_generation/python` 90, `complex_reasoning_agency/multi_step_planning/task_decomposition` 88, `complex_reasoning_agency/self_correction/debugging` 88, `complex_reasoning_agency/tool_use/code_execution` 88, `academic_scientific/mathematics/{algebra,calculus}` 88.
Unscored canonical path: `multimedia_processing/image/generation` only (1 of 32) — correct for a text model.

**Why this one.** Same $2/$10 sticker as the catalogue's `gpt-5.6-sol` with a cheaper cache-read ($0.10/M vs the 5.6 series' $0.20/M), 1.05M context, and it is the current OpenAI agentic-coding tier at DevDay pricing — a successor add, not a new cost line.

**`openrouter/*` vs native provider — decided from the catalogue, not by preference.**

| Option | Evidence | Verdict |
|---|---|---|
| `openrouter/openai/gpt-6.1-sol` | route already used by all 5 GPT-5.6 family entries (+17 `openrouter/` keys total); wire id proven 200 with the billed rates above; `gateway.py` openrouter branch returns the id verbatim | **recommended** |
| `openai/gpt-6.1-sol` (native) | `api_keys.openai` is populated (`${OPENAI_API_KEY}`, key present in `~/.hermes/.env`) and discovery lists `openai` in `discovered_not_configured`, but `/v1/health` reports provider `openai` as `{healthy: false, note: "no models configured for provider"}` — **zero catalog precedent**, and the first native entry would also be the first model to exercise that path | available, not recommended |

**Artifact defect worth knowing before pasting:** the scorer's `chimera_id: openai/openai/gpt-6.1-sol` is the **lane-resolved** id, not a routable catalog key (the gateway strips one segment → wire id `openai/gpt-6.1-sol`). Filed as **DF-CHIMERA-V2-68** (§8). Use the key in the table above.

---

## 4. Carried forward: the decision backlog is now 7 ticks old

Re-checked against `chimera.yaml` this tick (`grep -c` per id → **0 hits for every one**); all still live and uncatalogued, and all now invisible to future `--diff` runs:

| Verified add | First recommended | State |
|---|---|---|
| `openrouter/openai/gpt-6-sol`, `…/gpt-6-luna` | 2026-09-24 | uncatalogued (OR-created 2026-09-22) |
| `openrouter/anthropic/claude-opus-5.5` | 2026-09-24 | uncatalogued ($4/$20 — undercuts the catalogued `claude-opus-4.8` at $5/$25) |
| `openrouter/x-ai/grok-4.7` | 2026-09-24 | uncatalogued |
| `openrouter/z-ai/glm-5.3-flashx` | 2026-09-24 | uncatalogued |
| `openrouter/qwen/qwen3.7-flash` | 2026-09-28 | uncatalogued |
| `openrouter/anthropic/claude-sonnet-5.5` | 2026-09-29 | uncatalogued |
| **`openrouter/openai/gpt-6.1-sol`** | **today** | uncatalogued |

Catalogue has stood at **42 models for seven consecutive ticks**. Value order if only part is approved: `gpt-6.1-sol` → `gpt-6-sol` → `gpt-6-luna` → `claude-opus-5.5` → `claude-sonnet-5.5` → `grok-4.7` → `glm-5.3-flashx`.

---

## 5. Ledger behaviour after the DF-67 fix — and the DF-66 cost it now demonstrates

`472 → 474` (16,565 → 15,744 bytes, 474 unique, sorted). Both printed ids are present as exact entries:

```
line 159: "deepseek/deepseek/deepseek-v4.1-flash-fast"
line 375: "openai/openai/gpt-6.1-sol"
```

Pre-DF-67, lane ids were never written (yesterday measured 472 → 472 with all three printed ids absent), so lane rows re-reported every run. Recording them is the right fix — and it immediately exposes the **DF-66** trade: `openai/openai/gpt-6.1-sol` is now in the ledger, the `--diff` filter resolves basenames, so **tomorrow's run can never print this model again while it stays uncatalogued**. Today's headline find joins the seven-tick backlog in the invisible set. Nothing new to file (DF-66 covers it, P3, pending) — this is its first concrete core-candidate instance, and the argument for reprioritising it.

---

## 6. Carry-over measurement (unchanged, recorded not chased)

The wrapper's log line says `providers=25`; `data/tables/models.jsonl` holds **29** distinct provider blocks (1,877 rows). The scope footnote lists the 22 lane blocks it printed. Two counts, one file — same open discrepancy as yesterday's §4.3.

---

## 7. Deployment check — STALE at tick start → **reloaded, CURRENT, proven**

| Field | Value |
|---|---|
| running commit at tick start | `628fc2d` (process uptime 16h21m at 12:01, started 2026-09-30 19:40 −05) |
| HEAD | `897dbd0` |
| ancestry | `628fc2d` **is** an ancestor of HEAD |
| material diff (`src/ scripts/ tests/ pyproject.toml`) | `src/chimera/api/server.py`, `src/chimera/cli/main.py`, `src/chimera/web/routes.py`, `src/chimera/web/sse.py`, `tests/test_parallel_stages.py` — **NON-EMPTY** ⇒ **STALE** |
| nature of the diff | 19 insertions / 14 deletions — return-type annotations (`575ebd5`) plus module-level import hoisting in `web/routes.py`; plus a CI timing-threshold relaxation (`c5ef8b1`) |
| action | `sudo systemctl restart chimera` |
| post-restart `/health` | `{"status":"alive","commit":"897dbd0","version":"0.2.7","uptime_models":42}` — equals HEAD |
| smoke | `.venv/bin/python scripts/smoke_live.py` → `deployment: CURRENT — running commit 897dbd0 == expected commit origin/main`, `SMOKE PASS: live deliberation returned a merged answer`, **exit 0** |

Both halves of the evidence contract are met (post-restart `/health` shows the new commit **and** the smoke test passes), so this tick claims the reload rather than deferring it. No in-flight deliberation was interrupted (the only calls in the 60s before the restart were `/v1/health` probes).

---

## 8. Board row filed this run

| Row | Priority | Finding |
|---|---|---|
| **DF-CHIMERA-V2-68** | P3 | The scored-candidate artifact advertises a catalog key it does not produce: `chimera_id` is the **lane-resolved** id, so a lane-carried core release renders `openai/openai/gpt-6.1-sol` (report line 15, `model_scores_20261001_1200.yaml:34`) and a lane SKU renders triple-prefixed `deepseek/deepseek/deepseek-v4.1-flash-fast`. The gateway strips exactly one leading segment, so neither value is routable; the usable admission key (`openrouter/openai/gpt-6.1-sol`) appears nowhere in the artifact, including the scorer YAML the docs call "chimera.yaml-ready". Fix direction: emit a catalog-shaped key from the catalogue's own provider prefixes **alongside** the lane-resolved id (the seen filter must keep the lane id). |

Board census before append: **279 rows, 279 unique ids, 0 duplicates, 31 pending, max `DF-CHIMERA-V2-67` (complete)** — parsed line-wise via `json.loads`, not grep-counted. Appended with `~/.hermes/scripts/board_append.py` (single-line compact JSON, as the writer splits argv words on newlines). After: **280 rows, 280 unique, 0 duplicates, 32 pending**.

---

## 9. Method / reproducibility

```bash
# the run (cron wrapper did steps 1-2)
cd ~/chimera-v2 && .venv/bin/python scripts/model_sync_cron.py
#   -> reports/latest.md (+ latest_20261001_1200.md), /mnt/bulk/scratch/chimera-model-sync-diff-2813229.json

# this tick (read-only unless stated; no catalogue writes anywhere):
#   candidate truth   GET https://openrouter.ai/api/v1/models   (463 ids; key read from .env at runtime)
#   core-row proof    models.dev cache -> core `openai` block row `gpt-6.1-sol`
#   lane proof        OR has no `deepseek-v4.1-flash-fast` id (2 hits, neither -fast)
#   scoring           reports/model_scores_20261001_1200.yaml validated against
#                     {p for p, _ in chimera.selector.PATH_PATTERNS} (32 paths)
#   ledger proof      json.loads(.seen_models.json) -> 474 unique, both printed ids present
#   catalogue truth   load_config() -> models 42 / enabled 42 / providers 13; per-id grep -> 0 hits for all 7 backlog ids
#   deployment        git merge-base --is-ancestor 628fc2d HEAD; git diff --name-only 628fc2d..HEAD -- src/ scripts/ tests/ pyproject.toml
#                     sudo systemctl restart chimera; /health commit == git rev-parse --short HEAD; scripts/smoke_live.py -> exit 0
```

Artifacts: `reports/latest.md` (+ `latest_20261001_1200.md`), `/mnt/bulk/scratch/chimera-model-sync-diff-2813229.json`, `reports/model_scores_20261001_1200.yaml`, this file, `reports/model_sync_weekly_20260930_archive.md`. Throwaway diagnostics (`/tmp/_diag_*.py`) removed after use.

**Skill hygiene, still open (fourth tick):** `chimera-development` cites `references/category-paths.md`, which does not exist in the repo (`~/chimera-v2/references/` does not exist at all; the file lives in the skill dir and the canonical list is `chimera.selector.PATH_PATTERNS`). Not an AGENTS.md edit — flagged here only.

---

## 10. Action items

1. **Decide today's ADD:** `openrouter/openai/gpt-6.1-sol` — premium, $2/$10 per M, 1.05M ctx, verified via OR + models.dev + OpenAI + a paid probe.
2. **Decide the backlog (§4):** 7 verified adds, all now invisible to `--diff`; the pricing case that does not need a decision from you is `claude-opus-5.5` (cheaper than the catalogued 4.8).
3. **DF-CHIMERA-V2-66 (P3 → recommend P2)** — today's ledger write suppresses a live core-lab candidate permanently; seven ticks of backlog are the standing cost.
4. **Still open:** DF-61, -62, -63 (`pending`); DF-28 (StepFun native key vs OR); `mistralai/` 19-live / 0-catalogued; `deepseek-v4.1-flash` three-way pricing reconciliation; registry `providers=25` vs 29 blocks (§6).
5. **Deployment:** none owed — reloaded and proven this tick (§7).
