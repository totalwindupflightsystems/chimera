# Chimera Model Sync — Weekly Report

**Date:** 2026-09-19 (script stamp 17:00 UTC / wrapper run 12:00 local -05)
**Run:** `scripts/model_sync_cron.py` → `model_sync.py --diff --output reports/latest.md`, then `--diff --score`
**Diff result:** **1 new candidate** across 13 core providers — `zhipuai/glm-5.3-flashx` (GLM-5.3-FlashX).
**Cache:** hit, age ~1,663 s, `stale=False` — 222 provider blocks / 7,086 in-scope discovery models across 12 recognised providers.
**`.seen_models.json`:** **217 entries** (09-18 report: 216 — the +1 is exactly today's candidate).
**Catalog:** **42 models**, all `enabled: true`; `chimera.yaml` **untouched** by this run (recommend-only mandate).
**Archive process note:** the prior (09-18) weekly report was never committed and got overwritten by this run **without**
an archive — that week's full text is lost (only its head was captured pre-overwrite; archives on disk/git exist
through `20260917`). A timestamped copy of THIS report was created post-write:
`reports/model_sync_weekly_20260919_archive.md`.
**Scores file:** `reports/model_scores_20260919_1201.yaml` (LLM-scored top-5, all paths validated against the canonical 32-path list).

---

## 1. Diff honesty check (seen-file trap) — honest, +1 exactly accounted for

`model_sync.py`'s scan + seen/catalog loaders were re-run **without** `--diff`:

| Check | Result |
|---|---|
| Core providers scanned | 13 |
| In-scope candidates (full scan, no `--diff`) | **172** (171 on 09-18) |
| Candidates **not** in `.seen_models.json` | 1 — today's candidate (after this run's write) |
| Seen-file size | 217 entries (was 216) → **+1 = exactly the candidate** |
| Catalog hits filtered before the seen filter | 171 of 172 (scan drops catalog models first) |

**Conclusion:** the 1-candidate diff is real and complete — nothing else landed in
`openai / anthropic / deepseek / google / xai / mistral / moonshot / minimax / alibaba / zhipuai / meta / stepfun / xiaomi`.

**Honest window boundary.** The only in-scope (core-13) row with a `release_date` in this window is
`zhipuai/glm-5.3-flashx` (**2026-09-18**). Everything else new in the cache this week sits outside the core-13
provider scope (e.g. `~deepseek/deepseek-flash-latest`, an OpenRouter alias row). That is the measured statement,
not a claim that nothing was released anywhere.

---

## 2. Candidate: `glm-5.3-flashx` — **VERIFIED REAL, RECOMMENDED (native zai)**

| Field | Value |
|---|---|
| models.dev row (`zhipuai`) | name "GLM-5.3-FlashX", `release_date`/`last_updated` **2026-09-18**, ctx **1,000,000**, out 131,072, **$0.37 / $1.25 per MTok**, cache_read $0.075, `reasoning: true`, `tool_call: true`, `attachment: true` |
| OpenRouter | `openrouter.ai/api/v1/models/z-ai/glm-5.3-flashx/endpoints` → **HTTP 200**, id `z-ai/glm-5.3-flashx`, "Z.ai: GLM 5.3 FlashX", **1 endpoint (Z.AI direct)**, ctx 1,048,576, $0.37/$1.25 per MTok, **uptime_last_30m = 100** |
| Provider confirmation | **Yes** — Zhipu's official WeChat announcement, Sep 18, covered by TechFlow, BigGo Finance, KuCoin, PANews, Phemex, HuggingNews: officially launched GLM-5.3-FlashX (previously previewed globally as **"Ox Alpha"**); API and experience center open |
| What it is | A **high-speed serving tier of GLM-5.3-Flash** — inference raised from ~30–50 tok/s to up to **200 tok/s** on ~100k domestic chips. Press is explicit: **no new benchmarks, no architectural changes** — a speed/cost-optimized variant |
| Pricing position | $0.37/$1.25 per M sits between deepseek-flash ($0.15/$0.60 official) and GLM-5.3 standard ($1.40/$4.40); cache read $0.075/M. **Budget tier** |
| Newness | Genuinely new model id (new API product), released yesterday — not a relay/alias mapping like last week's `mistral/zai-glm-5-3` |
| Addability | **This deployment holds a `ZAI_API_KEY`** and the `zai` provider (`base_url`) is configured → addable natively, unlike last week's Mistral relay entry which had no credential |

