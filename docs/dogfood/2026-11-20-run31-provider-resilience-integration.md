# Run 31 — provider resilience: one dead aggregator costs the whole run

Tick `chimera-v2-dogfood-2026-11-20-06-01-48` · 2026-11-20 · build under test `d274585`
(origin/main == HEAD; the running service reports `commit=f0a34a2`, an ancestor with **0**
non-`.coding-hermes` product files changed since, so the deployed code is this code).

## The promise I tested

Two sentences a user can read for themselves:

1. **README:** one command gives you a multi-model deliberation answer, with the formation
   you named and a trace that says what it cost.
2. **`docs/operations.md`:** `/v1/health` is the "is the API working" endpoint and
   `/v1/health/ready` is the readiness gate you wire into an orchestrator.

Run 30 tested the timeout budget surface. This run tested the thing underneath it: **what
happens to a real deliberation when one provider in it is dead** — the ordinary failure a
self-hoster hits when a key runs dry, a plan caps, or a vendor has an outage.

## What I actually did

- Asked the CLI, exactly as documented, a real question a person would pay for (a
  Django/Postgres vs SQLite capacity decision with a $40/mo constraint), JSON output, four
  arms, wall-clocked with `date +%s.%N` around each invocation.
- Scraped the operator surface while a fresh instance was cold: `/health`, `/v1/health`,
  `/v1/health/ready`, `/metrics`, then a 420-second 1 Hz readiness poll.
- Built the wheel from HEAD and installed it into a clean CPython 3.14 venv, ran
  `chimera config init`, and ran a real deliberation from that install.
- Attempted the ephemeral-bunker install leg (`bunker-qa.sh`): SSH to the bunker host →
  `Permission denied (publickey,password)`. Filed as a **SKIPPED** row, not a pass.

## The numbers

| arm | formation / aggregator | wall | exit | degraded |
|---|---|---|---|---|
| run1 | `quick-panel`, aggregator `deepseek/deepseek-v4-flash` | 82,577 ms | 2 | yes |
| run2 | same, immediate retry | 186,852 ms | 2 | yes |
| survivor1 | dispatcher moved off deepseek, aggregator `qwen3.7-plus` | 113,729 ms | 2 | yes |
| survivor2 | aggregator `google/gemini-3.1-pro-preview` | 94,877 ms | 0 | no |

Worker output was produced and paid for in the three failed arms — e.g. run1's
`worker_1` consumed 441 input tokens in 4,446 ms, `worker_2` returned 309 output tokens,
`worker_3` 1,169 — and then thrown away, because the aggregator stage failed and the CLI
exits 2 with the failure text in the `answer` field. `src/chimera/cli/main.py:399-407` is the
`sys.exit(2)` on a degraded answer; nothing retries the aggregator on another provider.

CLI startup (warm, three runs): **0.311 / 0.313 / 0.374 s** — not a usability problem.
Steady-state readiness over 420 s: **367 probes, 0 x 503, mean 0.114 s, max 1.503 s**.
Cold-cache readiness on a fresh instance: `/v1/health` → 200 `healthy` in 1.519 s while
`/v1/health/ready` → **503** in 1.517 s (`in_flight: 13`, `unhealthy: 0`), reproduced 3/3.

## Findings (board rows the foreman works)

- **`DF-CHIMERA-V2-120` P1 — one dead provider destroys the whole deliberation.**
  Three of four real runs ended rc=2 after 83–187 s, discarding worker output already paid
  for, and the retry cost 2.3x the first attempt (82.6 s → 186.9 s) because backoff is not
  bounded by anything the user set. A fresh install hits the same wall on its first command:
  the `config init` default aggregator is `deepseek/deepseek-v4-flash`, so a new user's first
  `chimera run` fails in 10.7 s with `Insufficient Balance`. The mirror case is the proof of
  cause: the same prompt, same box, same hour, with a live aggregator answered cleanly
  (`survivor2`, 94.9 s, $0.082058).
- **`DF-CHIMERA-V2-121` P2 — trace token accounting trusts provider-reported usage.**
  `hermes/glm-5.3-flash` reported `tokens_input=149,511` for a **352-character** prompt —
  98.2% of the run's input tokens — and `trace` exposes no `total_tokens_input`/`output` to
  sanity-check it. Anything that meters, budgets or bills off the trace inherits that number.
