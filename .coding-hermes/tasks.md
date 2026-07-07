# Chimera v2 — Task List

## Open

- [x] Fix models.dev cache — provider discovery returns 0 models/providers. Fixed: _load_cache now supports ignore_ttl=True, fetch-failure fallback uses stale cache instead of returning empty. (ae82f57)
- [x] Wire progressive prompting — Stage.progressive/wait_messages/trigger fields are configured in YAML but not used by dispatcher/engine. Fixed: parse_dispatch_result now passes through progressive/wait_messages/trigger fields; engine already had progressive prompting logic. (2b6d5d1)
- [ ] Pricing accuracy — replace generic cost_tier averages with real per-model pricing from models.dev data.
- [ ] Closed iteration loop — Audit says "fail" but Refine doesn't re-trigger. Wire re-iteration.
- [ ] Aggregator saturates on large panel outputs — deep reconciliation from GPT-5.5 audit.
- [ ] Worker parallelism — stages configured as parallel still run sequentially in dispatch layer.

## Completed

- [x] spec-writer formation (STRUCTURE → WRITE×2 → MERGE → AUDIT → REFINE)
- [x] Progressive prompting config fields in Stage model
- [x] Timeout hierarchy (code → admin → request header)
- [x] 6 new OpenRouter models (31 total)
- [x] Per-model enable/disable toggle
- [x] Cost-weighted selection (price_sensitivity)
- [x] Provider auto-discovery via models.dev
- [x] OpenRouter API key for cross-provider testing
- [x] MCP noise fix (structlog WARNING filter + stderr)
