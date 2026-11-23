# Run 35 — live fallback, auth, and the three surfaces (2026-11-23)

Tick: `chimera-v2-dogfood-2026-11-23-14-28-25` (delivery 1). Graded tree: `925af817064c55c26951ef1ad12ded0103ab0b00` (HEAD at launch; controller manifest `20ce853d1ad44fb5834ff46b6dd7cdbdf0eb23fa1ef826135a338ee3cf349140`, 619 tracked files).

**Promise tested:** "One `POST /v1/deliberate` (or `chimera "<prompt>"`) returns a team-of-models
answer; a quota/credential-dead provider no longer sinks the deliberation (DF-CHIMERA-V2-130 fix,
landed 89aee38); `/v1/health` reports provider state."

**Verdict: ✅ SHIPPABLE** (with two P2s and one P5 filed). Every arm this run was a REAL
call against the LIVE deployed instance on `:8765` (commit `0eb9232`, which contains the
DF-130 fix; the 2-commit delta to HEAD is board-only — the run-34 stale-deploy finding is
resolved for product code).

## What was actually used

### Arm 1 — CLI (the README quickstart path, PATH-installed v0.3.0)

- `chimera --json "…" from ~ → RC=2, one-line error naming `chimera config init`.
  Config discovery is walk-up-from-cwd only (`src/chimera/config.py:1080`); `CHIMERA_CONFIG`
  (the documented pin, README.md:123) is never mentioned by the refusal — filed as
  DF-CHIMERA-V2-136 (P5).
- Same call from the repo dir: RC=0, coherent answer, **79.01 s wall, 5 % CPU** — the default
  `auto` formation dispatches a dispatcher + heavyweight `deepseek-v4-pro` worker for a
  one-sentence question. Same prompt, `--formation speed`: **5.77 s** (4.82 s model time,
  $0.000261). Same prompt via API `speed`: 3.75 s. The 13× difference is formation choice,
  and the quickstart never mentions it — filed as DF-CHIMERA-V2-137 (P2 docs/UX; the cost
  class itself is DF-CHIMERA-V2-114).
- Error paths verified: unknown formation → exit 2 + the full available-formations list;
  `--json --quiet` together → exit 2 with a one-line remedy. Both match the README's claims.

### Arm 2 — REST /v1/deliberate against the deployed instance

- Auth: unauthenticated POST → honest 401 naming both header options. Key resolution and
  use worked exactly as the owner would (env-mode `CHIMERA_API_KEY`).
- `speed` formation: 200, real 2-worker answer, **cold-after-idle 3.75 s / warm repeat
  4.61 s** — no product-side warm/cold delta; the wall is upstream model time (5 % CPU),
  consistent with run 34's stub-floor measurement (overhead ≤0.55 s). **No PERF row: nothing
  a user would feel is the product's own cost.**
- Trace quality is genuinely good: per-worker `wire_model`, `api_base`, `latency_ms`,
  tokens, `cost`, `fallback_attempts`; `total_cost` 0.000336–0.000378 per run.

### Arm 3 — DF-130 fix verified LIVE (defect reintroduced by formation/allowlist)

- `formation=quick` (includes `hermes/glm-5.3-flash`, unhealthy "queue_full" 6 min earlier):
  200 in 9.14 s; hermes had recovered and answered (7.8 s latency) — not a dead-provider arm.
- Forced dead provider: `allowed_models=["cliproxy/deepseek,deepseek-v4-flash"]` (cliproxy =
  missing credentials). Both workers failed after 3 attempts each, **HTTP 200 with a real
  answer in 3.63 s** — the aggregator served the merge alone. This is the DF-130 contract
  working: quota/credential-dead providers degrade to an aggregator-only answer instead of a 502.
- Worker spans are honest: `degraded=true`, `response` is an explicit
  "[stage worker_1 … unavailable: <full upstream error>]" notice, and
  `trace.worker_failures` carries the full litellm error text. But the TOP-LEVEL
  `degraded_reasons` is `[]` — it is truncation-only by spec (`src/chimera/engine.py:330`),
  so a caller keying on it reads a worker-layer wipeout as a clean multi-model merge.
  Recurrence of the DF-CHIMERA-V2-111 mechanism, measured on the response surface →
  filed as DF-CHIMERA-V2-111-R2.

### Arm 4 — OpenAI-compatible surface

- `POST /v1/chat/completions` with `model="speed"`: 200 in 3.54 s, `chimera_degraded_reasons`
  present ([]), standard `choices/usage` envelope. The docs' promise (drop-in OpenAI client)
  holds.

### Error contracts (documented behaviour, all reproduced)

| Arm | Expected | Got |
|---|---|---|
| unknown formation (REST) | 422 `Unknown formation: <v>` | ✅ exact |
| malformed `X-Chimera-Timeout` | 400 | ✅ `missing = in X-Chimera-Timeout: bananas` |
| missing prompt | 422 field required | ✅ |
| no API key | 401 naming both headers | ✅ |
| unknown formation (CLI) | exit 2 | ✅ |

## Verdict

- **Does it work?** Yes — 4/4 real deliberations answered across 3 surfaces; error contracts exact.
- **Is it useful?** Yes — cost/latency/trace per worker makes the multi-model tradeoff legible.
- **Is it usable?** Time-to-first-success from a clean directory is BLOCKED by the config
  refusal (self-explaining, 0.39 s); from the repo dir, the README's first command costs
  **79 s** where 5.77 s was one flag away.
- **Is it trustworthy?** Failed work is never hidden (worker notices + full error text),
  and the DF-130 fallback is proven live. The one trust gap is `degraded_reasons`'s
  truncation-only spec vs its name (111-R2).

## Rows filed this run

- `DF-CHIMERA-V2-136` (P5) — no-config refusal omits the documented `CHIMERA_CONFIG` pin.
- `DF-CHIMERA-V2-137` (P2) — README quickstart's first command is 79 s; `--formation speed`
  does the same job in 5.77 s; quickstart never mentions formation choice for latency.
- `DF-CHIMERA-V2-111-R2` (P2, recurrence of DF-CHIMERA-V2-111) — a worker-layer wipeout is
  invisible in top-level `degraded_reasons` (truncation-only by spec) on the REST response.

No PERF rows: warm/cold delta nil, product overhead model-bound (≤0.55 s, run 34).
