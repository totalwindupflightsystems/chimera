# Chimera Model Sync — Weekly Report

**Date:** 2026-09-22 (cron run 17:00 UTC / 12:00 local −05)
**Run:** `scripts/model_sync_cron.py` → `model_sync.py --diff --output reports/latest.md` (5 finds) → auto-score step reached (`DEEPSEEK_API_KEY` resolved from `~/.hermes/.env`).
**Diff result:** **5 new candidates** across 13 core providers — `reports/latest.md` line 4 reads `**Candidates:** 5 new models across 13 providers`.
**Cache:** hit, age ~1 088 s, `stale=False` — 223 provider blocks / 7 204 discovery models across 12 recognised providers.
**`.seen_models.json`:** **222 entries**, rewritten at 12:00 by this run (the finds were recorded).
**Catalog:** **42 models**, all `enabled: true`; `chimera.yaml` **untouched** by this run (recommend-only mandate).
**Archive:** the pre-run weekly file was byte-identical (`diff -q`) to `model_sync_weekly_20260920_archive.md`, so no new dated archive copy was written — that content is already preserved. (No weekly file was written on 09-21; the 09-20 report stood for two days.)
**Artifacts:** `reports/model_scores_20260922_1201.yaml` (auto-score, 5 entries), `reports/model_scores_20260922_1204.yaml` (targeted score, 1 entry — see §3).

---

## 1. Diff honesty check — the 5 are real, and one headline number in the tick stdout is not

The wrapper's own stdout reads, under `=== Auto-scoring new candidates ===`:

```
Chimera Model Sync — 2026-09-22 17:00 UTC
Candidates: 0 new models across 13 providers
```

That contradicts the report it had just written (`5 new models`). **It is a wrapper artifact, not a second scan result.** `scripts/model_sync_cron.py:122-128` writes the report *and* records the finds in `.seen_models.json`; step 3 (`:155-165`) then re-invokes `model_sync.py --diff --score`, whose `--diff` is now empty by construction, so its summary prints `0`. The scorer is **not** diff-scoped: it scores `select_top_candidates(candidates, limit=5)` by recency over **all** in-scope candidates (`model_sync.py:884`, `:378-398`). Consequences and the fix are filed as **DF-CHIMERA-V2-37** (§10).

Independently re-measured this tick (same cache, no `--diff`): **177 in-scope candidates**; **5** not previously in `.seen_models.json`.

Of the 5, **four are genuine 09-21/09-22 releases**; the fifth (`glm-4.6v-flash`, released **2025-12-08**) is a long-standing **catalog gap** that only now appeared in zhipuai's models.dev row — it is not a new model.

---

## 2. The five candidates — verification (all figures measured this tick)

Every candidate was probed live, not judged from the report table.

| Candidate | Route that can serve it | Release | Context | $/1M in / out | Live probe |
|---|---|---|---|---|---|
| `grok-4.7` | **`openrouter/x-ai/grok-4.7`** | 2026-09-21 | 500 K | **1.60 / 4.80** (OR) | **HTTP 200 in 2.2 s**, `content='ok'` |
| `mimo-v2.6-flash` | **`xiaomi/mimo-v2.6-flash`** (provider `openrouter`) | 2026-09-22 | 1 048 576 | **0.14 / 0.28** | **HTTP 200 in 2.1 s**, `content='ok'` |
| `mimo-v2.6-pro` | **`xiaomi/mimo-v2.6-pro`** (provider `openrouter`) | 2026-09-22 | 1 048 576 | **0.435 / 0.87** | **HTTP 200 in 1.7 s**, `content='ok'` |
| `mimo-v2.6-pro-ultraspeed` | `xiaomi/mimo-v2.6-pro-ultraspeed` (provider `openrouter`) | 2026-09-21 | 1 048 576 | **4.35 / 8.70** | **HTTP 200 in 2.8 s**, `content='ok'` |
| `glm-4.6v-flash` | **native `zai/` only** — **NOT on OpenRouter** | 2025-12-08 | 128 K / 32 K out | **0 / 0 (free)** | native **HTTP 200 in 1.1 s**, `content='\nok'` |

Route notes, each with its evidence:

- **The sync's suggested ids are not usable as printed.** It proposes `xai/grok-4.7` and `zai/glm-4.6v-flash`. The deployment has **no `xai` provider block** (only `api_keys.xai` — the discovery-only phantom already noted in CH-GAP-053), so grok must ride the existing grok convention: `openrouter/x-ai/grok-4.5` / `…/grok-4.20` are already catalog entries, so the correct key is **`openrouter/x-ai/grok-4.7`**.
- **grok-4.7 is 20 % cheaper through OpenRouter than the native figure the sync prints** — models.dev's `xai` row carries `$2 / $6` per MTok (xAI's own list price, i.e. grok-4.6 pricing), OpenRouter's live catalog carries `$1.60 / $4.80`. Adopting the OR route means the OR number is the one that bills.
- **The MiMo family mirrors the existing `xiaomi/mimo-v2.5` shape exactly** (`provider: openrouter`, id = the OR slug), so the YAML shape is already proven in-tree — no new provider, no adapter.
- **`glm-4.6v-flash` exists on no OpenRouter row** (`GET /api/v1/models`, 444 entries → absent; `z-ai/glm-5.3-flashx` *is* present). It is reachable only through the configured `zai` provider (`https://api.z.ai/api/coding/paas/v4`), which **serves it on the current plan** — `POST /chat/completions {model: glm-4.6v-flash, max_tokens: 64}` → HTTP 200, `content='\nok'`.
- **9router is not a route for any of these yet:** the fleet gateway (`master001:20128`, 271 lanes) has **no** `grok-4.7` and **no** `mimo-v2.6` lane (its newest MiMo is v2.5; its grok lane stops at `openrouter/x-ai/grok-4.6`). It *does* already carry `glm/glm-4.6v` and a local `lmstudio/zai-org/glm-4.6v-flash` lane — noted, not proposed, since `router9` is Bane's local-only fleet surface.

