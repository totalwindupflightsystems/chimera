# Chimera Dogfood Log

## 2026-08-03 — 🟡 PROMISING-BUT-ROUGH

**Promise:** "One API call. A team of models. One answer." — a multi-model
deliberation gateway where one dispatcher call designs a DAG of scoped
worker prompts, workers run in parallel, and an aggregator merges them with
dispatcher-written instructions. Entry points: CLI, REST API (OpenAI-compat),
MCP server for agents, web UI.

**Reality:** The core engine is real and works — 4 real deliberations run
across MCP + CLI + REST. The MCP path (what Hermes agents use) is excellent:
auto formation produced a real 2-worker + aggregator DAG with a genuinely
merged answer, and custom DAGs execute exactly as specified. The CLI works
with a nice boxed trace. BUT the REST server on :8765 runs with no provider
credentials — every deliberation fails with "Missing credentials" and the API
returns HTTP 200 with the error text as the "answer". `/v1/health` reports
all providers down while the same models work via CLI/MCP (false negatives).

**Top 3 findings:**
1. P0 `dogfood-http-server-no-creds` — `chimera serve` has no creds; README curl quickstart is dead.
2. P0 `dogfood-error-200-as-success` — failed deliberations return 200 + error-string as assistant content.
3. P1 `dogfood-health-lies` — health/ready claims "no providers reachable" while providers demonstrably work.

**Time-to-first-success:** ~15 min from start (docs reading + first MCP
deliberation; the call itself took 69s wall). **Friction count:** 9.

**Verdict:** PROMISING-BUT-ROUGH. Value is real (multi-model deliberation
with honest traces, ~$0.003–0.02/call), usability is the blocker (dead HTTP
deployment, lying health endpoint, silent override precedence).

**Board:** 8 tasks added (2 P0, 3 P1, 3 P2) via DuckDB board v2.1. Foreman
cooldown dropped 43200s → 900s to work them.
