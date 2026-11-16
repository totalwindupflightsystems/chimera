# Run 28 — the operator's view: can you tell a healthy panel from a broken one?

- **Lane:** `chimera-v2-dogfood-2026-11-16-05-02-33` (skill-driven dogfood, no driver script)
- **Target:** `/home/kara/chimera-v2` @ `5146d46` (== `origin/main`), running service `127.0.0.1:8765` reporting `commit=5146d46 version=0.2.9` (CODE-CURRENT)
- **Surface:** the monitoring/operations plane — `GET /metrics`, `GET /v1/health`, `GET /v1/health/ready`, `GET /v1/health/live` as an operator actually drives them
- **Verdict:** `PROMISING-BUT-ROUGH` — the service can be watched, but the watch surface cannot see the failure mode the product is built around (a panel whose models did not answer), and the documented readiness probe fails a rollout gate.

## Why this surface

`/metrics` appears **zero** times in runs 1–27 (`grep -l /metrics docs/dogfood/*.md` → no files). Every previous run judged deliberation, install, MCP, the web stream or the SDK surface; none judged the thing an operator stares at after the deploy. The promise under test, in the project's own words (`docs/operations.md`, "The three signals that matter"):

> `rate(chimera_requests_total{status="5xx"}[5m])` — a rising 5xx rate is the only early warning that upstream providers are failing.

That sentence is the claim this run tested against real traffic.

## What a real user did

1. Inventory of the live service: `/health` → `{"status":"alive","uptime_models":48,"commit":"5146d46","version":"0.2.9"}` in **2.769 ms**; `/metrics` → 200, 7,681 B in **1.739 ms**; `/v1/models`; `/web/`; `/v1/formations`.
2. Ran a real deliberation: `POST /v1/deliberate {"prompt":"In one sentence: what is the capital of France?","formation":"simple"}` → **200 in 10.897 s**, answer `The capital of France is Paris.`, clean trace.
3. Probed the documented error arms: unknown formation → **422 in 1.297 ms** with `{"detail":"Unknown formation: no-such-formation"}` (exact); `worker_model: "nonexistent/bogus-xyz"` → **400** naming the catalog rule (exact); `stage_models: {"worker_1": "nonexistent/bogus-model"}` → **400** naming the field and the fix (exact); `allowed_models: ["nonexistent/bogus-xyz"]` → **500 `Internal Server Error`** (row `DF-CHIMERA-V2-110`).
4. Built a **controlled degradation** rather than waiting for a provider to fail: started a second instance from the same tree with `GEMINI_API_KEY=invalid-key-for-dogfood-probe` (no real credential minted, no config edited) and ran `formation=simple, worker_model=google/gemini-3.5-flash` so the panel's workers must fail while the aggregator still answers. Result: **HTTP 200 in 9.078 s**, answer `The capital of France is Paris.`, and `trace.worker_failures` carries **2 entries** (`worker_1`, `worker_2`, both `provider 'google' rejected the credentials or none were found`) — 0 of 2 workers contributed, the answer is the aggregator alone.
5. Scraped `/metrics` after that fully-degraded run: `chimera_requests_total{method="POST",route="/v1/deliberate",status="2xx"} 1`, one duration observation at 9.08 s, **no** `chimera_request_errors_total` series, and a grep of the whole payload for `fail|degrad` matches only the HELP text. The operator cannot see it (row `DF-CHIMERA-V2-111`).
6. Adversarial cardinality probe: 25 requests to `/v1/models/garbage-$i/nested/path`, then `/metrics` again (7,681 B → 10,543 B). No per-path `route=` label was created; all 25 landed on `route="<unmatched>"` with `status="4xx"`. **Label cardinality is safe** — credit where due.
7. Drove the web surface (`POST /web/sessions` → `GET /web/sse/{id}?live=1`) and held one connection open: **20.002672 s** of wall clock for an idle stream, recorded in `chimera_request_duration_seconds{route="/web/sse/{session_id}"}` — i.e. in the same histogram the docs point the latency alert at (row `DF-CHIMERA-V2-112`).
8. Measured the health plane warm and cold, then found the one provider that pays for it (below).
9. Install leg on a clean bunker machine (below).

## Findings

| row | P | what |
|---|---|---|
| `DF-CHIMERA-V2-110` | P2 | `allowed_models` is never validated against the catalog: a typo returns **500 plain-text `Internal Server Error`** (7.99 s) while `worker_model` and `stage_models` both return an actionable **400** for the same class of mistake. |
| `DF-CHIMERA-V2-111` | P2 | `/metrics` is blind to degradation: 2/2 worker failures still read as one clean `2xx`. No formation/outcome/worker-failure metric exists anywhere in `metrics.py`, so the documented signal #1 ("rising 5xx is the only early warning") cannot catch the product's dominant failure mode. |
| `DF-CHIMERA-V2-112` | P3 | SSE connection lifetime is measured as request duration, so the unscoped `histogram_quantile(0.95, …)` the docs recommend tracks how long a user kept a tab open (measured 20.00 s for one idle stream); buckets top out at 60 s, so longer sessions clamp into `+Inf`. |
| `PERF-1` | **P1** | `/v1/health/ready` — the documented readiness probe — answers in **11.03 s / 11.00 s** on consecutive calls, uncached, because the endpoint's latency is the slowest provider probe (`hermes`, `error_class=slow`, `latency_s=11.007`). |

