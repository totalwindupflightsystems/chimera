# Chimera Model Sync — Weekly Report

**Run:** 2026-11-23 17:00 UTC (sync at 12:00 local / 17:00 UTC)
**Scope:** 13 core providers + reseller watch (kilo, llmgateway, nano-gpt, openrouter, vercel) + 22 task-router lanes
**Headline:** **4 verified core candidates (3 from core labs + 1 lane-carried promotion) + 1 rejected candidate with a skip-logic fix shipped.** All four have provider announcements and live OpenRouter pages. No catalog file was touched — additions await approval. DeepSeek auto-scoring ran on all 5.

| Artifact | Path / value |
|---|---|
| Sync report | `reports/latest.md` (`reports/latest_20261123_1200.md`) — 4 new models + 4 basename skips |
| Auto-scores | `reports/model_scores_20261123_1200.yaml` (5 models, 22-25 paths each) |
| Diff candidates (raw) | `/mnt/ssd/tmp/chimera-model-sync-diff-2984197.json` |
| Tooling fix | commit `68dee0c` — voxtral name-pattern skip; pushed origin+github, parity OK |
| Live service | `:8765` → `status=alive`, `uptime_models=48`, `commit=0eb9232`, `version=0.3.0` |
| Deploy parity | **STALE** — running `0eb9232` is an ancestor of HEAD `68dee0c`; material diff NON-EMPTY: `src/chimera/engine.py`, `pyproject.toml`, `scripts/model_sync.py`, `tests/test_release_workflow.py`. **Deferral recorded (see §4).** |
| Ledger | `.seen_models.json` 531 keys (11-07: 511) vs `uptime_models=48` — `--diff: 0` remains a novelty signal, not a currency check |

---

## 1. Candidates found and verified

| # | Candidate | Proposed ID | Announced | OpenRouter | Pricing | Verdict |
|---|---|---|---|---|---|---|
| 1 | Gemini 4 Neon | `google/gemini-4-neon` | ✅ Google blog, **Nov 18** | ✅ `google/gemini-4-neon` | $3/$15 per MTok, 1M ctx | **ADD** |
| 2 | GPT-6.2 Astra | `openrouter/openai/gpt-6.2-astra` | ✅ OpenAI, **Nov 17** (API-live) | ✅ `openai/gpt-6.2-astra` | $8/$40 per MTok, 1.05M ctx | **ADD** |
| 3 | GPT-6.2 Sol | `openrouter/openai/gpt-6.2-sol` | ✅ OpenAI, **Nov 17** (API-live) | ✅ `openai/gpt-6.2-sol` | $2/$10 per MTok | **ADD** |
| 4 | Qwen4-Max | `openrouter/qwen/qwen4-max` | ✅ Alibaba Group, **Nov 16** | ✅ `qwen/qwen4-max` | $1.5/$4.5 per MTok (OR page: $1.425/$4.275), 1M ctx | **ADD** (lane-carried core) |
| 5 | Voxtral Small 2507 | — | audio model, n/a | — | — | **REJECT** + skip fix shipped |

### 1.1 google/gemini-4-neon
Google's mid-tier between Carbon and Hydrogen; "frontier-level reasoning for high-frequency workflows faster and more cost efficiently" (blog.google + 9to5google, Nov 18). Live in Gemini API / AI Studio. OpenRouter page live, pricing matches the models.dev row exactly, 1,048,576-token context. No duplicate in catalog (catalog tops out at gemini-3.x).
- **Prefix:** native `google/gemini-4-neon`, matching the family convention. Caveat: Google's direct v1beta API 404s for gemini-3.x+ — if the provider-`google` health check fails, route via `openrouter/google/gemini-4-neon`.
- **Scores (cost_tier premium):** python 90, javascript 88, explanation 88, code_execution 86, error_analysis 86, task_decomposition 85.

### 1.2 openrouter/openai/gpt-6.2-astra
OpenAI flagship of the 6.2 pair ("Introducing GPT-6.2 Astra and Sol", Nov 17); available in ChatGPT Work, Codex **and the API** — first public model past OpenAI's own "High" self-improvement threshold. OpenRouter page live, pricing matches models.dev, 1.05M context.
- **Prefix:** `openrouter/openai/…`, matching how gpt-5.6/gpt-6.1 are admitted (`openrouter/openai/gpt-5.6*`, `openrouter/openai/gpt-6.1-sol`).
- **Scores (premium):** explanation 90, task_decomposition 88, python 88, debugging 86.

### 1.3 openrouter/openai/gpt-6.2-sol
Same release; OpenAI: within ~0.5 pt of Astra at max reasoning for ~1/5 the cost. OpenRouter page live, $2/$10.
- **Scores (premium):** explanation 90, logic_puzzle 88, algebra/statistics 86 — math/reasoning-tilted vs Astra's coding tilt.

