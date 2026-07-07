# Chimera v2 — Task List

## Open

- [ ] Closed iteration loop — Audit says "fail" but Refine doesn't re-trigger. Wire re-iteration.
- [ ] Aggregator saturates on large panel outputs — deep reconciliation from GPT-5.5 audit.
- [ ] Worker parallelism — stages configured as parallel still run sequentially in dispatch layer.

## Completed

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
