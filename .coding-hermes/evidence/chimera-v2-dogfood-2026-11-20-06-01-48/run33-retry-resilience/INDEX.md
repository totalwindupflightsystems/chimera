# Run 33 evidence — retry / rate-limit resilience (tick chimera-v2-dogfood-2026-11-20-06-01-48)

Read `REPORT.md` first. Every file here is raw output; nothing is a summary of a run that
was not executed.

## Probes (re-runnable)

| File | What it is | How to re-run |
|------|-----------|---------------|
| `stub429.py` | OpenAI-compatible upstream that answers N×429 (optional `Retry-After`) then 200, and appends `{"t": <seconds since stub start>, "status": …}` per arrival to a JSONL log | `python3 stub429.py 18081 <fail_budget> <log.jsonl> 429 [retry_after]` |
| `fixture.yaml` | Chimera config pointing provider `mock` at `http://127.0.0.1:18081/v1`; the only variables are `retry.*` | `CHIMERA_CONFIG=$PWD/fixture.yaml …` |
| `probe_retry.py` | In-process arms against `LiteLLMGateway.complete`: `always429:<n>` (max_attempts sweep) and `concurrent:<n>` | `python3 probe_retry.py always429:3` / `python3 probe_retry.py concurrent:4` |
| `probe_cfg.py` | Prints the *effective* resolved retry config and the client kwargs the gateway passes | `python3 probe_cfg.py` |
| `retry_after.sh` | Served-API arm that varies only the `Retry-After` header (`<ra> <budget> <outprefix>`) | `bash retry_after.sh 5 2 ra5` |

## Raw results

| File | Arm | Rows / what to read |
|------|-----|--------------------|
| `att1.out`, `att5.out` | max_attempts 1 / 5 against always-429 | arrival table + gap column (3 / 15 arrivals) |
| `t2_persistent.jsonl`, `t2_persistent.out` | always-429, 2 attempts, persistent | arrival timestamps on the stub clock |
| `t4_concurrent4.jsonl`, `t4_concurrent4.out` | 4 concurrent callers | 36 arrivals; the quartet gaps are the jitter finding (DF-127) |
| `api_clean_cold.json`, `api_clean_warm.json` | served `/v1/chat/completions`, no failure | 0.1048s / 0.1117s |
| `api_blip.jsonl`, `api_blip_warm.json`, `api_battery.log` | 2×429 then 200 on the served API | 429 @0.9615, 429 @1.9636, 200 @2.9662; HTTP 200 in 2.1077s |
| `api_down.jsonl`, `api_down_warm.json` | provider hard-down | 502 after 30.03s, 36 upstream requests |
| `p1.out` | served clean-arm request log | zero `gateway_retry` lines |
| `ra1.*`, `ra5.*` | `Retry-After: 1` vs `5` | walls 2.113065s / 10.113688s; gaps 1.0017/1.0015s and 5.0032/5.0055s |

## Install leg

| File | What it is |
|------|-----------|
| `install-battery.jsonl` | 26-cell `bunker-qa.sh` battery from a clean machine (bunker-mvp agent `ca76265a`), harvested after `CELLS-DONE`: fresh-install OK, tests OK (2234 passed / 67 skipped / 188.82s), lint OK, docker_build OK, upgrade OK; `ci-pass` FAIL is `act` dying inside `docker exec … setup/index.js` (infra, graded UNVERIFIED, not filed) |

## Notes

* All timings that matter are the **stub's** timestamps, not Chimera's — the client logs nothing
  about retries (that is DF-128).
* The tree was dirty from a concurrent writer during measurement; the retry region in
  `src/chimera/gateway.py` was diffed HEAD-vs-worktree and is identical, so these numbers describe
  HEAD `f47c0e4`.
