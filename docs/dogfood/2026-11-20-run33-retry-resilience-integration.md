# Run 33 — does Chimera survive a rate-limited provider, and can the user tell? (2026-11-20)

Tick: `chimera-v2-dogfood-2026-11-20-06-01-48` (re-fire; runs 31 and 32 delivered earlier under the same id)
Lane: `chimera-v2-dogfood` (skill-driven, read-only — no code or board-state changes by this lane)
Measured tree: HEAD `f47c0e4` (`origin/main` == HEAD), product `src/` byte-identical between HEAD and the dirty worktree in the retry region (`gateway.py` 953 vs 955)

## Promise statement

> A caller who hits a transient provider rate-limit still gets an answer, and the service both
> bounds and reports what that cost — `retry.max_attempts`, `retry.backoff_multiplier`,
> `retry.base_delay_ms` mean what `chimera.yaml` and `docs/RESILIENCE.md` F7 say they mean.

## Verdict

**SURVIVABLE BUT UNBOUNDED AND INVISIBLE.** The answer does arrive — every arm ended in HTTP 200
with a real deliberation, no crash and no fabricated success — but the retry layer multiplies
silently (3 upstream requests per attempt), ignores the operator's own delay policy in favour of an
uncapped provider header, synchronises its jitter across concurrent callers, and emits no retry
signal at all on the served surface. Four P2 rows, no P1: nothing lost data, but the numbers an
operator would use to reason about a provider incident are all wrong in the same direction.

## Arms (all executed, all recorded)

| # | Arm | Surface | Result |
|---|-----|---------|--------|
| 1 | always-429 stub, `max_attempts` ∈ {1,3,5} | in-process `LiteLLMGateway.complete` | 3 / 9 / 15 upstream arrivals; 4.81s / 11.0s / 19.8s |
| 2 | 4 concurrent calls, always-429 | in-process | 36 arrivals in synchronised quartets (0.2–0.9 ms apart), identical `delay_ms` 385/385/385/385 |
| 3 | 2×429 then 200, hard-down upstream | served `/v1/chat/completions` :18766 | clean 0.1048s cold / 0.1117s warm; blip 2.1077s; hard-down 502 after 30.03s (36 requests) |
| 4 | `Retry-After: 1` vs `Retry-After: 5` | served `/v1/chat/completions` | 2.113065s (gaps 1.0017/1.0015s) vs 10.113688s (gaps 5.0032/5.0055s) |

The stub (`stub429.py`) timestamps every arrival on its own clock, so no number here depends on
Chimera's own logs — which is the point, because there are none for retries.

## Findings (board rows)

| Row | P | One line |
|-----|---|----------|
| DF-CHIMERA-V2-126 | P2 | One Chimera attempt = 3 upstream requests. The inner OpenAI-SDK retry (`max_retries=2`) is unconfigured on the production path — `num_retries=0` is set only on the prewarm call, `gateway.py:128` — so `max_attempts: 3` is really nine provider calls, and raising it as the docs invite multiplies pressure on a provider already refusing. |
| DF-CHIMERA-V2-127 | P2 | Retry jitter is correlated, not per-call: `gateway.py:953` seeds it from `hash(str(attempt))`, a process-wide constant, so four in-flight callers retried within 0.9 ms of each other with identical delays — the thundering herd F7 says the jitter prevents. |
| DF-CHIMERA-V2-128 | P2 | A transient 429 recovers invisibly. One blip turned 0.11s into 2.1077s with **0** `gateway_retry` log lines and no retry/attempt/rate-limit counter anywhere in `/metrics` (grep over the full exposition: 0 matches), while F7 promises each attempt is logged with attempt number, delay and error. |
| DF-CHIMERA-V2-129 | P2 | A provider's `Retry-After` overrides `retry.base_delay_ms` entirely and is uncapped: the wait tracks the header linearly (2 × header, because of DF-126) while the configured 500 ms / ×2.0 policy never appears in the timeline. A provider can set the user's latency and there is no ceiling. |

## Credit (things that held)

* **The recovery is real.** Every arm that a user could plausibly hit ended in a correct 200 with a
  real panel answer; a hard-down provider produced an honest 502, not a made-up answer.
* **Prewarm works.** The served process pays no import cost: 0.1048s cold is the whole first-request
  path, so the retry numbers are not hiding a warmup.
