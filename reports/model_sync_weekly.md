# Chimera Model Sync — Weekly Report

**Date:** 2026-10-03 (cron run 17:00 UTC / 12:00 local −05)
**Run:** `scripts/model_sync_cron.py` → `model_sync.py --diff --output reports/latest.md` (diff json `/mnt/bulk/scratch/chimera-model-sync-diff-2979048.json`)
**Diff result:** `{}` — **0 new models, 0 task-router lane finds.** Report line 4: `**Candidates:** 0 new models across 13 providers, plus 0 task-router lane finds`.
**Score step:** no candidates ⇒ no `model_scores_<ts>.yaml` produced this run (last artifact remains `reports/model_scores_20261001_1200.yaml`).
**`.seen_models.json`:** **474 → 474 entries** (474 unique) — byte-count-identical to yesterday's post-run state; a printed candidate would have moved this count. Independent confirmation of the zero.
**Registry input:** `source=task-router`, `data/tables/models.jsonl` (1,885 rows, mtime 2026-10-03 09:01, **29 provider blocks**); provider cache `age_s=1747` → hit, `provider_discovery_done models=5214 providers=10`.
**Catalog:** **42 models / 42 enabled / 13 providers**, untouched by this run (recommend-only mandate).
**Deployment:** ran at `c2302c4`, gap classified **STALE** (2 material paths) → **reloaded this tick** → post-restart `/health` reports `f163e76` and `smoke_live.py` exits 0 ⇒ **CURRENT**. §3.
**Archive:** yesterday's file copied to `reports/model_sync_weekly_20261002_archive.md` before this file replaced it.

**Two deliveries landed in the runtime this tick** (both already committed, verified by reading the code/output, not the commit subject): the DF-66 backlog section now renders in the live report for the first time (§2), and the DF-61 catalog-hint error text is live on the reloaded service (§3).

---

## 1. Diff honesty: the zero is trustworthy (checked four ways)

| Check | Result |
|---|---|
| Discovery actually ran | `provider_cache_hit age_s=1747 providers=226 stale=False` + `provider_discovery_done models=5214 providers=10` — the cache is fresh and the scan enumerated 5,214 models across 10 registered providers |
| The report is populated | `reports/latest.md` = 95 KB, **909 rows** across Reseller Watch / Blind Spot — a live scanner, not an empty cache |
| The core-scope filter | The only candidate-shaped line is the standing basename skip `openai/gpt-5.6` — already admitted as `openrouter/openai/gpt-5.6`; unchanged |
| The ledger did not move | 474 before = 474 after, 474 unique (`.seen_models.json`, repo root) |
| The diff json itself | `/mnt/bulk/scratch/chimera-model-sync-diff-2979048.json` = `{}` |

Conclusion: no new core-lab model, no lane-carried core release, and no new reseller-only row worth a fresh review appeared in the 24 h window.

## 2. DF-CHIMERA-V2-66 has delivered — the backlog is now visible (first live render)

Today's report is **95 KB vs 81 KB yesterday** and carries a section that has never appeared in a live run before:

```
## Pending — seen, not catalogued        (432 entries)
```

That is the DF-66 fix (`cb1078f`, "fix(model-sync): `--diff` reports 'Pending — seen, not catalogued' backlog") — committed *after* yesterday's 12:00 run, so **today's 12:00 run is its first production execution**. The size growth is entirely this new section, not new discovery: the headline is still 0 candidates, and `--diff` still emits `{}`.

This closes exactly the suppression the previous eight ticks kept reporting: models discovered but never catalogued disappeared from every future `--diff`, so the scanner could not tell anyone the backlog existed. It now prints it every run, 432 ids wide, without touching `.seen_models.json`. The row was closed with tier2 COMPLETE `579c74f8`.

## 3. Deployment: STALE → reloaded → CURRENT (evidence contract satisfied)

| Field | Value |
|---|---|
| running commit at start of tick | `c2302c4` (`/health` → `{"status":"alive","commit":"c2302c4","version":"0.2.7","uptime_models":42}`) |
| HEAD / origin/main | `f163e76` (`main...origin/main`, no ahead/behind) |
| ancestry | `c2302c4` **is** an ancestor of HEAD |
| material diff (`src/ scripts/ tests/ pyproject.toml`) | **NON-EMPTY** — `src/chimera/api/server.py`, `tests/test_api.py` |
| pre-reload classification | **STALE** — `scripts/smoke_live.py` printed `deployment: STALE — running commit c2302c4 is behind expected commit origin/main and 2 material path(s) changed` |
| action taken | `sudo systemctl restart chimera` (rc 0) |
| post-reload `/health` | `{"status":"alive","commit":"f163e76","version":"0.2.7","uptime_models":42}` — the commit requested by the contract |
| post-reload smoke | `scripts/smoke_live.py` → `deployment: CURRENT`, `SMOKE PASS: live deliberation returned a merged answer.`, **exit 0** |

