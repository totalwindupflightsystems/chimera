# Chimera Documentation

- [README](../README.md) — overview, quickstart, architecture diagrams
- [CONFIG.md](CONFIG.md) — full `chimera.yaml` configuration reference
- [CLI_PROXY.md](CLI_PROXY.md) — run a local CLI proxy (`claude-code-router`, `one-api`/`new-api`) as a provider: contract, base_url/key wiring, model-id mapping, measured example
- [OPENAI_API.md](OPENAI_API.md) — OpenAI-compatible endpoint + custom DAG + SDK examples
- [USAGE.md](USAGE.md) — CLI, REST API, MCP, Python SDK patterns
- [INTEGRATION.md](INTEGRATION.md) — integrate into your app: deployment, clients, auth, errors
- [SECURITY.md](SECURITY.md) — security model and credential handling
- [EDGE_CASES.md](EDGE_CASES.md) — critical edge cases and handling
- [RESILIENCE.md](RESILIENCE.md) — retries, backpressure, format negotiation
- [FAILURE_RESILIENCE.md](FAILURE_RESILIENCE.md) — partial failures, token limits, budget exhaustion
- [LOCAL_CI.md](LOCAL_CI.md) — reproduce the hosted CI workflow locally with `act` (runner image pin, per-job commands)
- [REPO_LAYOUT.md](REPO_LAYOUT.md) — tracked repo-root layout, plus the intentional local-only exceptions (live config, harness state, ignore-rule policy)
- [GITREINS.md](GITREINS.md) — the quality gate: lanes, DEGRADED-PASS/skip semantics, the staged-diff verdict-ordering trap
- [model-catalog.yaml](model-catalog.yaml) — generated model catalog: category weights + cost tiers
- [CONTRIBUTING.md](../CONTRIBUTING.md) — dev setup, tests, PR process
- [CHANGELOG.md](../CHANGELOG.md) — release history

## Historical / archived

Early, dated artifacts kept for history. They are **not** current documentation
— the README and the guides above are authoritative.

- [PRD.html](PRD.html) — early, dated product-requirements draft (HTML), kept for history
- [Chimera-PRD.html](Chimera-PRD.html) — early, dated product-requirements draft (HTML), kept for history
- [audit-2026-08.md](audit-2026-08.md) — 2026-08 eleven-point audit snapshot, historical

## Dogfood run logs

Historical run logs: each file is a dated snapshot of one real-use dogfood run
against the live deployment, **not** a description of current behavior.

- [dogfood/2026-08-03-integration.md](dogfood/2026-08-03-integration.md) — run 1 integration report (2026-08-03)
- [dogfood/2026-08-13-integration.md](dogfood/2026-08-13-integration.md) — run 2 integration report (2026-08-13)
- [dogfood/2026-08-23-integration.md](dogfood/2026-08-23-integration.md) — run 3 integration report (2026-08-23)
- [dogfood/2026-09-04-runB-integration.md](dogfood/2026-09-04-runB-integration.md) — run 6, release-lag + deploy-parity focus (2026-09-04)
- [dogfood/2026-09-11-integration.md](dogfood/2026-09-11-integration.md) — run 7 integration report (2026-09-11)
- [dogfood/2026-09-16-runB-integration.md](dogfood/2026-09-16-runB-integration.md) — run 9B, real-SDK + bunker-install focus (2026-09-16)
- [dogfood/2026-09-20-runB-integration.md](dogfood/2026-09-20-runB-integration.md) — run 10, web-UI (`/web/`) live-DAG focus (2026-09-20)
- [dogfood/2026-09-22-integration.md](dogfood/2026-09-22-integration.md) — run 11, custom-formation authoring focus (2026-09-22)
- [dogfood/2026-09-23-integration.md](dogfood/2026-09-23-integration.md) — run 12, real-browser web-UI pass (2026-09-23)
- [dogfood/2026-09-24-integration.md](dogfood/2026-09-24-integration.md) — run 13, docker deploy surface on fresh hardware (2026-09-24)
- [dogfood/2026-09-25-integration.md](dogfood/2026-09-25-integration.md) — run 14, PyPI wheel install + independent MCP client (2026-09-25)
- [dogfood/2026-09-25-run15-integration.md](dogfood/2026-09-25-run15-integration.md) — run 15, official OpenAI SDK compat surface (2026-09-25)
- [dogfood/diagnostics.md](dogfood/diagnostics.md) — build/diagnostic trail behind the 2026-08-03 run
