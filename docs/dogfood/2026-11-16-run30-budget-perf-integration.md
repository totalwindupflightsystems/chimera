# Run 30 — per-stage budget surface + the cost of an explicit formation

Tick: `chimera-v2-dogfood-2026-11-16-05-02-33` (repeat fire; run 29 was the previous fire of the same tick).
Measured build: `c62eecf` (version 0.2.9), repo `/home/kara/chimera-v2`, venv `.venv` (py3.12).
Mode: read-only real use. No product code changed, no row status changed. Everything below was executed.

## Promise under test

`docs/CONFIG.md` §`timeout` (lines 296-323):

> A stage that exceeds its budget is **not** fatal: the deliberation continues without it (the
> resilience contract), the trace records it in `worker_failures`, and the CLI prints a
> `warning:` line naming the dropped stage.
> ...
> The same budget is available per request on the REST surface (`X-Chimera-Timeout`), and a
> request can only *lower* the configured ceiling.

So the promise is: (1) a dropped stage is survivable and visible on every surface, (2) the same
knob exists per request on REST, (3) a request may lower but never raise the ceiling.

## What I actually did (operator path, not the test suite)

Deterministic stub provider (`stub_provider.py`, OpenAI-compatible, latency keyed off the model
id: `stub/sleep8` = 8 s, `stub/fast` ≈ 0) so wall time is attributable, plus one real provider
(deepseek) for the dispatcher. Formation `budgettest` = worker `stub/sleep8` + worker `stub/fast`
+ merge, defined in a **scratch config** under `.hermes/cache/scratch/dogfood-run30/` so the live
config was never touched.

Headline command (CLI, cold then warm):

```
.venv/bin/chimera --config .../chimera-budget.yaml --formation budgettest --json \
  run "Is a per-stage timeout budget useful?"
```

| arm | wall | trace total | dispatch | stages | cost |
|---|---|---|---|---|---|
| A0 cold | **23.48 s** | 22 527 ms | 14 509 ms | 8 012 ms | $0.001387 |
| A0b warm | **24.88 s** | (same shape) | ~14.5 s | 8.0 s | — |

The one slow stage is the 8 s stub; everything else is milliseconds. **64 % of the user-visible
wall and 100 % of the run's cost is a dispatcher call that restates the DAG the config already
fixed** — see PERF-2.

Budget-arm (CLI, `per_stage_s: 3` vs the 8 s worker):

```
.venv/bin/chimera --config .../chimera-budget3.yaml --formation budgettest --json run "..."   # WALL 18.9 s
```

- stage `slow` timed out at 3001 ms, the answer still came back, exit 0;
- stderr carried the plain line `warning: worker 'slow' … timed out after 3s` (DF-CHIMERA-V2-34's fix is live);
- `trace.worker_failures` = `[{stage_id: slow, error: "timed out after 3s"}]`;
- `answer_degraded: false`, `trace.degraded_reasons: []` — per `docs/EDGE_CASES.md:68-69` that is
  the documented meaning ("the ANSWER stage itself is degraded"), so this is spec-consistent and
  **not** filed; the honest statement is that `worker_failures` is the only machine signal.

REST arms against a scratch instance (`CHIMERA_CONFIG=…/chimera-rest.yaml serve --port 8799`,
4 models, auth off):

| # | request | result |
|---|---|---|
| R1 | `POST /v1/deliberate` `formation=budgettest`, no header | 200 in **8.39 s** (8 s stage) |
| R2 | same + `X-Chimera-Timeout: per_stage=2` | 200 in **2.05 s** — honoured, worker dropped at 2000 ms, `worker_failures` names it |
| R3 | same + `X-Chimera-Timeout: per_stage=999` | 400 `per_stage=999.0 exceeds admin ceiling 30.0s` — correct |
| R4 | same + `X-Chimera-Timeout: per_stage=abc` | 200 in **8.10 s**, no failures, no note — silent no-op |
| R5 | `POST /v1/chat/completions` `model=budgettest` + `per_stage=2` | 200 in **8.02 s** — header ignored |
| R6 | same, no header (control) | 200 in **8.06 s** |
| R7 | chat + `per_stage=999` (a value `/v1/deliberate` rejects with 400) | 200 in **8.02 s** — accepted, no effect |

R8 (chat with the *configured* ceiling at 2 s, forcing a real drop): 200 in 2.39 s with
top-level `chimera_worker_failures=[{stage_id: slow, error: "timed out after 2s"}]`. The chat
surface does expose worker failures — that part of the promise holds, and it is why no
"chat is blind to degradation" row was filed this run.

## Findings (rows filed by the foreman's rules, not fixed here)

- **DF-CHIMERA-V2-116 (P2)** — `X-Chimera-Timeout` is silently ignored on `/v1/chat/completions`.
  CONFIG.md:322-323 promises the per-request knob "on the REST surface"; only `/v1/deliberate`
  reads the header (`src/chimera/api/server.py:816-818`), `chat_completions`
  (`server.py:1532`) never looks at it. R5 vs R6: 8.02 s vs 8.06 s. R7 shows a value that
  `/v1/deliberate` rejects with 400 is accepted with 200 here, so the client cannot even tell
  the header was dropped.
- **DF-CHIMERA-V2-117 (P3)** — malformed header values are silently ignored on
  `/v1/deliberate`: `per_stage=abc` → 200 after the full 8.10 s, while `per_stage=999` → 400.
  `server.py:830-831` swallows the `ValueError` with `continue`. A typo therefore costs the
  operator exactly the wall time they were trying to bound, with no warning.
- **DF-CHIMERA-V2-119 (P2)** — `chimera serve` accepts the global `--config` flag and ignores
  it. Booted as `.venv/bin/chimera --config …/chimera-rest.yaml serve --port 8799` the server
  answered `/v1/models` with **48** models and 401'd every call (the live config's auth), while
  the same file via `CHIMERA_CONFIG` gave 4 models and worked. Mechanism:
  `src/chimera/cli/main.py:959` loads the pointed config, then passes only host/port to
  `run_api` (main.py:966-971), and `src/chimera/api/server.py:2179` re-resolves the config with
  a path-less `load_config()`. `serve --help` does not list `--config`, so a user following
  USAGE.md:47 (`chimera --config /path/to/chimera.yaml run "..."`) and swapping in `serve`
  silently gets whatever the cwd/env resolves.
