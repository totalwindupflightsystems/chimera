# Active Context — Chimera

## Current Phase
**Phase 0: Architecture & Scaffolding** (June 17, 2026)

## What We're Building
Fresh implementation of Chimera v2 — dispatcher-first architecture with
category-weighted domain routing, dynamic DAG formations, and dispatcher-written
judge instructions.

## Key Decisions
- **No SpecLang** — clean Python project, no code generation pipeline
- **OpenCode + GLM-5.2** as the build agent (Z.AI subscription, no OpenRouter fees)
- **Memory bank pattern** from Axiom/Conscience projects
- **Config-driven from day one** — no hardcoded model assignments
- **Budget-first defaults** — DeepSeek V4 for dispatcher/worker/judge
- **Request-level overrides** — API accepts allowed_models, disallowed_models,
  dispatcher_model, judge_model, worker_model per request

## Model Strategy
- **Default**: DeepSeek V4 (cheap, good all-rounder) for all roles
- **Premium options**: GLM-5.2, Claude Sonnet 4 — available via request overrides
- **Per-request control**: Caller can force specific models, whitelist/blacklist
- **Category weights**: Each model scored 0.0–1.0 per domain (code, analysis, design, audit, reasoning)
- **Dispatcher uses weights** to auto-assign models when not overridden

## Blockers
None.

## Next Steps
1. ✅ Architecture spec written
2. ✅ Memory bank initialized
3. ✅ GLM-5.2 built full implementation (3,386 lines, 65 tests)
4. ✅ Request-level overrides added to API + config
5. 🔄 Live E2E deliberation test (budget-first defaults)
6. Create GitLab repo and push
7. MCP integration test with Hermes
