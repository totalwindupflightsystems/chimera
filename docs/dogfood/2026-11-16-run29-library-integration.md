# Run 29 — the in-process Python API (2026-11-16)

Tick: `chimera-v2-dogfood-2026-11-16-05-02-33` · surface: `from chimera import
Engine, LiteLLMGateway, load_config` (README.md:116-134) · build: the product code
measured here is HEAD `1638f7a` as it stood when the probes ran, identical to the
published `chimera-deliberation 0.2.9` (PyPI `info.version == 0.2.9`; every commit
since the run-28 pin `5ec04dd` touches only board, docs, evidence and skills, and
the sibling commits that landed during this fire — `792b17e` board-only, this run's
own commit — add no product path).

## Promise (null hypothesis)

> A Python user writes four lines — `load_config()`, `Engine(config,
> LiteLLMGateway(config))`, `await engine.deliberate(prompt)`, `result.answer` —
> and gets a multi-model answer **inside their own process**, with the same
> formation selection, cost accounting and observability the CLI/REST surfaces
> offer.

Twenty-eight prior runs drove the CLI, REST, SSE, MCP, web UI, Docker, PyPI wheel,
idempotency, custom DAGs, the task-router registry and `/metrics`. None of them
ever imported the package: `grep -c "in-process\|import chimera"` on
`.coding-hermes/dogfood-log.md` returns 0. This run is that leg.

## What was actually built (not a test)

`panel_review.py` (+ `buggy_target.py` in
`.coding-hermes/evidence/chimera-v2-dogfood-2026-11-16-05-02-33/library-consumer/`)
is a real tool a user would write: it reads a file, hands it to the panel as a
code review, and prints the verdict. The file under review is a 60-line
`TTLCache` with one planted logic bug (`invalidate()` calls `dict.get()` and
discards the result, so an invalidated key keeps being served until its TTL
expires) plus four lesser real defects.

The four documented lines work exactly as printed. **The panel found the planted
bug**, named the method and line, proved the mechanism, and gave the correct
one-line fix — plus four lesser issues, all of which survive checking:

> Primary defect: `TTLCache.invalidate`, line 51 … `dict.get()` neither deletes
> nor mutates the mapping, so after `set('k', 1.0)` then `invalidate('k')`,
> `get('k', None)` still returns `1.0` and `stats()['size']` remains `1` until
> TTL expiry … Fix: replace line 51 with `self._data.pop(key, None)`.
> Lesser: `None` default vs cached `None`; `set()` evicts before checking whether
> the key already exists; `capacity <= 0` reaches `_evict_one()` and raises
> `ValueError` from `min()`; `_evict_one()` is TTL-order, not LRU.

That is a genuinely useful reviewer, and it is the reason this run's value verdict
is positive rather than a formality. Cold cost of one 35-line review through
`formation=auto`: **222.1 s**, 5 stages (3 workers → aggregator → auditor),
26,686 worker/aggregator tokens, `trace.worker_failures=[]`. The fastest worker
answered correctly in 14.5 s; the other two were redundant opinions, and
`deepseek-v4-pro` alone took 144.2 s. Every second of that wall is model-bound:
the sum of the stage latencies accounts for the whole run, and no Chimera
function appears as a hot path (so no PERF row was filed — see "Perf" below).

## Measured numbers (two independent sweeps, same prompt, same config)

Prompt for every arm: `Reply with exactly: PONG`. Config:
`CHIMERA_CONFIG=/home/kara/chimera-v2/chimera.yaml` (the live config), loaded in
a scratch cwd outside the repo. Machine-written record:
`library-consumer/run29-evidence.json`.

| arm | wall | cost | tokens | stages | stdout | stderr |
|---|---|---|---|---|---|---|
| lib `deliberate(p, "auto")` | 13.4 s | $0.004016 | 22,162 | flash 1,120 ms · gpt-5.6-luna 1,959 ms · agg flash 2,246 ms | **6,310 B (10 info + 5 debug lines)** | 0 B |
| lib `deliberate(p, "simple")` | 38.3 s | $0.008821 | 25,648 | **deepseek-v4-pro 28,647 ms** · deepseek-v4-pro 13,859 ms · agg flash 1,515 ms | **7,706 B (9 info + 5 debug)** | 0 B |
| lib `deliberate(p, "speed")` | 12.0 s | $0.004312 | 23,344 | flash 2,633 ms · qwen3-coder 456 ms · agg flash 1,446 ms | **7,361 B (9 info + 5 debug)** | 0 B |
| CLI `--quiet` (default formation) | 30.7 s | — | — | — | **5 B (`"PONG\n"`)** | 2,841 B |
| CLI `--json` (default formation) | 18.2 s | $0.004340 | 22,763 | — | 10,946 B, 0 log lines (valid JSON) | 2,845 B |

