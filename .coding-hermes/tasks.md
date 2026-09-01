
## Dogfood Findings (2026-09-01)
Verdict: PROMISING-BUT-ROUGH
Promise: {"entry_point":"CLI binary `chimera` (chimera.cli.main:main; subcommands run/serve/mcp/formations/models) + HTTP server `chimera serve` on :8765 (OpenAI-compatible POST /v1/chat/completions, POST /v1/deliberate, /v1/models, /v1/formations, /docs, /web/ UI, health probes) + `chimera-mcp` stdio MCP se

- [P0] chimera-mcp is unusable for real clients — tools/list and tools/call always fail — After a full MCP stdio initialize handshake, tools/list and tools/call return -32602 'Invalid request parameters' every time; only initialize works, so no agent can discover or invoke any tool. This i
- [P1] Documented minimum setup is misleading and triggers unconfigured-provider guardrails — With only DEEPSEEK_API_KEY set (the README minimum), formation=auto still selects openrouter/qwen/qwen3.7-plus, producing model_blocked_guardrail warnings and a 300s cooldown on a provider the user ne
- [P1] CLI output is polluted and `chimera models` is unreadable — loguru debug/info lines interleave with the answer box — bare `chimera "<prompt>"` spews per-stage debug logs to stdout — and the rich table in `chimera models` truncates columns to 2-3 chars ('mo… pr
- [P2] smoke_live.py prints an alarming but harmless 'providers unhealthy' warning — On first run with absent keys it warns 'providers reported unhealthy: anthropic, openrouter, zai' yet still exits 0 and passes. Undocumented (keys are optional; the message reads like a failure), unde
- [P2] Plain `chimera run` emits truncated and duplicated warnings — A truncated litellm warning ('No endpoints available matching your guardrail restrictions and data polic...') plus a duplicated 'dispatch repaired: repaired: injected aggregator stage(s)' message appe