### 1.4 openrouter/qwen/qwen4-max (lane `opencode-go` → promoted to alibaba core)
Qwen4-Max launched Nov 16, 2026 on QwenCloud (Alibaba Group announcement; new MoE, native vision, 1M context, "agent-first coding"). Per DF-CHIMERA-V2-67 the lane row resolves to Alibaba's own registry block, so it is promoted as a lane-carried core release. OpenRouter page `qwen/qwen4-max` live; models.dev $1.50/$4.50 vs OpenRouter page $1.425/$4.275 — use models.dev sticker, note OR's lower numbers. Distinct from catalog (`openrouter/qwen/qwen3.8-max-prime` is the newest qwen).
- **Scores (premium):** python 86, language_to_language 85, code_execution 84, javascript 84 — the only candidate this week with a strong translation column.

### 1.5 mistral/voxtral-small-2507 — REJECT, and the leak is FIXED
Audio-in speech/STT family, not a text deliberation candidate. It reached the core section because the committed voxtral guard sat in `SKIP_FAMILIES`, which `_is_chat_model` matches against models.dev's `family` field — absent on voxtral rows — while the name-matching arm (`SKIP_NAME_PATTERNS`) lacked the token.
- **Fix shipped:** commit `68dee0c` adds `"voxtral"` to `SKIP_NAME_PATTERNS` in `scripts/model_sync.py`. Verified: `_is_chat_model` rejects all voxtral ids, keeps every chat family (8/8 assertions); 80 model_sync tests green; guard secrets/lint/lsp/static_analysis clean (tests lane DEGRADED-skip — no test file in the diff; covered by the manual 80-test run); pushed to origin + github with parity.

## 2. Carry-forward queue (11-07 report, re-verified)

The 7-item queue from 10-25/10-30 is **still unapproved**; all remain live and price-current in today's cache. Highest-leverage picks under the "newest live generation" rule: `openai/gpt-6.1-terra`, `anthropic/claude-opus-5.5`, `google/gemini-4-argon`, `moonshotai/kimi-k3.1-pro`, `minimax/minimax-m3.1-flash` (also `openai/gpt-6.1-sol`, `mistralai/mistral-large-4-0`).

- Note: this week's gpt-6.2 release **supersedes** the `gpt-6.1-sol` queue slot — approve the 6.2 pair instead if the rule is applied strictly.

## 3. Standing breakage — `openrouter/openai/gpt-5.6` (day 24)

Still dangling: `chimera.yaml:387` carries `openrouter/openai/gpt-5.6`, but today's cache confirms `openai/gpt-5.6` is **ABSENT** upstream (only `-luna/-sol/-terra` + `-pro` tiers serve). Any stage pinned to the bare id 404s at call time. The sync's basename-skip line keeps calling it "already admitted" so the scanner will never surface it — must be fixed by hand: repoint to `openrouter/openai/gpt-5.6-sol` or drop the row.

## 4. Deploy parity — STALE, deferral recorded

Running `0eb9232` (ancestor of HEAD `68dee0c`) vs HEAD material diff under `src/ scripts/ tests/ pyproject.toml` is **non-empty**: `src/chimera/engine.py`, `pyproject.toml`, `scripts/model_sync.py`, `tests/test_release_workflow.py`. The engine.py + pyproject delta pre-dates this tick (this run's own commit touches only the sync script, which the service never imports) — the supervised process is running older code regardless of this run. **No reload was performed this tick** (cron context; a restart aborts every in-flight deliberation). A reload + post-restart `/health` commit check + `scripts/smoke_live.py` is owed before any "deployed" claim; until then the gap is named here, not written off.

## 5. Action items (approval required — nothing applied)

1. **APPROVE** this week's 4 adds: `google/gemini-4-neon`, `openrouter/openai/gpt-6.2-astra`, `openrouter/openai/gpt-6.2-sol`, `openrouter/qwen/qwen4-max` — scored entries ready in `reports/model_scores_20261123_1200.yaml` (re-key `chimera_id` to the prefixes in §3 table when integrating).
2. **DECIDE** the 2-generation carry-forward queue (§2) — or clear it in favor of the 6.2 pair.
3. **FIX** the dangling `openrouter/openai/gpt-5.6` row (§3) — day 24.
4. **RELOAD** the service (§4) — `sudo systemctl restart chimera`, `/health` must show the new commit, `scripts/smoke_live.py` exit 0. Overdue on `src/chimera/engine.py` alone.
5. **DECIDE** the `.seen_models.json` re-baseline (531 seen / 48 catalogued).

Approval sequence (unchanged): edit `chimera.yaml` → mirror `models:` section into `chimera.yaml.example` / `chimera.yaml.docker` (hand-mirrored, never wholesale-copied) → offline suite green → restart → `/v1/models` count → `smoke_live.py`.

---

*Source of record for this run: `reports/latest.md` + `reports/latest_20261123_1200.md`, `reports/model_scores_20261123_1200.yaml`, provider cache `~/.chimera/models-dev-cache.json`, live `/health` (commit `0eb9232`, 48 models), HEAD `68dee0c`. This run modified only `scripts/model_sync.py` (skip fix, committed `68dee0c`) and this report; no catalog or config template was touched.*
