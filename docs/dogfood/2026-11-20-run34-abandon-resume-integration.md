# Run 34 — the client that walks away (abandon / resume), 2026-11-20

Tick: `chimera-v2-dogfood-2026-11-20-06-01-48` (fourth fire of this id; run 31 = provider resilience,
run 32 = container/PyPI delivery, run 33 = retry layer). Lane: `chimera-v2-dogfood`, workdir
`/home/kara/.hermes/stand-in/dogfood/chimera-v2`, target `/home/kara/chimera-v2`.

Promise under test, taken from the product's own words: **one `POST /v1/deliberate` returns a
multi-model answer, the queue's `max_concurrent` bounds how much work runs at once, and
`X-Chimera-Queue-Position` tells a waiting caller where it stands.** The user behaviour this run
puts on trial is the most common thing a human does with a slow endpoint: **close the tab and try
again.**

Verdict: **THE ABANDONED REQUEST IS INVISIBLE TO EVERY PART OF THE SYSTEM.** A caller who gives up
costs the deployment a full paid run, holds the only concurrency slot for that run's duration, makes
the next caller wait 5.6 s longer for the same work, and is then booked in `/metrics` as a delivered
2xx success. Nothing logs it, nothing counts it, nothing cancels it.

## Method

The live deployment on `:8765` cannot answer any deliberation (row `DF-CHIMERA-V2-130`: deepseek
balance empty, `error_class=quota`, every formation still routes there), so the behavioural arm ran
against a **scratch instance built from the measured tree** (`HEAD 20e7598 == origin/main`, version
0.3.0, port 18791) pointed at a metering stub upstream (`stub_slow.py`, 4 s per call, stdlib only,
timestamps arrivals on its own monotonic clock). Fixture: `queue.max_concurrent: 1`,
`queue.max_queue_depth: 4`, `provider_discovery: false`, single model `mock/m1`,
`formations.simple` with 1 worker. Everything is reproducible from
`probe_abandon.sh` in one command; every number below comes from the stub's clock or from curl,
never from Chimera's own logging.

The live deployment was still probed in the same session so the two surfaces are never conflated
(live = `f0a34a2`, six commits behind; scratch = `20e7598`).

## What the user hits

| arm | what the user did | what the product did |
|---|---|---|
| A1 control | one `POST /v1/deliberate`, waited it out | 200 in **8.54 s**, `X-Chimera-Queue-Position: 1`, 2 upstream stages (4.045 s + 4.057 s) |
| A2 abandon | gave up and closed the connection after **2.02 s** (`curl rc=28`, body `000`) | kept computing: stage 1 served at +2.0 s, stage 2 dispatched 2.0 s and served **6.0 s after the client was gone** |
| A3 retry | immediately re-sent the same request | 200 in **14.18 s** vs 8.54 s control (+5.64 s, **+66 %**), queue position 2, first upstream call 6.06 s after send |
| A4/A6 metrics | read `/metrics` after the arm | `chimera_requests_total{...status="2xx"} 3`, `_duration_seconds_sum 30.7469` over `_count 3` = 8.54 + 8.03 + 14.18 — **the abandoned run is in the numerator** |
| A5 CLI | Ctrl-C at 2 s on `chimera` CLI | Ctrl-C did **not** end the run; `timeout` had to kill it at 4.11 s (exit 124) with `engine_dispatched` on stderr 0.2 s earlier |
| A7/A8 upstream | — | 6 arrivals, 6 served: markers `Original ×3`, `CTRL1`, `ABORT1`, `AFTER1`; no arrival is ever cancelled |

Timeline (seconds from probe start, stub clock): `3.54 CTRL1 → 7.56 Original → 11.67 ABORT1 →
15.69 Original → 19.74 AFTER1 → 23.79 Original`. The abandoned request's two stages are the two
that matter: sent at 11.67 while its client was still connected until 13.68, second stage dispatched
at 15.69 and served at 19.69.

## Findings (board rows the foreman works — this lane fixed nothing)

- `DF-CHIMERA-V2-132` **P2** — an abandoned deliberation keeps the only concurrency slot and keeps
  buying upstream calls; the retry waits 6.1 s for a slot the corpse holds (14.18 s vs 8.54 s) and
  2 upstream calls are paid for an answer nobody received.
- `DF-CHIMERA-V2-133` **P2** — `/metrics` books the abandoned request as a delivered 2xx with its
  full 8.03 s duration; there is no aborted/disconnected status, so an operator sees a 100 %
  success rate while half the work is thrown away.
- `DF-CHIMERA-V2-130` **P1** — the live deployment serves 502 for every formation (deepseek quota,
  zero fallback despite 8 providers / 48 models); re-measured this run: speed 2.68 s, simple 2.27 s,
  auto 3.36 s.
- `DF-CHIMERA-V2-131` **P2** — `lock_aggregator: true` silently swallows an `aggregator_model`
  override: 502 in 2.29 s vs 2.34 s un-overridden, no 400, no warning. There is no documented
  escape from the dead provider.
