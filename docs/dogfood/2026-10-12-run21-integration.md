# Dogfood run 21 — chimera-v2 (2026-10-12)

**Angle:** re-proof of the run-20 fix wave (DF-CHIMERA-V2-75/77) on the deployed build,
plus the REST-vs-chat failure-visibility parity surfaces run 20 left untouched.

## Promise under test

"Dead-worker failures are visible on every client surface, and concurrent
requests get queue-position feedback" — as fixed by 10e6633 (DF-75) and
4e969dd (DF-77), both present in the running build (571dd2f).

## What a real user experienced (live :8765)

### Queue feedback (DF-77 re-proof) — VERIFIED FIXED

3 concurrent `POST /v1/deliberate` (simple, "What is 2+2?"):
every response carried `X-Chimera-Queue-Position` (1/2/3). Walls 15.3s /
15.4s / 25.7s, 3/3 unique answers, no cross-talk. A second 4x battery
(walls 9/18/49/66s) also carried positions 4/3/2/1. The silent-queue
defect from run 20 is gone; a queued caller can now see its rank.

### Worker-failure visibility (DF-75 re-proof) — VERIFIED FIXED on chat, ASYMMETRIC on REST

Forced a real dead worker (`worker_model=cliproxy/deepseek,deepseek-v4-flash`,
provider healthy=false missing-credentials):

- Chat surface (`POST /v1/chat/completions`, model=simple): 200/stop with
  `chimera_worker_failures` carrying per-stage errors ("failed after 3
  attempts: ... Missing credentials") for worker_1 and worker_2. That is the
  DF-75 fix working.
- REST surface (`POST /v1/deliberate`): the SAME death is trace-only. The
  response body is `{answer, request_id, trace}` — no top-level
  `worker_failures` field; the death hides in `trace.worker_failures`.
  → DF-CHIMERA-V2-78 (P2).
- Chat has no `chimera_degraded_reasons` field at all while REST trace
  carries `degraded_reasons`. Two surfaces, two degradation vocabularies.
  → DF-CHIMERA-V2-79 (P3).

### Bogus model in REST `models` — silent substitution, third surface

`POST /v1/deliberate {formation: simple, models: ["totally-bogus-model-xyz"]}`
returns 200 with workers running `deepseek/deepseek-v4-pro`. The bogus id is
dropped silently: no 400, no warning, no dispatch note. The repo fixed this
class twice already (CH-GAP-027 on chat `model`, DF-61/400 on unknown
`worker_model`) but the REST `models` pool field still swallows garbage.
→ DF-CHIMERA-V2-80 (P2).

## Perf

Warm simple deliberation 7.4 / 8.8 / 9.2s — model-bound, matches runs 19-20.
Nothing a user would flag; no PERF row.

## Live deploy

STALE vs origin/main bcdbd73; smoke_live.py exits 1 with the actionable STALE
message while still delivering a real merged answer ("Paris", providers 7/10
healthy). Material delta is pyproject.toml/uv.lock only (dep bumps
995b2ac/6a6a4c7) — explicit deferral recorded, no reload this tick.

## Install leg

SKIPPED-install-bunker: premise unchanged — runs 19/20 PROVED the install
path on bunker-las-02 (agent 1b594f64, HEAD 0e5de41, install 65s RC=0) and
no install-doc/install-path commit has landed since (`git log --since=10-09`
shows src/scripts/tests/pyproject only). Evidence-backed skip, not a silent
pass.

## Rows filed

- DF-CHIMERA-V2-78 (P2) REST top-level response hides dead-worker failures
- DF-CHIMERA-V2-79 (P3) chat surface omits degraded_reasons
- DF-CHIMERA-V2-80 (P2) REST `models` silently drops bogus ids
