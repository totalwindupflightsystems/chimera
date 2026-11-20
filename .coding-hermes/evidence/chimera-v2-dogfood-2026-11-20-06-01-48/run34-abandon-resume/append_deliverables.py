import pathlib, json

repo = pathlib.Path("/home/kara/chimera-v2")
evd = ".coding-hermes/evidence/chimera-v2-dogfood-2026-11-20-06-01-48"

diag = """
## 2026-11-20 — run 34 (abandon / resume, live + scratch + fresh machine)

**Question:** what does the deployment pay when a caller gives up?

**Arm A — live service (`:8765`, build 20e7598, PID 2584)**, same minute:
`for f in speed simple auto; do curl -s -o /tmp/b.$f -w "%{http_code} %{time_total}" ... /v1/deliberate; done`
→ `speed 502 2.68s`, `simple 502 2.27s`, `auto 502 3.36s`; body: `no usable answer produced. Upstream
error: deepseek/deepseek-v4-flash call failed: ... Insufficient Balance`.
Same-minute `/v1/health`: `status=degraded`, `unhealthy_providers=[cliproxy,deepseek]`,
`providers_configured=8`, `models_configured=48`, `details.providers.deepseek.error_class=quota`.
Override arms (`dispatcher_model`/`aggregator_model` = `z-ai/glm-5`) → still 502 in 2.29s / 2.34s
(vs 2.34s un-overridden): the override does not reach the failing stage (`lock_aggregator: true`).

**Arm B — scratch instance on a slow stub**, `fixture.yaml` (`queue.max_concurrent: 1`,
`queue.max_queue_depth: 4`, `providers.mock.base_url: http://127.0.0.1:18091/v1`,
`api_key_env: CHIMERA_LOCAL_FIXTURE_KEY`, `provider_discovery: false`) + `stub_slow.py`
(4 s per call, arrival/serve timestamps on the stub's clock). Probe: `bash probe_abandon.sh`.
- control: 1 worker + aggregator, wall **8.54 s**, HTTP 200, `X-Chimera-Queue-Position: 1`;
  stub arrivals `t_in 3.5379 → t_out 7.5402`, `t_in 7.5639 → t_out 11.564` = 2 calls × 4.0 s.
- abandon: client gone at **t+2.02 s** (`curl rc=28`), yet arrival 1 served at t_out 7.5402 and
  arrival 2 at t_out 11.564 — the **first upstream call started 2.0 s after the client left, the
  second 6.0 s after**.
- retry (new request after abandoning): wall **14.18 s**, `X-Chimera-Queue-Position: 2`, first
  arrival at t_in 19.74 → **6.06 s** waiting for the slot the dead request still held.
- CLI arm: Ctrl-C at 2 s did **not** end the run; `timeout` killed it at 4.11 s (exit 124) with
  `engine_dispatched` logged 0.2 s earlier — upstream arrival **UNRESOLVED**.
- `/metrics` after the arm: `chimera_requests_total{status="2xx"} 3`, duration sum **30.7469**
  over count 3 — the discarded run is booked as a delivered success.

**Arm C — perf read (no PERF row).** The stub floor is 2 × 4.0 s = 8.00 s, control wall 8.54 s,
so Chimera's own overhead on this path is **≤0.55 s (≈6 % of wall)**. Nothing here is slow enough
that a user would feel it: the wall is the model, not the product. The one user-felt time cost in
this arm is the **+5.64 s (+66 %)** the next caller waits behind an abandoned run — filed as
`DF-CHIMERA-V2-132` (a resource/correctness defect), not as a PERF row.

**Arm D — fresh machine (install leg, `bunker-qa.sh`)** `launch /home/kara/chimera-v2 --keep` →
agent 1434cbce, clean clone; `collect --evidence /tmp/bunker-qa-evidence-20261120T092905Z-1812609.jsonl`
→ cells: `launch OK`, `repo-head OK`, `toolchain-bootstrap OK`, `fresh-install OK`, `lint OK`,
`docker_build OK`, `compose_config OK`, **`tests FAIL (rc=1)`**. First failure on the clean box is
`test_tracked_docs_file_is_reachable[docs/dogfood/2026-11-20-run33-retry-resilience-integration.md]`
— the same red as a local `pytest tests/test_docs_index.py -x -q` (1 failed, 49 passed). The install
works; the tree is red. Filed as `DF-CHIMERA-V2-135` (P1).

**Docs index repair (this lane, docs only):** added run 33 and run 34 lines to `docs/README.md`
after the detector proved run 33's report was referenced nowhere (`git log -S 'run33-retry-resilience'
-- docs/README.md` → empty). No `src/` file touched.
"""

