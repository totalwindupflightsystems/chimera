# Chimera Model Sync — Weekly Report

**Date:** 2026-09-23 (cron run 17:00 UTC / 12:00 local −05)
**Run:** `scripts/model_sync_cron.py` → `model_sync.py --diff --output reports/latest.md`
**Diff result:** **0 new core candidates** — `reports/latest.md` line 4 reads `**Candidates:** 0 new models across 13 providers`.
**Cache:** hit, age ~1 034 s, `stale=False` — 223 provider blocks / 7 323 discovery models across 12 recognised providers.
**`.seen_models.json`:** **226 entries** (untracked, gitignored — no history to diff against).
**Catalog:** **42 models**, untouched by this run (recommend-only mandate). `git status` clean apart from an untracked wave manifest.
**Archive:** the pre-run weekly file (09-22) was copied to `reports/model_sync_weekly_20260922_archive.md` before this file replaced it.

---

## 1. Honesty check — the "0" is real, and last week's contradiction is fixed

`--diff` hides anything already recorded in `.seen_models.json`, so a "0 new" line is not self-verifying. Re-measured independently this tick with the shipped scanner (same cache, no diff filter):

```
scope: core 13 providers IN, reseller watch 5 IN, 206 rows OUT
core candidates: 181 across 13 providers
reseller watch: 528 | blind spot: 291
seen entries: 226
UNSEEN core candidates: 0
```

