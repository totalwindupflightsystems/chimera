# Chimera Model Sync — Weekly Report

**Date:** 2026-09-28 (cron run 17:00 UTC / 12:00 local −05)
**Run:** `scripts/model_sync_cron.py` → `model_sync.py --diff --output reports/latest.md --diff-json /tmp/chimera-model-sync-diff-137001.json`, then step 3 `--score`
**Diff result:** `reports/latest.md` line 4 reads `**Candidates:** 7 new models across 13 providers` — **7 rows, 4 first appearances, 2 catalogue candidates**
**Score step:** **OK** — `reports/model_scores_20260928_1200.yaml` written (5 entries, **77** path scores, 0 unknown paths, 0 scores <60).
**`.seen_models.json`:** **464 → 471 entries** (+7 rows). +7 rows ≠ 7 new models — **3 of the 7 were already seen under a differently-shaped id** (§1).
**Registry input:** `source=task-router`, `data/tables/models.jsonl`, **25 providers** (the 09-26 run saw 22 — that growth is the whole story of today's diff, §4); provider cache hit, `age_s=1924` then `stale=False`, `provider_discovery_done models=5146 providers=10`.
**Catalog:** **42 models / 13 providers**, untouched by this run (recommend-only mandate; `load_config()` re-read to confirm). Nothing written to `chimera.yaml`, `chimera.yaml.example` or `chimera.yaml.docker`.
**Deployment:** HEAD `63534fd`, `/health` `commit: 55ed827`, running is an ancestor of HEAD, **material diff (`src/ scripts/ tests/ pyproject.toml`) = 0 files** → **CODE-CURRENT** (bookkeeping/board-only gap). No reload owed.
**Archive:** yesterday's file copied to `reports/model_sync_weekly_20260926_archive.md` before this file replaced it.

---

## 1. Diff honesty check: 7 rows, **3** re-reports, **4** first appearances

`--diff` filters on the lane-resolved id (`model_sync.py:1061-1066`: `m["chimera_id"] not in seen`). The seen file stores ids **as they were resolved on the day they were first seen**, so a later lane that resolves a different string defeats the filter (DF-CHIMERA-V2-64, filed 09-26, still `pending`). Measured this run by tracing every row across all `reports/latest_*.md` and the seen file:

| Row id printed today | Evidence of prior sighting | Class |
|---|---|---|
| `alibaba/qwen3.7-flash` | **core** candidate on 09-25 (seen file also holds `alibaba/Qwen/Qwen3.7-Flash` and `alibaba/qwen/qwen3.7-flash:free`); reseller-watch row on every run since 09-21 | **re-report** (id-shape change) |
| `alibaba/qwen3.5-flash` | core candidate on 09-25; reseller-watch row since 09-21 | **re-report** + superseded (§2) |
| `moonshot/moonshotai/kimi-k2.7-code-highspeed` | seen 2026-07-05 and again 2026-09-25 as `moonshot/moonshotai/Kimi-K2.7-Code-Highspeed` | **re-report** |
| `moonshot/moonshotai/kimi-k2.8-preview` | today only | **first appearance** |
| `moonshot/moonshotai/kimi-k3-256k` | today only | **first appearance** |
| `openai/gpt-daybreak-blue-latest` | today only | **first appearance** |
| `openai/gpt-daybreak-red-latest` | today only | **first appearance** |

Consequences, stated plainly:

- The lane-prefix shape is still not cosmetic: `moonshot/moonshotai/…`, `openai/…` are **not** catalogue keys (the catalogue's convention is `openrouter/moonshotai/kimi-k2.7-code`, `openrouter/openai/gpt-5.6-sol`). Acting on a report row verbatim would add an unroutable key.
- **A "new candidate" is still not evidence of a new release.** Two of today's seven rows are a 09-25 find surfacing again because the lane-side id changed, not because anything shipped — the DF-CHIMERA-V2-64 class, reproduced one tick later.

---

## 2. What is genuinely new — verification this tick

Method: live OpenRouter catalogue (`GET /api/v1/models`, **458 ids**, key read from `~/chimera-v2/.env` at runtime, never printed) + provider documentation. **Neither the sync's scope line nor its `provider` field was treated as evidence** — and §4 shows why that mattered today.

| Id as printed | OR catalogue | Public evidence | Verdict |
|---|---|---|---|
| `alibaba/qwen3.7-flash` | **present** as `qwen/qwen3.7-flash`: created **2026-07-27 22:16 UTC**, ctx 1 000 000, text+image+video, $0.03/$0.13 per M | vendor coverage dates Qwen 3.7 Flash to 2026-07-27 at exactly that price | **ADD** (budget tier, family completion) |
| `moonshot/moonshotai/kimi-k2.8-preview` | **absent** (stem `kimi-k2.8` → NONE in 458 ids) | official Moonshot launch **2026-09-11**: mid-tier between K2.7 Code and K3, 1M ctx, multimodal, near-K3 coding/agent scores; **rolled out in place on the existing `kimi-for-coding` API id** (no client config change) | **HOLD — no route** (see §3) |
| `moonshot/moonshotai/kimi-k3-256k` | **absent** | **no public evidence for the id at all** (zero web hits); xkiro lane row only, ctx 262 144, release_date null | **HOLD** (unverifiable) |
| `openai/gpt-daybreak-blue-latest` | **absent** (stem `daybreak` → NONE) | OpenAI Enterprise Daybreak onboarding: the alias **maps to model ID `gpt-5.6-sol`** — already catalogued as `openrouter/openai/gpt-5.6-sol` | **ALIAS — do not add** |
| `openai/gpt-daybreak-red-latest` | **absent** (stem `cyber` → NONE) | OpenAI Daybreak Red: the alias **maps to model ID `gpt-5.6-cyber`** (Bedrock card `openai.gpt-5.6-cyber`), a restricted cyber-research model | **ALIAS — access-gated, not routable** |
| `moonshot/moonshotai/kimi-k2.7-code-highspeed` | **absent** | lane sticker $0.95/$4.00 per M **equals the BASE kimi-k2.7-code rate**, while Moonshot's own first-party price list (9router `pricing.js`, platform.kimi.ai) puts highspeed at **$1.90/$8.00 per M — double** | **re-report + price conflict** |
| `alibaba/qwen3.5-flash` | only the dated `qwen/qwen3.5-flash-02-23` | task-router's own lifecycle pass (2026-09-26) stamped it `valid_to 2026-09-26`, `replaced_by xkiro/qwen/qwen3.7-flash:free`, "lane released 2026-02-23 (age 215d > 90d)" | **superseded — do not add** |

### 2.1 The three facts that decide this week

- **The two "OpenAI" rows are aliases of a model we already have and a model nobody here can call.** `gpt-daybreak-blue-latest` → `gpt-5.6-sol` (in catalogue). `gpt-daybreak-red-latest` → `gpt-5.6-cyber`, Daybreak-program gated: OpenAI's own troubleshooting page requires API-key auth and openai/codex issue #39441 shows the alias returning HTTP 400 on ChatGPT-account auth, and the docs warn the alias can change its underlying model. Adopting the alias would put a *moving* pointer in the catalogue instead of a model.
- **Kimi K2.8 Preview is real, already in service, and still not a catalogue candidate.** It shipped 2026-09-11 and, by Moonshot's design, replaced K2.7 inside the `kimi-for-coding` id — so the fleet's kimi-for-coding/xkiro lanes are serving it today with no config change, and there is no distinct public id (OpenRouter has none) for a catalogue key to point at. The catalogue gained nothing by not acting.
- **Qwen is the one clean win, and it is a family completion, not a frontier catch.** `openrouter/qwen/qwen3.7-flash` sits under the two Qwen 3.7 entries already admitted (`qwen3.7-max` standard, `qwen3.7-plus` budget) with 1M context, image+video input, and a lower input rate than the plus tier. Note the sync *scored* it narrowly (image analysis, multilingual summarisation/translation) — that is the honest shape of a flash tier and the reason to buy it, not a defect.

---

## 3. Recommendation: **1 ADD + 1 HOLD (no route) + 5 not carried**

Scored artifact: `reports/model_sync_candidates_20260928.yaml` — **2 entries, 29 path scores, validated against the canonical 32-path list (`{p for p, _ in chimera.selector.PATH_PATTERNS}`): 0 unknown paths, 0 out-of-bounds, 0 scores below the 60 floor.** Both entries carry the scorer's per-path values verbatim from `model_scores_20260928_1200.yaml`; the file also records why the other 5 rows are not carried.

| Proposed key | ← predecessor | tier | $/1k in–out | status |
|---|---|---|---:|---|
| `openrouter/qwen/qwen3.7-flash` | `openrouter/qwen/qwen3.7-plus` | budget | 0.00003 / 0.00013 | **recommend-add** |
| `moonshot/kimi-k2.8-preview` | `openrouter/moonshotai/kimi-k2.7-code` | standard | 0.0005 / 0.002 | **hold — no route** |

**Why `openrouter/*`:** unchanged from 2026-09-25/26 — `openrouter` is the reseller row the task-router table carries and the deployment holds `OPENROUTER_API_KEY`, so the key stays watch-visible and pricing resolves.

**Why the Kimi hold is a routing hold, not a quality doubt:** OpenRouter lists no kimi-k2.8 id at all, and Moonshot's own platform serves it under `kimi-for-coding`. Admitting it would require either an OR listing or a new `moonshot` provider entry (`KIMI_API_KEY` exists in `~/.hermes/.env`; `chimera.yaml` has no `moonshot` provider today). Both are decisions, not findings — hence HOLD with the reason named.

**Not carried, with reasons** (`reports/model_sync_candidates_20260928.yaml` → `not_carried`): both Daybreak aliases (alias/access-gated), `kimi-k3-256k` (no public evidence), `kimi-k2.7-code-highspeed` (re-report + 2× price conflict), `qwen3.5-flash` (superseded 2026-09-26).

**Carried, not new** — a gap worth one line: the catalogue has **no Kimi K3 key at all**, while OpenRouter serves `moonshotai/kimi-k3` (1 048 576 ctx, $0.003/$0.015 per 1k, created 2026-07-16) and `moonshotai/kimi-k3:batch`. Likewise `qwen/qwen3.8-flash` (created 2026-08-26, 1M ctx, $0.00015/$0.00047 per 1k) is OR-live and uncatalogued. Neither surfaced today (both are in the seen file from the 09-25 flood), so they were not scored this run — flagging them is the honest middle ground, not a recommendation on scores I do not have.

Nothing was written to `chimera.yaml`, `chimera.yaml.example` or `chimera.yaml.docker`.

---

## 4. The registry-source finding behind today's 7 rows (new this tick)

The diff's own `provider` field, read from `/tmp/chimera-model-sync-diff-137001.json`, splits today's rows cleanly in two:

- **5 of 7 rows came from LANE providers, not core labs:** `xkiro` supplied all three Moonshot rows (`moonshotai/kimi-k2.7-code-highspeed`, `…-k2.8-preview`, `…-k3-256k`) and `openai-codex` supplied both Daybreak rows. Those rows carry **empty `family`/`description`** (lane-registry shape), while the two Alibaba rows carry family + description (models.dev core-row shape).
- **The report groups by LAB, not by provider** — so lane SKUs land inside `## Moonshot (Kimi)` and `## OpenAI` sections under a header that claims `across 13 providers`. The task-router registry grew **22 → 25 provider blocks** between the 09-26 and 09-28 runs; that growth, not a release wave, is what produced this tick's 7 candidates.

Consequence: the core sections can now print **internal lane SKUs and vendor API aliases as core-lab candidates**, which is a false-positive risk of exactly the same magnitude as DF-CHIMERA-V2-49's false-negative (that row, `complete`, recorded the *opposite* symptom — preferring the task-router source cost the scan 10 of 13 core labs). Filed as **DF-CHIMERA-V2-65** (§7) with the measured split; fix direction is to tag lane-provider rows explicitly (or exclude `xkiro`/`openai-codex`/`kimi-for-coding`-class providers from core-lab attribution) and to mark alias rows, rather than let them inflate a core-candidate count.

---

## 5. Deployment check

| Field | Value |
|---|---|
| `/health` running commit | `55ed827` |
| HEAD | `63534fd` |
| ancestry | running is an ancestor of HEAD (`git merge-base --is-ancestor` exit 0) |
| material diff `src/ scripts/ tests/ pyproject.toml` | **0 files** |
| classification | **CODE-CURRENT** — bookkeeping/board-only gap |
| action | **none owed** — no reload claimed, none required |

---

## 6. Action items

1. **Decide §3** — 1 ADD (`openrouter/qwen/qwen3.7-flash`) and 1 routing decision (`moonshot/kimi-k2.8-preview`: OR listing vs a native `moonshot` provider entry). The other 5 rows need no decision; their reasons are recorded in the candidates file.
2. **DF-CHIMERA-V2-64** (09-26, still `pending`) — the seen filter is a ledger of ids, not of models; today reproduced the class (3 of 7 rows). Fix before the next lane-namespace change.
3. **DF-CHIMERA-V2-65** (§7) — tag lane-provider rows so core-lab sections stop inheriting lane SKUs and vendor aliases.
4. **Carried gaps to consider in a later scored pass:** `moonshotai/kimi-k3`, `qwen/qwen3.8-flash` (both OR-live, both uncatalogued, neither scored this run).
5. **Still open from previous ticks:** the 09-25 batch of 14 and the 09-26 batch of 4 (none applied; catalog still 42), DF-CHIMERA-V2-28 (StepFun native key vs OR), DF-CHIMERA-V2-49, -50, -57 (all `complete`), -60..-64.
6. **Skill hygiene:** `chimera-development` cites `references/category-paths.md`, which is absent from the repo; the 09-26 note stands — repoint it at `chimera.selector.PATH_PATTERNS` **and** record the tuple-unpacking step (`{p for p, _ in PATH_PATTERNS}`, else all scores read as "unknown paths").

---

## 7. Board row filed this run

| Row | Priority | Finding |
|---|---|---|
| **DF-CHIMERA-V2-65** | P2 | Core-lab sections of the sync report now inherit **lane-provider SKUs and vendor API aliases** as core candidates. Measured 2026-09-28: `reports/latest.md` says "7 new models across 13 providers", but 5 of the 7 rows came from two lane providers outside the core-13 (`xkiro` → 3 Moonshot rows, `openai-codex` → 2 rows) and those rows carry empty family/description (lane shape) vs the models.dev core shape of the 2 Alibaba rows. Result: 2 of the 7 are OpenAI **program aliases** (`gpt-daybreak-blue-latest` → `gpt-5.6-sol`, already catalogued; `gpt-daybreak-red-latest` → `gpt-5.6-cyber`, access-gated) and 2 are lane-only Moonshot SKUs with no OpenRouter row. The registry grew 22 → 25 provider blocks since the 09-26 run. Fix direction: tag/exclude lane-provider rows in the core-lab scan and mark alias rows, so the headline candidate count is a core-lab count. |

Board census before append: **260 rows, 260 unique ids, 0 duplicates, max `DF-CHIMERA-V2-64`**.

---

## 8. Method / reproducibility

```bash
cd ~/chimera-v2 && .venv/bin/python scripts/model_sync.py --diff \
    --diff-json /tmp/chimera-model-sync-diff-137001.json --output reports/latest.md
# then step 3 of the cron wrapper: --score against the diff json
# verification this tick (read-only, no catalog writes):
#   OR catalogue: GET https://openrouter.ai/api/v1/models  (458 ids, key from .env at runtime)
#   provenance:   diff json "provider" field per row (xkiro/openai-codex vs alibaba)
#   re-report trace: every row id grepped across reports/latest_*.md + .seen_models.json
#   scores: validated against {p for p, _ in chimera.selector.PATH_PATTERNS} (32 canonical paths)
#   deployment: /health commit vs HEAD + path-scoped git diff (src/ scripts/ tests/ pyproject.toml)
```

Artifacts: `reports/latest.md` (+ timestamped `latest_20260928_1200.md`), `/tmp/chimera-model-sync-diff-137001.json`, `reports/model_scores_20260928_1200.yaml`, `reports/model_sync_candidates_20260928.yaml`, this file, `reports/model_sync_weekly_20260926_archive.md`.
