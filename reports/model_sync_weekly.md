# Chimera Model Sync — Weekly Report

**Date:** 2026-09-29 (cron run 17:00 UTC / 12:00 local −05)
**Run:** `scripts/model_sync_cron.py` → `model_sync.py --diff --output reports/latest.md` (diff json `/tmp/chimera-model-sync-diff-1058170.json`), then step 3 `--score`
**Diff result:** `reports/latest.md` line 4 reads `**Candidates:** 1 new models across 13 providers` — **1 row, and it is a genuine first appearance** (§1)
**Score step:** **OK** — `reports/model_scores_20260929_1200.yaml` written (1 entry, **30** path scores, 0 unknown paths, 0 out-of-bounds, 0 scores <60; min 68, max 88).
**`.seen_models.json`:** **471 → 472 entries** (+1 = this row only; the `openai/gpt-5.6` basename skip is byte-identical to 09-28, so the arithmetic is unambiguous). The ledger is **untracked/gitignored**, which is finding §4.
**Registry input:** `source=task-router`, `data/tables/models.jsonl`, **25 providers** (unchanged from 09-28); provider cache hit `age_s=1086` then `stale=False`; `provider_discovery_done models=5149 providers=10`.
**Catalog:** **42 models / 13 providers**, untouched by this run (recommend-only mandate; `load_config()` re-read to confirm: `models=42 enabled=42`). Nothing written to `chimera.yaml`, `chimera.yaml.example` or `chimera.yaml.docker`.
**Deployment:** HEAD `3f32a87`, `/health` `commit: 3f32a87`, `version 0.2.7`, `uptime_models: 42` → **CURRENT** (identical commits; the running process also reports the same 42 models that are on disk). No reload owed, none claimed.
**Archive:** yesterday's file copied to `reports/model_sync_weekly_20260928_archive.md` before this file replaced it.

---

## 1. Diff honesty check: 1 row, 1 first appearance

`--diff` filters on the lane-resolved id (`model_sync.py:1063-1065`, with `_seen_match()` doing exact-then-basename matching — the DF-CHIMERA-V2-64 fix). Today's ledger grew by exactly **one** entry and the report printed exactly **one** row, so the row is new rather than re-surfaced:

| Row id printed today | Ledger evidence | Class |
|---|---|---|
| `anthropic/claude-sonnet-5-5` | `anthropic/claude-sonnet-5-5` was **absent** from the ledger before this run; it is present after (471 → 472) | **first appearance** |

The only other candidate-shaped output was the `## Basename Skips` line (`openai/gpt-5.6` — already admitted as `openrouter/openai/gpt-5.6`), byte-identical to the 09-28 report, so it contributed no new ledger entry. **No re-reports today** — the DF-CHIMERA-V2-64 class did not reproduce.

