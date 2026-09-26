# Chimera Model Sync — Weekly Report

**Date:** 2026-09-26 (cron run 17:00 UTC / 12:00 local −05)
**Run:** `scripts/model_sync_cron.py` → `model_sync.py --diff --output reports/latest.md --diff-json /tmp/chimera-model-sync-diff-3255096.json`, then step 3 `--score`
**Diff result:** `reports/latest.md` line 4 reads `**Candidates:** 7 new models across 13 providers` — **7 rows, 6 distinct models**
**Score step:** **OK** — `reports/model_scores_20260926_1201.yaml` written (5 entries, 119 path scores, 0 unknown paths, 0 scores <60). First successful `--score` since 2026-09-24; the DF-CHIMERA-V2-57 fix (`2bbb130`, `raw_decode` + `response_format: json_object`) **is verified in production by this run** (§4).
**`.seen_models.json`:** **457 → 464 entries** (+7 rows). But +7 rows ≠ 7 new models — **6 of the 7 were already in the seen file under a differently-shaped id** (§1).
**Registry input:** `source=task-router`, `data/tables/models.jsonl`, 22 providers; provider cache hit, `age_s=727`, `stale=False`, `provider_discovery_done models=5087 providers=10`.
**Catalog:** **42 models**, untouched by this run (recommend-only mandate). Nothing written to `chimera.yaml`, `chimera.yaml.example` or `chimera.yaml.docker`.
**Deployment:** HEAD `7554d75`, `/health` `commit: d3e390d`, running is an ancestor of HEAD, **material diff (`src/ scripts/ tests/ pyproject.toml`) EMPTY** → **CODE-CURRENT** (bookkeeping/board-only gap: `.coding-hermes/board/{events,tasks}.jsonl`). No reload owed.
**Archive:** yesterday's file copied to `reports/model_sync_weekly_20260925_archive.md` before this file replaced it.

---

## 1. Diff honesty check: 7 rows, **1** first-appearance

`--diff` filters on the lane-resolved id (`model_sync.py:1061-1066`: `m["chimera_id"] not in seen`, plus a `"<id> [basename=…]"` prefix-marker branch). The seen file holds ids **as they were resolved on the day they were first seen**. When the same model later arrives through a lane that resolves the id differently, the string differs and the filter cannot match it. Measured on today's 7 rows:

| Row id reported today | Seen earlier as | Class |
|---|---|---|
| `anthropic/anthropic/claude-opus-5.5` | — (bare `anthropic/claude-opus-5.5` absent; `anthropic/claude-opus-5` present) | **first appearance** |
| `openai/openai/gpt-6-sol` | `openai/gpt-6-sol` (2026-09-25 flood) | re-report |
| `openai/openai/gpt-6-luna` | `openai/gpt-6-luna` (2026-09-25 flood) | re-report |
| `xai/x-ai/grok-4.7` | `xai/grok-4.7` | re-report |
| `xai/xai/grok-4.7` | `xai/grok-4.7` | re-report (same model, second lane) |
| `zai/z-ai/glm-5.3-flashx` | `zai/glm-5.3-flashx` (**2026-09-19**) | re-report, **a week old** |
| `stepfun/stepfun/Step-5-Preview` | `stepfun/step-5-preview` | re-report |

Consequences, stated plainly:

