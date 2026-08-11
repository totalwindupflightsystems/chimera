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

| Entry | Command / tool | Verdict (2026-08-03) |
|---|---|---|
| **MCP** (for agents) | `chimera_deliberate(prompt=..., formation="auto")` | ✅ best path — full trace, works |
| **CLI** | `chimera run "prompt"` (or `-v` for trace) | ✅ works, boxed trace table |
| **REST** | `POST :8765/v1/deliberate` / `/v1/chat/completions` | 🔴 broken on this deployment — server has no provider creds (see Pitfalls) |
| Web UI | `http://localhost:8765/web/` | served; SSE session-based |

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

### REST (only after fixing the creds issue — see Pitfall 1)

```bash
curl -X POST http://127.0.0.1:8765/v1/deliberate \
  -H 'Content-Type: application/json' \
  -d '{"prompt": "Your prompt", "formation": "auto"}'
# NOTE: body uses "prompt" (string), NOT OpenAI-style "messages" — that 422s.
```

## Pitfalls (all hit for real)

1. **The REST server may have zero provider credentials.** Symptom: every
   request returns HTTP 200 whose content starts `[stage aggregator ... 
   unavailable: ... Missing credentials ...]`. The MCP/CLI load the repo
   `.env`; `serve` may not. Fix: `set -a; source .env; set +a; chimera serve`,
   then verify `curl /v1/health/ready` == ready. (Task: dogfood-http-server-no-creds)
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
- For agent use, prefer MCP over REST (creds + contract issues are MCP-immune).
- For deterministic pipelines, use custom DAGs + `formation="custom"` and pin
  models you know the account can reach.
- Keep prompts small unless you need the multi-model depth — each worker call
  costs money and the dispatcher always pays the catalog-token tax.