**Verdict: RECOMMEND adding `z-ai/glm-5.3-flashx`.** It is the first Z.AI-direct flash-family entry in the catalog —
the nearest existing relative, `hermes/glm-5.3-flash`, routes through the local Hermes gateway, not Z.AI direct.
Use cases: fast worker/aggregator stages and the plan-lane chain (xkiro → 9router → **zai** → deepseek), where its
200 tok/s + 1M ctx + $0.37/$1.25 pricing is a strong slot. Caveats: (a) it inherits the **zai weekly quota cap**
(err 1310) that is currently exhausted until 2026-09-20 04:07 UTC — a new entry does not bypass that; (b) the
LLM-scored categories below are inferred from positioning (no published benchmarks), so treat them as provisional.

### Proposed entry (for approval — NOT applied)

```yaml
  z-ai/glm-5.3-flashx:
    categories:
      technology_code/code_generation/python: 78
      technology_code/code_generation/javascript: 74
      technology_code/code_generation/shell: 72
      technology_code/data_interaction/file_based/json: 66
      technology_code/system_design/devops: 65
      technology_code/testing_debugging/error_analysis: 68
      complex_reasoning_agency/tool_use/code_execution: 75
      complex_reasoning_agency/self_correction/debugging: 70
      complex_reasoning_agency/multi_step_planning/task_decomposition: 64
    cost_tier: budget
    provider: zai
    enabled: true
    cost_per_1k_input: 0.00037
    cost_per_1k_output: 0.00125
```

*ID note:* the sync proposed `zai/glm-5.3-flashx` (provider-name prefix strips cleanly to the native API id
`glm-5.3-flashx`); the existing catalog convention for Z.AI-direct entries is `z-ai/…` (`z-ai/glm-5`,
`z-ai/glm-5-turbo`). Either works; the block above follows the existing `z-ai/` convention. OpenRouter wiring
(`openrouter/z-ai/glm-5.3-flashx`) is **not** recommended — OR exposes exactly one endpoint (Z.AI itself), so it
adds fees with no redundancy.

If approved: add to `chimera.yaml`, `cp` to `chimera.yaml.example` + `chimera.yaml.docker`, restart the unit,
`curl /v1/models` for 43, then live-smoke the new stage (after zai quota resets 09-20 04:07 UTC).

---

## 3. `--score` top-5 (carried queue — all already seen, none new this week)

The `--score` path deliberately pulls its top-5 from **all** candidates (not just the diff), so previously-seen
gaps stay reachable. All five below are in the seen file and unchanged from prior weeks' assessments:

| Model | Released | $/MTok in/out | Status |
|---|---|---|---|
| `openai/gpt-6-astra` | 09-04 | $10 / $50 | Verified live on OR (earlier runs); premium flagship — user decision pending |
| `google/gemini-3.8-flash` | 09-02 | $0.75 / $3.75 | OR + google rows; note the standing pitfall: gemini-3.x are Vertex/OR-only, direct `v1beta` 404s |
| `meta/muse-spark-1.3` | 09-02 | $1.25 / $4.25 | OR + native meta rows; no mistral/meta credential in this deployment |
| `deepseek/deepseek-flash` | 09-10 | $0.15 / $0.60 | **Not a new model** — same flash product under current DeepSeek naming (API accepts `deepseek-flash` / `deepseek-v4-pro`); already represented by `deepseek/deepseek-v4-flash` catalog entries |
| `zhipuai/glm-5.3-flashx` | 09-18 | $0.37 / $1.25 | Today's candidate — see §2 |

---

## 4. Deployment state (measured this tick)

- `/health` → `{"status":"alive","uptime_models":42,"commit":"ff952d9"}`; local HEAD = **51b7359** → **deploy drift**:
  the running service predates today's stand-in PM cycle commit. `sudo systemctl restart chimera` needed to load it
  (then `/health` must show `51b7359`).
- Live smoke test: **PASS** (formation=simple, merged answer returned), **8/9 providers healthy**.
- `zai` unhealthy: weekly quota exhausted (err 1310 class), resets **2026-09-20 04:07:32 UTC** — known weekly-cap
  behavior, self-heals; plan lanes already chain around it.

---

## 5. Action items

1. **Bane decision:** approve adding `z-ai/glm-5.3-flashx` (§2) — recommended; budget tier, 1M ctx, fastest Z.AI
   serving tier. Not added without approval per the recommend-only mandate.
2. On approval: apply the entry + sync both derived configs + restart + verify `/v1/models` count 43 + smoke.
3. **Restart the service** to clear the `ff952d9` → `51b7359` deploy drift (independent of item 1).
4. No catalog action on the other four scored models (§3) — no credentials / duplicates / prior decisions stand.