- The lane-prefix shape is not cosmetic. `openai/openai/…`, `anthropic/anthropic/…`, `xai/xai/…`, `zai/z-ai/…` are **not catalogue keys** (the catalogue's convention is `anthropic/claude-opus-4.8`, `openrouter/openai/gpt-5.6-sol`, `z-ai/glm-5`). Acting on a report row verbatim would add an unroutable key.
- **A "new candidate" is not evidence of a new release.** `z-ai/glm-5.3-flashx` was live-verified and recommended on 2026-09-19; it re-surfaced today purely because the lane-side id changed, not because anything new shipped. The 09-19 archive is still its authority (native `z-ai/…` key, budget tier, `ZAI_API_KEY` present, weekly-quota caveat).
- **The 09-25 prediction did not hold.** That report said "tomorrow's diff should collapse back to a handful — the prediction to hold this report to." It collapsed (225 → 7), but not to a clean handful of new finds: 6 of the 7 are re-reports. The seen file is a ledger of *ids*, not of *models* — a decision must not be assumed safe merely because a model "won't reappear".
- Filed as **DF-CHIMERA-V2-64** (§7): extend the seen comparison to the same basename resolution the catalogue-hit dedupe already got in `c941150`/`0c87a0b` (DF-CHIMERA-V2-50), which fixed the *catalogue* path but left the *seen* path exact-string.

---

## 2. What is genuinely new — verification this tick

Method: live OpenRouter catalogue (`GET /api/v1/models`, **458 ids**, key read from `~/chimera-v2/.env` at runtime, never printed) + provider announcements; pricing/context are the OR catalogue values, not roundup text. Neither the sync's scope line nor its `provider` field was treated as evidence — the rows arrived via the `xkiro`/`commandcode` reseller lanes.

| OR id | OR created | ctx | $/1k in–out | Catalogue comparator | Verdict |
|---|---|---:|---|---|---|
| `anthropic/claude-opus-5.5` | 2026-09-22 16:32 UTC | 1 000 000 | 0.004 / 0.020 | `anthropic/claude-opus-4.8` 0.005 / 0.025; 09-25 candidate `claude-opus-5` 0.005 / 0.025 | **ADD** (supersedes opus-5) |
| `openai/gpt-6-sol` | 2026-09-22 18:12 UTC | 1 050 000 | 0.002 / 0.010 | `openrouter/openai/gpt-5.6-sol` **0.002 / 0.010** (identical); `gpt-6-astra` 0.010 / 0.050 (5×) | **ADD** |
| `openai/gpt-6-luna` | 2026-09-22 18:13 UTC | 1 050 000 | 0.0001 / 0.0005 | `openrouter/openai/gpt-5.6-luna` 0.0002 / 0.0012 (≈½) | **ADD** |
| `x-ai/grok-4.7` | 2026-09-21 16:19 UTC | 500 000 | 0.0016 / 0.0048 | `openrouter/x-ai/grok-4.5` 0.002 / 0.006 (cheaper than the incumbent); xAI list $2/$6 per M | **ADD** |
| `z-ai/glm-5.3-flashx` | 2026-09-18 15:07 UTC | 1 048 576 | 0.00037 / 0.00125 | `z-ai/glm-5` 0.000573 / 0.00258; `z-ai/glm-5.3-flash` 0.00004 / 0.0005 (**9× cheaper input**) | **ADD but old news** — 09-19 verdict, re-reported (§1) |
| `stepfun/Step-5-Preview` | 2026-09-20 (announced) | 1 000 000 | 0.001 / 0.0027 | **not in the OR catalogue at all** (458 ids, zero `step-5` rows) | **HOLD** |

Release corroboration: OpenAI's GPT-6 Sol/Luna launch is dated 2026-09-22 (feed 18:00 UTC; the OR `created` stamp 18:12/18:13 is consistent), Claude Opus 5.5's release notes carry a 2026-09-22 entry, Grok 4.7 shipped 2026-09-21 with `docs.x.ai` release notes, GLM-5.3-FlashX officially launched 2026-09-18 (previously previewed as "Ox Alpha"), Step 5 Preview announced 2026-09-20 with open weights promised for 2026-10-15.

### 2.1 The two price facts that decide this week

- **`openai/gpt-6-sol` costs exactly what the incumbent `gpt-5.6-sol` costs** (0.002/0.010 per 1k) on a 1.05 M context with a newer generation — a same-price upgrade, not a spend. `gpt-6-luna` is the same story at the budget end (half the incumbent's rate). These are the cheapest catalogue improvements available this week.
- **`anthropic/claude-opus-5.5` undercuts the incumbent flagship** (0.004/0.020 vs `claude-opus-4.8`'s 0.005/0.025). **`openrouter/anthropic/claude-opus-5` from the 09-25 recommendation should be dropped** — 5.5 is newer (OR created 60 days later) *and* cheaper. Approving both would put a dominated entry in the catalogue.
- **`glm-5.3-flashx` is a speed tier, not a value tier.** Its sibling `z-ai/glm-5.3-flash` is 9× cheaper on input; FlashX buys ~200 tok/s. It remains a good fast-worker/plan-lane slot and still cannot bypass the `zai` weekly quota cap (err 1310).

### 2.2 HOLD / notes

- **HOLD `stepfun/Step-5-Preview`** — genuinely released (600B MoE, 1M ctx, AA Index 44, finance-heavy positioning, open weights promised 2026-10-15), but **not routable from here**: absent from OpenRouter's 458-id catalogue, and no `stepfun` credential is configured (DF-CHIMERA-V2-28 is still the open row for the native-key-vs-OR question). Revisit when it lands on OR or a StepFun key exists — that is exactly the check it would need to pass again.
- **No action on the 6 other rows of the flood class.** `gpt-6-luna-pro` / `gpt-6-sol-pro` / `gpt-6-astra-pro` are the same family at identical prices with a `-pro` suffix; `z-ai/glm-5.3-prime` (0.0028/0.0088) and the `:batch` variants are routing aliases of entries already admitted (batch rates only apply to a batch endpoint the gateway does not use).

---

## 3. Recommendation: **4 ADD + 1 already-recommended ADD + 1 HOLD**

Scored artifact: `reports/model_sync_candidates_20260926.yaml` — **5 entries, 130 path scores, validated against the canonical 32-path list (`chimera.selector.PATH_PATTERNS`) with 0 unknown paths and 0 out-of-bounds values**. Four entries are this run's LLM-scored values verbatim (from `model_scores_20260926_1201.yaml`); the `glm-5.3-flashx` entry is **templated** from in-catalogue `z-ai/glm-5` with a labelled uniform delta (that is stated in the file, not hidden). The sync's own score file carries lane-prefixed ids — the candidates file repackages them under canonical keys.

| Proposed key | ← predecessor | Δ | tier | $/1k in–out |
|---|---|---:|---|---|
| `openrouter/anthropic/claude-opus-5.5` | `anthropic/claude-opus-4.8` | +1 | premium | 0.004 / 0.020 |
| `openrouter/openai/gpt-6-sol` | `openrouter/openai/gpt-5.6-sol` | +1 | premium | 0.002 / 0.010 |
| `openrouter/openai/gpt-6-luna` | `openrouter/openai/gpt-5.6-luna` | +1 | standard | 0.0001 / 0.0005 |
| `openrouter/x-ai/grok-4.7` | `openrouter/x-ai/grok-4.5` | +2 | standard | 0.0016 / 0.0048 |
| `z-ai/glm-5.3-flashx` | `z-ai/glm-5` | +2 (templated) | budget | 0.00037 / 0.00125 |

**Also due (carried, not new):** drop `openrouter/anthropic/claude-opus-5` from the 09-25 batch as dominated by 5.5.

**Why `openrouter/*` for four of them:** unchanged from 2026-09-25 — `openrouter` is the reseller row the task-router table carries, so the keys stay visible to the watch list and pricing resolves; `glm-5.3-flashx` stays native `z-ai/…` because OR exposes exactly one endpoint (Z.AI itself) and the deployment holds `ZAI_API_KEY` (09-19 verdict).

**If only part of this is approved**, the order that maximises value per approval is: `gpt-6-sol` → `gpt-6-luna` → `claude-opus-5.5` → `grok-4.7` → `glm-5.3-flashx`. The first two cost nothing new per token and replace incumbents; opus-5.5 is a price cut on a flagship seat; grok-4.7 is cheaper than the Grok already in the catalogue; flashx is a speed purchase.

Nothing was written to `chimera.yaml`, `chimera.yaml.example` or `chimera.yaml.docker`.

---

## 4. DF-CHIMERA-V2-57 (scorer) — fix verified, and one method note

The 09-25 score failure (two concatenated JSON objects, `finish_reason=stop`, no score file written) **did not recur**: this run's step 3 wrote `reports/model_scores_20260926_1201.yaml`. The tree carries the fix — `scripts/model_sync.py` now parses via `json.JSONDecoder().raw_decode()` at the first `{` (`:1345`) and sends `response_format: {"type": "json_object"}` (`:1360`), committed as `2bbb130` ("fix(model-sync): score from first JSON object of concatenated replies; scoring failure exits non-zero"). Row status on the board reads `complete`. Independent check of the artifact: 5 entries, 119 path scores, **0 unknown paths, 0 scores <60**.

**Method note (my own first pass, corrected):** `PATH_PATTERNS` is a **list of `(path, regex)` tuples**, so extracting the canonical 32 paths requires `{p for p, _ in PATH_PATTERNS}`. A naive `set(PATH_PATTERNS)` yields 32 *tuples* and then reports all 119 scores as "unknown paths" — a false finding I produced and discarded before writing this report. The 09-25 report's instruction ("the real 32-path authority is `chimera.selector.PATH_PATTERNS`") is correct but needs that unpacking step recorded, since the skill's cited `references/category-paths.md` still does not exist in the repo.

---

## 5. Deployment check

| Field | Value |
|---|---|
| `/health` running commit | `d3e390d` |
| HEAD | `7554d75` |
| ancestry | running is an ancestor of HEAD |
| material diff `src/ scripts/ tests/ pyproject.toml` | **empty** |
| classification | **CODE-CURRENT** — bookkeeping/board-only gap (`.coding-hermes/board/{events,tasks}.jsonl`) |
| action | **none owed** — no reload claimed, none required |

---

## 6. Action items

1. **Decide §3** — 4 new ADDs + the 09-19 `glm-5.3-flashx` re-recommendation + 1 HOLD. All row ids in this report were checked against the live OR catalogue; the catalogue keys proposed above are the canonical forms, not the lane-prefixed ids the diff prints.
2. **Drop `openrouter/anthropic/claude-opus-5`** from the 09-25 batch — dominated by 5.5 on both recency and price.
3. **DF-CHIMERA-V2-64** (§7) — the seen filter is a ledger of ids, not models; fix it before the next lane-namespace flood, or weekly reports will keep re-surfacing week-old recommendations as "new".
4. **Step-5-Preview** — re-check when it appears on OpenRouter or a StepFun credential exists; HOLD today.
5. **Still open from previous ticks:** the 09-25 batch of 14 (none applied; catalog still 42), DF-CHIMERA-V2-49 (core-lab coverage under the task-router source), DF-CHIMERA-V2-50, DF-CHIMERA-V2-28, DF-CHIMERA-V2-60/61/62/63.
6. **Skill hygiene:** `chimera-development` cites `references/category-paths.md`, which is absent; repoint it at `chimera.selector.PATH_PATTERNS` **and** record the tuple-unpacking step (§4).

---

## 7. Board row filed this run

| Row | Priority | Finding |
|---|---|---|
| **DF-CHIMERA-V2-64** | P2 | `model_sync.py --diff` seen filter compares the **lane-resolved** `chimera_id` as an exact string (`:1061-1066`) against a seen file holding ids in the shape they had on first sight. When the same model arrives later through a lane that resolves a different id (`openai/gpt-6-sol` → `openai/openai/gpt-6-sol`, `zai/glm-5.3-flashx` → `zai/z-ai/glm-5.3-flashx`), the match fails and the model is re-reported as new. Measured 2026-09-26: 7 diff rows, only **1** first-appearance; `glm-5.3-flashx` re-surfaced a week after its 09-19 verification. Fix direction: apply the basename resolution that the catalogue-hit dedupe already received (`c941150`/`0c87a0b`, DF-CHIMERA-V2-50) to the seen comparison, or store the resolved basename alongside the raw id. |

Board census before append: **235 rows, 235 unique ids, 0 duplicates, max `DF-CHIMERA-V2-63`**.

---

## 8. Method / reproducibility

```bash
cd ~/chimera-v2 && .venv/bin/python scripts/model_sync.py --diff \
    --diff-json /tmp/chimera-model-sync-diff-3255096.json --output reports/latest.md
# then step 3 of the cron wrapper: --score-from the diff json
# verification this tick (read-only, no catalog writes):
#   OR catalogue: GET https://openrouter.ai/api/v1/models  (458 ids, key from .env at runtime)
#   scores: validated against {p for p, _ in chimera.selector.PATH_PATTERNS} (32 canonical paths)
#   seen leak: set(.seen_models.json) membership test per diff row id
#   deployment: /health commit vs HEAD + path-scoped git diff (src/ scripts/ tests/ pyproject.toml)
```

Artifacts: `reports/latest.md` (+ timestamped `latest_20260926_1200.md`), `/tmp/chimera-model-sync-diff-3255096.json`, `reports/model_scores_20260926_1201.yaml`, `reports/model_sync_candidates_20260926.yaml`, this file, `reports/model_sync_weekly_20260925_archive.md`.
