# Dogfood Run 14 — PyPI wheel install + MCP-first client (2026-09-25)

**Verdict: SHIPPABLE** (6th consecutive). **Angle:** the two surfaces runs 1-13
never touched — the README's first quickstart line (`pip install
chimera-deliberation[full]` from PyPI, no repo) and the MCP stdio server driven
by an independent client (not the repo's own probe).

## Promise under test

> "A user installs the `[full]` wheel from PyPI in a throwaway venv, runs
> `chimera config init`, and gets a working CLI; an agent connects to
> `chimera-mcp` over stdio with a plain JSON-RPC client and deliberates."

## What I did (all real use, no test suite)

### Leg 1 — PyPI wheel, local throwaway venv (Python 3.11.15)

- `python3.11 -m venv venv && pip install 'chimera-deliberation[full]'` —
  **36s cold**, rc=0. `chimera --version` → 0.2.7; `python -m chimera
  --version` fallback also 0.2.7 (both README-claimed paths work from a wheel).
- Copied `chimera.yaml.example` → `chimera.yaml` in the scratch dir (documented
  alternative to `chimera config init`; both tested — see Leg 3 for the real
  `config init` from the wheel, which found the template inside
  site-packages and wrote it).
- `chimera --quiet "Name the three primary colors."` — **29.2s cold**, real
  merged answer, rc=0. (Cold includes the provider-cache refresh: stderr shows
  `provider_cache_stale age_s=13933` then a models.dev refetch.)
- Warm path: `--quiet` math prompt **11.2s** wall, `--json` trace
  `total_duration_ms: 11314` — wall ≈ trace duration, i.e. **model-bound with
  no measurable client overhead**.
- `--quiet run "…"`, `--json "…" | jq`-style parse — one JSON payload on
  stdout, `total_tokens` present. `--formation no-such-formation` → exit 2 with
  the available-formation list; `--quiet` + `--json` together → exit 2.

### Leg 2 — MCP server via an INDEPENDENT client

I wrote a raw JSON-RPC-over-stdio client (`initialize` →
`notifications/initialized` → `tools/list` → `tools/call`) — not the repo's
`probe_mcp_stdio.py` — the way an agent harness actually speaks MCP.

- `initialize` **0.49s** → `serverInfo {name: chimera, version: 0.2.7}`,
  protocol `2024-11-05` negotiated.
- `tools/list` → 3 tools: `chimera_deliberate`, `chimera_formations`,
  `chimera_models`; `prompt` required, formation/stage_models/dag optional.
- `chimera_formations` / `chimera_models` → correct JSON documents, 0.00s.
- `chimera_deliberate {prompt}` → **12.75s**, `isError=false`, answer +
  full trace in the content text. Clean shutdown on `terminate()`.
- Repeated unchanged on the bunker agent (Leg 3): initialize 0.95s,
  deliberation **45.5s**, same tool set — MCP interop is not
  machine-specific.

### Leg 3 — Fresh-machine install leg (ephemeral bunker, bunker-las-03)

- The QA driver leg **failed** (see Finding 1): `bunker-qa.sh launch` synced
  the repo but shipped a **0-byte qa-run.sh**, so no battery ever ran and
  `collect` failed with `pull-failed`. Per the skill I completed the install
  leg by hand on the same ephemeral agent (`c26d8af2`, destroyed after).
- Bare Debian agent: Python **3.13.5**, venv+pip present, PyPI reachable.
  `python3 -m venv ~/venv && pip install 'chimera-deliberation[full]'` →
  **266s**, `chimera --version` → 0.2.7.
- `chimera config init` → "Created chimera.yaml from …/site-packages/chimera/
  chimera.yaml.example" — the wheel template discovery works on a machine with
  no repo checkout at all.
- With only `DEEPSEEK_API_KEY` injected from a 600-file: real deliberation
  **18s** (correct RYB/RGB answer), then the full MCP battery again.
- Agent destroyed (`bunker destroy` verified gone via `bunker list`).

### Local deployment sanity (every run's obligation)

`scripts/smoke_live.py` → `service: alive commit=ee8ad95`, deployment
classified **CODE-CURRENT** (bookkeeping-only gap to HEAD cd44092),
providers 6/7 healthy (zai weekly quota exhausted — resets 09-27, class-aware
warning), live merged "Paris" answer. Smoke PASS.

## Findings

1. **[P2] `bunker-qa.sh launch` can ship a dead battery: 0-byte qa-run.sh.**
   `DETECT_UP_PREV_DIR: unbound variable` at line 846 (plus a
   `docker pull requires 1 argument` warning) aborted the launch script mid-
   generation after the repo sync — the agent got an empty battery script, ran
   nothing, and `collect` reported `pull-failed`. Nothing in the local output
   said the battery died; only reading `wc -c ~/qa-run.sh` on the agent did.
   Filed as DF-CHIMERA-V2-51 (driver defect, hermes-infra class).
2. **[P3] `scripts/mcp-liveness-check.sh` requires an npm toolchain.** It dies
   with `npx: not found` on a fresh machine (the repo's own CI agent class) —
   the MCP surface it exists to verify is exactly the one a wheel-only user
   has, and the check cannot run there. Filed as DF-CHIMERA-V2-52 (the
   stdlib-only client pattern in this report is the fix direction).

## Perf (Step 2b)

No PERF row. The only waits are model-bound: warm CLI 11.2s wall vs trace
11314ms; MCP deliberations 12.8s (local) / 45.5s (bunker) are provider time;
install 36s local / 266s on a bare agent is one-time setup, same order as the
prior runs' numbers. Nothing a user would feel as a project defect.

## Time-to-first-success

~2 min on an existing machine (36s install + config + 29s first answer);
~7 min from a bare box (266s install + answer). Friction count: 2 (both
findings above are tooling, not product).

## Left behind

- `docs/dogfood/2026-09-25-integration.md` (this file)
- `docs/dogfood/diagnostics.md` — wheel/MCP leg appended
- `skills/chimera-usage/SKILL.md` v1.6.0 — PyPI-wheel + independent-MCP-client
  section
- Board rows DF-CHIMERA-V2-51, DF-CHIMERA-V2-52
- `.coding-hermes/dogfood-log.md` run-14 entry
