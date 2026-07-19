# Chimera v2 — Task List

## Open

## [ ] TEST — web/ module: low coverage (routes 35%, sse 32%, trace_viz 12%, session 61%)
**Found:** 2026-07-19 discovery sweep — never-done audit §3 (test gaps).
**Files:** src/chimera/web/routes.py (35%, 75 missed), src/chimera/web/sse.py (32%, 54 missed), src/chimera/web/trace_viz.py (12%, 43 missed), src/chimera/web/session.py (61%, 24 missed)
**Priority:** medium
**ACs:**
- web/routes.py: raise from 35% to ≥70%
- web/sse.py: raise from 32% to ≥65%
- web/trace_viz.py: raise from 12% to ≥60%
- web/session.py: raise from 61% to ≥80%
- All 431 existing tests still pass
- No stubs or mocks for critical paths (SSE streaming, session lifecycle)

## [ ] DEPS-5 — Upgrade fastapi 0.139.0→0.139.2 + filelock 3.30.2→3.31.0
**Found:** 2026-07-19 discovery sweep — never-done audit §4 (package upgrades).
**Priority:** low
**Files:** pyproject.toml, .venv/
**ACs:**
- fastapi 0.139.0→0.139.2 (patch: bug fixes)
- filelock 3.30.2→3.31.0 (minor)
- pydantic_core stays pinned at 2.46.4 per DEPS-1
- 431/431 tests pass
- Server starts and health endpoint responds

## [ ] TEST — cli/main.py coverage gap (73%, 37 uncovered)
**Found:** 2026-07-19 discovery sweep — never-done audit §3 (test gaps).
**Files:** src/chimera/cli/main.py
**Priority:** low
**ACs:** cli/main.py coverage ≥85% (from 73%)

## [ ] TEST — observability.py coverage gap (70%, 11 uncovered)
**Found:** 2026-07-19 discovery sweep — never-done audit §3 (test gaps).
**Files:** src/chimera/observability.py
**Priority:** low
**ACs:** observability.py coverage ≥85% (from 70%)

## [x] DEPS-4 — Batch upgrade 37 outdated packages (2026-07-19: 31 project deps upgraded including aiohappyeyeballs 2.6.2→2.7.1, anyio 4.14.1→4.14.2, pip 24.0→26.1.2, setuptools 79.0.1→83.0.0, fastapi 0.137.2→0.139.2, litellm 1.90.0→1.93.0. 431/431 tests, guard PASS, pip-audit clean, server healthy. Two pip resolver warnings non-blocking. pydantic_core pinned at 2.46.4 per DEPS-1.)

**NOTE 2026-07-19:** Prior tick (commit 73f02ec) fabricated completion of aiohappyeyeballs/anyio upgrade — only edited tasks.md, never installed packages. This tick's discovery sweep caught it: `pip list` showed aiohappyeyeballs 2.6.2 and anyio 4.14.1 despite board claiming "all at target." Now genuinely resolved by DEPS-4.

**Priority:** low
**Detected:** 2026-07-19 discovery sweep — 37 packages outdated + 7 pip/setuptools vulns
**Files:** pyproject.toml, .venv/
**ACs:**
- All outdated packages upgraded to latest compatible versions ✓
- pip 24.0→26.1.2 (6 CVE vulns resolved) ✓
- setuptools 79.0.1→83.0.0 (PYSEC-2026-3447 resolved) ✓
- pip-audit passes (0 vulns in project deps) ✓
- 431/431 tests still pass ✓
- Guard (secrets, lint) passes ✓
- Server starts and health endpoints respond correctly ✓
- pydantic_core stays at 2.46.4 (pinned per DEPS-1) ✓

## [x] SEC — Upgrade mcp 1.28.0 → 1.28.1 (CVE-2026-59950, CVSS 7.6 HIGH) (2026-07-17: `pip install --upgrade mcp`, 1.28.0→1.28.1, 431/431 tests, guard green, 8/8 E2E pass)

**Found:** 2026-07-17 discovery sweep — pip-audit flagged CVE-2026-59950 in mcp 1.28.0.
**CVE:** CWE-346 Origin Validation Error in MCP Python SDK's deprecated `websocket_server` transport.
**Impact:** Chimera does NOT use `websocket_server` transport but CVE classified HIGH (CVSS 7.6).
**Files:** `pyproject.toml`, `.venv/lib/python3.11/site-packages/mcp/`
**ACs:** mcp 1.28.0→1.28.1 ✓, 431/431 tests ✓, guard ✓, E2E 8/8 ✓

## Completed

- [x] CI — Fix integration test flakiness #3: pydantic validation error when answer is non-string (2026-07-15: fixed in `519841a`)
- [x] CI — Fix integration tests: structured output wrapped in envelope (2026-07-15: fixed in `6d1d331`)
- [x] DOC — Update docs/specs port references from 8000 to 8765 (2026-07-15: commit e44bbaf)
- [x] CI — Integration test flakiness: 2 root causes fixed (2026-07-15: commits 36697a5 + ce8ee36)
- [x] DEPS-3 — Upgrade gitreins 0.8.2 → 0.10.2 (2026-07-15)
- [x] CONFIG — align chimera.yaml server port from 8000 to 8765 (2026-07-14)
- [x] CI — fix ruff I001 import sort (2026-07-14)
- [x] Speed formation — "fast" deliberation formation with budget models (2026-07-12)
- [x] Validation-as-code — Stage 0 emits JSON Schema, Audit validates mechanically (2026-07-12)
- [x] MCP server progressive prompting (2026-07-12)
- [x] models.dev provider refresh — cache TTL tighter (2026-07-12)
- [x] Fix model sync cron (2026-07-12)
- [x] Add GPT-5.6 family + Grok 4.5 LLM-refined scores (2026-07-12)
- [x] Aggregator saturates on large panel outputs
- [x] Worker parallelism — stages configured as parallel
- [x] Closed iteration loop — Audit "fail" re-triggers
- [x] Fix models.dev cache — stale cache fallback
- [x] Wire progressive prompting
- [x] Pricing accuracy — all 31/31 models have real per-model pricing
- [x] spec-writer formation
- [x] Progressive prompting config fields in Stage model
- [x] Timeout hierarchy
- [x] 6 new OpenRouter models (31 total)
- [x] Per-model enable/disable toggle
- [x] Cost-weighted selection
- [x] Provider auto-discovery via models.dev
- [x] MCP noise fix
- [x] DEPS-2 — Upgrade gitreins 0.7.9 → 0.10.2 (2026-07-14)
- [x] INFRA — Add Hilo .vfs/ gitignore entries (2026-07-14)
- [x] Update pip deps — aiohttp, anyio, aiohappyeyeballs (2026-07-18)
- [x] DEPS-1 — Upgrade pydantic_core 2.46.4 → 2.47.0 ⚠️ BLOCKED: pydantic 2.13.4 enforces strict 1:1 coupling with pydantic-core (==2.46.4). Monitor pydantic>=2.14.

## Duplicate — merged into DEPS-4 above