Sweep A (earlier probes in the same fire) reproduced the same shape: auto
18.9 s / $0.004388, simple 44.7 s / $0.007801, speed 17.7 s / $0.004732, CLI
`--quiet` 5 B on stdout with 2,651 B on stderr. The preset ranking and the stdout
split are stable across sweeps; individual walls move with provider latency, which
is why the ratios — not the absolute seconds — are the claim.

The loaded config in every library arm is
`{"log_level": "warning", "use_stdout": false, "trace_enabled": true}`.

## Finding 1 (DF-CHIMERA-V2-113, P2) — the in-process API ignores `observability`

`docs/CONFIG.md:722-723` documents two knobs: `log_level` (default `info`) and
`use_stdout` (default `true`, "false = stderr"). The live config sets
`log_level: warning` and `use_stdout: false`. Inside the process, neither takes
effect: every library arm above wrote **info *and* debug** lines to **stdout**
(10 info + 5 debug in the auto arm) and **zero bytes** to stderr.

The CLI, loading the same file, honours both — 5 bytes on stdout, 2,841 on stderr,
no info or debug lines on stdout. So the contract holds on the CLI surface and
silently fails on the library surface, which is the surface the README puts first
for Python users.

Consequence for a consumer: `print(json.dumps(review))` to stdout is corrupted by
~7 KB of log lines, and at `log_level: debug` the same stream carries full worker
prompts. Mechanism (from source, not guesswork): `configure_logging` is called
only from the CLI entrypoint — `src/chimera/cli/main.py:238` and `:257`
(`configure_logging(cfg.observability, force_stderr=True)`), defined at
`src/chimera/observability.py:38`. A consumer that builds `Engine` directly never
triggers it, so structlog's default print logger (stdout, verbose) governs.

Fix direction: apply `config.observability` when `load_config()`/`Engine` is
constructed, or make `configure_logging` part of the documented four-line recipe.

## Finding 2 (DF-CHIMERA-V2-114, P2) — `simple` is the most expensive preset, and it is the one the README shows

Same prompt, same process, three presets:

- `auto` — 13.4 s / $0.004016 (2 workers + aggregator, cheapest models that fit)
- `speed` — 12.0 s / $0.004312
- `simple` — **38.3 s / $0.008821**, 2.4-2.9x the wall and 1.8-2.2x the cost of
  `auto` across the two sweeps

Cause, measured from the trace and the config: `formations.simple` is
`workers: 2` + `aggregator: default`, and the default worker is
`defaults.default_worker: deepseek/deepseek-v4-pro` (`chimera.yaml:11`), so
"simple" means two of the most expensive worker models in the catalog. `speed`
pins cheap models explicitly and `auto` plans adaptively; `simple` is the only
preset whose name reads "cheap" and whose behaviour is "premium".

`README.md:37` is where a new user learns formations exist:
`chimera --formation simple "Compare …"  # pick a formation`. Nothing in the
README or `docs/USAGE.md` compares preset cost, and nothing says `auto` — the
library's default — is the cheaper choice for a one-line answer.

Fix direction (docs-first, no behaviour change implied): name the cost shape of
each preset in the README quickstart and point the "pick a formation" example at
`speed`/`auto`; if `simple` is meant to be the cheap default, resolve its workers
from a cheap tier instead of `default_worker`.

## Finding 3 (DF-CHIMERA-V2-115, P3) — the library recipe hides the parts a real consumer needs

README.md:116-134 is the only documentation of the Python API, and it stops at
`print(result.answer)`. A consumer that has to account for money, correlate
requests or configure logging is on their own:

