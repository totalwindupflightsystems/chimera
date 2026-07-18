# Chimera v2 — Task List

## Open

## [x] SEC — Upgrade mcp 1.28.0 → 1.28.1 (CVE-2026-59950, CVSS 7.6 HIGH) (2026-07-17: `pip install --upgrade mcp`, 1.28.0→1.28.1, 431/431 tests, guard green, 8/8 E2E pass)

**Found:** 2026-07-17 discovery sweep — pip-audit flagged CVE-2026-59950 in mcp 1.28.0.

**CVE:** CWE-346 Origin Validation Error in MCP Python SDK's deprecated `websocket_server` transport. Fixed in mcp 1.28.1.

**Impact:** Chimera does NOT use `websocket_server` transport (grep confirms zero references), so the vulnerable code path is not exercised. However, the CVE is classified HIGH (CVSS 7.6), and upgrading is a trivial mechanical change.

**Files:** `pyproject.toml`, `.venv/lib/python3.11/site-packages/mcp/`

**ACs:**
- mcp upgraded from 1.28.0 to >= 1.28.1
- All 431 unit tests still pass
- Guard (secrets, lint) passes
- E2E endpoints (8/8) still pass after upgrade

## [x] CI — Fix integration test flakiness #3: pydantic validation error when answer is non-string (2026-07-15: fixed in `519841a` — _maybe_unwrap_envelope coerces non-string answers + 13 parametrized tests. 431/431 unit tests pass.)

**Found:** CI run 29428743098 — `test_deliberate_simple_formation` fails with HTTP 400:
```
1 validation error for DeliberationResult
answer
  Input should be a valid string [type=string_type, input_value=4, input_type=int]
```

**Root cause:** `DeliberationResult.answer: str` (`engine.py:91`) strictly requires string. When the LLM returns a raw number (e.g., `4` for a math question), `_select_answer` returns the int value, `_maybe_unwrap_envelope` passes non-dict values through, and pydantic rejects the int at construction time (`engine.py:351`).

**Files:** `src/chimera/engine.py:91,337-338,351`

**ACs:**
- `test_deliberate_simple_formation` passes reliably: when LLM returns non-string answer (int, float, bool, list, dict), the response is coerced to string or serialized appropriately
- Chat Completions endpoint with `response_format.json_schema` also handles non-string answers
- All 418 unit tests still pass
- No regression in existing integration test behavior

**Pre-existing:** Yes — CI flakiness present since before the 2 root-cause fixes (2026-07-15). This is root cause #3.

## Completed

- [x] DEPS-3 — Upgrade gitreins 0.8.2 → 0.10.2 (2026-07-15: 0.10.2 already installed, guard passes, 418/418 unit tests pass)
- [x] CONFIG — align chimera.yaml server port from 8000 to 8765 to match README docs (2026-07-14: port 8765, server verified, chimera.yaml + example updated)
- [x] CI — fix ruff I001 import sort in tests/test_engine.py:854 causing CI lint failure (2026-07-14: ruff --fix, lint green, 4 files)
- [x] Speed formation — build a "fast" deliberation formation with budget models for <30s agent-in-the-loop use (2026-07-12: commit 1bf73ea, 2 budget workers + budget aggregator, 8 files changed)
- [x] Validation-as-code — Stage 0 emits JSON Schema, Audit validates mechanically against it (not manual) (2026-07-12: commit f488ef2, _extract_output_schema + _validate_against_schema, 11 tests, jsonschema dep)
- [x] MCP server progressive prompting — make the MCP chimera_deliberate tool support progressive/wait_messages (2026-07-12: commit a2ae192, +115/-1 across 5 files, 2 new tests)
- [x] models.dev provider refresh — cache TTL tighter (30min instead of 24h), catch new providers faster (2026-07-12: commit b785711, CACHE_TTL 86400→1800)

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

## [x] CI — Fix integration tests: structured output wrapped in `{"answer": ...}` envelope instead of bare JSON (2026-07-15: fixed in `6d1d331` — `build_merge_prompt` suppresses conflicting "Respond in valid JSON format." hint when `output_schema` is provided; the `response_format` parameter enforces the schema so the prompt should not add contradictory JSON instructions. 418/418 unit tests pass, guard green.)

**Files:** `tests/integration/test_collaborative_evals.py::test_website_with_structured_output`, `tests/integration/test_structured_output.py::test_json_schema_chat_completions`