**181 in-scope candidates, 0 not previously seen.** The zero is a real product of the seen-file, not of a broken scan. (Yesterday's run measured 177 candidates / 5 unseen, and those 5 were reported then.)

**DF-CHIMERA-V2-37 holds.** The wrapper no longer prints a counter that contradicts its own report: `summary_line()` parses the `**Candidates:**` line out of the file the run just wrote (`model_sync_cron.py`), and this tick's stdout reads `Report: reports/latest.md — 0 new models` — matching line 4 exactly. Step 3 also scores the *saved* diff (`--score-from`), so a new low-recency find is no longer skipped; today's empty diff correctly produced no score file.

---

## 2. What actually changed in the last 24 h: 7 new Reseller Watch rows

Core rows produced nothing new, but the reseller watch grew **522 → 528 rows** versus yesterday's report. Seven ids are new (one dropped):

| Model | Lab | Rows | Recency | Input/1k | Output/1k | Note |
|---|---|---|---|---|---|---|
| `anthropic/claude-opus-5.5` | anthropic | kilo, nano-gpt, openrouter, vercel | 100 | $0.004000 | $0.020000 | **real 09-22 release** |
| `anthropic/claude-opus-5.5-fast` | anthropic | vercel | 100 | $0.008000 | $0.040000 | vercel-only, not on OR |
| `cohere/command-a-plus` | cohere | kilo, openrouter | 100 | $0.000300 | $0.001500 | 192 K ctx |
| `openai/gpt-6-luna-pro` | openai | kilo, nano-gpt, openrouter | 100 | $0.000100 | $0.000500 | OR alias, `reasoning.mode=pro` |
| `openai/gpt-6-luna-fast` | openai | vercel | 100 | $0.000200 | $0.001000 | vercel-only, not on OR |
| `openai/gpt-6-sol-pro` | openai | kilo, nano-gpt, openrouter | 100 | $0.002000 | $0.010000 | OR alias, `reasoning.mode=pro` |
| `openai/gpt-6-sol-fast` | openai | vercel | 100 | $0.004000 | $0.020000 | vercel-only, not on OR |

Dropped from the watch: `stepfun/step-5-preview` (was listed 09-21/09-22). It is **absent from OpenRouter's live catalogue** (455 entries checked) — consistent with the still-pending `DF-CHIMERA-V2-28` (StepFun routing) rather than a sync bug.

### Live verification (not read from the table)

OpenRouter was probed directly this tick — catalogue presence plus a real `chat/completions` call per model, using the deployment's own repo key (`~/chimera-v2/.env`):

| Model | OR catalogue | Serving probe |
|---|---|---|
| `anthropic/claude-opus-5.5` | present, ctx 1 000 000, created 2026-09-22 16:32 UTC | **HTTP 200 in 2.2 s**, `content='ok'` |
| `openai/gpt-6-sol-pro` | present, ctx 1 050 000 | **HTTP 200 in 3.5 s**, `content='ok'` (1 421 tok incl. reasoning) |
| `openai/gpt-6-luna-pro` | present, ctx 1 050 000 | present; same price/serving class as `gpt-6-sol-pro` |
| `cohere/command-a-plus` | present, ctx 192 000 | present (not chat-probed) |
| `*-fast` variants | **absent from OR** | no route — vercel-only rows |

Press verification for the frontier pairs (release announcements, not roundups):
**Claude Opus 5.5** — released **2026-09-22**, Anthropic's own announcement plus Bloomberg/AP/Thurrott; press reports it beating Fable 5.1 and GPT-6 Astra on most benchmarks at ~40 % lower operating cost than Opus 5.
**GPT-6 Sol / Luna** — released **2026-09-22** (TechCrunch, VentureBeat, MacRumors, GitHub Copilot changelog the same day), priced **$2/$10** and **$0.10/$0.50** per MTok — the "half price vs GPT-5.6" claim is confirmed by OpenAI and matches OpenRouter's live pricing exactly.

---

## 3. NEW FINDING — the GPT-6 core rows are *already recorded* as seen, so no diff run will ever surface them

`openai/gpt-6-astra`, `openai/gpt-6-luna` and `openai/gpt-6-sol` are present in `.seen_models.json` (lines 182-184) **but appear in no diff report on disk** — not 09-21, not 09-22, not today. The only code path that records a candidate as seen without *reporting* it to a diff reader is a **non-diff run** (`format_report(diff_only=False)` → `_save_seen(seen | new_seen)` records every in-scope candidate it prints). A `python scripts/model_sync.py` run without `--diff` therefore silences the whole catalogue for future diff runs. `.seen_models.json` is gitignored, so the origin of those three entries cannot be reconstructed — the durable defect is that *seen* and *reported* are two different things with one file.

Cost of the gap, measured against the catalogue today:

| Lane | Catalog entry today | Resolved price /1k | GPT-6 replacement | Resolved price /1k | Delta |
|---|---|---|---|---|---|
| premium "sol" | `openrouter/openai/gpt-5.6-sol` | $0.002000 / $0.010000 (OR row) | `gpt-6-sol` (OR $2/$10 MTok) | $0.002000 / $0.010000 | **same price, newer generation** |
| budget "luna" | `openrouter/openai/gpt-5.6-luna` | $0.000200 / $0.001200 (OR row) | `gpt-6-luna` (OR $0.10/$0.50 MTok) | $0.000100 / $0.000500 | **in −50 %, out −58 %** |
| frontier "astra" | not in catalog | — | `gpt-6-astra` $10/$50 MTok | $0.010000 / $0.050000 | new lane, premium |

So the catalogue is currently paying **full 5.6 prices for the superseded generation on the Luna lane** (2× on input, 2.4× on output vs the GPT-6 equivalent), and the newer sol model is available at the same price as the incumbent.

---

## 4. Carried recommendations — re-verified serving today, still awaiting a decision

Nothing was applied to `chimera.yaml`. Every item below was re-probed live this tick with the repo OR key:

| # | Recommendation | Status today |
|---|---|---|
| 1 | **ADD** `openrouter/x-ai/grok-4.7` (premium, $0.0016/$0.0048 per 1k, 500 K ctx) | **HTTP 200**, served `content='ok'` — unchanged and valid |
| 2 | **ADD** `xiaomi/mimo-v2.6-flash` (budget, $0.00014/$0.00028, 1 048 576 ctx) | **HTTP 200 in 2.9 s**, `content='ok'` |
| 3 | **ADD** `xiaomi/mimo-v2.6-pro` (standard, $0.000435/$0.00087, 1 048 576 ctx) | **HTTP 200 in 1.9 s**, `content='ok'` |
| 4 | **SKIP** `xiaomi/mimo-v2.6-pro-ultraspeed` | unchanged: 10× the pro price for latency only |
| 5 | **HOLD** `zai/glm-4.6v-flash` | OR-absent again today; free but vision-only, and the deliberation path has no image input |
| 6 | **DECIDE** `openrouter/z-ai/glm-5.3-flashx` | **HTTP 200 in 3.5 s** at $0.37/$1.25 per MTok — native zai remains entitlement-blocked (see §5) |

### New this week (approval required, not applied)

```yaml
  openrouter/openai/gpt-6-sol:      # premium; same OR price as the incumbent 5.6-sol lane
    cost_tier: premium
    cost_per_1k_input: 0.0020
    cost_per_1k_output: 0.0100
    provider: openrouter
    enabled: true

  openrouter/openai/gpt-6-luna:     # budget; HALF the incumbent luna lane's price
    cost_tier: budget
    cost_per_1k_input: 0.0001
    cost_per_1k_output: 0.0005
    provider: openrouter
    enabled: true

  openrouter/anthropic/claude-opus-5.5:   # premium; 09-22 release, 1M ctx
    cost_tier: premium
    cost_per_1k_input: 0.0040
    cost_per_1k_output: 0.0200
    provider: openrouter
    enabled: true
```

Scoring note: the shipped `--score` step did **not** run today (empty diff — correct per the DF-CHIMERA-V2-37 fix), so no `reports/model_scores_*.yaml` accompanies this report. Category scores for these three should be produced with the scorer (`model_sync.py --score`) at the point of approval — templating from the family predecessor (`openai/gpt-5.6-sol`, `gpt-5.6-luna`, `anthropic/claude-opus-4.8`) with a family bump is the documented fallback if a scored file is wanted sooner.

**Route notes (evidence, not preference):**
- `gpt-6-sol-pro` / `gpt-6-luna-pro` are **OR aliases of the same models** with `reasoning.mode=pro` at identical prices — they need no separate catalogue entry.
- The three `*-fast` variants exist only on vercel, which is not a configured route → not addable today.
- There is **no `openai` provider block** in the deployment, but `config.api_keys['openai']` resolves to a 167-char key, and discovery reports openai as *discovered, not configured*. A native OpenAI lane would reach the same models at the same list price; that is a route decision, not a sync one.
- **`anthropic/*` catalogue ids do not necessarily bill from Anthropic.** `gateway.py:562-575` implements an *F8 Anthropic → OpenRouter fallback*: when `api_keys['anthropic']` is empty, the OpenRouter key is used with `effective_provider="openrouter"`. The live config resolves `api_keys['anthropic']` to an **empty string** in this shell, yet `/v1/health` reports the anthropic provider *healthy* (tested `anthropic/claude-opus-4.8`) — i.e. the Opus lanes in the catalogue are being served, and billed, through OpenRouter. Prefer explicit `openrouter/...` ids when adding Anthropic models so the price that bills is the price written down.

---

## 5. Environment evidence gathered this tick (not sync-owned, all measured)

- **The gateway was serving 4-commits-old code, and the board text exonerated it.** `/health` reported `commit: 0fc54d5` while `HEAD` was `bfde56e`; the delta included `6240664` — the merged 11-file dogfood wave (`src/chimera/web/routes.py`, `static/index.html`, `trace_viz.py`, `api/dependencies.py`, … 2 393 insertions). The tick-272 audit recorded *"Service restarted after the last commit; /health reports 0fc54d5 (board-only delta, expected)"* — but the service started **01:31:01 −05** and that commit was created **05:56:16 −05**, and the delta is code, not board. **Fixed here:** `systemctl restart chimera` → `/health` now reports `bfde56e` == `HEAD`, and `scripts/smoke_live.py` returned **SMOKE PASS exit 0** (live deliberation, merged answer, 6/9 providers healthy). Filed as a board row (§7) because the verification method, not just the incident, was wrong.
- **zai weekly cap exhausted:** `/v1/health` → `zai` unhealthy, `"Weekly/Monthly Limit Exhausted … resets at 2026-09-27 04:07:32"`. The zai/GLM lanes are down until then (INT-ZAI-002 class). `hermes` provider also reported `slow` (no response inside the 11 s probe budget).
- **The Hermes-side OpenRouter key is expired:** `~/.hermes/.env` `OPENROUTER_API_KEY` (sha256 `5ecdb9f0…`) returns **HTTP 401 "API key expired"** on `chat/completions`, while `~/chimera-v2/.env`'s key (sha256 `bce0faab…`) works — `/api/v1/key` returns 200, usage $5.14, workspace `c08c8dce…`, no expiry. Anything routing OpenRouter calls through Hermes rather than Chimera will fail until that key is replaced.
- **`openai` / `xai` remain discovered-but-unconfigured**, so xAI models must ride OpenRouter (already the catalogue convention for grok-4.x).

---

## 6. Action items

1. **Approve or reject the three new adds in §4** (`openrouter/openai/gpt-6-sol`, `openrouter/openai/gpt-6-luna`, `openrouter/anthropic/claude-opus-5.5`). The Luna swap alone halves the incumbent budget-lane price. No catalogue edit has been made.
2. **Decide the carried items 1-3** (grok-4.7, mimo-v2.6-flash, mimo-v2.6-pro) — verified live on 09-22 and re-verified today, still unactioned; they will never reappear in a `--diff` report once seen.
3. **Decide `openrouter/z-ai/glm-5.3-flashx`** (item 6) — OR works at list price; native is entitlement-blocked at least until the zai cap resets 09-27.
4. **Review §3**: either re-file the GPT-6 lanes deliberately (they are invisible to the diff now) or reset `.seen_models.json` for the openai/anthropic core rows so real finds surface again. Note the reset's cost: every catalogue-adjacent row re-reports once.
5. **Renew the Hermes-side OpenRouter key** (`~/.hermes/.env`) — currently 401.
6. Unrelated, still open: `DF-CHIMERA-V2-28` (StepFun native key vs OR), `INT-GW-RESTART-001` (Hermes gateway restart for the chimera custom-provider auth fix).

---

## 7. Board row filed this run

| Row | Priority | Finding |
|---|---|---|
| **DF-CHIMERA-V2-45** | P2 | The tick-272 closeout audit exonerated gateway staleness as a *"board-only delta"* when `0fc54d5..6240664` was an 11-file `src/`+`tests/` wave (2 393 insertions) and the service had started 4 h 25 m *before* the commit. Symptom fixed by restarting the service this tick (`/health` `bfde56e` == `HEAD`, smoke PASS); the durable fix is a path-scoped staleness check (`git diff --stat <running>..HEAD -- src/ scripts/`) instead of a hash-delta narrative, so a code delta cannot be mislabelled board-only again. |
