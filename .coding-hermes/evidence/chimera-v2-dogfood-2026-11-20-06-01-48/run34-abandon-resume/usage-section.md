## Update 2026-11-20 (run 34) — WALKING AWAY COSTS YOU, AND NOBODY NOTICES

Field-tested on a scratch instance from `HEAD 20e7598` with `queue.max_concurrent: 1` and a 4 s-per-call
metering stub, plus the live `:8765` deployment in the same hour. Everything below was executed;
numbers come from the stub's own clock and from curl, not from Chimera's logs.

### The rule that matters most: closing the tab does not stop the work

A client that gives up mid-run is **not noticed at all**. Abandoned at t+2.02 s (curl `rc=28`) on a
run that takes 8.5 s:

- the first upstream stage was served **2.0 s after** the client was gone, the second **6.0 s after**;
- both are paid for — the answer went nowhere;
- with `max_concurrent: 1` the **next** caller waits for the corpse: retry **14.18 s** vs **8.54 s**
  control (**+5.64 s, +66 %**), queue position 2, first upstream call 6.06 s after send;
- `/metrics` afterwards: `chimera_requests_total{...status="2xx"} 3`, duration sum 30.7469 over
  count 3 — the discarded run is booked as a **delivered success** (`DF-CHIMERA-V2-132`, `-133`).

Practical consequences, until that is fixed:

- **Set client timeouts above your worst-case queue wait**, not above your provider latency. A retry
  is not free — it queues behind your own abandoned run.
- **Do not use "close the tab and retry" as your recovery loop** on a shared deployment: you are
  paying twice and making your own next call slower.
- **Do not trust a 100 % 2xx rate as "nothing is being wasted."** There is no aborted/disconnected
  status to look for.
- **Ctrl-C on the CLI does not end the run either.** At t+2 s it kept going; `timeout` had to kill it
  at 4.11 s (exit 124) with `engine_dispatched` already on stderr. Wrap long CLI runs in `timeout`
  if you intend to be able to stop them.

### The method (re-runnable)

1. Stub upstream that logs every arrival on a monotonic clock with a per-request marker
   (`run34-abandon-resume/stub_slow.py`), fixture with `queue.max_concurrent: 1`.
2. Control call, timed with curl's `%{time_total}` **and** `-H 'X-Chimera-Queue-Position'` response
   header captured.
3. Same call with `curl -m 2`, which abandons it mid-flight; then immediately re-send the same prompt.
4. Compare: control wall vs retry wall (the difference is queue wait), and each marker's stub arrival
   time vs the moment the client left (the difference is work done for nobody).
5. Scrape `/metrics` and reconcile `_duration_seconds_sum / _count` against the three walls — if the
   sum equals control + abandoned + retry, the abandoned run is in the success numerator.

### Check provider health before blaming the queue

The live deployment answered **502 to every formation** in this run (speed 2.68 s, simple 2.27 s,
auto 3.36 s). `GET /v1/health` → `status: degraded`, `unhealthy_providers: [cliproxy, deepseek]`,
`details.providers.deepseek.error_class: quota`, 8 providers and 48 models configured, and every
formation still routed to the dead one. Passing `allowed_models: ["z-ai/glm-5"]`, or
`dispatcher_model` + `aggregator_model`, did **not** rescue it (502 in 2.29 s vs 2.34 s for the plain
request — statistically identical), and with `lock_aggregator: true` the `aggregator_model` override
is dropped silently (`DF-CHIMERA-V2-130`, `-131`).

There is **no supported escape today** from a quota-dead provider: check `/v1/health` first, and if
`error_class` says `quota`, stop — the run will spend time and return nothing.

### Perf: the engine is not the problem

`POST /v1/deliberate` with `formation: simple` = **8.54 s cold** for 8.10 s of upstream stages, i.e.
**438 ms (5.1 %) of Chimera-owned overhead** for two local round trips + prompt assembly. No profile
was earned. The only user-felt slowdown in this run was the **+5.64 s queue wait** behind the
abandoned request — and that is a lifecycle bug, not a hot path.

Open rows from this run: `DF-CHIMERA-V2-130` (P1, live deployment cannot answer), `-131` (P2,
silent override drop), `-132` (P2, abandoned work keeps the slot), `-133` (P2, abandoned work counted
as success), `-134` (P3, live build six commits stale). Evidence:
`.coding-hermes/evidence/chimera-v2-dogfood-2026-11-20-06-01-48/run34-abandon-resume/`
(`probe_abandon.sh` runs the whole arm in one command).