## Perf (Step 2b) — numbers first

Headline operation for an operator is "is this thing up and healthy", not the deliberation (whose 9–11 s is provider-bound and already documented across runs 1–27 as model latency, not Chimera cost).

| operation | cold / uncached | warm / cached |
|---|---|---|
| `GET /health` | 0.071883 s (first) | 0.002082–0.002769 s |
| `GET /v1/health/live` | 0.002082 s | 0.002082 s |
| `GET /v1/health` | **4.535, 5.270, 11.008, 10.291, 2.633, 11.010 s** (n=6, all 200) | 0.000923–0.002405 s (n=5) |
| `GET /v1/health/ready` | **11.026457 s, 11.004615 s** (consecutive, uncached) | no cache — always re-probes |
| `GET /metrics` | 0.001739 s @ 7,681 B | 0.003539 s @ 10,543 B |

Attribution instead of a flamegraph: `details.providers.hermes` carries `error_class="slow"`, `latency_s=11.007` on the same response, while every other provider answers or fails instantly (`cliproxy` → `missing_credentials`, no network call). `_check_providers` (`src/chimera/api/server.py:1901`) probes concurrently under `config.server.health_timeout_s` (default 10.0 s), so **endpoint latency = max(provider probe)**. `_ProviderHealthCache` (`src/chimera/api/server.py:884`, `ttl_s=60`) hides it for `/v1/health` only, and 60 s is exactly the interval a monitor naturally polls at — so a 60 s poller pays the full wait nearly every call.

Profiling was not justified beyond this: the cost is one bounded upstream probe, not a hot loop, and the response payload already names the culprit with its own latency number. The fix is not micro-optimisation, it is "do not let one slow probe define the readiness answer".

**Why P1 rather than P3:** `docs/operations.md:59-62` tells operators to use `/v1/health/ready` as the readiness probe. That endpoint answers in ~11 s on every call on this deployment, so a `readinessProbe` (Kubernetes default `timeoutSeconds: 1`) or a compose healthcheck with a 5–10 s timeout marks a **healthy** service unready and blocks the rollout it gates. Container healthchecks are unaffected — the Dockerfile uses `/v1/health/live` (2.1 ms).

## What held (credit, measured)

- `/health`, `/v1/health/live` are fast and carry build identity (`commit` + `version`), which made CODE-CURRENT verification trivial.
- `/metrics` is cheap and cardinality-safe: 25 hostile paths produced **zero** new `route=` series and a single `<unmatched>` bucket.
- Error contracts are exact where they exist: unknown formation **422** with the offending name, `worker_model` **400** with the catalog rule and the doc pointer, `stage_models` **400** naming the field. Two of three model-selecting fields are best-in-class; only `allowed_models` is not.
- Degradation is *graceful*: with 2/2 workers dead, the caller still got a correct answer in 9.08 s and a full `trace.worker_failures` record. The product hides the failure from the **monitoring** plane, not from the caller — the fix is a metric, not a redesign.
- `/v1/health`'s `credential_sources` and `error_class` fields (from earlier waves) are exactly what let this run name the culprit provider in one call instead of an hour of log reading.

## Deployment parity

Running process reports `commit=5146d46`; `git rev-parse HEAD` = `5146d46` = `origin/main` (`git rev-list --left-right --count HEAD...origin/main` → `0 0`). **CODE-CURRENT**, no deferral needed. Two tracked files were already dirty in the checkout and were left untouched and uncommitted by this lane: `docker-compose.yml` (default models `deepseek-v4-pro` → `deepseek-flash`) and `reports/model_sync_weekly.md` (regenerated report).

## Install leg (fresh machine)

`bunker-qa.sh launch /home/kara/chimera-v2` → agent `951ddc07` on **bunker-mvp** (ttl 4 h), evidence `/tmp/bunker-qa-evidence-20261116T053209Z-1630941.jsonl`. Cells observed OK on the clean machine: `launch`, `toolchain-bootstrap` ×5 (go 1.27.4, python venv + pytest, gcc/g++, make, jq), `fresh-install` (full dependency resolution + editable install), `lint` (`ruff check .` rc=0), `tests`. The remaining battery cells (act CI, docker-deploy, ui-probe, chaos) were still running when this tick's artifacts were written; see the log entry for the final state.