The delta is `f163e76` "fix(docs+api): document catalog requirement for custom providers + improve unknown-model error (DF-CHIMERA-V2-61)": 38 lines in `server.py`, 52 test lines, 31 doc lines. It appends a `models:`-catalog teaching sentence to the 400 `detail` on unknown-model errors; **status code and JSON error shape are unchanged**. It is not a silent gap — it was found by the smoke's own classifier, not by a commit subject.

Live proof the deployed change is actually serving (not just present in the tree):

```
POST /v1/deliberate  {"stage_models":{"worker":"definitely-not-a-model"}}
HTTP 400 — stage_models references unknown stage 'worker'; valid stages: [...] A model id must
declared in the `models:` catalog section of chimera.yaml (a `providers.<name>` entry alone is
not enough) before it is dispatchable; see docs/CONFIG.md.
```

`/health` also confirmed alive + `uptime_models=42` after the reload. Nothing else was restarted; no config was written.

## 4. Carry-over measurements (recorded, unchanged)

- **Registry block count:** `data/tables/models.jsonl` = **1,885 rows across 29 distinct provider blocks** (up from 1,881 rows yesterday; blocks steady at 29); the wrapper's log line says `providers=25`. Same open discrepancy as the last several ticks — two counts, one file.
- **Provider probe noise (not a failure):** `providers: 6/9 healthy`; `hermes [slow]` (no response inside the 10 s probe budget) and `openai`/`xai` reported `[unknown]` by `/v1/health`. The deliberation itself returned a merged answer both before and after the reload, so this is probe-budget noise, not provider outage.
- **Key-name discrepancy:** `model_sync_cron.py` writes `/mnt/bulk/scratch/chimera-model-sync-diff-<pid>.json` (`-2979048` today), while the skill text names `.seen_models.json` in the repo root; the live ledger path is the repo-root `.seen_models.json` (474 entries, gitignored). No action, noted for the next reader.
- **Skill hygiene (sixth tick, not an AGENTS.md edit):** `chimera-development` cites `references/category-paths.md`, which does not exist in the repo (`~/chimera-v2/references/` does not exist); the canonical list is `chimera.selector.PATH_PATTERNS` (32 paths).

## 5. Recommendation

**No new ADD recommended this tick — there is nothing new to recommend.** The standing backlog is unchanged and now, for the first time, printed in full by the tool itself (432 ids, §2). The value-ordered short list remains:

`openrouter/openai/gpt-6.1-sol` (2026-10-01, $2/$10 per M, 1.05M ctx) → `gpt-6-sol` → `gpt-6-luna` → `claude-opus-5.5` (cheaper than the catalogued `claude-opus-4.8`) → `claude-sonnet-5.5` → `grok-4.7` → `glm-5.3-flashx` → `qwen3.7-flash`.

All eight are permanently invisible to `--diff` (recorded in the ledger), which is why they survived nine ticks without re-printing. Nothing was written to `chimera.yaml`; raw grep for each id still returns **0 hits**, and `chimera.yaml` is git-clean.

## 6. Method / reproducibility

```bash
# the run (cron wrapper did steps 1-2)
cd ~/chimera-v2 && .venv/bin/python scripts/model_sync_cron.py
#   -> reports/latest.md (+ latest_20261003_1200.md), /mnt/bulk/scratch/chimera-model-sync-diff-2979048.json == "{}"

# this tick (read-only w.r.t. the catalogue):
#   diff truth        json.loads(diff json) -> {} ; reports/latest.md line 4 -> 0 core + 0 lane
#   ledger truth      json.loads(.seen_models.json) -> 474 entries, 474 unique (unchanged)
#   registry truth    line-wise json.loads(task-router data/tables/models.jsonl) -> 1885 rows / 29 blocks
#   catalogue truth   load_config() -> 42 / 42 / 13 ; raw-grep each backlog id in chimera.yaml -> 0 hits
#   report sections   today: 4 sections incl. "Pending — seen, not catalogued" (432) ; yesterday: 3 sections, 0 pending
#   deployment        scripts/smoke_live.py -> STALE (2 material paths) ; sudo systemctl restart chimera ;
#                     /health -> f163e76 ; scripts/smoke_live.py -> CURRENT, exit 0
#   DF-61 proof       POST /v1/deliberate with an unknown model -> HTTP 400 detail carries the catalog hint
```

Artifacts: `reports/latest.md` (+ `latest_20261003_1200.md`), `/mnt/bulk/scratch/chimera-model-sync-diff-2979048.json`, this file, `reports/model_sync_weekly_20261002_archive.md`.

## 7. Action items

1. **Decide the backlog (§5)** — the tool now prints it every run; no evaluation is needed for the cheapest item (`claude-opus-5.5` undercuts the catalogued `claude-opus-4.8`).
2. **Deployment:** none owed — reloaded to `f163e76`, smoke exit 0, `/health` matches (§3).
3. **Still open:** DF-61, DF-62, DF-63 (`pending`); DF-28 (StepFun native key vs OR); `mistralai/` 19 live / 0 catalogued; `deepseek-v4.1-flash` three-way pricing reconciliation; registry `providers=25` vs 29 blocks (§4).
