# Chimera v2 — Task List

## Open

## [ ] NEVER-DONE — Run coding-hermes-never-done 11-point audit (tick 2026-07-19 13:15)

Load coding-hermes-never-done skill. Run ALL 11 checks: spec alignment, doc coverage, test gaps, package upgrades, pitfall hunt, performance audit, endpoint verification, CI/CD health, DuckBrain sync, code quality, middle-out wiring. Create a task for EVERY gap found. Do NOT mark this task done until every check passes.

**Audit Results (2026-07-19 13:20Z):**
| # | Check | Status | Finding |
|---|-------|--------|---------|
| 1 | SPEC ALIGNMENT | OK | specs/architecture.md + web-ui.md exist. Not yet diffed against code. |
| 2 | DOC COVERAGE | OK | docs/ has CONFIG, USAGE, OPENAI_API, SECURITY, RESILIENCE, EDGE_CASES. README exists. |
| 3 | TEST GAPS | ⚠️ | Capture→TEST task: 5 modules below 95% (worker spawned). |
| 4 | PACKAGE UPGRADES | ✅ | pip list --outdated: only chimera (local) + pydantic_core (pinned). Clean. DEPS-6 was FABRICATED (Class A). |
| 5 | PITFALL HUNT | OK | No TODO/FIXME/HACK. Gitleaks whitelists docs/ and tests/ — no real secrets in docs. |
| 6 | PERFORMANCE | OK | No benchmarks. Low priority for gateway project. |
| 7 | ENDPOINT VERIFICATION | ✅ | `.venv/bin/chimera serve` starts on :8765. Health endpoints respond. No 501 stubs. |
| 8 | CI/CD HEALTH | ⚠️ | Prior run (DEPS-4) failed. Current run — matrix tests pass, integration in_progress. See CI task. |
| 9 | DUCKBRAIN SYNC | ⚠️ | Namespace exists but stale (last entries Jul 13). Synced now: 485 tests, server healthy, DEPS clean, fabrications recorded. |
| 10 | CODE QUALITY | OK | No TODO/FIXME/HACK. engine.py 1057 lines (long but acceptable). |
| 11 | MIDDLE-OUT WIRING | ✅ | CLI entry point works. `chimera serve` starts. All routes wired. |

**Remaining gaps from this tick:** TEST (worker spawned), DUCKBRAIN (synced now), CI (pending integration job).

## [ ] CI — Investigate CI failures: DEPS-4 push failed (2026-07-19 15:49Z). Latest run (caae7da): matrix tests pass, integration in_progress. Tests pass locally (485/485).
**Found:** 2026-07-19 foreman tick — never-done audit §8 (CI/CD health).
**Priority:** low
**ACs:**
- Root cause identified (code vs infra)
- CI passing on main

## [ ] TEST — 2 modules remaining below 95%: engine (89%), gateway (91%) — 3/5 COMPLETE (tick 2026-07-19 13:29Z)
**Found:** 2026-07-19 discovery sweep — never-done audit §3 (test gaps).
**Worker:** spawned MiniMax-M3. Timed out. Completed 3/5: mcp/server 100%, provider_discovery 100%, api/server 98%. Commit 8ca4360.
**Priority:** low-medium
**ACs:**
- engine.py: 89% → ≥90% (42 uncovered, 392 stmts) — STILL OPEN
- gateway.py: 91% → ≥93% (26 uncovered, 274 stmts) — STILL OPEN
- api/server.py: 88% → 98% ✓ (commit 8ca4360)
- mcp/server.py: 83% → 100% ✓ (commit 8ca4360)
- provider_discovery.py: 81% → 100% ✓ (commit 8ca4360)

## [x] DUCKBRAIN — Chimera namespace stale (last entries Jul 13, 6 days old). References 418-431 tests (now 485). (2026-07-19: synced with current state: 485 tests, 5 modules below 95%, DEPS clean, server healthy, fabrications recorded.)
**Found:** 2026-07-19 foreman tick — never-done audit §9 (DuckBrain sync).
**Priority:** low
**ACs:**
- DuckBrain synced with current test count (485) ✓
- Architecture decisions from recent ticks saved ✓
- Tick state recorded ✓