- `DF-CHIMERA-V2-134` **P3** — the live `:8765` runs `f0a34a2`, six commits behind `20e7598`; the
  run-32 and run-33 fixes are not in the build a user is exercising, and nothing in `/v1/health`
  says the build is stale.

Credit where it is due: the control path is clean and fast (8.54 s wall for 8.10 s of upstream
work), the queue position header is accurate (1, then 2), the answer echoes correctly, and a dead
provider produces a *fast, honest* 502 (2.3–3.4 s) rather than a hang. The defect is not that
Chimera is slow; it is that it does not notice nobody is listening.

## Performance verdict (Step 2b): no PERF row, and here is the arithmetic

The headline operation is `POST /v1/deliberate` with `formation: simple`.

- **Cold** (first request against a freshly booted fixture): **8.54 s** wall.
- **Warm**: the same formation's stage latencies are identical (4.045 s / 4.057 s), and the only
  warm call the fixture could accept was the retry — **14.18 s**, of which 5.64 s is queue wait
  behind the orphan, not engine time.
- **Chimera-owned overhead** = 8.54 s − 8.10 s of upstream = **438 ms (5.1 %)** covering two local
  HTTP round trips, prompt assembly and the aggregator's request build. That is not a number any
  user can feel, so no profile was earned and none was run: a flamegraph of 438 ms of local
  plumbing would devalue run 30's real `PERF-2`.
- The number a user *does* feel is **+5.64 s** on their retry, and it is not a hot path — it is a
  dead client holding a slot. It belongs to `DF-CHIMERA-V2-132`, where it is written down with the
  exact command that produced it, rather than dressed up as a profile target.

## Install leg (fresh machine)

`bunker-qa.sh` drove the ephemeral-bunker procedure (no driver script, per the lane contract):

- `resolve /home/kara/chimera-v2` → rc=0, repo path resolved.
- `launch … --keep` → **agent `1434cbce` @ bunker-mvp** (tailscale), detached battery, ttl 4 h.
- `collect` → **6 evidence rows synced, battery still running**: `launch OK`, `repo-head OK ×2`,
  `toolchain-bootstrap OK ×5`; `fresh-install`, `lint`, `tests`, `docker_build`, `compose_config`,
  `upgrade` had not reported yet when this report was written.
- This is **not** a skipped leg and **not** a proven one — it is a launched-but-unfinished battery,
  stated as such. The final collect result is recorded in `.coding-hermes/dogfood-log.md`; if it did
  not finish, the honest reading is "installability not proven this run", not a pass.

## Deploy parity

Repo `HEAD = 20e7598 = origin/main` (measured tree, source of every scratch number). Live `:8765`
reports `details.commit=f0a34a2`, version 0.3.0 = **6 commits behind**, `f0a34a2` an ancestor of
HEAD. Row `DF-CHIMERA-V2-134` carries the staleness; this lane does not restart a shared service
(see below).

## Considered and refused

- **Restarting `:8765` to measure cold start** — it is the owner's live service and a restart would
  have produced a cold number at the cost of someone else's session state. Not worth it; disclosed.
- **Minting a bunker credential** — `bunker-mvp` accepted the existing key; nothing was minted, no
  visibility or permission was touched anywhere.
- **Filing "no cancellation exists" as a code claim without reading the source** — the row cites the
  observed behaviour and the missing metric, not a line number I did not verify this tick.
- **A PERF row for the 438 ms of overhead** — a win nobody can feel is not a finding.

## Artifacts

`.coding-hermes/evidence/chimera-v2-dogfood-2026-11-20-06-01-48/`

- `run34-abandon-resume/stub_slow.py` — metering OpenAI-compatible stub (arrival log on its own clock)
- `run34-abandon-resume/fixture.yaml` — `max_concurrent: 1`, `max_queue_depth: 4`, one mock model
- `run34-abandon-resume/probe_abandon.sh` — the whole arm in one command (control, abandon, retry, metrics, CLI)
- `run34-abandon-resume/run34-results.txt` — the raw result file quoted above
- `run34-abandon-resume/stub-arrivals.jsonl` — 6 upstream arrivals with monotonic timestamps
- `run34-abandon-resume/live-simple-{1,2}.json`, `live-override-{1,2}.json`, `live-timing.txt` — live arms
- `run34-abandon-resume/fix_row{130,132,132b,133}.py`, `file_rows*.sh` — the exact row-writing steps (kept so the
  board text is reproducible)
- `run34-install-bunker/launch.log`, `run34-install-bunker/collect1.log` — bunker battery evidence

Trace:

`ch:trace row=DF-CHIMERA-V2-132 spec=docs/dogfood/2026-11-20-run34-abandon-resume-integration.md#findings wave=chimera-v2-dogfood-2026-11-20-06-01-48 evidence=.coding-hermes/evidence/chimera-v2-dogfood-2026-11-20-06-01-48/run34-abandon-resume verdict=abandoned-work-invisible commit=20e7598 memory=none:foreman-writes`