---

## 3. Scoring (shipped scorer, 32-path list)

**Auto-scored** (`model_scores_20260922_1201.yaml`) — top-5 by recency over all candidates:

| Model | cost_tier emitted | Scored paths | Notable top scores |
|---|---|---|---|
| `xai/grok-4.7` | premium | 24 | python 90, task_decomposition 90, explanation 90, debugging 88, tool_use 88, logic_puzzle 88 |
| `xiaomi/mimo-v2.6-pro` | premium | 16 | python 88, tool_use 86, image/analysis 84, error_analysis 84 |
| `xiaomi/mimo-v2.6-pro-ultraspeed` | premium | 19 | python 88, tool_use 88, image/analysis 88, task_decomposition 86 |
| `xiaomi/mimo-v2.6-flash` | budget | 12 | python 82, tool_use 80, image/analysis 78 |
| `zai/glm-5.3-flashx` (carried) | standard | 14 | python 82, tool_use 82, debugging 80 |

**Not auto-scored, scored on demand** (`model_scores_20260922_1204.yaml`, produced this tick by re-using the shipped `_llm_score_candidates` on that single candidate): `zai/glm-4.6v-flash` → `cost_tier: budget`, **one** path: `multimedia_processing/image/analysis: 82`. It is below the scorer's top-5 cut precisely because its recency bucket is the oldest (release 2025-12-08) — the same blind spot DF-CHIMERA-V2-37 describes.

**Two scoring artifacts to correct if these are ever added:** (a) `mimo-v2.6-pro` at `$0.435 / $0.87` per MTok is labelled `premium` by the scorer although it sits between `budget` and `standard` on price — add explicit `cost_per_1k_*` and pick `standard`; (b) `glm-4.6v-flash` has **one** scored path, which makes it effectively invisible to the selector — that is only correct if image analysis is the intended lane, and §4 shows it is not reachable.

---

## 4. NEW FINDING — the deliberation request path has no image input, so a vision-scored entry is unroutable

`glm-4.6v-flash` (and every omni input advertised for `mimo-v2.6-*`) is only reachable **as text** in this deployment:

```
$ grep -rn "image_url\|inline_data\|content_parts\|multimodal\|base64" src/chimera --include="*.py"
(no matches)
$ grep -rn "image" src/chimera/api/server.py src/chimera/engine.py src/chimera/gateway.py
(no matches)
```

- `DeliberateRequest` (`src/chimera/api/server.py:223-236`) exposes `prompt: str` and overrides only — no attachment, image or multipart field.
- `ChatMessage.content` is `str`, not a parts list.
- Consequently the selector can route an `image/analysis`-keyword task to a model whose **only** scored strength is image analysis, and the model will receive text with no image — the exact task class where it is weakest relative to a text model.

**Verdict: hold `glm-4.6v-flash`.** Adding it today buys a free lane that can only be mis-routed; if a cheap vision lane is wanted, the input path is the work item, not the catalog row. The same caveat applies to MiMo's omni modalities — the MiMo rows are still worth considering *as text* models, which is how the scores in §3 were assigned.

---

## 5. Recommendations (approval required — **nothing was applied**; `chimera.yaml` is untouched)

**ADD — 3 entries, all verified live this tick**

```yaml
  openrouter/x-ai/grok-4.7:            # template grok-4.5/4.6 scores + family bump (+2)
    categories: { ... from openrouter/x-ai/grok-4.6, +2 across the board ... }
    cost_tier: premium
    cost_per_1k_input: 0.0016          # OR live price ($1.60/MTok), not models.dev's $2
    cost_per_1k_output: 0.0048
    provider: openrouter
    enabled: true

  xiaomi/mimo-v2.6-flash:              # mirrors xiaomi/mimo-v2.5 shape
    categories: { ... scored paths from model_scores_20260922_1201.yaml ... }
    cost_tier: budget
    cost_per_1k_input: 0.00014
    cost_per_1k_output: 0.00028
    provider: openrouter
    enabled: true

  xiaomi/mimo-v2.6-pro:
    categories: { ... }
    cost_tier: standard                # scorer said premium; price says standard
    cost_per_1k_input: 0.000435
    cost_per_1k_output: 0.00087
    provider: openrouter
    enabled: true
```

