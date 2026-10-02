# Chimera Model Sync — Weekly Report

**Date:** 2026-10-02 (cron run 17:00 UTC / 12:00 local −05)
**Run:** `scripts/model_sync_cron.py` → `model_sync.py --diff --output reports/latest.md` (diff json `/mnt/bulk/scratch/chimera-model-sync-diff-2311260.json`)
**Diff result:** `{}` — **0 new models, 0 task-router lane finds.** Report line 4: `**Candidates:** 0 new models across 13 providers, plus 0 task-router lane finds`. First zero-diff run since 2026-09-28.
**Score step:** no candidates ⇒ the wrapper's auto-score produced no `model_scores_<ts>.yaml` this run (last artifact remains `reports/model_scores_20261001_1200.yaml`).
**`.seen_models.json`:** **474 → 474 entries** (474 unique, 0 dups) — the ledger is byte-count-identical to yesterday's post-run state, which is the second, independent confirmation that nothing new was printed.
**Registry input:** `source=task-router`, `data/tables/models.jsonl` (1,881 rows, mtime 2026-10-02 07:34), **29 provider blocks**; provider cache `age_s=2166` → stale → refetched `provider_fetch_ok providers=227`, then hit; `provider_discovery_done models=5209 providers=10`. The log's `providers=25` still disagrees with the file's 29 (§4).
**Catalog:** **42 models / 42 enabled / 13 providers**, untouched by this run (recommend-only mandate).
**Deployment:** HEAD `21d1a69`, running commit `69e6870`, ancestry holds, material diff (`src/ scripts/ tests/ pyproject.toml`) **EMPTY** ⇒ **CODE-CURRENT** — bookkeeping-only gap (the two intervening commits are `docs(config)` DOC-3/DOC-4 and its board commit). §3.
**Archive:** yesterday's file copied to `reports/model_sync_weekly_20261001_archive.md` before this file replaced it.

**Zero is a real zero, not a silent scanner.** This tick's job was to prove that, because the classic failure mode here is a false negative (`--diff` hides anything the ledger has already recorded). Evidence in §1.

---

## 1. Diff honesty: the zero is trustworthy (checked three ways)

| Check | Result |
|---|---|
| Discovery actually ran | `provider_cache_stale age_s=2166` → `provider_fetch_ok providers=227` → `provider_cache_hit age_s=1 providers=226 stale=False` — the cache was refetched this run, not served blind |
| The report is populated | `reports/latest.md` = 81 KB: **Reseller Watch** table alone carries 600+ rows including this month's row family (`gpt-6.1-sol-pro/fast`, `claude-opus-5.5`, `grok-4.7`, `claude-sonnet-5.5`) — a live scanner, not an empty cache |
| The core-scope filter | The only candidate-shaped line is the standing basename skip `openai/gpt-5.6` — already admitted as `openrouter/openai/gpt-5.6`; byte-identical to recent runs |
| The ledger did not move | 474 before = 474 after, 474 unique; the previous two runs appended exactly the ids they printed, so a printed candidate would have moved this count |

Conclusion: no new core-lab model, no lane-carried core release, and no new reseller-only row worth a fresh review appeared in the 24 h window.

---

## 2. Nothing new in the catalog either — it is still flat

`load_config()` re-read this tick: **42 models / 42 enabled / 13 providers**. Raw `chimera.yaml` grep for every id on the standing backlog still returns **0 hits**:

`gpt-6.1-sol`, `gpt-6-sol`, `gpt-6-luna`, `claude-opus-5.5`, `claude-sonnet-5.5`, `grok-4.7`, `glm-5.3-flashx`, `qwen3.7-flash` — all 0.

The catalogue has now stood at **42 models for eight consecutive daily ticks** (2026-09-25 → 2026-10-02) while verified, evidence-backed adds sit unapproved. This is a decision backlog, not a discovery backlog.

---

## 3. Deployment: CODE-CURRENT (no reload owed)

| Field | Value |
|---|---|
| running commit | `69e6870` (`/health` → `{"status":"alive","commit":"69e6870","version":"0.2.7","uptime_models":42}`) |
| HEAD | `21d1a69` |
| ancestry | `69e6870` **is** an ancestor of HEAD (`git merge-base --is-ancestor` exit 0) |
| material diff (`src/ scripts/ tests/ pyproject.toml`) | **EMPTY** |
| nature of the gap | `2fcb0ca docs(config)…` + `21d1a69 chore(board)…` — docs + board only, zero `src/` delta |
| classification | **CODE-CURRENT** — bookkeeping-only; the running code is current and no reload is owed |

Per the AGENTS.md evidence contract: an empty material diff is reported as bookkeeping-only and **no code deployment is claimed here**. Nothing was restarted this tick.

---

## 4. Carry-over measurements (recorded, unchanged)

