---
name: chimera-usage
description: >-
  How to actually USE the Chimera multi-model deliberation gateway (CLI, MCP,
  REST). Entry points, working recipes, common failure modes and their fixes.
  Load this before running any deliberation. Written from the 2026-08-03
  dogfood run — everything here was executed for real.
version: 1.0.0
category: software-development
---

# Chimera Usage — Field-Tested Recipes

Chimera = one prompt → dispatcher designs a DAG of scoped LLM worker tasks →
workers run in parallel → aggregator merges with dispatcher-written
instructions → one answer + a full trace (per-stage model/tokens/cost).

## Entry points (fastest → slowest)

| Entry | Command / tool | Verdict (2026-08-20 re-verified) |
|---|---|---|
| **MCP** (for agents) | `chimera_deliberate(prompt=..., formation="auto")` | ✅ best path — full trace, works |
| **CLI** | `chimera run "prompt"` (or `-v` for trace) | ✅ works, boxed trace table |
| **REST** | `POST :8765/v1/deliberate` / `/v1/chat/completions` | ✅ works — live-verified 2026-08-20: `/v1/health` healthy (7/7 providers), `/v1/health/ready` 200, real deliberation answered |
| Web UI | `http://localhost:8765/web/` | ✅ served (HTTP 200); SSE session-based |

## Working recipes

### MCP (agent integration) — the flagship

```python
# auto formation: dispatcher designs the whole deliberation
r = chimera_deliberate(prompt="Compare X and Y for use case Z", formation="auto")
answer = r["answer"]          # merged answer
r["trace"]["total_cost"]      # ~$0.003–0.02 per small run
r["trace"]["source"]          # "auto" = dispatcher designed it; "fallback" = degraded

# custom DAG: you define structure, dispatcher writes the prompts
r = chimera_deliberate(
    prompt="...",
    formation="custom",
    allow_custom_dag=True,
    dag={"stages": [
        {"id": "researcher", "kind": "worker",     "model": "deepseek/deepseek-v4-flash", "depends_on": []},
        {"id": "critic",     "kind": "aggregator", "model": "deepseek/deepseek-v4-flash", "depends_on": ["researcher"]},
        {"id": "final",      "kind": "aggregator", "model": "deepseek/deepseek-v4-flash", "depends_on": ["critic"]},
    ], "edges": [["researcher","critic"], ["critic","final"]]},
)
```

### CLI

```bash
cd <path-to-chimera-v2>   # .env must be here and in the process env
chimera run "Your prompt"
chimera -v run "Your prompt"    # trace table: stage | model | tokens | latency | cost
chimera formations              # simple, debate, audit, speed, spec-writer, auto
chimera serve                   # REST + web UI on :8765
```

### REST (verified working 2026-08-20)

```bash
curl -X POST http://127.0.0.1:8765/v1/deliberate \
  -H 'Content-Type: application/json' \
  -d '{"prompt": "Your prompt", "formation": "auto"}'
# NOTE: body uses "prompt" (string), NOT OpenAI-style "messages" — that 422s.
```

## Pitfalls (all hit for real)

1. **REST creds issue — RESOLVED on this deployment (2026-08-20).** The old
   failure mode was: every request returns HTTP 200 whose content starts
   `[stage aggregator ... unavailable: ... Missing credentials ...]` because
   `serve` didn't load the repo `.env` (the MCP/CLI did). Current deployment
   runs `chimera serve` as a supervised service with full creds —
   `/v1/health` = healthy (7/7 providers), `/v1/health/ready` = ready. If a
   fresh manual `serve` ever shows the symptom again: `set -a; source .env;
   set +a; chimera serve`, then verify `curl /v1/health/ready` == ready.
   (Historical task: dogfood-http-server-no-creds; CH-GAP-037 re-verified)
2. **Failed deliberation → HTTP 502 (RESOLVED 2026-08-23).** The old failure
   mode (HTTP 200 with `[stage ... unavailable` error text as assistant
   content) is gone: `server.py` raises `_NoUsableAnswerError` when
   `result.answer_degraded` and the handler returns 502 with an
   OpenAI-compatible structured error body (both `/v1/deliberate` and
   `/v1/chat/completions`). Re-verified live 2026-08-23: unknown model →
   404 `model_not_found`, unknown formation → 422; no 200-with-bracketed-error
   path remains. (Tasks: dogfood-error-200-as-success, CH-GAP-043)
