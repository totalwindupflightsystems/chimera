# Dogfood Run 23 — 2026-10-15 — Idempotency contract + the REST custom-DAG seam

**Verdict: SHIPPABLE** (14th consecutive). **Promise tested:** "a third-party
integrator can retry a deliberation safely — `idempotency_key` replays the
cached success (`X-Idempotent-Replay: true`), coalesces concurrent duplicate
keys onto one execution, and never caches failures — and a custom DAG can be
driven over the documented REST seam (`POST /v1/chat/completions` with
`model: "custom"`), exactly as README.md and docs/OPENAI_API.md describe."

Runs 1–22 never touched the idempotency surface at all (grep over
`docs/dogfood/` finds zero mentions), and the custom-DAG drives of runs 3/12
went through the library and MCP seams, never the documented REST contract.
This run consumed both the way the docs tell an integrator to.

## Environment

- Live deployment `localhost:8765`, systemd `chimera.service`, `/health`:
  `commit=3c394ec`, version 0.2.7. HEAD `12011c7`; running commit resolves, is
  an ancestor of HEAD, and the material diff (`src/ scripts/ tests/
  pyproject.toml`) below `3c394ec` is **empty** (HEAD adds board rows + a
  dependency-reconcile commit `38332c4` whose only tracked file is
  `uv.lock`/pyproject-adjacent packaging — verify: `git diff --name-only
  3c394ec..12011c7` lists no `src/` file). Classification **CODE-CURRENT**
  per the AGENTS.md hand-reproduction: no reload owed.
- No repo state modified by this lane; every probe ran from `/tmp/chv2-df23/`.

## Leg 1 — Idempotent replay on POST /v1/deliberate (documented surface)

- First call, `idempotency_key=df23-idem-001`, prompt "number 23", formation
  simple: HTTP 200, 53s, answer "23 is a factorial prime, equal to 4! − 1.",
  request_id `ebb2b32e9775458b`.
- Repeat, byte-identical body: HTTP 200 **fast** (<1s), header
  `x-idempotent-replay: true`, `x-chimera-queue-position: 1`; response body
  byte-identical (same answer, same `trace.request_id`) — no re-execution,
  no re-billing. **Contract held.**

## Leg 2 — Concurrent duplicate coalescing + failure-not-cached

- **Coalescing (DF-77 regression check):** 4 simultaneous POSTs, same key
  `df23-idem-004`: all 200, all four carry `request_id=e74af4880be84e3a`
  (one execution), 3 of 4 responses carry `x-idempotent-replay: true`, the
  executing request carries none. Spread 119.1s (wall, all waited on the one
  run). Exactly the documented "concurrent duplicates coalesce onto the same
  execution". **Held.**
- **Failure-not-cached:** first POST with `idempotency_key=df23-fail-001` and
  `models:["totally/bogus-model"]` → HTTP 400 with the exact catalog error
  and **no** `X-Idempotent-Replay` header; immediate retry with the same key
  and a VALID body executed for real (200, fresh answer, no replay header).
  The failure was not cached; the key was reusable. **Held.**
- Same probe with a live-but-uncredentialed worker
  (`worker_model=google/gemini-3.1-pro-preview`, key `df23-fail-002`):
  first call 200 with a real answer (gemini credentials ARE present in the
  deployment env — so this leg graded "provider healthy", not failure; the
  retry then replayed correctly with `X-Idempotent-Replay: true`). Both
  halves of this leg are recorded for completeness; the 400-leg above is the
  discriminating one.

## Leg 2c — FINDING DF-CHIMERA-V2-83 (P2): replay ignores the request body

