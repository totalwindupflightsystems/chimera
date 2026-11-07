# Chimera Model Sync — Weekly Report

**Run:** 2026-11-07 17:00 UTC (sync at 12:00 local / 17:00 UTC)
**Scope:** 13 core providers + reseller watch (kilo, llmgateway, nano-gpt, openrouter, vercel) + 22 task-router lanes
**Headline:** **0 new core-lab candidates, 0 lane promotions — nothing new to add this week.** The 7-item carry-forward queue from 10-25/10-30 is still unapproved; all 7 re-verified against today's provider cache with prices unchanged. `openrouter/openai/gpt-5.6` is still absent upstream (**day 8**) and will 404 at call time. No catalog file was touched.

| Artifact | Path / value |
|---|---|
| Sync report | `reports/latest.md` (`reports/latest_20261107_1200.md`) |
| Diff candidates (raw) | `/var/tmp/hermes-scratch/chimera-model-sync-diff-1887420.json` — literally `{}` (2 bytes) |
| Live service | `:8765` → `status=alive`, `uptime_models=43`, `commit=7093215`, `version=0.2.9` |
| Deploy parity | **CODE-CURRENT** — running `7093215` resolves, is an ancestor of HEAD `bbbb688`, material diff (`src/ scripts/ tests/ pyproject.toml`) **empty** (HEAD's advance is the fleet-ops board commit). No reload performed or claimed. |
| Cron state | weekly job ran via pre-run script, `--diff: 0`, agent leg completed this tick |

---

## 1. What the scan reported

- `--diff`: **0 new models across 13 core providers**, **0** task-router lane finds; diff file is literally `{}`
- provider cache: `provider_cache_stale age_s=23390` fell back to a marker, then `provider_fetch_ok providers=236`; discovery then ran on the fresh cache (`age_s=0/1`)
- attribution: `models=8719 providers=9 unattributed=5487` (11-06: 8697 / 5467) — the unattributed pool grew by 21 rows, all in reseller/blind-spot territory, none in core scope
- OpenRouter block: **377** rows (11-06: 375) — two net new rows, neither a core-lab family release
- basename skips: 3 standing (`openai/gpt-5.6`, `-luna`, `-sol`); the first is bogus — see §3
- ledger: `.seen_models.json` holds **511** keys (unchanged since 10-29); the catalog holds **43** models. `--diff: 0` means "nothing novel", never "catalog current"

**Reseller-watch state** (informational, not counted in the headline; these rows are deliberately re-reported every run until they appear in a core row or are admitted):

- No new reseller families surfaced — the diff file being `{}` covers the reseller watch too.
- Standing rows still name live core-lab SKUs that are **not** in the catalog: `openai/gpt-6.1-terra-pro` ($1/$5), `openai/gpt-6.1-sol-pro` ($2/$10), `openai/gpt-6-luna` ($0.10/$0.50), `anthropic/claude-haiku-5.5` ($0.10/$0.50), `anthropic/claude-sonnet-5.5` ($2/$10), `anthropic/claude-opus-5.5`, `google/gemini-4-argon`, `moonshotai/kimi-k3.1-pro`, `minimax/minimax-m3.1-flash`, `mistralai/mistral-large-4-0`, `x-ai/grok-4.7` ($2/$6), `stepfun/step-5-preview` ($1/$2.70), `meta/muse-spark-open` ($1.25/$4.25), `meta/muse-wonder` ($4/$20).
- `tencent/hy4` ($0.834/$2.501 per 1k, 4 reseller rows) stays reseller-only: `tencent` is not one of the 13 core providers.
- Reseller variants that do **not** resolve on the OpenRouter block this run: `openai/gpt-6.1-terra-fast`, `openai/gpt-6.1-sol-fast`, `mistralai/mistral-large-4` (only `-4-0` is live).

## 2. Verification — carry-forward queue re-checked against today's cache

Read from `~/.chimera/models-dev-cache.json` (236 providers, OpenRouter block 377 rows), exact slugs:

| # | OR id | Status | $/MTok in | $/MTok out | ctx | Waiting since | In catalog |
|---|---|---|---|---|---|---|---|
| 1 | `openai/gpt-6.1-terra` | LIVE | 1.00 | 5.00 | 1,050,000 | 10-25 | no |
| 2 | `minimax/minimax-m3.1-flash` | LIVE | 0.075 | 0.30 | 1,048,576 | 10-29 | no |
| 3 | `anthropic/claude-opus-5.5` | LIVE | 4.00 | 20.00 | 1,000,000 | 10-25 | no |
| 4 | `openai/gpt-6.1-sol` | LIVE | 2.00 | 10.00 | 1,050,000 | 10-29 | no |
| 5 | `google/gemini-4-argon` | LIVE | 2.00 | 10.00 | 1,048,576 | 10-25 | no |
| 6 | `moonshotai/kimi-k3.1-pro` | LIVE | 2.00 | 10.00 | 1,048,576 | 10-29 | no |
| 7 | `mistralai/mistral-large-4-0` | LIVE | 0.70 | 2.10 | 1,048,576 | 10-30 | no |

No price moved vs 11-06 (nor vs 11-05). Grep-confirmed against the parsed `models:` map (43 entries): none of the 7 is present under any prefix. Nothing applied.

## 3. Standing breakage — `openrouter/openai/gpt-5.6` (day 8, unfixed)

`chimera.yaml:358` still carries `openrouter/openai/gpt-5.6` (siblings `-luna`, `-sol`, `-terra` at :395/:430/:467 are fine). Today's cache read: `openai/gpt-5.6` → **ABSENT**; the OpenRouter block serves only the tiered family (`-luna`, `-luna-pro`, `-sol`, `-sol-pro`, `-terra`, `-terra-pro`, plus the 6.1 tier rows). Any stage pinned to the bare id 404s at call time.

Two fixes, both awaiting approval: repoint to `openrouter/openai/gpt-5.6-sol` ($4.00/$20.00 per MTok, live) or drop the row. The sync's basename-skip line keeps describing the stale id as "already admitted", so the skip logic will not surface this — it must be fixed by hand.

## 4. Action items (approval required — nothing applied)

1. **DECIDE** the queue in §2 — 7 ids live and price-current. Under the "newest live generation" rule the highest-leverage picks are `openai/gpt-6.1-terra`, `anthropic/claude-opus-5.5`, `google/gemini-4-argon`, `moonshotai/kimi-k3.1-pro`, `minimax/minimax-m3.1-flash`.
2. **FIX** `openrouter/openai/gpt-5.6` — dangling 8 days; repoint to `-sol` or drop (§3).
3. **CONSIDER** two cheap-tier additions surfaced in the reseller watch: `openai/gpt-6-luna` ($0.10/$0.50, 1.05M ctx) and `anthropic/claude-haiku-5.5` ($0.10/$0.50) — both live on OpenRouter, newer generation than the catalog's current budget rows at the same or lower price.
4. **DECIDE** the `.seen_models.json` re-baseline (511 seen / 43 catalogued) — until then `--diff: 0` is a novelty signal only.
5. **NO ACTION** on deploy: parity is CODE-CURRENT (`7093215` ancestor of HEAD, empty material diff); no restart owed or performed.

If any row is approved the sequence is unchanged: edit `chimera.yaml` → `cp chimera.yaml chimera.yaml.example && cp chimera.yaml chimera.yaml.docker` → offline suite green (`pytest tests/ --ignore=tests/integration --ignore=tests/compat -q`) → `sudo systemctl restart chimera` → `/health` shows the new commit → `/v1/models` count check (43 → 44 per row) → `python scripts/smoke_live.py` (exit 0).

---

*Source of record for this run: `reports/latest.md` + `reports/latest_20261107_1200.md`, `/var/tmp/hermes-scratch/chimera-model-sync-diff-1887420.json` (empty `{}`), `~/.chimera/models-dev-cache.json` (236 providers, 377 OpenRouter rows), `.seen_models.json` (511 keys), live `/health` at commit `7093215`, HEAD `bbbb688`. No catalog file, config template, cron job, or service was modified by this run; this report is the only written artifact.*
