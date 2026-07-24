<!--
  ⚠️  BOARD FORMAT — coding-hermes-model-router v1.3 (2026-07-24)
  All tasks MUST use matrix format: | ID | Task | Pri | Cpx | Deps | Tags | Model | Reasoning | Fallback |
  Before editing this file, load the skill: skill_view(name='coding-hermes-model-router')
  Validate: python3 ~/.hermes/scripts/validate-board-format.py .coding-hermes/tasks.md
  NEVER remove the matrix header row or NEVER-DONE / E2E-001 fixtures.
-->

# Chimera v2 — Model Router Task Matrix

**Core purpose:** Multi-model deliberation system — runs prompts through multiple LLMs in parallel formations (panel, debate, cascade, ensemble) and returns merged answers with trace. Python/FastAPI, 553 tests, 97% coverage, 5046 models across 9 providers.

## Active Tasks

- [ ] **E2E-001 — E2E Testing Tick (self-improving loop)** 🔁 Every 5-10 ticks
  Spawn Luna (browser/screenshots) or Step 3.7 Flash (CLI/API). Deploy/build, Playwright, screenshots, endpoints, console. → e2e-output/tasks.md → inject into board.

| ID | Task | Pri | Cpx | Deps | Tags | Model | Reasoning | Fallback |
|----|------|-----|-----|------|------|-------|-----------|----------|
| NEVER-DONE | 11-point audit sweep | High | 2 | — | ++code-review, +testing | DeepSeek V4 Pro | Audit runs every tick; 1 pricing-drift test fails (NOT regression) | GLM-5.2 |

**Assumptions:** Python 3.12+, FastAPI, Pydantic v2. 517/615 tests pass, 62 skipped. 1 pricing-drift failure in `test_provider_discovery.py` (expected — pre-existing, NOT regression). 3 vulns in GitPython 3.1.53 (GHSA-fjr4, GHSA-6p8h, GHSA-r9mr — fixable by upgrading to 3.1.55). 16 outdated packages (patch-level only). All endpoints wired. 9 providers configured.

**Routing Notes:** Board has 0 real tasks — project feature-complete. Scheduler CooldownS=43200 (12h) — stable this tick. All NEVER-DONE checks pass every tick except pricing drift. HEALTH-001 and VALIDATION-001 both completed. DuckBrain chimera-v2 namespace populated this tick (was empty).

**Execution Order:** NEVER-DONE only.

**Escalation Conditions:** No actionable tasks remain. Cooldown at 12h max. 15 consecutive idle ticks (streak). BANE ESCALATION: project has been idle for 15+ ticks with no regressions. Feature-complete. Recommend disable or de-prioritize to allow scheduler budget for active projects.

## Completed

| ID | Task | Pri | Cpx | Commit | Model |
|----|------|-----|-----|--------|-------|
| HEALTH-001 | Parallel health provider checks with 3s timeout | Medium | 2 | 25722e4 | MiniMax-M3 |
| VALIDATION-001 | Pydantic validation on DeliberateRequest + ChatCompletionRequest (min_length, formation enum) | High | 2 | 272f989 | MiniMax-M3 |
| U01 | Usability & coverage audit — found HEALTH-001 + VALIDATION-001 | High | 3 | — | DS-V4-Flash |
| DEPS | Upgrade 6 outdated pip packages (aiohttp, botocore, filelock, GitPython, sse-starlette, yarl) | Low | 2 | — | Foreman-direct |