## Diagnostics trail

| artifact | contents |
|---|---|
| `/tmp/ch_health.json` | live `/health` body (commit/version) |
| `/tmp/ch_metrics.txt` → `/tmp/metrics_after_scan.txt` | `/metrics` before vs after 25 hostile-path probes (7,681 → 10,543 B) |
| `/tmp/s_degraded.json` | the 200-with-2-failed-workers response (`trace.worker_failures`) used for `DF-CHIMERA-V2-111` |
| `/tmp/s_am1.json` | the 500 from `allowed_models` (`DF-CHIMERA-V2-110`) |
| `/tmp/ch_8902.log` | instance log showing the unhandled exception behind that 500 |
| `/tmp/s_h3.json`, `/tmp/s_h8902.json` | `/v1/health` payloads with `hermes` `error_class=slow latency_s=11.007` |
| `/tmp/bunker-qa-evidence-20261116T053209Z-1630941.jsonl` | fresh-machine battery evidence |

Scratch instances used for controlled probes: `8901`, `8902` (bad `allowed_models`, readiness timing), `8903` (`GEMINI_API_KEY=invalid-key-for-dogfood-probe` to force worker failure). No repository code, config, or board row was edited except appending the four findings rows below.

## Rows filed

`DF-CHIMERA-V2-110`, `DF-CHIMERA-V2-111`, `DF-CHIMERA-V2-112`, `PERF-1` — minted with `board_next_id.py` (DF family → 110–112, `PERF` family → `PERF-1`, both families free beforehand), appended via `boardctl create`, verified on disk (`jq` readback, `boardctl validate` → `RESULT: OK (361 warning(s))`, the pre-existing baseline), no duplicate ids.

## Addendum (run 28, cell closure)

The install-leg cells still running when the run-28 report was written have since finished; they are
closed here from the collected logs (no re-run, no code change). Evidence:
`.coding-hermes/evidence/chimera-v2-dogfood-2026-11-16-05-02-33/install-bunker-951ddc07/`
(`qa-evidence.jsonl`, `qa-run.log`, `qa-logs/qa-logs-3012060/`).

### What actually works (live, first-hand)

The documented compose path, which the battery graded UNVERIFIED, serves on the clean machine:

| probe | result |
| --- | --- |
| `docker ps` | `chimera` Up 9 minutes (healthy), `0.0.0.0:8765->8765/tcp` |
| `GET /v1/health/live` x3 | 200 in 2.87 / 3.08 / 2.43 ms |
| `GET /v1/health` | 200 in 4.15 ms |
| `POST /v1/deliberate` (no credentials) | 502 in 7.19 s, body names `DEEPSEEK_API_KEY` and `providers.deepseek.api_key_env` |

The 502 leg is the useful product evidence: an unconfigured deployment comes up healthy and fails
honestly with an actionable remedy instead of answering with the upstream error (the run-19
`DF-CHIMERA-V2-71` shape). Nothing to fix on this path.

The 2.4-4.2 ms health numbers are *not* a counter-example to `PERF-1`: with every provider missing
credentials the probes short-circuit, so the unconfigured path never reaches the slow-provider wait
that `PERF-1` measures. Hence no new PERF row from this addendum.

### Cell verdicts that contradict their own logs

| cell | reported | its own log says |
| --- | --- | --- |
| `chaos-shutdown` | OK | `sd.log` (all 6 lines): `UP=0 STOP=0 RESTART=0 KILL=0 KILLRECOVER=0 DOWN=0` — nothing was operated |
| `chaos-disconnect` | UNVERIFIED | `disc.log:1` = `NETWORK_CUT_APPLIED`; the hosted suite ended 2178 passed / 67 skipped |
| `docker-deploy` | UNVERIFIED | serves, per the table above |
| `ci-pass` (act) | red | `ci.log` holds no step stdout at all, so no failing test is named; `lint` died at `ci.log:65` on `ln: failed to create symbolic link 'python': File exists` (setup-python 3.11 toolcache race between the lint job and matrix leg test-1, an act-only condition) |

`ci.log:126/131/136` are the three matrix legs (3.13 3m26.19s, 3.11 3m34.43s, 3.12 3m43.50s), each
`exitcode '1': failure`. They are **unattributable**, not "the product is red": the same battery
reported `toolchain-bootstrap` x5, `fresh-install`, `ruff` (rc=0), the native suite and `docker_build`
all OK, and run 26 measured 2163 passing tests on a real interpreter at this line of code.

### Left behind

Container `chimera` still running on agent `951ddc07` with port 8765 published; the agent was **not**
destroyed and the stack was **not** torn down — `docker compose down` and agent destroy are
destructive and this lane is read-only, so both were left for the foreman. Nothing outside
`.coding-hermes/` and `docs/dogfood/` was touched.