**SKIP — `xiaomi/mimo-v2.6-pro-ultraspeed`:** 10× the pro price ($4.35 / $8.70 per MTok) for latency only, identical weights, no benchmark evidence, and it would compete with grok-4.7 spend while adding nothing the pro row doesn't already cover. (It is verified working, so it stays a one-line add if Bane wants the speed lane.)

**HOLD — `zai/glm-4.6v-flash`:** free and serving, but vision-only-scored and unroutable (§4).

**UPDATE to the carried item — `z-ai/glm-5.3-flashx`:** the 09-20 report set this to HOLD because the zai plan returns `1311` (*"plan does not yet include access"*). **Native is still 1311 today, but OpenRouter now serves it** — `POST` → HTTP 200 in 2.2 s, `$0.37 / $1.25` per MTok, 1 048 576 ctx. So the recommendation becomes: **addable via `openrouter/z-ai/glm-5.3-flashx` at OR list price**, or keep holding for the cheaper plan lane whenever the entitlement lands.

---

## 6. zai native plan — probe matrix this run

| Probe (against the configured coding endpoint) | Result |
|---|---|
| `glm-4.6v-flash` | **200** in 1.1 s, visible content |
| `glm-5.3-flash` | **200** in 5.6 s … then **429 `1302` rate limit reached** seconds later |
| `glm-5.2` (the catalog's `zai-coding-plan/glm-5.2`) | **429 `1302` rate limit reached** |
| `glm-5.3-flashx` | **429 `1311`** — plan entitlement still missing |
| `glm-4.7` | 200, but `content` empty at `max_tokens=64` (reasoning ate the budget — known pitfall) |

Reading: the plan is **intermittently** request-rate-limited (`1302`) rather than weekly-exhausted (`1310` as on 09-20) — the same model alternated between 200 and 429 within one tick, in both directions. Any zai-side flake seen by users right now is most likely this, not a gateway fault.

---

## 7. Deployment state (measured this tick)

- `/health` and `/v1/health/live` → `{"status":"alive","uptime_models":42,"commit":"faf78b4"}`.
- Local `HEAD` = **43665b2**; the running commit is **2 commits behind**, both **non-code** (`43665b2` board cleanup, `151d455` dogfood notes) — `git diff --stat faf78b4..HEAD -- src/ scripts/ tests/ pyproject.toml` is **empty**, so the running code *is* HEAD's code. **No restart needed** (last week's 15-commit real drift did not recur).
- CI on HEAD is **red** (`test 3.11/3.12/3.13` fail: `docs/dogfood/2026-09-22-integration.md` not indexed; `lint` green). Owned by the releng satellite row `RELEASE-READINESS-2026-09-22` (RELEASE-FINDING-001), noted here only so the sync report isn't read as "all green".
- Providers configured: 7 (`deepseek`, `openrouter`, `zai`, `anthropic`, `google`, `hermes`, `router9`); `xai` has a key but **no provider block** — that is why grok must ride OpenRouter (§2).

---

## 8. Carried board rows — status re-read from the board, not from memory

| Row | Status now | Note |
|---|---|---|
| DF-CHIMERA-V2-26 (sync blind spot) | **complete** | The scan now emits the Reseller Watch / Blind Spot sections this report carries — the 09-20 decision landed. |
| DF-CHIMERA-V2-27 (`hermes` health probe) | **complete** | — |
| DF-CHIMERA-V2-28 (StepFun native key vs 402) | **pending (P3)** | Still open; unchanged this tick. |
| DF-CHIMERA-V2-32 … 35 (dogfood: `--stage-models` silent no-op, `auto` not implicit, degraded-DAG RC=0, CONFIG.md scale) | **pending** | From `151d455`; not sync-owned. |

---

## 9. Action items

1. **Approve or reject the 3 adds in §5** (`openrouter/x-ai/grok-4.7`, `xiaomi/mimo-v2.6-flash`, `xiaomi/mimo-v2.6-pro`). No catalog edit has been made.
2. **Decide the vision question** (§4): either wire an image input into the request path, or stop scoring image-only lanes. Until then `glm-4.6v-flash` stays out.
3. **Decide `openrouter/z-ai/glm-5.3-flashx`** — native is entitlement-blocked, OR works at list price (§5).
4. **DF-CHIMERA-V2-37** (filed this run): fix the wrapper so its printed candidate count cannot contradict the report it just wrote, and so a new low-recency find gets auto-scored instead of silently skipped.
5. Unrelated but open from the same tick: **DF-CHIMERA-V2-28** (StepFun) and the CI-red docs-index item (releng-owned).

---

## 10. Finding filed as a board row this run

| Row | Priority | Finding |
|---|---|---|
| **DF-CHIMERA-V2-37** | P3 | `model_sync_cron.py` step 3 re-runs `--diff --score` after step 1 already wrote `.seen_models.json`, so the tick prints `Candidates: 0 new models` directly under a report that says `5 new models`; and `--score`'s top-5-by-recency selection means a new find with an old release date is never auto-scored (proof: `zai/glm-4.6v-flash`, scored only by a manual targeted run). |
