# Chimera Model Sync — Weekly Report

**Run:** 2026-11-03 17:00 UTC (sync at 12:00 local / 17:00 UTC)
**Scope:** 13 core providers + reseller watch (kilo, llmgateway, nano-gpt, openrouter, vercel) + 22 task-router lanes
**Headline:** **0 new core-lab candidates, 0 lane promotions — nothing to add this week.** The 7-item carry-forward queue from 10-25/10-30 is still unapproved and was **re-verified live on today's refetched provider cache** (all 7 present, prices unchanged). `openrouter/openai/gpt-5.6` is **still absent upstream (day 4)** and will 404 at call time. No catalog file was touched.

| Artifact | Path / value |
|---|---|
| Sync report | `reports/latest.md` (`reports/latest_20261103_1200.md`) |
| Diff candidates (raw) | `/var/tmp/hermes-scratch/chimera-model-sync-diff-3840354.json` — literally `{}` |
| Live service | `:8765` → `status=alive`, `uptime_models=43`, `commit=7093215`, `version=0.2.9` |
| Deploy parity | **CODE-CURRENT** — running `7093215` resolves, is an ancestor of HEAD `72771bb`, material diff (`src/ scripts/ tests/ pyproject.toml`) **empty**. No reload performed or claimed. |
| Cron state | `chimera-model-sync` state=scheduled, enabled, **failure_streak 0** (was 6 on 11-02), last run 11-02 12:11, next 11-04 12:00 local |

---

## 1. What the scan reported

- `--diff`: **0 new models across 13 core providers**, **0** task-router lane finds; diff file is literally `{}`
- provider cache: **stale at start** (age 23,378 s ≈ 6.5 h) → refetched **236 providers**, served from cache afterwards (235), so this scan ran on **fresh** data, not the stale cache
- attribution: `models=8700 providers=9 unattributed=5456` (11-02: 8702 / 5458 / 3244 attributed) — backlog flat, drift is noise
- basename skips: 3 standing (`openai/gpt-5.6`, `-luna`, `-sol`); the first is bogus — see §3
- reseller watch: the standing large set (batch / quantized / `-uncensored` / `-latest` / `:thinking` variants). Informational, not recorded in `.seen_models.json`, re-reported every run. It again carries every frontier release the core blocks lack — Claude 5.5 family, Gemini 4 Argon, GPT-6.1 Terra/Sol, Kimi K3.1 Pro, MiniMax M3.1 Flash, Step-5 Preview, Grok 4.7, Mistral Large 4. None was promoted to a core-lab row, so none counted toward the headline (DF-CHIMERA-V2-67 behaviour).
- ledger: `.seen_models.json` holds **511** keys; the catalog holds **43** models. The headline is novelty relative to the ledger, **not** gap relative to the catalog — `--diff: 0` means "nothing novel", never "catalog current".

## 2. Verification — carry-forward queue re-checked

Read from `~/.chimera/models-dev-cache.json`, refetched by this run at 12:00 (OpenRouter block, exact slugs):

| # | OR id | Status | $/MTok in | $/MTok out | ctx | Waiting since | In catalog |
|---|---|---|---|---|---|---|---|
| 1 | `openai/gpt-6.1-terra` | LIVE | 1.00 | 5.00 | 1,050,000 | 10-25 | no |
| 2 | `minimax/minimax-m3.1-flash` | LIVE | 0.075 | 0.30 | 1,048,576 | 10-29 | no |
| 3 | `anthropic/claude-opus-5.5` | LIVE | 4.00 | 20.00 | 1,000,000 | 10-25 | no |
| 4 | `openai/gpt-6.1-sol` | LIVE | 2.00 | 10.00 | 1,050,000 | 10-29 | no |
| 5 | `google/gemini-4-argon` | LIVE | 2.00 | 10.00 | 1,048,576 | 10-25 | no |
| 6 | `moonshotai/kimi-k3.1-pro` | LIVE | 2.00 | 10.00 | 1,048,576 | 10-29 | no |
| 7 | `mistralai/mistral-large-4-0` | LIVE | 0.70 | 2.10 | 1,048,576 | 10-30 | no |

No price moved since 11-02. Grep-confirmed: none of the 7 exists in `chimera.yaml`. Nothing applied.

## 3. Standing breakage — `openrouter/openai/gpt-5.6` (day 4, unfixed)

`chimera.yaml:358` still carries `openrouter/openai/gpt-5.6`. The provider cache's OpenRouter block (`has("openai/gpt-5.6") → false`) serves only the tiered family:

```
openai/gpt-5.6-luna      openai/gpt-5.6-luna-pro
openai/gpt-5.6-sol       openai/gpt-5.6-sol-pro
openai/gpt-5.6-terra     openai/gpt-5.6-terra-pro
```

Any stage pinned to it 404s at call time. Two fixes, both awaiting approval: repoint to `openrouter/openai/gpt-5.6-sol` ($2.00/$10.00 per MTok) or drop the row. The sync's own basename-skip line keeps describing the stale id as "already admitted", so the skip logic will not surface this — it has to be fixed by hand.

## 4. Action items (approval required — nothing applied)

1. **DECIDE** the queue in §2 — 7 ids live and price-current. Under the "newest live generation" rule the highest-leverage picks are `openai/gpt-6.1-terra`, `anthropic/claude-opus-5.5`, `google/gemini-4-argon`, `moonshotai/kimi-k3.1-pro`, `minimax/minimax-m3.1-flash`.
2. **FIX** `openrouter/openai/gpt-5.6` — dangling 4 days; repoint to `-sol` or drop (§3).
3. **DECIDE** the `.seen_models.json` re-baseline (511 seen / 43 catalogued) — until then `--diff: 0` is a novelty signal only.
4. **NO ACTION** on cron reliability this week: `failure_streak` recovered 6 → 0 and this tick's agent leg completed (unlike 10-30/10-31, which wrote 0-byte output).

If any row is approved the sequence is unchanged: edit `chimera.yaml` → `cp chimera.yaml chimera.yaml.example && cp chimera.yaml chimera.yaml.docker` → offline suite green (`pytest tests/ --ignore=tests/integration --ignore=tests/compat -q`) → `sudo systemctl restart chimera` → `/health` shows the new commit → `/v1/models` count check (43 → 44 per row) → `python scripts/smoke_live.py` (exit 0).

---

*Source of record for this run: `reports/latest.md` + `reports/latest_20261103_1200.md`, `/var/tmp/hermes-scratch/chimera-model-sync-diff-3840354.json` (empty `{}`), `~/.chimera/models-dev-cache.json` (refetched this run, 236→235 providers, 8700 models), `.seen_models.json` (511 keys), live `/health` at commit `7093215`, HEAD `72771bb`, `~/.hermes/cron/jobs.json`. No catalog file, config template, cron job, or service was modified by this run; this report is the only written artifact.*