3. **`/v1/health` lies — RESOLVED 2026-08-23.** The old failure mode (health
   reporting all providers down while real calls succeed) is fixed: probes
   now run real per-provider LLM pings with the same creds/params as the
   engine. Re-verified live 2026-08-23: `/v1/health` = healthy 7/7 with
   per-provider `model_tested` in details. If it reads `degraded`, that is a
   REAL signal now (transient under concurrent probes — re-probe
   sequentially 2-3× before escalating). (Tasks: dogfood-health-lies,
   CH-GAP-043)
4. **`lock_aggregator: true` silently beats request overrides.** Set
   `aggregator_model` in the request and it will be ignored if config locks
   the aggregator. Read chimera.yaml first. (Task: dogfood-lock-aggregator-silent-override)
5. **OpenRouter 404 `No endpoints available matching your guardrail
   restrictions`** = the account's privacy settings block that model; the
   dispatcher may keep picking it. The engine degrades to a partial merge —
   usable but check `trace` for dropped workers. (Task: dogfood-model-guardrail-404)
6. **`source=fallback`** in the trace means the dispatcher's DAG was
   malformed (e.g. missing the aggregator stage) and a single-worker preset
   was used instead. Retry; usually dispatches cleanly. (Task: dogfood-dispatcher-malformed-dag-fallback)
7. **First CLI call is slow** (~30–60s): it refreshes the LiteLLM provider
   catalog (5309 models). Later calls hit the cache (~2–20s).
8. **Cost floor ~$0.003** — the dispatcher call carries the full model catalog
   in context (~17k input tokens). Per-run totals: $0.003–0.02 for small prompts.

## The "right way" patterns

- Always read `trace.source` and `trace.workers` before trusting an answer.
- For agent use, prefer MCP over REST (MCP handles creds/contract details for you).
- For deterministic pipelines, use custom DAGs + `formation="custom"` and pin
  models you know the account can reach.
- Keep prompts small unless you need the multi-model depth — each worker call
  costs money and the dispatcher always pays the catalog-token tax.

---

## Update 2026-08-13 (second dogfood run) — what changed

The engine-level P0s from run 1 are FIXED in current code (verified by real
use): `/v1/health` reports honestly (real probe calls, `healthy` with 12/12
providers), `/health` alias works, `/v1/deliberate` returns proper 400s, full
suite 648 passed / 62 skipped in 17.5s. **But three NEW traps, all hit for
real:**

### New pitfalls (2026-08-13)

9. **Port squatting on :8765 — RESOLVED.** A stale root-owned `chimera serve`
   (PID 21212, started Aug 2, pre-fix code) used to squat :8765 on this
   machine: `chimera serve` → "address already in use"; every curl on :8765
   returned HTTP 200 whose content starts `[stage aggregator ... unavailable:
   ... Missing credentials ...]`. That zombie was killed and the port is now
   owned by the supervised service (verified healthy 2026-08-20). Keep the
   habit anyway: `ss -tlnp | grep 8765` + `ps -o lstart -p <pid>` before
   trusting the port; test on `--port 8790`+ if a stranger owns it.
   (Task CH-GAP-025; CH-GAP-037 re-verified)
10. **Bare `pip install chimera-deliberation` then the README Python snippet
    crashes**: `from chimera import Engine` → `ModuleNotFoundError: fastapi`
    (web routes imported unconditionally). Must install `[full]`. (Task
    CH-GAP-026)
11. **`/v1/chat/completions` silently substitutes models — RESOLVED
    2026-08-23.** Unknown `model` → HTTP 404 `model_not_found` with a
    structured OpenAI-style error (re-verified live 2026-08-23); no silent
    substitution remains. (Task CH-GAP-027)
12. **Use `chimera-mcp` (standalone), NOT `chimera mcp` — FIXED in HEAD
    (2026-08-23).** The subcommand crashed with `FileNotFoundError: 'mcp'`
    (argv bug, CH-GAP-028); the handshake now works via `chimera mcp` too —
    the standalone entry point remains preferred for agent use. (Task
    CH-GAP-028)
13. **Custom DAGs go to `/v1/chat/completions` with `model:"custom"`** —
    `/v1/deliberate` rejects `formation:"custom"` with a bare 422. (Task
    CH-GAP-029)