* **Missing config fails loudly.** `CHIMERA_CONFIG=/nonexistent chimera serve` → `rc=2` with
  `error: [Errno 2] No such file or directory: '…'` — re-checked by hand because the battery's
  chaos cell flagged "started but exited cleanly on missing config (rc=0)"; with an explicit path the
  behaviour is correct, so that INFO is a battery probe artifact, not a product defect. No row filed.
* **Nothing was promised that did not happen.** No arm reported a success the body contradicted.

## Install leg — PROVEN on a fresh machine (not skipped this time)

`bunker-qa.sh` ran a full battery on bunker-mvp agent `ca76265a`; 26 cells, `CELLS-DONE`, all
evidence harvested to `install-battery.jsonl` before the agent could be reaped.

* `toolchain-bootstrap` OK ×10, `repo-head` OK, `fresh-install` OK, `lint` OK (ruff rc=0),
  `tests` OK — **2234 passed, 67 skipped in 188.82s** on a clean machine, `docker_build` OK,
  `compose_config` OK, `upgrade` OK (PiPy 0.2.8 → HEAD).
* `chaos-resource` PASS (survives a 3 GiB cap).
* `docker-deploy` SKIPPED and `chaos-shutdown` SKIPPED — the battery's own safety gate ("controller
  is the live Hermes host").
* `ci-pass` **FAIL is act infrastructure, not a red repo**: `act` dies inside `docker exec … setup/index.js`
  before the workflow steps run. Graded UNVERIFIED accordingly; no repo row filed for it.
* `ci-act` UNVERIFIED, `chaos-disconnect` UNVERIFIED, `chaos-corruption` N/A, `ui-probe` N/A.

This closes the gap run 31 disclosed (its bunker SSH leg was `Permission denied`) and the substitute
run 32 walked (container-only). The private-mirror clone leg remains unproven on a machine with no
Python, no `~/.hermes` dotenv and no docker daemon.

## Performance (Step 2b) — no PERF row, deliberately

The headline operation is the served deliberate call, and its cost is dominated by things this run
did not cause a change in: clean 0.1048s cold / 0.1117s warm (pipeline), 2.1077s under one transient
429, 10.113688s under `Retry-After: 5`. Profiling Chimera would be measuring an `asyncio.sleep`
chosen by a header — the actionable part is that the wait is **unbounded and unsettable**, which is
resilience (DF-129), not a hot path. No user-felt Chimera-owned compute was found, so no PERF row is
filed; filing one here would devalue run 30's PERF-2 (which carried a real 64%-of-wall dispatcher
finding).

## Diagnostics trail

`.coding-hermes/evidence/chimera-v2-dogfood-2026-11-20-06-01-48/run33-retry-resilience/` (34 files):
`stub429.py` (metering 429/200 stub), `fixture.yaml` (mock provider + retry settings),
`probe_retry.py` (arms: always-429, concurrent:N), `probe_cfg.py`, `att1.out` / `att5.out`
(arrival tables), `t4_concurrent4.jsonl`, `t2_persistent.jsonl`, `api_battery.log`,
`api_clean_cold.json`, `api_blip.jsonl`, `api_down.jsonl`, `p1.out`, `t2_persistent.out`,
`retry_after.sh` + `ra1.txt`/`ra5.txt`/`ra1.jsonl`/`ra5.jsonl` (header arms),
`install-battery.jsonl` (26-cell bunker battery), `REPORT.md` (this file), `INDEX.md`.

Every number above is re-derivable: run the stub, run the arm, read the stub's own timestamps.

## Deploy parity

`origin/main` == HEAD `f47c0e4`. The working tree carried 11 pre-existing uncommitted paths from a
concurrent writer at measurement time (untouched by this lane); the retry region was diffed
HEAD-vs-worktree and is byte-identical, so these findings are not a stale-checkout artifact.

## Lessons

1. Count arrivals at the upstream, not calls in the client — the ×3 SDK multiplication is invisible
   from inside the process and would have been missed by any assertion on Chimera's own retry log.
2. A recovery that leaves no trace is a finding: the request took 19× longer and the only evidence it
   ever happened was the wall clock.
3. When a battery cell disagrees with the product (chaos-errorpath), reproduce it by hand before
   filing — here the product was right and the probe was blunt.
