# Chimera v2 — Task List

## Open

- [ ] Speed formation — build a "fast" deliberation formation with budget models for <30s agent-in-the-loop use
- [ ] Validation-as-code — Stage 0 emits JSON Schema, Audit validates mechanically against it (not manual)
- [ ] MCP server progressive prompting — make the MCP chimera_deliberate tool support progressive/wait_messages
- [ ] models.dev provider refresh — cache TTL tighter (30min instead of 24h), catch new providers faster

## Completed

- [x] Fix model sync cron — clear stale seen_models.json, verify daily sync finds new models, pipe results to foreman (2026-07-12: deleted stale reports/.seen_models.json, sync verified 0 new models across 13 providers, 5/5 verification)
- [x] Add GPT-5.6 family + Grok 4.5 LLM-refined scores (95 adjustments, commit b7ca553, 2026-07-12)
- [x] Aggregator saturates on large panel outputs — deep reconciliation from GPT-5.5 audit. (token-aware truncation + config option)
- [x] Worker parallelism — stages configured as parallel still run sequentially in dispatch layer. (acompletion + create_task waves + overlap tests)
- [x] Closed iteration loop — Audit says "fail" but Refine doesn't re-trigger. Wire re-iteration. (d6c1d10)
- [x] Fix models.dev cache — _load_cache now supports ignore_ttl=True, fetch-failure fallback uses stale cache. (ae82f57)
- [x] Wire progressive prompting — parse_dispatch_result now passes through progressive/wait_messages/trigger fields. (2b6d5d1)
- [x] Pricing accuracy — all 31/31 models now have real per-model pricing from models.dev via provider_discovery.
- [x] spec-writer formation (STRUCTURE → WRITE×2 → MERGE → AUDIT → REFINE)
- [x] Progressive prompting config fields in Stage model
- [x] Timeout hierarchy (code → admin → request header)
- [x] 6 new OpenRouter models (31 total)
- [x] Per-model enable/disable toggle
- [x] Cost-weighted selection (price_sensitivity)
- [x] Provider auto-discovery via models.dev
- [x] OpenRouter API key for cross-provider testing
- [x] MCP noise fix (structlog WARNING filter + stderr)
