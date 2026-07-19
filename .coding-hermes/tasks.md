# Chimera v2 — Task List

## Open

## [ ] DEPS-1 — Upgrade pydantic_core 2.46.4 → 2.47.0 ⚠️ BLOCKED: pydantic 2.13.4 (latest) enforces strict 1:1 coupling with pydantic-core (==2.46.4). Core 2.47.0 (May 2026) requires a future pydantic release. Monitor pydantic>=2.14 for compatibility. (2026-07-14: foreman investigated, blocked)

## Completed

## [x] DEPS-4 — Batch upgrade 37 outdated packages (2026-07-19 tick: 31 project deps upgraded. Two pip resolver warnings non-blocking — pygount/chardet, litellm/importlib-metadata — all imports verified. 431/431 tests, guard PASS, pip-audit 0 project vulns. pydantic_core pinned at 2.46.4 per DEPS-1.)

**Priority:** low
**Detected:** 2026-07-19 discovery sweep — 37 packages outdated
**Files:** pyproject.toml, .venv/
**ACs:**
- All 37 packages upgraded to latest compatible versions
- pip-audit passes (0 vulns in project deps)
- 431/431 tests still pass
- Guard (secrets, lint) passes
- pydantic_core stays at 2.46.4 (pinned per DEPS-1)

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

**Found:** CI run 29428743098 — `test_deliberate_simple_formation` fails with HTTP 400
**Root cause:** `DeliberationResult.answer: str` (`engine.py:91`) strictly requires string.
**Pre-existing:** Yes — CI flakiness present since before the 2 root-cause fixes (2026-07-15).

## [x] CI — Fix integration tests: structured output wrapped in envelope (2026-07-15: fixed in `6d1d331`)

## [x] DOC — Update docs/specs port references from 8000 to 8765 (2026-07-15: commit e44bbaf, 6 files)
## [x] CI — Integration test flakiness: 2 root causes fixed (2026-07-15: commits 36697a5 + ce8ee36)
## [x] DEPS-3 — Upgrade gitreins 0.8.2 → 0.10.2 (2026-07-15: 0.10.2 already installed)
## [x] CONFIG — align chimera.yaml server port from 8000 to 8765 (2026-07-14)
## [x] CI — fix ruff I001 import sort (2026-07-14)
## [x] Speed formation — "fast" deliberation formation with budget models (2026-07-12)
## [x] Validation-as-code — Stage 0 emits JSON Schema, Audit validates mechanically (2026-07-12)
## [x] MCP server progressive prompting (2026-07-12)
## [x] models.dev provider refresh — cache TTL tighter (2026-07-12)
## [x] Fix model sync cron (2026-07-12)
## [x] Add GPT-5.6 family + Grok 4.5 LLM-refined scores (2026-07-12)
## [x] Aggregator saturates on large panel outputs — deep reconciliation
## [x] Worker parallelism — stages configured as parallel
## [x] Closed iteration loop — Audit "fail" re-triggers
## [x] Fix models.dev cache — stale cache fallback
## [x] Wire progressive prompting
## [x] Pricing accuracy — all 31/31 models have real per-model pricing
## [x] spec-writer formation
## [x] Progressive prompting config fields in Stage model
## [x] Timeout hierarchy
## [x] 6 new OpenRouter models (31 total)
## [x] Per-model enable/disable toggle
## [x] Cost-weighted selection
## [x] Provider auto-discovery via models.dev
## [x] MCP noise fix
## [x] DEPS-2 — Upgrade gitreins 0.7.9 → 0.10.2 (2026-07-14)
## [x] INFRA — Add Hilo .vfs/ gitignore entries (2026-07-14)
## [x] Update pip deps — aiohttp, anyio, aiohappyeyeballs (2026-07-18)
