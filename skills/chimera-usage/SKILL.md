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
2. **A failed deliberation still returns HTTP 200** with the error text as
   assistant content — an OpenAI-compat contract violation. Check content for
   `[stage ... unavailable` before trusting a 200. (Task: dogfood-error-200-as-success)
3. **`/v1/health` lies.** It can report all providers down while real calls
   succeed (probe uses different params/creds). Don't kill the service on it.
   (Task: dogfood-health-lies)
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
11. **`/v1/chat/completions` silently substitutes models**: unknown `model`
    → HTTP 200 answered by a DIFFERENT model (17k tokens billed). If you
    request a specific model, verify the response is really from it — or use
    `/v1/deliberate` (validates → 400) until fixed. (Task CH-GAP-027)
12. **Use `chimera-mcp` (standalone), NOT `chimera mcp`** — the subcommand
    crashes with `FileNotFoundError: 'mcp'` (argv bug). (Task CH-GAP-028)
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

### Stale pitfalls from earlier runs (verify before trusting)

- Pitfall #2 ("failed deliberation returns HTTP 200 with error text") and #3
  ("/v1/health lies") could NOT be reproduced on 2026-08-23: health is honest
  7/7, unknown model 404s, unknown formation 422s, and HEAD server.py has no
  `[stage ... unavailable` serialization path. Treat #2/#3 as historical
  until the foreman re-verifies them (Task CH-GAP-043).
- Pitfall #12 ("use `chimera-mcp`, NOT `chimera mcp`") is FIXED in HEAD —
  `chimera mcp` handshake verified working 2026-08-23 (CH-GAP-028).
- Pitfall #6 (`source=fallback`): observed on 1 of 2 auto runs 2026-08-23 —
  more common than "rare"; retry once (Task CH-GAP-044).

### Verified-still-true (2026-08-23)

- Pitfalls #1 (creds — the supervised service has full creds; 7/7 healthy),
  #4 (lock_aggregator), #7 (first call slow), #8 (cost floor ~$0.003).
- Custom DAG via library: `engine.deliberate(prompt, formation="custom",
  dag=..., allow_custom_dag=True)` works and returns excellent results —
  but a 3-stage sequential DAG took **4m15s** wall. Budget minutes.