- `result` has **no** `total_cost` and **no** `request_id` (measured
  `hasattr` → False for both). They exist one level down:
  `result.trace.total_cost` ($0.004016 in the auto arm), `result.trace.request_id`,
  `result.trace.total_duration_ms`, `result.trace.worker_failures`. The 2026-08-13
  integration report recorded a library run returning `$0.003`, so the field moved
  and the README never followed.
- The library's default formation is **not documented** anywhere. Measured: the
  one-argument call runs `formation=auto, source=auto` (NOT `simple`, which is the
  `smoke_live.py` default the README's nearby line refers to). `docs/EDGE_CASES.md:17`
  shows a second call shape (`deliberate(p, "auto")`); both work, and that
  inconsistency between the two docs is the only hint a formation argument exists.
- Nothing in the library recipe mentions that logs land on stdout (Finding 1) or
  that `~/.chimera/blocked-models.json` is machine-scoped outside a repo checkout
  (an import-time `UserWarning` says so, but the recipe never does).

## Install leg

**Not re-run, deliberately — and not a silent pass.** The same tick already proved
installability on a clean machine: agent `951ddc07` on `bunker-mvp`, full battery
(launch, toolchain bootstrap ×5, fresh-install, lint, tests, docker-build OK) with
all 27 evidence files committed at
`.coding-hermes/evidence/chimera-v2-dogfood-2026-11-16-05-02-33/install-bunker-951ddc07/`,
and the agent destroyed in the run-28 closeout. The install **premise** is
byte-identical now — `git diff --stat 5146d46..HEAD` touches no product path — so a
second battery inside the same tick would re-measure the same tree. `bunker-mvp` is
reachable (4 agents listed this fire); the skip is my call, not a blocker. Filed as
`SKIPPED-INSTALL-CHIMERA-V2-19` so the leg is on the record either way.

Consequence for this run's claims: the library findings were measured against the
repo checkout (`0.2.9`, editable), and PyPI `info.version` is also `0.2.9` with a
published `0.2.9` release, so the product code exercised here is what
`pip install chimera-deliberation==0.2.9` gives a user.

## Perf

Nothing Chimera-owned is slow enough for a user to feel. Every arm's wall time is
accounted for by its own stage latencies (`trace.total_duration_ms` matches wall):
`load_config()` 0.30 s, `Engine(...)` 0.002 s, and the rest is provider latency.
The 222 s review and the 38 s `simple` call are the same fact twice — model
latency multiplied by dispatched stage count — so the honest record is a cost
finding (Finding 2), not a profile. No PERF row was filed; run 28's PERF-1
(`/v1/health/ready` pinned to the slowest provider) remains the only perf row and
its numbers still hold (`/v1/health` 5.96 s uncached, `/v1/health/ready` 2.6-5.4 s
on this fire, cheaper than the 11 s measured when the `hermes` provider was the
slowest probe).

## What a new user needs that still isn't documented

1. How to keep a library consumer's stdout clean (`observability.use_stdout`) —
   and that it currently doesn't work in-process anyway.
2. That cost/request_id live on `result.trace`, not `result`.
3. Which preset to pick for cost vs latency (and that `simple` is not it).
4. That the one-argument library call runs `auto`, whose stage count varies with
   the prompt — a 35-line file can cost 5 stages and 3.7 minutes.

## Repro

```bash
cd <scratch>            # outside the repo, so the machine-scoped fallbacks are visible
CHIMERA_CONFIG=/home/kara/chimera-v2/chimera.yaml \
  /home/kara/chimera-v2/.venv/bin/python \
  .coding-hermes/evidence/chimera-v2-dogfood-2026-11-16-05-02-33/library-consumer/run_evidence.py \
  /tmp/run29-evidence.json
```

`probe2.py`…`probe5.py` are the intermediate arms (result-field census, CLI/log
split, per-stage attribution, level counts); `panel_review.py` is the real-user
tool. Placeholder credentials only — nothing in the artifacts carries a key.

## Verdict

**PROMISING-BUT-ROUGH.** The promise holds where it matters most: four documented
lines, a real multi-model review, the planted bug found with a correct fix. What
does not hold is the seam around it — the observability config a Python user sets
is ignored, a consumer's stdout is corrupted, and the docs stop one field short of
what a library integrator needs. All three are small, local fixes; none of them
requires touching the deliberation engine.
