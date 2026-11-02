# Chimera Model Sync — Weekly Report

**Run:** 2026-11-02 17:00 UTC (sync at 12:00 UTC)
**Scope:** 13 core providers + reseller watch (kilo, llmgateway, nano-gpt, openrouter, vercel) + 22 task-router lanes
**Headline:** **0 new core-lab candidates, 0 lane promotions — nothing to add this week.** The scan is clean, not idle: the 7-item carry-forward queue from 10-30 is still unapproved and was **re-verified live on OpenRouter this run** (all 7 still present, prices unchanged), and the dangling catalog row `openrouter/openai/gpt-5.6` is **still absent upstream (day 3)** and will 404 at call time. The one genuinely new information is operational: today's 12:00 tick was caught in a gateway-connection failure that paused this job (along with three other crons) for ~5 minutes — the sync script leg succeeded, the agent leg wrote 0-byte output on 10-30 and 10-31, and the job carries `failure_streak: 6`.

| Artifact | Path |
|---|---|
| Sync report | `reports/latest.md` (`reports/latest_20261102_1200.md`) |
| Diff candidates (raw) | `/var/tmp/hermes-scratch/chimera-model-sync-diff-1133359.json` — empty object `{}` |
| Live service | `:8765` → `status=alive`, `uptime_models=43`, `commit=7093215`, `version=0.2.9` |
| Deploy parity | **CODE-CURRENT** — running `7093215` resolves, is an ancestor of HEAD `18cd0f6`, and the material diff (`src/ scripts/ tests/ pyproject.toml`) is **empty**. No reload performed or claimed. |
| Cron state | `chimera-model-sync` state=scheduled, next 2026-11-03 12:00 local, `failure_streak: 6` (paused 12:03, auto-resumed 12:08) |

---

## 1. What the scan reported

- `--diff`: **0 new models across 13 core providers**, **0** task-router lane finds; diff file is literally `{}`
- basename skips: 3 standing (`openai/gpt-5.6`, `-luna`, `-sol` — reported as already admitted under `openrouter/` prefixes; the first of those is bogus, see §3)
- registry: task-router `data/tables/models.jsonl` (25 providers); provider cache stale at start (**age 4,081 s**) then refetched — **236 providers** fetched, **235** served from cache afterwards; `provider_discovery_done models=8702 providers=9 unattributed=5458`
  - vs 10-30: `models 8713 → 8702` (−11), `attributed 3233 → 3244`, `unattributed 5480 → 5458` (−22). Attribution backlog effectively flat.
- reseller watch: the standing large set (batch / quantized / `-uncensored` / `-latest` / `:thinking` variants). Informational, not recorded in `.seen_models.json`, re-reported every run. **This run it carries every frontier release the core blocks still lack** — Claude 5.5 family, Gemini 4 Argon, GPT-6.1 Terra/Sol, Kimi K3.1 Pro, MiniMax M3.1 Flash, Step-5 Preview, Grok 4.7, Mistral Large 4. None was promoted to a core-lab row, so none counted toward the headline (DF-CHIMERA-V2-67 behaviour).
- ledger: `.seen_models.json` holds **511** keys; the catalog holds **43** models. The headline is novelty relative to the ledger, not gap relative to the catalog (unchanged from the 10-30 §4.3 finding).

## 2. Verification — carry-forward queue re-checked live

Live OpenRouter `/api/v1/models` pulled this run with the dotenv key: **HTTP 200, 419 ids** (10-30: 424 — the roster shrank by 5). Every queued or recommended id was checked by exact slug:

| # | OR id | Live | $/Mtok in | $/Mtok out | ctx | Waiting since | Catalog hit |
|---|---|---|---|---|---|---|---|
| 1 | `openai/gpt-6.1-terra` | **LIVE** | 1.0000 | 5.0000 | 1,050,000 | 10-25 | none |
| 2 | `minimax/minimax-m3.1-flash` | **LIVE** | 0.0750 | 0.3000 | 1,048,576 | 10-29 | none |
| 3 | `anthropic/claude-opus-5.5` | **LIVE** | 4.0000 | 20.0000 | 1,000,000 | 10-25 | none |
| 4 | `openai/gpt-6.1-sol` | **LIVE** | 2.0000 | 10.0000 | 1,050,000 | 10-29 | none |
| 5 | `google/gemini-4-argon` | **LIVE** | 2.0000 | 10.0000 | 1,048,576 | 10-25 | none |
| 6 | `moonshotai/kimi-k3.1-pro` | **LIVE** | 2.0000 | 10.0000 | 1,048,576 | 10-29 | none |
| 7 | `mistralai/mistral-large-4-0` | **LIVE** | 0.7000 | 2.1000 | 1,048,576 | 10-30 | none |