14. **`result.trace` is a pydantic `DeliberationTrace`** — use
    `model_dump()`, not dict access.

### Updated "right way" patterns

- Server: verify port ownership first; the supervised deployment on :8765 is
  healthy (7/7 providers, live-verified 2026-08-20).
- Library consumers: always `pip install "chimera-deliberation[full]"`.
- Agent integration: MCP still best (standalone `chimera-mcp`).
- Check `trace.source` and per-stage entries; `source=auto` = dispatcher
  designed the DAG.

---

## Update 2026-08-23 (third dogfood run) — what changed

Re-ran everything for real against HEAD wheel (486a409) + live :8765.

### New pitfalls (all hit for real)

15. **The live :8765 service runs STALE code.** systemd `chimera.service` has
    been up since 2026-08-14 14:53; every fix merged after that (stream 400,
    max_tokens, port default) is NOT in the running process. Live symptoms on
    :8765: `stream:true` → 200 non-stream full completion; `max_tokens:1` →
    3548-token essay. HEAD code behaves correctly — the deployed process
    doesn't. **Always check `systemctl show chimera -p ActiveEnterTimestamp`
    before trusting live behavior; restart the unit to get HEAD.** (Task
    CH-GAP-039)
16. **PyPI 0.2.0 (Jul 19) is the July product.** `pip install
    chimera-deliberation` → `from chimera import Engine` →
    `ModuleNotFoundError: fastapi` (CH-GAP-026 fix never shipped). Install
    from a HEAD-built wheel or wait for 0.2.1. (Task CH-GAP-040)
17. **Bare install's console scripts crash**: `chimera --help` after bare
    install → `ModuleNotFoundError: rich` (click/rich/mcp are extras-only but
    the entry points ship in the base package). Always install `[full]`.
    (Task CH-GAP-041)
18. **README.md ends with a literal `# test comment`** — ignore it; it's a
    leftover artifact. (Task CH-GAP-042)

### Stale pitfalls from earlier runs — re-verified 2026-08-23 (CH-GAP-043)

- Pitfall #2 ("failed deliberation returns HTTP 200 with error text") —
  **RESOLVED**: 502 structured error now (verified above).
- Pitfall #3 ("/v1/health lies") — **RESOLVED**: health honest 7/7 with
  per-provider `model_tested` (verified above).
- Pitfall #12 ("use `chimera-mcp`, NOT `chimera mcp`") — **FIXED in HEAD**:
  `chimera mcp` handshake verified working 2026-08-23 (CH-GAP-028).
- Pitfall #11 (silent model substitution) — **RESOLVED**: 404
  `model_not_found` live-verified 2026-08-23 (CH-GAP-027).
- Pitfall #6 (`source=fallback`): observed on 1 of 2 auto runs 2026-08-23 —
  still true; more common than "rare"; retry once (Task CH-GAP-044).
- Pitfall #5 (OpenRouter guardrail 404): not re-hit 2026-08-23, but it is an
  account-setting failure mode, not a code bug — keep as-is (Task
  dogfood-model-guardrail-404).
- Pitfall #9 (port squatting): supervised service owns :8765, unit active —
  habit (ss/ps check) still recommended (CH-GAP-025/037).
- Pitfall #10 (bare install fastapi crash): FIXED at HEAD (CH-GAP-026 lazy
  import) but STILL TRUE for PyPI 0.2.0 (Jul 19) — install from a HEAD-built
  wheel until 0.2.1 publishes (Task CH-GAP-040).
- Pitfall #13 (custom DAGs only via `/v1/chat/completions` model:"custom"):
  still true 2026-08-23 — deliberate rejects formation custom with 422
  (live-verified; CH-GAP-029).
- Pitfall #14 (`result.trace` is a pydantic `DeliberationTrace`): still true
  2026-08-23 — use `model_dump()`, not dict access.

### Verified-still-true (2026-08-23)

- Pitfalls #1 (creds — the supervised service has full creds; 7/7 healthy),
  #4 (lock_aggregator), #7 (first call slow), #8 (cost floor ~$0.003).
- Custom DAG via library: `engine.deliberate(prompt, formation="custom",
  dag=..., allow_custom_dag=True)` works and returns excellent results —
  but a 3-stage sequential DAG took **4m15s** wall. Budget minutes.
