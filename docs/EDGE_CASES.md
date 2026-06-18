# Edge Case Handling — Chimera v2

> Based on GPT-5.5 external audit, June 2026.
> Status: ✅ = implemented and tested, 📋 = documented for future

## C1 — Concurrent Request Safety ✅

**Risk:** Multiple simultaneous deliberations on one Engine instance could leak state (stage results, traces, budget tracking).

**Resolution:**
- `Engine` now validates unique `request_id` per deliberation
- Stage results are keyed by `stage_id` within each deliberation dict — no cross-request leakage
- `test_concurrency.py` covers: 2, 10, 20, and 50 concurrent deliberations with state isolation assertions

**Reproduction:**
```python
results = await asyncio.gather(*[engine.deliberate(p, "auto") for p in prompts])
assert all(r.answer for r in results)  # all complete independently
```

## C2 — Partial Worker Failure Recovery ✅

**Risk:** If 1 of 3 workers fails, the aggregator receives incomplete inputs and may produce silently corrupted output.

**Resolution:**
- `StageResult.degraded` flag marks failed worker outputs
- Aggregator `build_merge_prompt()` labels degraded workers with `[DEGRADED]` prefix
- WARNING `aggregator_partial_inputs` logged with counts (total_deps, degraded, healthy)
- Tests: 1-of-3 fails → completes with valid output; 2-of-3 → appropriate degraded response; 3-of-3 → clear error

## C3 — Token Limit Exceeded Mid-DAG ✅

**Risk:** A model hits its `max_tokens` limit mid-response, producing truncated dispatcher plans or partial worker reasoning without error indication.

**Resolution:**
- `GatewayResponse.finish_reason` field captures provider's finish reason
- `_build_response()` logs WARNING `token_limit_reached` with model + token counts when `finish_reason == "length"`
- `GatewayResponse.is_empty` flag helps downstream code detect truncation

## C4 — Empty/Null Model Responses ✅

**Risk:** Models may return empty strings, null content, missing `choices`, or `finish_reason="stop"` with zero-length output — crashing response extraction.

**Resolution:**
- `_extract_text()` handles all variants: empty choices, null content, missing message, whitespace-only
- Sets `is_empty=True` on `GatewayResponse` instead of raising exceptions
- Tests cover: empty content, null content, missing choices, stop-with-empty, reasoning fallback

## C5 — Mixed Provider Availability 📋

**Risk:** One provider is down while others work. Entire deliberation fails when it could degrade gracefully.

**Status:** Documented, not yet implemented. Planned approach:
- Dispatcher model unavailable → fallback to next-best model
- Worker model unavailable mid-DAG → mark stage degraded, continue with remaining workers
- Aggregator unavailable → return best available partial result with warning

## C6 — Deeply Nested DAG Cycles 📋

**Risk:** Self-referencing nodes, indirect cycles through aggregators, depth > 10 causing stack overflow.

**Status:** Documented, not yet implemented. Cycle detection exists for basic cases but may miss indirect cycles through multi-level aggregator chains. Planned: full topological sort with cycle detection before execution.

## C7 — Budget Exhaustion Errors ✅

**Risk:** Provider returns quota/billing errors that are not surfaced clearly to the user or operator.

**Resolution:**
- `BudgetExhaustedError` exception class in `src/chimera/exceptions.py`
- Gateway detects keywords: `insufficient_quota`, `billing`, `payment required`, `quota exceeded`
- Logs CRITICAL with model, provider, and error details
- Engine catches and propagates to API layer

## C8 — Config Immutability During Requests ✅

**Risk:** Config file modified while requests are in-flight → model catalog changes mid-DAG, causing stale references or inconsistent scoring.

**Resolution:**
- `Engine.__init__()` deep-copies config via `model_copy(deep=True)`
- Frozen snapshot stored as `_config` for all in-flight requests
- `_check_config_mutation()` called at start of each `deliberate()` — hashes original object against stored checksum
- WARNING `config_mutated_after_snapshot` logged if external mutation detected
- Tests: modify config after Engine init → snapshot unchanged; delete model from live config → snapshot intact; mutation triggers warning