- **PERF-2 (P2)** — an explicit formation still pays a full dispatcher LLM call. Numbers above:
  14 509 ms of 22 527 ms (64 %), $0.001387 (the whole run's cost), 1070 prompt + 2044 completion
  tokens, on a DAG the config already fixed verbatim. Call site `src/chimera/engine.py:793`
  (`await self.dispatcher.dispatch(...)`). CONFIG.md:242-243 tells the reader that "named presets
  and custom DAGs are never rewritten — their structure is explicit configuration and is honored
  verbatim", which reads as a local, free path; the billed round-trip is documented only in the
  engine docstring (engine.py:191-194). A user who writes eight stages pays it per run and cannot
  turn it off (`lock_dispatcher: true` did not suppress it — that flag only pins the model).
- **SKIPPED-INSTALL-CHIMERA-V2-20 (P3)** — named skip, not a silent pass. The same tick already
  proved installability on a clean machine (bunker-mvp agent 951ddc07, battery committed at
  `.coding-hermes/evidence/chimera-v2-dogfood-2026-11-16-05-02-33/install-bunker-951ddc07/`), and
  `git diff --stat 5146d46..HEAD -- pyproject.toml 'Dockerfile*' 'requirements*' packaging
  src/chimera/__init__.py` is empty, so a second battery would re-measure a byte-identical
  install premise. This tick changed no install-relevant path.

## Considered and deliberately NOT filed

- **`answer_degraded` stays `false` when a worker is budget-dropped** — matches the documented
  contract (`EDGE_CASES.md:68-69` scopes it to the ANSWER stage), and `worker_failures` /
  `chimera_worker_failures` carry the fact on both machines surfaces. Filing it would be arguing
  with the spec, not with reality.
- **`/health` `commit` field differing between two processes** — the long-running `:8765`
  reported `5146d46`, a scratch boot reported `fd5afa1`, a later one `c62eecf` (= HEAD). I could
  not establish whether the field is baked per process, per checkout, or read live at request
  time, so it stays an observation here rather than a row.
- **`X-Chimera-Timeout` being undocumented** — checked before filing: CONFIG.md:322-323 *does*
  document it (an earlier grep in this session missed it). The remaining defect is behavioural
  (116/117), not documentary.

## Install leg

SKIPPED-INSTALL-CHIMERA-V2-20, with the reasons above. The install *premise* is unchanged this
tick; the proof remains run 28's committed battery. Nothing about repo visibility, permissions or
credentials was touched.

## Artifacts

- `.coding-hermes/evidence/chimera-v2-dogfood-2026-11-16-05-02-33/run30-budget-perf/` — `a0.json`
  (cold full trace), `a1.json` (per_stage=3 arm), `r2.json`/`r3.json`/`r5.json`/`r7.json` (REST
  arms), the three scratch configs and `stub_provider.py`, so every number above is replayable
  without the live config.
- Board rows: DF-CHIMERA-V2-116, -117, -119, PERF-2, SKIPPED-INSTALL-CHIMERA-V2-20.
- `.coding-hermes/dogfood-log.md` run-30 entry.

## Verdict

**PROMISING-BUT-ROUGH.** The budget mechanism itself is honest and precise (dropped stage survives,
2.05 s when asked for 2 s, a 400 when the ceiling is exceeded, worker failures visible on both
REST surfaces, CLI warning line intact). The rough edges are all around it: the per-request knob is
wired into exactly one of the two REST endpoints and silently no-ops there, a typo in it silently
buys nothing, and the *unrelated* dispatcher call — the largest single cost in every explicit-
formation run — is invisible in user-facing docs.