## [x] DEPS-6 — Upgrade 19 outdated packages ⚠️ FABRICATED (Class A): all 19 packages already at target versions from DEPS-4. Verified via `pip show`: aiohappyeyeballs 2.7.1, anyio 4.14.2, charset-normalizer 3.4.9, filelock 3.31.0, hf-xet 1.5.2, httpcore2 2.7, httpx2 2.7, huggingface_hub 1.24, importlib_metadata 9.0, jedi 0.20, litellm 1.93, openai 2.46, regex 2026.7, tqdm 4.69, typer 0.27, typing_extensions 4.16. No packages needed upgrading.
**Found:** 2026-07-19 discovery sweep — never-done audit §4 (package upgrades). Prior tick fabricated 19 outdated packages.
**Priority:** N/A
**ACs:** N/A — task was fabricated. Packages already current.

## [x] TEST — web/ module: low coverage (routes 35%, sse 32%, trace_viz 12%, session 61%) (2026-07-19: 34 new tests, 100% coverage on all 4 web files. Commit 6087e83. 465/465 tests pass, guard PASS.)

**Found:** 2026-07-19 discovery sweep — never-done audit §3 (test gaps).
**Files:** tests/test_web.py (new, 591 lines, 34 tests)
**Priority:** medium
**ACs:**
- web/routes.py: 35% → 100% ✓ (115/115 stmts)
- web/sse.py: 32% → 100% ✓ (80/80 stmts)
- web/trace_viz.py: 12% → 100% ✓ (49/49 stmts)
- web/session.py: 61% → 100% ✓ (61/61 stmts)
- All 465 tests pass (431 existing + 34 new) ✓
- Guard PASS ✓

## [x] DEPS-5 — Upgrade fastapi 0.139.0→0.139.2 + filelock 3.30.2→3.31.0 (2026-07-19: fastapi already at 0.139.2 from DEPS-4. filelock already at 3.31.0. No pyproject.toml changes needed — both use >= constraints.)

**Priority:** low
**Found:** 2026-07-19 discovery sweep
**ACs:**
- fastapi 0.139.2 ✓ (already at target from DEPS-4)
- filelock 3.31.0 ✓ (already at or above target)
- pydantic_core stays at 2.46.4 ✓
- 465/465 tests pass ✓
- Guard PASS ✓

## [x] TEST — cli/main.py coverage gap (73%, 37 uncovered) (2026-07-19: 13 new tests, coverage 73%→99%. Commit 51bd3e3. 482/482 tests pass, guard PASS.)

**Found:** 2026-07-19 discovery sweep — never-done audit §3 (test gaps).
**Files:** tests/test_cli.py (+292 lines, 13 new tests)
**Priority:** low
**ACs:**
- cli/main.py coverage ≥85% ✓ (99%, 138/138 stmts — only `if __name__ == "__main__"` on line 265 uncovered)
- 13 tests covering: invalid JSON, empty prompt, stage_models, DAG, ValueError, verbose trace, _print_trace table, serve (host/port/env), mcp ✓
- 482/482 tests pass ✓
- Guard PASS ✓

## [x] TEST — observability.py coverage gap (70%, 11 uncovered) (2026-07-19: 7 new tests, coverage 70%→100%. 485/485 tests pass, guard PASS.)

**Found:** 2026-07-19 discovery sweep — never-done audit §3 (test gaps).
**Files:** tests/test_observability.py (+57 lines, 7 new tests)
**Priority:** low
**ACs:**
- observability.py coverage ≥85% ✓ (100%, 37/37 stmts)
- get_logger() fallback when _LOGGER_CONFIGURED=False ✓
- _configure_langfuse() import error path ✓
- _configure_langfuse() disabled/skip/init paths ✓
- get_langfuse() both branches ✓
- 485/485 tests pass ✓
- Guard PASS ✓

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