Same-run spot checks of the remaining generational-gap names, all **LIVE**, prices as previously reported: `anthropic/claude-sonnet-5.5` 2.00/10.00, `anthropic/claude-haiku-5.5` 0.10/0.50, `x-ai/grok-4.7` 2.00/6.00 (500k ctx), `stepfun/step-5-preview` 1.00/2.70, `meta/muse-wonder` 4.00/20.00.

No price moved since 10-30. Nothing was applied; `chimera.yaml` is untouched.

## 3. Standing breakage — `openrouter/openai/gpt-5.6` (day 3, unfixed)

`openai/gpt-5.6` is **ABSENT** from the live roster for the third consecutive check. The only surviving family ids are tiered:

```
openai/gpt-5.6-luna      openai/gpt-5.6-luna-pro      (+ :batch each)
openai/gpt-5.6-sol       openai/gpt-5.6-sol-pro       (+ :batch each)
openai/gpt-5.6-terra     openai/gpt-5.6-terra-pro     (+ :batch each)
```

`chimera.yaml` still contains `openrouter/openai/gpt-5.6` (one of 43 catalog models), so any stage pinned to it 404s at call time. Two fixes, both awaiting approval: repoint to `openrouter/openai/gpt-5.6-sol` (nearest non-Luna tier, $2.00/$10.00 per MTok) or drop the row. The sync's own basename-skip line keeps describing the stale id as "already admitted", so the skip logic will not surface this.

## 4. Operational finding — the tick itself was a casualty

Not a catalog issue, but it decides whether next week's report exists at all:

1. At **12:03:13** the scheduler paused `chimera-model-sync` (and `9ecfe9d23fc0`, `869aec0b1c15`, `55afdcd33d7f`) with: *"Cron execution unverified … Gateway connection failed; no local fallback"*.
2. The **script leg succeeded** — the sync ran and wrote `reports/latest.md` + `reports/latest_20261102_1200.md`. What failed was the agent/delivery leg.
3. The same pattern explains 10-30 and 10-31: `~/.hermes/cron/output/chimera-model-sync/2026-10-30_12-18-36.md` and `2026-10-31_12-06-12.md` are **0 bytes**, while 10-29 was 59 KB. Three agent outputs missing, not three clean runs.
4. All four jobs were **auto-resumed at 12:08** (`state=scheduled`, `enabled=True`, `paused_at=None`); the gateway is healthy now (`:8642/health` → 200). But `failure_streak: 6` is retained, so one more failure likely re-pauses the job.

Consequence: read "sync ran" from `reports/latest.md`, never from cron status. If the job re-pauses, the fix is at the gateway/admission layer, not in `model_sync.py`.

## 5. Action items (approval required — nothing applied)

1. **DECIDE** the queue in §2 — 7 ids verified live and price-current. Under Bane's "newest live generation" rule the highest-leverage picks are `openai/gpt-6.1-terra`, `anthropic/claude-opus-5.5`, `google/gemini-4-argon`, `moonshotai/kimi-k3.1-pro`, `minimax/minimax-m3.1-flash`.
2. **FIX** `openrouter/openai/gpt-5.6` — dangling for 3 days; repoint to `-sol` or drop (§3).
3. **DECIDE** the `.seen_models.json` re-baseline (511 seen / 43 catalogued) — until then `--diff: 0` means "nothing novel to the ledger", not "catalog current".
4. **WATCH** the cron's `failure_streak: 6` (§4) — the sync output is trustworthy, the job's recording leg is not.

If any row is approved the sequence is unchanged: edit `chimera.yaml` → `cp chimera.yaml chimera.yaml.example && cp chimera.yaml chimera.yaml.docker` → offline suite green (`pytest tests/ --ignore=tests/integration --ignore=tests/compat -q`) → `sudo systemctl restart chimera` → `/health` shows the new commit → `/v1/models` count check (43 → 44 per row) → `python scripts/smoke_live.py` (exit 0).

---

*Source of record for this run: `reports/latest.md`, `reports/latest_20261102_1200.md`, `/var/tmp/hermes-scratch/chimera-model-sync-diff-1133359.json` (empty), `~/.chimera/models-dev-cache.json` (refetched this run, 236→235 providers), `openrouter.ai/api/v1/models` (fetched 2026-11-02, 419 ids), `.seen_models.json` (511 keys), `cron/jobs.json` + `cron/executions.db` + `cron/output/chimera-model-sync/` (cron reliability), live `/health` at commit `7093215`, HEAD `18cd0f6`. No catalog file, config template, cron job, or service was modified by this run; this report is the only written artifact.*