Reusing `idempotency_key=df23-idem-001` with a **different prompt** ("What is
the capital of France?") returned HTTP 200, `x-idempotent-replay: true`, and
the **original number-23 answer** — no warning field, no body-match marker.
First-write-wins is a defensible design, but a client bug that reuses a key
across different requests gets silently wrong answers with a success status.
Filed as **DF-CHIMERA-V2-83** (fix direction: 409/422 on body-hash mismatch,
or an `X-Idempotent-Body-Match: false` marker, plus a docs warning).

## Leg 3 — REST custom-DAG seam (documented in README "Custom DAGs")

- Happy path: `POST /v1/chat/completions`, `model:"custom"`,
  `allow_custom_dag:true`, 3-stage dag (deepseek-flash researcher →
  deepseek-pro critic → gpt-5.6-luna final): HTTP 200 in 47.2s,
  `finish_reason:stop`, coherent merged answer on the exact YOUR-structure
  path. Usage tokens 28002; `chimera_degraded_reasons: []`.
- Worker-failure resilience inside a custom dag: anthropic/claude-sonnet-4.6
  worker leg returned 200 in 8.8s with the merged answer "yes" — the
  anthropic credential also resolves in this deployment.
- Negative contracts, all correct status: `allow_custom_dag:false` → 400
  "Custom DAG requires allow_custom_dag=true"; `formation:"custom"` on
  `/v1/deliberate` → 422 "Unknown formation: custom" (documented).
- **FINDING DF-CHIMERA-V2-85 (P3):** a structurally invalid dag (two worker
  stages, no aggregator) gets a 400 whose detail concatenates the structural
  reason with the model-catalog rule — the copy points the integrator at
  their model catalog when the DAG SHAPE is the actual problem
  (src/chimera/dispatcher.py:403). Filed.

## Leg 4 — FINDING DF-CHIMERA-V2-84 (P3): idempotency silently ignored on the chat surface

The same `idempotency_key` field sent to `POST /v1/chat/completions` is
accepted without error but does nothing: two identical POSTs executed for
real (13.3s, then 8.2s, different completion ids, no replay header). Docs
document the key only on `/v1/deliberate`; the OpenAI-compatible surface
gives no signal that retry-safety is absent. Filed.

## Deploy-parity + install leg

- Deploy classification CODE-CURRENT (see Environment) — no reload owed.
- **Install: PROVEN on bunker-mvp** (las-01/02/03/04 all offline this tick;
  mvp answered `systemctl is-active bunkerd` = active). Ephemeral agent
  `df23chv2`, TTL 2h: spawn 19s → fresh-agent clone of the PUBLIC GitHub
  mirror (shallow) in 1s, HEAD `12011c7` == local HEAD → `python3 -m venv` +
  `pip install -e ".[full]"` **53s RC=0** (Python 3.12.3, 8 cores) →
  `chimera config init` creates the yaml from the example → `chimera
  --version` = 0.2.7 → **zero-credential CLI smoke**: exit 2, stderr carries
  the actionable DEEPSEEK_API_KEY guidance (run 19's DF-71 fix VERIFIED on
  the fresh box) → serve on :8765 healthy, `/health` commit=12011c7 →
  keyless `/v1/deliberate` correctly 502s with the upstream-credential error
  (REST/CLI failure-contract asymmetry as run 19 filed) → `/web/` 200.
  Server stopped, home cleaned, **agent destroyed; post-destroy recheck at
  ~95s shows 0 residue rows**. install_seconds≈75 end-to-end (spawn+clone to
  healthy serve), install-only 53s.

## Performance (Step 2b)

Headline operation = simple deliberation, cold (unique idempotency key):
**52.7s** wall; warm repeats on separate keys: 119.3s / 158.5s (both 200).
`/usr/bin/time`-style attribution from the run-22 traces still holds: the
trace itself reports `total_duration_ms=52389` for the 53s first call — the
wall IS model time (dispatch 1.5s + 2 workers 27-42s + merge). The warm
119/158s spread matches the 4-way concurrent probe (116-220s with clean
X-Chimera-Queue-Position 1/2/3/4 rank set — DF-77 fix holding) and is
provider/queue-bound, not chimera-bound; identical input to run 22 measured
7-57s on the same formation. **No PERF row:** nothing here is a chimera
defect a user would file — the numbers are model-bound latency and queue
wait the queue-position header already discloses. Replay path itself is
sub-second (cached), which is the only chimera-owned latency on this surface.

## Value judgment

1. **Does it work?** Yes — every documented contract on both surfaces held
   except the three filed defects; the deploy runs current code.
2. **Is it useful?** The idempotency contract is real integrator value
   (coalescing + failure-not-cached verified); the REST custom-DAG seam is
   the documented "full control" path and works.
3. **Is it usable?** Friction 3: DF-83 (silent stale replay), DF-84
   (silent no-op key), DF-85 (misleading error copy). All are API-contract
   polish, not blockers.
4. **Is it trustworthy?** No data corruption, no state leaks; scratch
   blocked-models.json pollution avoided this run (no credentialless
   scratch-instance runs).
5. **Is it fast enough?** Yes beyond model latency — replay is instant,
   queue position is disclosed, nothing chimera-owned to file.

**Verdict: SHIPPABLE.**