- **Registry block count:** `data/tables/models.jsonl` = 1,881 rows across **29 distinct provider blocks**; the wrapper's log line says `providers=25`. Same open discrepancy as the last several ticks — two counts, one file. The scope footnote lists the 22 lane blocks it printed.
- **Key-name discrepancy:** `model_sync_cron.py` writes to `/mnt/bulk/scratch/chimera-model-sync-diff-<pid>.json` (`-2311260` today), while the skill text names `.seen_models.json` in the repo root; the live ledger path is the repo-root `.seen_models.json` (474 entries, gitignored). No action, noted for the next reader.
- **Skill hygiene (fifth tick, not an AGENTS.md edit):** `chimera-development` cites `references/category-paths.md`, which does not exist in the repo (`~/chimera-v2/references/` does not exist); the canonical list is `chimera.selector.PATH_PATTERNS` (32 paths).

---

## 5. Status of the two board items this series was tracking

- **DF-CHIMERA-V2-68 — FIXED (shipped, not just claimed).** Commit `71343a1` is an ancestor of HEAD and the fix is present in the working tree: `scripts/model_sync.py` now carries `_admission_key()` (line 953, "Routable Chimera-gateway admission key for one candidate (DF-CHIMERA-V2-68)"), an `ensure_admission_key()` backstop (line 1850) and the scorer now scores the routable key (line 1904). Verified by reading the code at HEAD, not by the commit subject. The closed row was recorded with judge PASS `136cce5d`.
- **DF-CHIMERA-V2-66 — still P3, still the standing cost.** The ledger cannot distinguish *seen-and-admitted* from *seen-and-ignored*: this tick's ledger query shows `openai/openai/gpt-6.1-sol`, `openai/gpt-6-sol`, `anthropic/anthropic/claude-opus-5.5`, `xai/grok-4.7`, `zai/glm-5.3-flashx`, `alibaba/qwen3.7-flash` all recorded ⇒ none of them can ever re-print in `--diff`. Eight ticks of backlog is the accumulated price of that design. Recommend re-prioritising to **P2**.

---

## 6. Recommendation

**No new ADD recommended this tick — there is nothing new to recommend.** The seven-tick (now eight) backlog stands unchanged, value order:

`openrouter/openai/gpt-6.1-sol` (2026-10-01, $2/$10 per M, 1.05M ctx) → `gpt-6-sol` → `gpt-6-luna` → `claude-opus-5.5` (cheaper than the catalogued `claude-opus-4.8`) → `claude-sonnet-5.5` → `grok-4.7` → `glm-5.3-flashx` → `qwen3.7-flash`.

Nothing was written to `chimera.yaml`; the catalogue is byte-identical to yesterday's (recommend-only mandate).

---

## 7. Method / reproducibility

```bash
# the run (cron wrapper did steps 1-2)
cd ~/chimera-v2 && .venv/bin/python scripts/model_sync_cron.py
#   -> reports/latest.md (+ latest_20261002_1200.md), /mnt/bulk/scratch/chimera-model-sync-diff-2311260.json  == "{}"

# this tick (read-only; no catalogue writes anywhere):
#   diff truth        json.loads(diff json) -> {} ; reports/latest.md line 4 -> 0 core + 0 lane
#   ledger truth      json.loads(.seen_models.json) -> 474 entries, 474 unique (unchanged)
#   registry truth    line-wise json.loads(task-router data/tables/models.jsonl) -> 1881 rows / 29 blocks
#   catalogue truth   load_config() -> 42 / 42 / 13 ; raw-grep each backlog id in chimera.yaml -> 0 hits
#   DF-68 proof       grep -n '_admission_key|ensure_admission_key' scripts/model_sync.py (present at HEAD 21d1a69)
#   deployment        git merge-base --is-ancestor 69e6870 HEAD (0); git diff --name-only 69e6870..HEAD -- src/ scripts/ tests/ pyproject.toml (empty)
```

Artifacts: `reports/latest.md` (+ `latest_20261002_1200.md`), `/mnt/bulk/scratch/chimera-model-sync-diff-2311260.json`, this file, `reports/model_sync_weekly_20261001_archive.md`. No throwaway diagnostics needed this tick.

---

## 8. Action items

1. **Decide the backlog (§6)** — 8 verified, evidence-backed adds, eight ticks old, all now permanently invisible to `--diff`. Cheapest decision that needs no evaluation from you: `claude-opus-5.5` (undercuts the catalogued `claude-opus-4.8`).
2. **DF-CHIMERA-V2-66 (P3 → recommend P2)** — emit a "Pending — seen, not catalogued" section each run; today's ledger query is the direct evidence of the suppression.
3. **Deployment:** none owed — CODE-CURRENT, no reload (§3).
4. **Still open:** DF-61, DF-62, DF-63 (`pending`); DF-28 (StepFun native key vs OR); `mistralai/` 19 live / 0 catalogued; `deepseek-v4.1-flash` three-way pricing reconciliation; registry `providers=25` vs 29 blocks (§4).