log = """
2026-11-20 (run 34) | PROMISING-BUT-ROUGH | promise: "one POST /v1/deliberate returns a multi-model answer; `queue.max_concurrent` bounds concurrency; `X-Chimera-Queue-Position` tells a caller where it stands" → WALKING AWAY IS FREE FOR THE PRODUCT AND COSTLY FOR EVERYONE ELSE (the abandoned client was the one surface runs 1-33 never drove) | premise: the live service is 502 for every formation right now (deepseek `Insufficient Balance`, `/v1/health` status=degraded, 8 providers/48 models configured, no fallback), so the abandon question was driven on a metering stub instead of pretending the dead provider was the finding | t2fs: ~2 min on a warm venv (scratch fixture + stub, no install needed); first honest number at 8.54 s | friction 3 (one P1 provider-outage row, two abandon rows) | headline: control 8.54 s / queue pos 1 vs retry after abandoning 14.18 s / queue pos 2 — the abandoned request kept the ONLY slot for 6.06 s and the stub was still being called 2.0 s and 6.0 s after the client left; `/metrics` books the discarded run as `status="2xx"` (count 3, duration sum 30.7469) | findings: DF-CHIMERA-V2-130 P1 every formation 502s because the default deepseek key is out of balance and nothing falls back (2.27-3.36 s, error text names the provider; health knows, callers get a 502 body only); DF-131 P2 `lock_aggregator: true` silently swallows an `aggregator_model` override — no 400, no warning, failure still names the locked model; DF-132 P2 an abandoned request keeps the concurrency slot and keeps buying upstream calls (+5.64 s / +66 % wall for the next caller, 2 paid calls after abandonment, Ctrl-C on the CLI does not end the run); DF-133 P2 aborted work is absent from every telemetry series, so the deployment cannot see the waste it pays for; DF-134 P3 (see row) | credit: the queue signal itself is honest (`X-Chimera-Queue-Position` 1 then 2, exactly the wait observed), the 502 contract is honest (never a fabricated answer), `/v1/health` names the culprit provider and its error_class in one call | install: PROVEN on bunker agent 1434cbce (fresh machine, clean clone): fresh-install OK, lint OK, docker_build OK, compose_config OK, toolchain-bootstrap OK, launch OK — **tests FAIL** on the same docs-index orphan a local run hits, which is the row above (DF-135), not an install defect | smoke=n/a (live service degraded: 502 by provider, so a smoke claim would be meaningless) | no PERF row: stub floor 8.00 s vs control wall 8.54 s = Chimera's own overhead ≤0.55 s (≈6 %), i.e. model-bound; the only user-felt time cost is the queue wait an abandoned run imposes, filed as DF-132 | docs index repair (docs only, no src touched): run 33 + run 34 lines added to docs/README.md | artifacts: docs/dogfood/2026-11-20-run34-abandon-resume-integration.md, diagnostics run-34 section, usage skill v1.19.0, evidence .coding-hermes/evidence/chimera-v2-dogfood-2026-11-20-06-01-48/run34-abandon-resume/ | lesson: measure the abandon window on the UPSTREAM side (stub clock), never from the client's exit time — the client telling you it gave up says nothing about whether the server did
ch:trace row=DF-CHIMERA-V2-132 spec=docs/dogfood/2026-11-20-run34-abandon-resume-integration.md#findings wave=chimera-v2-dogfood-2026-11-20-06-01-48 evidence=.coding-hermes/evidence/chimera-v2-dogfood-2026-11-20-06-01-48/run34-abandon-resume verdict=walk-away-invisible commit=20e7598 memory=none:foreman-writes
"""

d = repo / "docs/dogfood/diagnostics.md"
t = d.read_text()
if "run 34 (abandon / resume" in t:
    print("diagnostics already has run 34")
else:
    d.write_text(t.rstrip("\n") + "\n" + diag)
    print("diagnostics appended")

lp = repo / ".coding-hermes/dogfood-log.md"
lt = lp.read_text()
if "run 34" not in lt:
    lp.write_text(lt.rstrip("\n") + "\n" + log)
    print("dogfood-log appended")
else:
    print("dogfood-log already has run 34")

for p in (d, lp):
    print(p.name, len(p.read_text().splitlines()), "lines")
print("diag has run34:", "run 34 (abandon" in d.read_text())
print("log has trace:", "verdict=walk-away-invisible" in lp.read_text())
