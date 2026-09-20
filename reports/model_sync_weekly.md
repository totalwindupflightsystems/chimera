# Chimera Model Sync — Weekly Report

**Date:** 2026-09-20 (cron run 17:00 UTC / 12:00 local −05)
**Run:** `scripts/model_sync_cron.py` → `model_sync.py --diff --output reports/latest.md`. Auto-score step **not reached** (diff = 0, wrapper short-circuits).
**Diff result:** **0 new candidates** across 13 core providers — `reports/latest.md` reads "Candidates: 0 new models across 13 providers".
**Cache:** hit, age ~496 s, `stale=False` — 222 provider blocks / 7,085 discovery models across 12 recognised providers.
**`.seen_models.json`:** **217 entries**, unchanged from the 09-19 run.
**Catalog:** **42 models**, all `enabled: true`; `chimera.yaml` **untouched** by this run (recommend-only mandate).
**Archive:** the pre-run file was byte-identical to `model_sync_weekly_20260919_archive.md`; a copy was verified with `diff -q` before overwrite, so no text is lost. (Last week's 09-18 report had already been lost by the pre-overwrite path; this run checked first.)

---

## 1. Diff honesty check (seen-file trap) — honest, 0 is real

The scan + seen/catalog loaders were re-run **without** `--diff` (`/tmp/_diag_scan.py`):

| Check | Result |
|---|---|
| Core providers scanned | 13 |
| In-scope candidates (full scan, no `--diff`) | **172** (171 on 09-19) |
| Candidates **not** in `.seen_models.json` | **0** |
| Seen-file size | 217 entries (was 217) → no writes |
| Catalog models filtered before the seen filter | 42 |

**Conclusion:** the 0-candidate diff is real and complete *for the scan's own scope*.
Nothing new landed in `openai / anthropic / deepseek / google / xai / mistral / moonshotai /
minimax / alibaba / zhipuai / meta / stepfun / xiaomi` since 09-19.

**⚠️ But "0 new models" is NOT the honest headline this week — the scope is the problem.**
A genuine frontier release shipped today and the scan is structurally unable to see it (§2).

---

## 2. The real finding: StepFun **Step-5 Preview** shipped 2026-09-20 and the sync cannot see it

| Field | Value |
|---|---|
| What it is | StepFun's new flagship: **600B/27B sparse MoE** (27B active), 92-layer narrow-deep stack, **1M-token context**, native text+image+video input, reasoning + tool use. Aimed at coding, long-document work and long-horizon agents |
| Announced / released | **2026-09-18** (StepFun announcement) / cache + press **2026-09-20**; open weights promised **Oct 15** |
| Pricing | **$1.00 / $2.70 per MTok**, cache read $0.05 (Artificial Analysis, myclaw, StepFun rate card) |
| Benchmark | **AA Intelligence Index 44** — press positions it "global top 25" at ~1/5 the price of comparable frontiers |
| Native API | **LIVE** — `GET https://api.stepfun.ai/v1/models` (with `STEPFUN_API_KEY`) → **HTTP 200**, 16 models, `step-5-preview` present: `enable_vision_input: true`, `enable_reason: true`, `max_input_tokens: 1024000`, protocols `chat, messages, responses` |
| Provider announcement | **Yes** — StepFun's own platform docs + Pandaily, Intelligent Living, runtimewire, myclaw, Artificial Analysis |
| OpenRouter page | **NO** — `GET /api/v1/models` (446 models) lists only `stepfun/step-3.7-flash` and `stepfun/step-3.5-flash`; `…/models/stepfun/step-5-preview/endpoints` → **HTTP 404**. Not on OR yet |
| models.dev **core** `stepfun` row | **ABSENT** — still only `step-1-32k, step-2-16k, step-3.5-flash, step-3.5-flash-2603, step-3.7-flash, step-tts-2, stepaudio-2.5-*`. Verified in the on-disk cache **and** on a fresh `urllib` fetch of `models.dev/api.json` (222 providers) |
| Where it IS in models.dev | Only `nano-gpt/stepfun/step-5-preview` and `vercel/stepfun/step-5-preview` — **both outside `CORE_PROVIDERS`** |

**Why the sync reports 0:** `scripts/model_sync.py` iterates exactly `CORE_PROVIDERS`
(13 ids) and resolves each row to a chimera id. A release whose only models.dev rows sit
under a **reseller/aggregator** id is never a candidate — the model is not filtered out, it
is never *seen*. Resolution check: `nano-gpt + step-5-preview → "nano-gpt/step-5-preview"`,
which is neither a catalog key nor a native lab id, so widening `CORE_PROVIDERS` naively
would produce junk ids rather than the model.

**Blind-spot scale (measured, not estimated):** **39 model ids** with `release_date ≥ 2026-09-10`
exist *only* in non-core rows — `step-5-preview`, `ternary-bonsai-2-27b`, `pareto`,
`qwen3.8-omni-flash`, `fugu-max`, `fugu-ultra-v2`, `gpt-{astra,sol,luna,terra}-latest`,
`schematron-v2-small/-turbo`, `arrow-2`, `arrow-2-telos`, `qwen3.8-27b-cybersecurity`, ….
The 09-17 report already recorded the sibling case (`sakana/fugu-max`, 09-11, verified live on
OpenRouter) as *"a sync-scope decision is needed to ever see it."* **That decision is now overdue.**

**Verdict: DO NOT ADD yet — the account cannot serve it.**
The deployment holds `STEPFUN_API_KEY` and `GET /v1/models` succeeds, but **every chat call
returns HTTP 402** `{"type":"quota_exceeded","message":"You exceeded your current quota,
please check your plan and billing details"}`, reproduced on **three** models
(`step-3.5-flash`, `step-3.7-flash`, `step-5-preview`) — so it is **account-wide, not
model-specific**, and not an invalid key. Endpoint gotcha recorded: the same key against
`https://api.stepfun.com/v1` (China) returns **HTTP 401 `Incorrect API key provided`** — the
China and Global endpoints are **not interchangeable**.

→ Filed as **DF-CHIMERA-V2-26** (scan blind spot) and **DF-CHIMERA-V2-28** (route + quota).

---

## 3. Carried candidate from 09-19: `z-ai/glm-5.3-flashx` — now BLOCKED for a new reason

The 09-19 report recommended adding this and named its only caveat as the zai weekly quota
(reset 2026-09-20 04:07 UTC). **Measured today, after the reset:**

```
zai glm-5.3-flashx → HTTP 429 {"error":{"code":"1311",
   "message":"Your current subscription plan does not yet include access to GLM-5.3-FlashX"}}
zai glm-5.3-flash  → HTTP 200 in 4.1 s   (control: provider is healthy, key is valid)
```

The quota reset; the entitlement did not arrive. **The recommendation is downgraded to
"hold"** — it is not addable on this subscription, regardless of the YAML patch. It remains
"recommended when/if the plan gains the model". (The unit is otherwise healthy: the deployed
service is at HEAD and `/v1/health` shows zai healthy on `zai-coding-plan/glm-5.2`.)

---

## 4. Deployment drift found and FIXED this tick

The tick opened with the supervised service **stale**: `/health` reported `commit 69acfb4`
while local HEAD was `6fcfbb1` — **15 commits behind**, i.e. `Restart=always` had not
recovered the drift. Two of those commits are security-relevant, so this was not cosmetic:

- **Verified live pre-restart:** `POST /web/debug/reset` → **HTTP 200 `{"status":"ok"}`** on a
  **`0.0.0.0`-bound** server. That endpoint rebinds the global session manager and SSE
  broadcaster — **one anonymous request wipes every live session**. The fix (`796d396`, now
  deployed) gates it on `CHIMERA_WEB_DEBUG_RESET`.
- The same window carried the private-host leak gate, the stage-observer SSE fix and the
  `/web` queue/rate-limit parity fix.

**After restart:** `/health` → `commit 6fcfbb1` == `git rev-parse --short HEAD`.
**Re-verified:** `POST /web/debug/reset` → **HTTP 404 `{"detail":"Not found"}`** ✅.
**Smoke:** `scripts/smoke_live.py --formation simple` → **SMOKE PASS**, merged answer returned
(request `fb43b06cd08e4d25`), exit 0, `providers: 6/9 healthy`.

---

## 5. Second finding: the `hermes` provider can never pass the health probe

`/v1/health` reports `status: degraded` with `hermes: {healthy: false, error: "timeout: no
response within 10.0s"}` on every probe. The gateway is demonstrably alive — but the gate is
**structural**, not load:

| Probe | Result |
|---|---|
| `GET 127.0.0.1:8642/v1/models` (same key) | **HTTP 200 in 0.33 s** — alive |
| `POST :8642/v1/chat/completions` `{max_tokens: 1}` | **HTTP 200 after 108.3 s**, `prompt_tokens=43599` |
| Same call, second attempt | still running at **300 s** |
| **Control**: same model direct against `api.z.ai` | **HTTP 200 in 1.9 s**, `prompt_tokens=13` |
| `server.health_timeout_s` (live config) | **10.0 s** |

The gateway **injects its own ~43.6k-token agent system prompt**, so the provider's floor
latency is ~100 s+ against a 10 s budget — no realistic `health_timeout_s` fixes it without
turning the probe into a hanging request for every other provider. DF-CHIMERA-V2-17's
cold-start grace (default 1.0 s) cannot cover a 100 s floor. Effect: the documented health
contract can never be satisfied while `hermes` is configured, and a **real** hermes outage is
indistinguishable from the standing condition.

→ Filed as **DF-CHIMERA-V2-27**.

---

## 6. `--score` top-5 (carried queue — none new this week)

The `--score` path pulls its top-5 from **all** candidates, so previously-seen gaps stay
reachable; the wrapper skipped it this run because the diff was empty. Queue unchanged:

| Model | Released | $/MTok in/out | Status |
|---|---|---|---|
| `zhipuai/glm-5.3-flashx` | 09-18 | $0.37 / $1.25 | **BLOCKED** — plan entitlement missing (§3) |
| `openai/gpt-6-astra` | 09-04 | $10 / $50 | Verified live on OR (earlier runs); premium flagship — user decision pending |
| `google/gemini-3.8-flash` | 09-02 | $0.75 / $3.75 | OR + google rows; standing pitfall: gemini-3.x are Vertex/OR-only, direct `v1beta` 404s |
| `meta/muse-spark-1.3` | 09-02 | $1.25 / $4.25 | OR + native meta rows; no mistral/meta credential in this deployment |
| `deepseek/deepseek-flash` | 09-10 | $0.15 / $0.60 | **Not a new model** — same flash product under current DeepSeek naming; already represented |

---

## 7. Carried minor findings (status re-measured, not assumed)

1. **Three-YAML drift — now measured by parse, not grep.** Line counts 1580 / 1649 / 1376
   (`chimera.yaml` / `.example` / `.docker`); model keys **42 / 43 / 36**.
   - `.example` has 1 extra: `cliproxy/deepseek,deepseek-v4-flash` (documented example entry) — **intentional**.
   - `.docker` is missing **6** catalog entries: `hermes/glm-5.3-flash`, `router9/ds/deepseek-v4-flash`,
     `router9/ds/deepseek-v4-pro`, `router9/mmx/MiniMax-M3`, `router9/openrouter/x-ai/grok-4.6`,
     `router9/xai/grok-4` — **real drift** (the `router9` + `hermes` provider families never propagated).
   - `server.health_timeout_s` is in the live file (10.0) and **absent from both** derived configs.
   - *Correction to prior reports:* the 09-17 archive claimed `health_timeout_s` present in `.example` — a
     grep count of 1 there is a **comment/other match**; a real YAML parse reads `None`. Grep counts on
     these files are not evidence; parse them.
2. **Stale cron docstring** — `scripts/model_sync_cron.py:1` still says *"Mondays 12:00 CT"*; observed
   cadence is **daily 12:00 local**. Two-line fix, unfixed since 09-14.
3. **`DF-CHIMERA-V2-13`** (AGENTS.md describes model-sync auto-scoring as "when `DEEPSEEK_API_KEY` is
   set") — still `pending`; the dotenv fallback has been live since 09-17. One-line docs fix.

---

## 8. Deployment state (measured this tick, post-restart)

- `/v1/health` → `status: degraded`, `commit 6fcfbb1` == local HEAD ✅
  `providers_configured: 7`, `providers_discovered: [openai, xai]` (discovery-only phantoms, correctly
  reported as `healthy: false` + note after CH-GAP-053).
- Healthy and probed: `anthropic` (claude-opus-4.8), `google` (gemini-3.1-pro-preview), `openrouter`
  (qwen/qwen3.7-max), `router9` (ds/deepseek-v4-flash), `deepseek` (deepseek-v4-flash), `zai`
  (zai-coding-plan/glm-5.2). Unhealthy: `hermes` (timeout, §5), `openai`/`xai` (no models configured).
  `smoke_live.py` renders **6/9** counting only model-tested entries.
- `GET /v1/models` == **42** == `load_config().models`; all `enabled: true`.
- **zai weekly quota: recovered** (429 code 1310 gone; 1311 entitlement error is model-specific, §3).
- `chimera.yaml` mtime unchanged by this run.

---

## 9. Action items

1. **Bane decision — the sync-scope question is now blocking real value.** Approve one of:
   (a) reseller/aggregator watch list + native cross-check, (b) native lab API scanning, or
   (c) a mandatory named "blind spot" section in every weekly report. **DF-CHIMERA-V2-26.**
2. **Bane decision — StepFun billing.** The native account is quota-exhausted (402) while a
   600B frontier model ships on it. Top up → then route natively; or leave it unused. **DF-CHIMERA-V2-28.**
3. **`z-ai/glm-5.3-flashx`: HOLD** (§3) — the 09-19 recommendation is not actionable on this plan.
4. **`hermes` provider health** — approve per-provider probe control or a liveness-only probe. **DF-CHIMERA-V2-27.**
5. **Deploy drift** — done this tick; the running service now matches HEAD. The pattern (15 commits of
   drift, including an open destructive endpoint) argues for the foreman's existing `/health`-vs-HEAD
   audit to *restart*, not just report.
6. Carried docs fixes: cron docstring (§7.2), `DF-CHIMERA-V2-13` (§7.3), `.docker` model drift (§7.1).

---

## 10. Findings filed as board rows this run

Per Bane's ops doctrine (findings become rows on the owning project, not report prose only):

| Row | Priority | Finding |
|---|---|---|
| **DF-CHIMERA-V2-26** | P2 | Sync blind spot: a release whose only models.dev rows are reseller/aggregator ids is invisible — `step-5-preview` is the proof; 39 such ids measured since 09-10 |
| **DF-CHIMERA-V2-27** | P2 | `hermes` can never pass the `/v1/health` probe — 43.6k-token injected prompt, 108 s measured floor vs 10 s budget |
| **DF-CHIMERA-V2-28** | P3 | StepFun routed via OpenRouter while a native `STEPFUN_API_KEY` exists — and the native account 402s account-wide (policy-gated on billing) |

Board delta: **194 → 197 rows**, appended via `~/.hermes/scripts/board_append.py`
(`APPENDED=3 PRIOR=194 TOTAL=197`), one object per physical line, file ends with exactly one
newline. `DF-CHIMERA-V2-25` was not modified by this run (its `pending → in_progress` flip in
the working tree is the live foreman's 11:54 dispatch).