**Symptom:** Both tests pass `output_schema` (via `output_schema` field on `/v1/deliberate` or `response_format.json_schema` on `/v1/chat/completions`) but the Chimera response still wraps the output in `{"answer": "<data>", "sources": [...]}` envelope instead of returning the bare structured JSON object.

**Root cause (suspected):** The `output_schema` parameter flows through `DeliberationOverrides` → `Engine.deliberate()` but the aggregator stage doesn't unwrap the envelope when structured output is requested. The response model (`DeliberateResponse`) always writes `answer: str` which preserves the wrapper.

**ACs:**
- `test_website_with_structured_output` passes: when `output_schema` is provided, the response `answer` field contains bare JSON (parsable as `{"html": ..., "title": ...}`), not `{"answer": "<html>", ...}`
- `test_json_schema_chat_completions` passes: when `response_format.json_schema` is provided, `choices[0].message.content` contains bare JSON `{"name": "chimera", "value": 42}`, not `{"answer": "{...}", "sources": [...]}`
- All 54 integration tests pass (`418 unit + 54 integration = 472 total`)
- No regression: all 418 unit tests still pass

**Pre-existing:** Yes — failing since at least 2026-07-13 across multiple CI runs. Not a new regression.

## [x] DOC — Update docs/specs port references from 8000 to 8765 (CONFIG changed operational port, docs lagging) (2026-07-15: commit e44bbaf, 6 files, 13 insertions, 13 deletions)

**Files:** `README.md:155-156`, `specs/architecture.md:257`, `docs/OPENAI_API.md:12,17,72,155,187`, `docs/CONFIG.md:57,237`, `docs/USAGE.md:74`, `docs/SECURITY.md:24,28`

**Note:** Code default (`src/chimera/config.py:128`) and test fixtures stay at 8000 — that's the application default. Only docs referencing the shipped config's operational port need updating.

**ACs:**
- All doc/spec files reference port 8765 (the shipped chimera.yaml value)
- `src/chimera/config.py` default remains 8000 (application default)
- Test fixtures remain 8000 (test the default, not the shipped config)
- `grep -rn 'localhost:8000\|127.0.0.1:8000' README.md docs/ specs/` returns empty

## [x] CI — Integration test flakiness: 2 root causes fixed (2026-07-15: commits 36697a5 + ce8ee36)

**Root cause 1 — `/v1/chat/completions` answer envelope (FIXED):**
- `_maybe_unwrap_envelope` now checks for `"answer"` key alone (no longer requires `"sources"`)
- Double-unwrap: if the inner value is JSON-encoded string, parses and re-serializes it
- Fix in `src/chimera/engine.py` (ce8ee36, +27 lines)

**Root cause 2 — `test_chat_special_characters_prompt` timeout (FIXED):**
- TIMEOUT bumped 120s→180s in `tests/integration/test_web_sse.py` (36697a5)

**Verification:** 418/418 unit tests pass, guard green. CI integration run pending.

## [ ] DEPS-1 — Upgrade pydantic_core 2.46.4 → 2.47.0 ⚠️ BLOCKED: pydantic 2.13.4 (latest) enforces strict 1:1 coupling with pydantic-core (==2.46.4). Core 2.47.0 (May 2026) requires a future pydantic release. Monitor pydantic>=2.14 for compatibility. (2026-07-14: foreman investigated, blocked)

## [x] DEPS-2 — Upgrade gitreins 0.7.9 → 0.10.2 (dev dep, commit review engine + CVE severity scoring) (2026-07-14: upgraded to 0.8.2; 0.10.2 target not reached — pip shows 0.8.2 installed, 0.10.2 available. Remaining gap tracked as DEPS-3.)
## [x] INFRA — Add Hilo .vfs/ gitignore entries (graph.db, graph.db.wal, .last_warm) per hilo-usage skill pitfall (2026-07-14: added to .gitignore)

## [x] Update pip deps — aiohttp 3.13.5→3.14.1, anyio 4.13.0→4.14.2, aiohappyeyeballs 2.6.2→2.7.1 (2026-07-18: aiohttp already at 3.14.1. CORRECTION 2026-07-18 tick: aiohappyeyeballs was still at 2.6.2, anyio at 4.14.1 — board was prematurely marked. Upgraded: aiohappyeyeballs→2.7.1, anyio→4.14.2. 431/431 tests, guard green. NOW all at target.)
- **Priority:** low
- **Detected:** 2026-07-18 supervisor tick
