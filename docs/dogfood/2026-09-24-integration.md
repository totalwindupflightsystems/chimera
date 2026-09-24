# Dogfood Run 13 — Docker Deployment Surface (2026-09-24)

**Tick:** chimera-v2-dogfood-2026-09-24-09-26-20
**Surface:** the container deployment path (Dockerfile + docker-compose.yml +
CHIMERA_* env keys) — never exercised in runs 1–12, which covered CLI, REST,
MCP, library, PyPI wheel, editable install, custom formations and the
real-browser SPA.
**Verdict:** SHIPPABLE for the docker deploy surface (headline feature re-proven
on the fresh box), with a P1 deployment-trust defect on the live service.

## Promise under test

"A fresh user follows the Dockerfile/compose quickstart: `docker compose up -d`
with only `DEEPSEEK_KEY` exported, gets a healthy container on :8765, and the
web UI + deliberation work with no YAML editing."

## Where it ran

Ephemeral bunker agent `5d1b8e8e` on bunker-las-03 (bare Debian user, uid 1002,
nothing preinstalled beyond the rootless docker runtime bunkerd manages), TTL
2h, destroyed after the leg. Clone of the **public** GitHub mirror:

```
git clone https://github.com/totalwindupflightsystems/chimera.git ~/app   # 4s
HEAD = 3335322  (same commit as the private primary — mirror current)
```

## What the fresh user path did, step by step

| Step | Command (documented form) | Result | Time |
|---|---|---|---|
| clone | `git clone https://github.com/totalwindupflightsystems/chimera.git` | ok, 3335322 | 4s |
| build | `docker compose build` | ok | 106s |
| up (no keys) | `docker compose up -d` | container healthy | <1s |
| health | `curl localhost:8765/v1/health` | `degraded`, 4 providers missing-credentials | — |
| bad-key probe | `DEEPSEEK_KEY=sk-…-fake compose up -d` | deepseek flips to `auth … invalid` — **real API round-trip proves the env var reaches the engine** | — |
| real key | `DEEPSEEK_KEY=<real> compose up -d` | deepseek healthy; others (correctly) missing-credentials | 1s |
| smoke | POST /v1/deliberate `simple` "Name the capital of France" | `"Paris"`, full trace, request_id 396a5ed6 | 34s |
| warm ×2 | same POST again | 32s, 30s — zero failures | — |
| restart | `docker restart chimera` | healthy again, 36 models configured | — |
| CLI | `docker run --rm app-chimera --version` | `chimera 0.2.7` | — |
| web | `curl localhost:8765/web/` | HTTP 200 | — |

**Install leg verdict: PROVEN.** clone 4s → build 106s → healthy container →
real merged answer on the fresh box. No sudo, no compose-plugin install, no
toolchain prep was needed on the agent — the bare Debian user + bunkerd's
rootless docker carried the documented path as-is.

## Timing (perf leg, same numbers the run produced)

- build (cold): 106s
- up: <1s; health probe ~8s to `healthy`
- headline operation (one `simple` deliberation, 2 workers + aggregator,
  deepseek-v4-pro): **34s cold / 32s, 30s warm** — identical to the CLI/REST
  numbers prior runs measured; containerization adds nothing a user can feel.
- No PERF row: model-bound latency, not a code path. Nothing to profile.

## Findings (filed as board rows DF-CHIMERA-V2-46..48)

1. **[P1] DF-CHIMERA-V2-46 — live :8765 deployment is STALE again, repeat of the
   DF-CHIMERA-V2-45 class.** Running process started 2026-09-23 19:32:14 -05;
   material commits (src/chimera/provider_discovery.py,
   task_router_registry.py, scripts/model_sync.py + 5 test files) landed
   21:05–21:49 the same evening. `scripts/smoke_live.py` classifies: STALE
   (material diff non-empty), exit code is still 0 because deliberation passes
   — the *finding* is that no reload and no deferral happened after the wave,
   and the smoke's exit-0 does not surface staleness loudly. Evidence:
   /health `"commit":"e163a53"`, `git merge-base --is-ancestor e163a53 HEAD` →
   ancestor, `git diff --name-only e163a53..HEAD -- src/ scripts/ tests/
   pyproject.toml` → 8 files.
2. **[P2] DF-CHIMERA-V2-47 — docker docs say `DEEPSEEK_KEY`, template expands
   `${DEEPSEEK_API_KEY}`.** Dockerfile header + docker-compose.yml +
   Chimera-PRD.html all instruct `DEEPSEEK_KEY`; the shipped
   `chimera.yaml.docker` writes `deepseek: ${DEEPSEEK_API_KEY}`. It works only
   because `config._apply_env_overrides` happens to map both names into
   `config.api_keys` (config.py:1032). One name change away from breaking the
   documented quickstart; the docker leg should pin one canonical short name.
3. **[P3] DF-CHIMERA-V2-48 — container /health reports `"commit":"unknown"`.**
   The wheel install has no git metadata (correct), but /health then carries no
   version at all while /v1/health does report 36 models/5 providers. Cheap
   fix: fall back to package version (`chimera --version` → 0.2.7) when the
   git commit is unavailable.

## Things that worked exactly as documented (credit)

- `compose config --quiet` validates; the opt-in bind-mount warning about the
  "mount a directory onto a file" trap is written in the compose file itself
  and matches the fresh-clone reality (no chimera.yaml exists).
- Unhealthy-provider triage in /v1/health names the class per provider
  (`missing_credentials` vs `auth`) — the fake-key probe distinguished itself
  from a missing key instantly.
- The image ships a working default config; zero YAML editing was needed.

## Non-findings (checked, fine)

- `/v1/sessions` 404 + restart wipe: sessions are in-memory **by documented
  design** (session.py:100 "in-memory is correct for the single-node use case").
- Dockerfile pins `chimera-deliberation[full]>=0.2.0` → installs latest wheel
  0.2.7 while the repo is ahead; acceptable for a release-based image, and the
  container's engine behavior matched (simple formation dispatched correctly).
- bunker-las-03 rootless docker: the per-agent daemon socket is
  `/run/bunker/<agent>/docker.sock` (bunkerd-managed), NOT
  `/run/user/<uid>/docker.sock` and the `docker.service` user unit on the host
  is failed-idle. Agent-local `docker` CLI works against the bunker socket with
  no DOCKER_HOST juggling only after pointing `-H` at it; `docker context` is
  unaware. That is a bunker-runtime quirk, not a chimera defect.

## Artifacts

- `docs/dogfood/2026-09-24-integration.md` (this file)
- `skills/chimera-usage/SKILL.md` v1.5.0 — docker deploy section
- `docs/dogfood/diagnostics.md` — docker leg entry
- `.coding-hermes/tasks.md` — Dogfood Findings (2026-09-24, run 13)
- Board rows DF-CHIMERA-V2-46, -47, -48