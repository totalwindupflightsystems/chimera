
## Dogfood Findings (2026-09-01)
Verdict: PROMISING-BUT-ROUGH
Promise: {"entry_point":"CLI binary `chimera` (chimera.cli.main:main; subcommands run/serve/mcp/formations/models) + HTTP server `chimera serve` on :8765 (OpenAI-compatible POST /v1/chat/completions, POST /v1/deliberate, /v1/models, /v1/formations, /docs, /web/ UI, health probes) + `chimera-mcp` stdio MCP se

- [P0] chimera-mcp is unusable for real clients — tools/list and tools/call always fail — After a full MCP stdio initialize handshake, tools/list and tools/call return -32602 'Invalid request parameters' every time; only initialize works, so no agent can discover or invoke any tool. This i
- [P1] Documented minimum setup is misleading and triggers unconfigured-provider guardrails — With only DEEPSEEK_API_KEY set (the README minimum), formation=auto still selects openrouter/qwen/qwen3.7-plus, producing model_blocked_guardrail warnings and a 300s cooldown on a provider the user ne
- [P1] CLI output is polluted and `chimera models` is unreadable — loguru debug/info lines interleave with the answer box — bare `chimera "<prompt>"` spews per-stage debug logs to stdout — and the rich table in `chimera models` truncates columns to 2-3 chars ('mo… pr
- [P2] smoke_live.py prints an alarming but harmless 'providers unhealthy' warning — On first run with absent keys it warns 'providers reported unhealthy: anthropic, openrouter, zai' yet still exits 0 and passes. Undocumented (keys are optional; the message reads like a failure), unde
- [P2] Plain `chimera run` emits truncated and duplicated warnings — A truncated litellm warning ('No endpoints available matching your guardrail restrictions and data polic...') plus a duplicated 'dispatch repaired: repaired: injected aggregator stage(s)' message appe

## Dogfood Findings (2026-09-04)
Verdict: PROMISING-BUT-ROUGH
Promise: {"entry_point":"CLI binary `chimera` (entry point chimera.cli.main:main) with subcommands run/serve/models/formations/config, plus `chimera-mcp` (chimera.mcp.server:run) for MCP stdio; the `chimera serve` subcommand starts a FastAPI HTTP server (default :8765) exposing POST /v1/chat/completions (OpenAI-compatible)"}

- [P0] chimera-mcp is unusable by any real MCP client — stdout log pollution breaks JSON-RPC framing — loguru log lines are written to stdout, so the initialize response arrives after log lines and every MCP client fails at parse; this kills the advertised 'MCP tools for agents' surface aimed at the stated primary user (AI agents like Hermes/Claude Code)
- [P1] Default formation=auto routes workers to unconfigured/guardrail-blocked openrouter providers, causing worker failures and 300s cooldowns — With only DEEPSEEK_API_KEY set (the documented minimum), auto formation picked gpt-5.6-luna and qwen3.7-plus/max on a key that blocks them; worker failed with 300s cooldown and degraded aggregation in BOTH CLI and SDK runs
- [P1] Config friction: ${ENV_VAR} key substitution with no .env auto-load and no documentation — README says 'add DEEPSEEK_API_KEY' but chimera.yaml uses ${ENV_VAR} substitution that requires manual export/sourcing; the tester had to source ~/.hermes/.env by hand (which even printed a spurious 'Agent: command not found')
- [P2] CLI/UX rough edges: no --version, truncated tables, log interleaving, unexplained degraded health — `chimera --version` fails with 'No such option'; `chimera models` truncates every column to ~3 chars; `chimera formations` is dominated by a huge spec-writer DAG JSON blob; loguru debug lines and litellm 'Provider List' spam interleave with the answer box
- [P2] Silent internal repair of dispatcher errors undermines trace trust — Dispatcher emitted a DAG missing the aggregator edge; engine silently repaired it (dispatch_repaired_missing_edge_targets) with no user-facing notice — a user inspecting the returned trace cannot tell the DAG was repaired