- **`DF-CHIMERA-V2-122` P2 — `/v1/health` says healthy while `/v1/health/ready` says 503**
  on the identical cold cache, because the health math excludes in-flight providers and
  therefore reports green when *nothing is known*. An operator scraping the documented "is it
  up" endpoint sees healthy while the orchestrator keeps the pod out of rotation.
- **`DF-CHIMERA-V2-123` P3 — docs:** `operations.md` offers `/v1/health/ready` as a k8s
  readiness gate without saying to raise `timeoutSeconds` above the 1 s default, while the
  server's own probe budget is 1.5 s (`server.health_endpoint_budget_s`) — a copy-paste
  manifest fails its first probe.
- **`DF-CHIMERA-V2-124` P3 — a fresh install warns on every invocation**, including
  `chimera --version`: `blocked-models state outside any repo checkout: falling back to the
  machine-scoped ~/.chimera/blocked-models.json`. Harmless, but it is the first thing a new
  user sees, and it appears on stdout-adjacent streams that consumers parse.

## Install leg

**SKIPPED, and said so:** the ephemeral bunker leg cannot run from this box — the host
answers SSH but rejects this box's key (`Permission denied (publickey,password)`), and the
lane forbids minting a credential. Filed as `SKIPPED-INSTALL-CHIMERA-V2-21` with the probe
transcript.

Compensated locally with a genuinely fresh environment, which is why the P1 above has a
second, independent reproduction: `uv build` at HEAD → wheel installs into a clean 3.14 venv
with no repo on `sys.path` → `chimera --version` rc=0 → `config init` writes a working config
→ first real run reaches the provider seam and fails on billing, not on packaging. What this
does **not** prove: a machine with no Python and no `~/.hermes/.env` fallback — the fresh-venv
run still picked keys up from the dotenv fallback, so "works with no configuration at all"
stays unproven until the bunkerd leg runs.

## Performance

Nothing Chimera owns is slow enough for a user to feel: warm CLI start is 0.31–0.37 s, the
readiness probe is bounded at 1.5 s by design, steady-state p50 is 0.11 s, and every arm's
wall time equals the sum of its own provider latencies. **No PERF row was filed.** The one
number a user does feel — 82 s stretching to 187 s on retry — is a resilience/backoff defect
(row `-120`), not a profile target, and filing it as perf would have devalued the two real
perf rows already open.

## Artifacts

- `docs/dogfood/2026-11-20-run31-provider-resilience-integration.md` (this file)
- `.coding-hermes/evidence/chimera-v2-dogfood-2026-11-20-06-01-48/run31-provider-resilience/`
  — `INDEX.md` (re-run recipe), `cold-repro.log` + 6 raw health/ready payloads,
  `runs-summary.jsonl` (per-arm trace), `readiness-1hz-420s.tsv`, `install-local.txt`
- `skills/chimera-usage/SKILL.md` v1.17.0 Run-31 section
- `.coding-hermes/dogfood-log.md` run-31 entry
- board rows `DF-CHIMERA-V2-120/121/122/123/124`, `SKIPPED-INSTALL-CHIMERA-V2-21`

## Lessons

1. **Test the failure the operator will actually hit**, not the success path with a healthy
   provider set. Four arms of the same prompt differed by nothing except which provider held
   the aggregator stage — that is what turned "it failed" into "the aggregator has no
   fallback and the run's cost is already sunk when it fails".
2. **A traced `prompt` string is not the model's input.** The aggregator's traced prompt is
   68 characters (`merge stage 'aggregator' over upstream: worker_1..3`) while its reported
   input is 2,562 tokens — the upstream answers are passed out-of-band. Reading only the
   trace string would have produced a false "the aggregator never sees the workers" row.
3. **Exit code and payload disagree by design.** `answer_degraded` + rc=2 + a non-null
   `answer` field holding the error text is the real shape; "no answer" in a report must be
   written as "the answer field holds a failure placeholder", or the next reader thinks the
   field was empty and re-files a phantom.
4. **A probe that only runs once proves nothing about a flap.** The first cold 503 looked like
   a rolling readiness problem; 367 samples over 420 s showed it is startup-only, which
   changed the row from P1 "flapping gate" to P2 "cold asymmetry". Measure the steady state
   before naming a rate.