Note the shape of the row: `anthropic/claude-sonnet-5-5` is the **core models.dev row shape** (dashes, `family=claude-sonnet`, a description string, `provider=anthropic`), *not* a lane-resolved shape. Unlike 09-28 — where 5 of 7 rows were lane SKUs (§4 of last week's report, DF-CHIMERA-V2-65, still `pending`) — today's single row came from a core lab and names a real model.

---

## 2. What is genuinely new — verification this tick

Method: live OpenRouter catalogue (`GET /api/v1/models`, **460 ids**, key read from `~/chimera-v2/.env` at runtime, never printed) + the models.dev cache + the vendor's own product page + independent press. No report field was treated as evidence on its own.

| Id | Evidence | Verdict |
|---|---|---|
| `anthropic/claude-sonnet-5.5` (OR) / `claude-sonnet-5-5` (models.dev) | **OR-live**: created **2026-09-28 18:04 UTC**, ctx **1,000,000**, **$2/M in, $10/M out**; batch variant `:batch` live at $1/$5. **models.dev core row**: `claude-sonnet-5-5`, release_date **2026-09-28**, cost in 2 / out 10 / cache_read 0.2 / cache_write 2.5. **Vendor page** (`anthropic.com/claude/sonnet`): "$2 per million input tokens and $10 per million output tokens", 1M ctx, 90% caching / 50% batch savings. **Press, all 2026-09-28**: VentureBeat, SiliconANGLE, 9to5Mac, Thurrott, Benzinga (+ llm-stats/alphacorp: 1M ctx, 128k max output). | **ADD** (family completion + price cut) |

### 2.1 The three facts that decide this week

- **It is real, shipped yesterday, and the catalogue has no Sonnet 5 at all.** The newest sonnet entry in `chimera.yaml` is **`anthropic/claude-sonnet-4.6`** at **$3/$15 per Mtok** (OR-created 2026-02-17). Sonnet 5.5 is seven months newer **and cheaper per token** — the rare case where the successor dominates rather than displaces. There is no Sonnet 5 (June 2026) entry to step over, so this is a straight family jump.
- **The route is proven with paid calls, both shapes, not inferred from the config.** Two wire ids were probed live against OpenRouter: `anthropic/claude-sonnet-5.5` (what the explicit `openrouter/…` key shape produces) and `claude-sonnet-5.5` (what the native `anthropic` shape produces after the F8 reroute). **Both returned HTTP 200 and were served as `anthropic/claude-sonnet-5.5`** (~$0.0001 of tokens in total). The detailed trace is in §3.
- **The 1M context is worth stating on its own.** Bane's floor is 500k; 5.5 clears it at 1M with 128k max output, matching Opus 5.5 — so an add here is a mid-tier seat that can take whole-repo prompts, not just a cheaper chat model.

**Two independent sources agree on price, and the third-party coverage is unanimous on the date.** No "coming soon" or rumour class here — this is a shipped model with a vendor pricing statement.

---

## 3. Recommendation: **1 ADD**

Scored artifact: `reports/model_sync_candidates_20260929.yaml` — 1 entry, 30 path scores reproduced verbatim from the scorer, validated against the canonical path list read from the code (`{p for p, _ in chimera.selector.PATH_PATTERNS}` = **32** paths): **0 unknown, 0 out-of-bounds, 0 below the 60 floor.**

| Proposed key | ← predecessor | tier | $/1k in–out | status |
|---|---|---|---:|---|
| `openrouter/anthropic/claude-sonnet-5.5` | `anthropic/claude-sonnet-4.6` | standard † | 0.002 / 0.010 | **recommend-add** |

† **Open question, named rather than resolved:** the scorer says `standard`, while the sibling entry it would sit beside (`anthropic/claude-sonnet-4.6`) is `premium` in the catalogue. The measured average is **(0.002 + 0.010)/2 = 0.006 $/1k**, which sits between the tier defaults (`standard` 0.001, `premium` 0.009). Because `selector.price_sensitivity = 0.0`, the tier feeds only the cost model and **does not influence model selection** — so either choice is selection-neutral and this is a bookkeeping decision, not a performance one.

**Which key shape?** Both work; the difference is what the entry *depends on*:

| Shape | Key | Wiring | Wire id sent | Probed |
|---|---|---|---|---|
| A (explicit) | `openrouter/anthropic/claude-sonnet-5.5` | `provider: openrouter` → `gateway.py:322-325` returns the id verbatim | `anthropic/claude-sonnet-5.5` | **200** |
| B (native) | `anthropic/claude-sonnet-5.5` | `provider: anthropic` → no Anthropic credential → **F8** (`gateway.py:622-634`) reroutes to OpenRouter with `fallback_provider="openrouter"` → same literal-passthrough branch | `anthropic/claude-sonnet-5.5` | **200** |

Shape A is recommended because it states the route the call actually takes instead of relying on a credential-fallback. Shape B matches the three existing native entries (`claude-opus-4.8`, `claude-sonnet-4.6`, `claude-haiku-4.5`) and is equally functional — a legitimate choice if family symmetry is preferred.

**Verified credential fact behind that choice:** `load_config()` returns `api_keys = {anthropic: False, deepseek: True, google: True, openai: True, openrouter: True, xai: True, zai: True}`. `ANTHROPIC_API_KEY` is absent from both `~/chimera-v2/.env` (which holds **only** `OPENROUTER_API_KEY`) and `~/.hermes/.env`. So **the three "native anthropic" catalogue entries are today 100 % OpenRouter-routed via F8** — by design, not a defect, and it means a Sonnet 5.5 add lands on OpenRouter whichever shape is chosen.

**A hunch, tested and refuted (recorded because the next tick should not re-raise it):** I expected `anthropic/claude-opus-4.7` (whose key shape and `provider: openrouter` do not match, so it cannot be caught by the `openrouter/` passthrough) to resolve through the generic `base_url` branch at `gateway.py:357-379` to a **bare** wire id. Reading the code, the explicit `provider == "openrouter"` branch at **`gateway.py:322-325` returns first** and emits `openrouter/anthropic/claude-opus-4.7`; and as a second check the bare id `claude-opus-4.7` **returned HTTP 200 from OpenRouter anyway** (OR normalises it). No defect — no row filed.

**Accounted-for and not carried:** the single `Basename Skips` row (`openai/gpt-5.6`, already admitted) and the ~300 Reseller Watch / Blind Spot rows (informational by design, deliberately not recorded in the ledger). Reasons recorded in the candidates file → `not_carried`.

Nothing was written to `chimera.yaml`, `chimera.yaml.example` or `chimera.yaml.docker`.

---

## 4. The coverage number behind the recommendations (measured this tick, new section)

Recommendations only mean something against the catalogue's real coverage, so this tick measured it directly: the live OpenRouter catalogue has **460 ids** against a **42-model** Chimera catalogue.

| lab | OR-live | catalogued | missing | missing, **non-batch, released since 2026-08-01** |
|---|---:|---:|---:|---:|
| `anthropic/` | 29 | 5 | 24 | **3** |
| `openai/` | 100 | 5 | 95 | **6** |
| `google/` | 41 | 4 | 37 | **2** |
| `deepseek/` | 15 | 2 | 13 | **3** |
| `z-ai/` | 18 | 2 | 16 | **4** |
| `qwen/` | 54 | 4 | 50 | **7** |
| `moonshotai/` | 8 | 2 | 6 | 0 |
| `minimax/` | 8 | 1 | 7 | 0 |
| `x-ai/` | 8 | 4 | 4 | **2** |
| `mistralai/` | 25 | **0** | 25 | 0 |
| **totals** | | | **277** | **27** |

The honest reading of that table: most of the 277 are batch variants, `:free` tiers, superseded point releases and legacy ids — that is what a curated catalogue is *for*. The sharp number is the last column: **27 non-batch models released since 2026-08-01 are live and uncatalogued**, and they are the ones the last four ticks have been recommending one at a time. Two entries of note: **`mistralai/` has 25 live models and zero catalogue entries**, and the newest uncatalogued items per lab are `anthropic/claude-sonnet-5.5` (today), `z-ai/glm-5.3-prime`, `qwen/qwen3.8-max-prime`, `anthropic/claude-opus-5.5`, `openai/gpt-6-sol` / `gpt-6-luna`, `x-ai/grok-4.7`, `z-ai/glm-5.3-flashx`, `deepseek/deepseek-v4.1-flash`.

### 4.1 The decision queue is now the real story (state it plainly)

The catalogue has stayed at **42 models across five consecutive ticks** while verified additions accumulate. Every one of these was verified live on the date shown and **none will re-appear in a future `--diff` report** — the ledger silences them the moment they are first seen (§5):

| Verified add | First recommended | Today's state |
|---|---|---|
| `openrouter/openai/gpt-6-sol`, `openrouter/openai/gpt-6-luna` | 2026-09-24 | uncatalogued (re-verified OR-live: `openai/gpt-6-sol` created 2026-09-22) |
| `openrouter/anthropic/claude-opus-5.5` | 2026-09-24 | uncatalogued (OR-created 2026-09-22, $4/$20 — undercuts `claude-opus-4.8` $5/$25) |
| `openrouter/x-ai/grok-4.7` | 2026-09-24 | uncatalogued (OR-created 2026-09-21, $2/$6) |
| `openrouter/z-ai/glm-5.3-flashx` | 2026-09-24 | uncatalogued (OR-created 2026-09-18) |
| `openrouter/qwen/qwen3.7-flash` | 2026-09-28 | uncatalogued |
| `openrouter/anthropic/claude-sonnet-5.5` | **today** | uncatalogued (recommend-add, §3) |

That is a **decision backlog, not a discovery backlog** — and it is the one thing this cron cannot fix for itself (mandate: recommend-only). If only part of it is ever approved, the order that maximises value per approval is unchanged from 09-24: `gpt-6-sol` → `gpt-6-luna` (replace incumbents at no new cost) → `claude-opus-5.5` (a price cut on a flagship seat) → **`claude-sonnet-5.5`** (newer *and* cheaper than the sonnet 4.6 it would replace) → `grok-4.7` → `glm-5.3-flashx`.

---

## 5. The ledger half that is still unfixed (finding, filed this tick)

`.seen_models.json` is the **only** record of what has been seen, and it has two properties that matter together:

1. **It cannot distinguish "seen and admitted" from "seen and ignored".** The filter suppresses a row once its id is in the ledger, so a verified-but-unapplied find is silent forever. Measured instance: `anthropic/claude-opus-5.5` (verified ADD on 09-24/25/26) is in the ledger and **not** in the catalogue — today's `--diff` cannot report it, and no run ever will again. The only thing keeping it alive is prose in weekly reports.
2. **It is untracked and gitignored.** `git ls-files --error-unmatch .seen_models.json` fails, so the ledger has no history, cannot be diffed against a known state, and a lost or stale copy silently changes what counts as "new" — the failure mode the skill's own *seen-file trap* note describes.

DF-CHIMERA-V2-64 fixed the *other* half (id-shape matching, `status: done`). This half is filed as **DF-CHIMERA-V2-66** (§7) with a concrete fix: a "seen but not catalogued" section derived at run time by intersecting the ledger with the live catalogue.

---

## 6. Deployment check

| Field | Value |
|---|---|
| `/health` running commit | `3f32a87` |
| HEAD | `3f32a87` |
| ancestry / material diff | **identical commits** — no diff run; nothing can be unreleased |
| `/health` `version` / `uptime_models` | `0.2.7` / `42` (= the 42 models on disk) |
| classification | **CURRENT** |
| action | **none owed** — no reload claimed, none required |

The catalogue itself is untracked/local-only by design (AGENTS.md), so a catalogue edit could never be inferred from git; the `uptime_models: 42` read-back is the available evidence that the running process matches the on-disk file.

Working-tree note (not this job's to fix, recorded so it is not mistaken for a sync artifact): untracked leftovers exist at the repo root and board dir — `gaps.json`, `.coding-hermes/board/.lock`, and three `*.jsonl.bak*` files, plus a modified `.gitreins/tasks.yaml`. Nothing in this run wrote to any of them.

---

## 7. Board row filed this run

| Row | Priority | Finding |
|---|---|---|
| **DF-CHIMERA-V2-66** | P3 | `scripts/model_sync.py`'s `.seen_models.json` ledger suppresses a candidate permanently once seen, so verified-but-unapplied finds stop being reported (measured: `anthropic/claude-opus-5.5` verified ADD 2026-09-24, still uncatalogued 09-29, cannot re-surface), and the ledger is untracked/gitignored so it has no auditable history. Fix direction: emit a "Pending — seen, not catalogued" section each run by intersecting the ledger with the live catalogue (normalising `openrouter/*`), so an approved-but-unapplied add keeps appearing until admitted or explicitly dismissed. |

Board census before append: **269 rows, 269 unique ids, 0 duplicates, max `DF-CHIMERA-V2-65`** (verified by parsing every line, not by grep count). Appended with `~/.hermes/scripts/board_append.py` (O_APPEND, fusion guard, post-write re-read).

---

## 8. Method / reproducibility

```bash
# the run (cron wrapper does both steps)
cd ~/chimera-v2 && .venv/bin/python scripts/model_sync_cron.py
#   -> reports/latest.md (+ latest_20260929_1200.md), /tmp/chimera-model-sync-diff-1058170.json,
#      reports/model_scores_20260929_1200.yaml

# verification this tick (read-only; no catalogue writes anywhere):
#   OR catalogue        GET https://openrouter.ai/api/v1/models   (460 ids, key from .env at runtime)
#   route proof         POST /chat/completions max_tokens=4 for wire ids
#                       'anthropic/claude-sonnet-5.5' and 'claude-sonnet-5.5'  (both 200)
#   score validation    against {p for p, _ in chimera.selector.PATH_PATTERNS}  (32 canonical paths)
#   credentials         load_config().api_keys -> booleans only; ANTHROPIC_API_KEY absent
#   coverage            per-lab OR-live vs catalogue ids, non-batch cutoff 2026-08-01
#   suppression proof   ledger presence of anthropic/claude-opus-5.5 vs its absence in chimera.yaml
#   deployment          /health commit vs HEAD (identical) + uptime_models vs on-disk count
```

Artifacts: `reports/latest.md` (+ `latest_20260929_1200.md`), `/tmp/chimera-model-sync-diff-1058170.json`, `reports/model_scores_20260929_1200.yaml`, `reports/model_sync_candidates_20260929.yaml`, this file, `reports/model_sync_weekly_20260928_archive.md`. Throwaway diagnostics (`/tmp/_diag_*.py`) were removed.

**Skill hygiene, still open:** `chimera-development` cites `references/category-paths.md`, which does not exist in the repo. Repoint it at `chimera.selector.PATH_PATTERNS` **and** record the tuple-unpacking step (`{p for p, _ in PATH_PATTERNS}` — unpacking wrong makes every score read as an unknown path).

---

## 9. Action items

1. **Decide today's ADD:** `openrouter/anthropic/claude-sonnet-5.5` (tier question in §3†: scorer `standard` vs sibling `premium`; selection-neutral either way).
2. **Decide the backlog (§4.1):** 6 verified adds spanning five ticks, all invisible to future `--diff` runs. Suggested order recorded there.
3. **DF-CHIMERA-V2-66** (§5/§7) — the ledger cannot distinguish admitted from ignored, and is untracked. P3.
4. **DF-CHIMERA-V2-65** (09-28, still `pending`) — lane-provider SKUs and vendor aliases printed as core-lab candidates. Not reproduced today (today's row is a core row), but unfixed.
5. **Still open from previous ticks:** DF-CHIMERA-V2-61, -62, -63 (`pending`); DF-CHIMERA-V2-28 (StepFun native key vs OR); `mistralai/` is 25-live / 0-catalogued if Mistral coverage is ever wanted.
6. **Carried gaps, still unscored:** `moonshotai/kimi-k3` (OR-live), `qwen/qwen3.8-flash` (OR-live) — both uncatalogued, neither surfaced today (both long since in the ledger).
