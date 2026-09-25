# Chimera Diagnostics Trail (2026-08-03)

How the thing is built, why, the errors encountered on the way, and the right
way to run it. Written from a real-use dogfood run; not raw logs.

## What Chimera is and how it's built

**Architecture (from README/specs + observed behavior):**

```
User prompt
   → Dispatcher (ONE LLM call): designs the DAG — picks worker models by
     category weights (code/analysis/reasoning/design/audit), writes a scoped
     prompt per worker, writes aggregator merge instructions, writes an
     output_schema.
   → Workers (parallel LLM calls): each solves their scoped subtask.
   → Aggregator (LLM call): merges worker outputs using the dispatcher's
     instructions, honoring output_schema (JSON object with "answer").
   → Response + full trace (per-stage model, tokens, latency, cost).
```

- **Package layout:** `src/chimera/` — `engine.py` (orchestration),
  `dispatcher.py`, `aggregator.py`, `selector.py`, `gateway.py`
  (LiteLLM-backed), `circuit_breaker.py`, `api/` (FastAPI), `web/` (SSE UI),
  `cli/`. Config: `chimera.yaml` (67KB — model catalog + formations).
- **Providers:** LiteLLM with env-expanded keys (`api_keys: {deepseek:
  ${DEEPSEEK_API_KEY}, ...}`). On this deployment only `OPENROUTER_API_KEY`
  is set in `.env`, and every provider is routed through OpenRouter (health
  probe model strings confirm: deepseek→openai base, google→gemini base).
- **Key config knobs observed live:** `lock_aggregator: true` (config wins
  over request `aggregator_model`), `default_aggregator:
  deepseek/deepseek-v4-flash`, `default_worker: deepseek/deepseek-v4-pro`,
  `provider_discovery: true` (LiteLLM catalog refresh, 5309 models).
- **Board:** foreman migrated to a DuckDB board (BOARD-V2, tick #64) —
  `.coding-hermes/board/{board.db,tasks.parquet,events.parquet,schema.sql}`;
  `tasks.md` archived to `tasks.md.bak`. Tasks are rows in the `tasks` table
  (id/title/status/priority/complexity/reasoning/foreman_note/...).

## Errors encountered during real use, explained

1. **"Missing credentials. Please pass an `api_key` ... or set the
   `OPENAI_API_KEY` ... environment variable"** — every stage on the REST
   server. Root cause: the `serve` process env lacks the keys that the CLI
   and MCP processes have (they load `.env`). Not a code bug per se — a
   deployment/credential-injection bug: three entry points, three different
   env behaviors. The right way: one credential-loading path shared by all
   entry points (dotenv in `serve` too).

2. **HTTP 200 with `[stage X unavailable: ...]` as the answer** — when the
   answer stage fails, the API serializes a placeholder string into the
   response and returns 200. Why it exists: "graceful degradation". Why it's
   wrong: OpenAI-compat clients can't distinguish this from success; usage is
   all zeros; the error is stringly-typed. The right way: 502 + structured
   `{"error": {...}, "request_id": ...}` when no answer exists.

3. **`/v1/health` degraded + `/v1/health/ready` 503 "Not ready"** — probes
   fail for different reasons than real calls: openrouter 401 (probe env lacks
   the valid key the engine uses), anthropic `claude-opus-4.8` rejecting
   `temperature=0.0` (probe sends a param the model forbids), google
   `LLM Provider NOT provided` (probe model string not mapped), deepseek/zai
   missing creds (probe env again). The right way: probes should reuse the
   engine's gateway/credential path with provider-valid params — or report
   "unknown" instead of "unhealthy" when the probe itself can't run.

4. **`dispatcher_parse_failed: dispatch produced no aggregator/merge/audit
   stage`** — the dispatcher LLM emitted a valid-looking DAG whose `stages[]`
   omitted the aggregator (only `edges` referenced it). The engine detected
   it and fell back to a preset (`source=fallback`, 1 worker). This is the
   resilience design working: the dispatcher is "one call designs everything",
   so when that one call is malformed, the whole design is suspect — fallback
   is the correct response. The gap: the user only sees `source=fallback`,
   not why.

5. **`This response_format type is unavailable now`** (deepseek via openai-
   compat endpoint) — `json_object` mode rejected; engine retried plaintext
   and succeeded. Circuit-breaker/retry design working as intended.

6. **OpenRouter 404 `No endpoints available matching your guardrail
   restrictions`** — account-level privacy setting blocks a model the
   dispatcher picked (qwen3.7-plus). Not a chimera bug; a discovery gap: the
   catalog lists models the account cannot actually reach, and the dispatcher
   has no availability signal. `aggregator_partial_inputs degraded=1
   healthy=1` shows the engine merging with fewer inputs — by design.

7. **HTTP 422 on `/v1/deliberate` with `messages`** — schema wants `prompt`.
   OpenAPI (`/openapi.json`) is the source of truth; README's curl example
   only covers `/v1/chat/completions`.

## The right way (summary)

- **Run:** `set -a; source .env; set +a; chimera serve` (or use the CLI/MCP
  which already do this). Verify with `/v1/health/ready` → then still sanity-
  check with one real `/v1/deliberate` (health can lie).
- **Consume:** MCP `chimera_deliberate` for agents; CLI for humans; REST once
  creds are fixed. Never trust a 200 without checking content for
  `[stage ... unavailable`.
- **Extend:** formations are YAML in `chimera.yaml` (see `speed`/`spec-writer`
  presets); custom DAGs at request time need `allow_custom_dag=true` +
  `formation="custom"`.
- **Board:** tasks live in `.coding-hermes/board/board.db` (DuckDB, table
  `tasks`); the foreman reads that table each tick.

## Built/observed facts for the curious

- Dispatch calls consume ~17k input tokens (catalog in context) → ~$0.003
  floor per run; observed totals $0.003–0.019 for small prompts.
- MCP server (`chimera-mcp`) runs from the Hermes venv with the repo's
  `chimera.yaml`; it exposes 4 tools (deliberate/formations/models) and 0
  resources/prompts — tools-only is fine for its purpose.
- `chimera.__version__` now derives from pyproject.toml via dist metadata
  (was drifted at 0.1.0 vs pyproject 0.2.0 — fixed by dogfood-version-drift).

---

# Diagnostics Trail — 2026-08-13 (second dogfood run)

Follow-up to the 2026-08-03 trail. Same deployment, current `main`. The big
news: the engine-level P0s from run 1 are genuinely fixed in code (verified
by real use, see integration report). What remains is deployment + packaging.

## What changed since run 1 (verified, not assumed)

- `/v1/health` now runs REAL probe calls and reports honestly: on a fresh
  server it returned `healthy` with all 12 configured providers probed
  (openrouter, zai, anthropic, deepseek, google all tested live). The old
  "all providers down" lie came from the *old* server binary (see zombie).
- Bare `GET /health` → 200 `{"status":"alive","uptime_models":N}` (CH-GAP-022).
- `/v1/deliberate` returns clean HTTP 400 JSON for unknown models.
- Full pytest: 648 passed / 62 skipped in 17.5s — the foreman's "suite green"
  claim is real and fast. The 2026-08-03 "1 pricing-drift baseline fail"
  is gone (tests now hermetic — CH-GAP-021).
- `chimera run` no longer logs `response_format ... unavailable` retries
  (CH-GAP-024: deepseek removed from the json_schema providers; aggregator
  does one plaintext call).

## The zombie server (root cause of "server still broken" reports)

`ps aux` showed PID 21212: root-owned `/usr/local/bin/python3.11
/usr/local/bin/chimera serve --host 0.0.0.0 --port 8765`, started **Aug 2** —
i.e. pre-fix code, running as root, no provider creds. Every health/deliberate
curl against :8765 (the README's documented port) hit THIS process, which
exhibited the exact run-1 P0s. A new `chimera serve` cannot bind ("address
already in use"). The fixes were invisible because the fixed code never got
the port. **Lesson: a "server broken" finding must first check WHICH process
owns the port — stale long-running processes outlive their code.** Also:
`:8766` is squatted by another fleet app (off-by-one), so port hygiene is a
fleet-wide concern; use `ss -tlnp | grep <port>` before assuming your server
is the one answering.

## `chimera mcp` argv bug (root cause, explained)

`src/chimera/mcp/server.py run(config_path=None)`:
```python
if config_path is None and len(sys.argv) > 1:
    # treats argv[1] as a config path
```
The click subcommand `cli/main.py:286` calls `run_mcp(ctx.obj.get("config_path"))`
— which is `None` when no `-c` flag was given. So `run()` looks at
`sys.argv = ["chimera", "mcp"]` and tries to open the file `"mcp"` →
`FileNotFoundError: 'mcp'`. The standalone `chimera-mcp` console script calls
`run()` with `sys.argv == ["chimera-mcp"]`, `len(argv)==1`, so it falls back
to `find_config_path()` and works. **Right way:** the click wrapper must pass
the *resolved* path (or a sentinel ≠ None) so `run()` skips argv parsing, or
`run()` should ignore argv entries that match known subcommand names.

## Bare-wheel import crash (root cause)

`chimera/__init__.py` imports `chimera.web.trace_viz` unconditionally →
`chimera.web.routes` → `from fastapi import ...`. `fastapi` is only in the
`[server]`/`[full]` extras, so `pip install chimera-deliberation` (base) gives
you an import that crashes on line 1. **Right way:** defer the web imports
(lazy import inside the `serve` path) so the base package is self-contained,
and add a test that imports `chimera` from a bare wheel install.

## chat/completions silent model substitution

The chat/completions path does not validate `model` against the catalog;
unknown names fall through to auto-selection and the request is answered by a
different model with HTTP 200 (17k tokens billed). `/v1/deliberate` validates
(stage models checked → 400). The two paths drifted. **Right way:** validate
`model` in the OpenAI-compat path too; return `model_not_found` 404 per the
OpenAI contract.

## Right-way checklist for running this project (2026-08-13 state)

1. `cd ~/chimera-v2 && set -a && source .env && set +a` (or rely on
   `load_config`'s repo-.env loading).
2. CLI: `.venv/bin/chimera run "prompt"` — works from repo root.
3. Server: verify nothing else owns the port first (`ss -tlnp | grep 8765`).
   `chimera serve --port <free>` if the documented port is taken.
4. Library: install `chimera-deliberation[full]` (bare wheel import crashes).
5. MCP: use `chimera-mcp` (standalone); `chimera mcp` is broken (CH-GAP-028).
6. Trace trust: read `trace.source` (`auto` = dispatcher-designed) and
   per-stage entries; `DeliberationTrace` is a pydantic model — use
   `model_dump()`.
7. Board: tasks live in `.coding-hermes/board/board.db` (canonical) with
   git-tracked JSONL mirrors. Add via DuckDB INSERT then `COPY ... TO
   tasks.jsonl`. NOTE: JSONL had 34 rows vs DB 24 (pre-existing drift —
   reconcile with `fleet-board-audit.py`; don't re-export FROM the DB or the
   JSONL-only rows vanish).

---

# Diagnostic trail — 2026-08-23 (third dogfood run)

## How the deployment is built and why it went stale

`chimera serve` runs as a systemd unit (`/etc/systemd/system/chimera.service`,
`Restart=always`, started 2026-08-14 14:53) using the repo's `.venv` editable
install. An editable install means the FILES are always HEAD — but a Python
process only loads code at start time, and `Restart=always` restarts only on
crash. Nothing ever restarts the service after new code lands, so the running
process is whatever HEAD was at 14:53 on Aug 14. Every runtime fix merged
after that (CH-GAP-030 stream 400, CH-GAP-031 max_tokens, CH-GAP-038 port
8765) exists in the source tree but NOT in the running process. The
foreman's light-audit health probes cannot detect this: `/v1/health` is
"healthy 7/7" on old code. Fixes were PASS-verified on throwaway servers
(:8790/:8799) that were started fresh from HEAD — which is exactly why the
verification passed while production stayed broken. **The lesson: verify
deployments, not just code. "PASS verified live" must name the process
(start time / commit) it was verified against.**

Evidence (live, 2026-08-23):
- `stream:true` → HTTP 200 full non-stream completion (HEAD would 400
  `stream_not_supported`; server.py:542).
- `max_tokens:1` → 3548-token essay (HEAD honors it; server.py:224/553).
- Unknown model → 404 `model_not_found` WORKS — CH-GAP-027 (Aug 13) landed
  before the service start; consistent with the staleness window.

## Release pipeline reality

`pip install chimera-deliberation` (PyPI) gives 0.2.0 from **Jul 19**: the
CH-GAP-026 bare-import crash reproduces exactly (`from chimera import Engine`
→ `ModuleNotFoundError: fastapi`). HEAD is 186 commits / ~5 weeks ahead of
origin (no-push convention, see INT-CI-001). CH-GAP-026's PASS criterion was
verified against a locally-built wheel, not the artifact that ships — the
classic "verified the build, not the release" gap. **Lesson: smoke-test the
exact artifact you publish (PyPI upload), not a fresh local build.**

## Packaging contract keeps breaking (third instance)

`[project.scripts]` declares `chimera`/`chimera-mcp` in the base package;
their deps (`click`, `rich`, `mcp`) are extras-only. Bare install → entry
points present but crash (`No module named 'rich'`). Same class as CH-GAP-026
(fastapi) and CH-GAP-034 (venv scripts missing). **Root pattern: no
bare-install smoke test exists, so every extras/deps shuffle breaks the base
install silently.** Fix direction: a CI job that bare-installs the wheel in a
fresh venv and runs import + `--help` + MCP handshake.

## Dispatcher malformed-DAG fallback (observed, not new)

1 of 2 auto runs on the fresh wheel: dispatcher emitted `edges:
[["worker_1","aggregator"],["worker_2","aggregator"]]` with NO aggregator
stage in `stages` → `dispatcher_parse_failed` → `source=fallback` (1 worker
+ aggregator). Known pitfall #6; the answer was still correct, so a user
cannot tell without reading `trace.source`. Frequency on this run: 50%.

## Updated right-way checklist (2026-08-23 state — supersedes the 08-13 list)

1. Keys: `set -a; source ~/.hermes/.env; set +a` (or repo `.env`); config
   substitutes `${VAR}` tokens from process env.
2. CLI: `.venv/bin/chimera run "prompt"` (repo) or `chimera` from a `[full]`
   install. First call is slow (provider catalog refresh).
3. Server: check `systemctl show chimera -p ActiveEnterTimestamp` BEFORE
   trusting :8765 behavior — if it predates the fix you care about, restart
   the unit (there is no auto-deploy).
4. Library: `pip install chimera-deliberation[full]` from PyPI is BROKEN
   (bare import crash, Jul 19 release); build from HEAD or wait for 0.2.1.
5. MCP: `chimera mcp` subcommand is FIXED in HEAD (CH-GAP-028); standalone
   `chimera-mcp` also works.
6. Board: `.coding-hermes/board/tasks.jsonl` is canonical (JSONL-NORM-001);
   `board.db` is a DuckDB cache, gitignored.
7. Trace trust: read `trace.source`; `DeliberationTrace` is pydantic —
   `model_dump()`.

---

# Diagnostic trail — 2026-09-04 run B (install legs + bunker skip)

**Why the PyPI leg exists.** Chimera shipped broken packaging to users three
times in August (fastapi bare-import crash CH-GAP-026; rich console-scripts
crash CH-GAP-041; wheel missing chimera.yaml.example CH-GAP-049). Each fix
was "PASS verified" against a locally-built wheel — and CH-GAP-040's 0.2.1
release proved verification ≠ publication. Run B therefore tests the
PUBLISHED artifact and the HEAD wheel separately, in fresh venvs:

- PyPI 0.2.1, install 20s: import OK, --help OK, but the config story is
  broken twice over — the wheel force-includes only chimera.yaml.docker
  (pyproject force-include maps the example only in unreleased HEAD), and
  `config init` does not exist as a command. The error message's own remedy
  ("Copy chimera.yaml.example") is impossible → dead end.
- HEAD 0.2.3 wheel, install 17s: example ships, `chimera config init`
  writes a working 67,740-byte chimera.yaml, and a bare `chimera run` with
  only DEEPSEEK_API_KEY returned a real merged answer.

**Right way (today):** install from a HEAD-built wheel; `config init`;
export the provider key; expect possible guardrail warnings from auto
formation (see DF-CHIMERA-0906-3). REST quickstart against the supervised
:8765 is the other verified path — its full contract battery passed live.

**MCP root-cause trail (3 runs) + 4th-run resolution.** 09-01:
tools/list+call → -32602 after a clean initialize (cause never pinned).
09-04 run A: loguru lines on stdout before the initialize response. 09-04
run B: pinned precisely with scripts/probe_mcp_stdio.py against the 0.2.3
wheel — stdout lines 1–2 are `provider_cache_hit` / `provider_discovery_done`
info logs; the JSON-RPC initialize response is line 3. Conforming clients
read line 1 and die. Three different proximate causes hit the same surface.
**4th run (DF-CHIMERA-0906-2 fix, landed at HEAD):** root cause pinned to
an ORDERING bug, not a config bug — the repo chimera.yaml resolves
`observability.use_stdout: false` correctly, but provider auto-discovery
runs INSIDE `load_config()` → `_apply_env_overrides()` → `discover_providers()`,
i.e. BEFORE `build_server()` reaches `configure_logging()`. With structlog
unconfigured at that moment, its 26.x default emits ConsoleRenderer lines to
sys.stdout (line 1 `provider_cache_hit`, line 2 `provider_discovery_done`,
initialize shifted to line 3). STRUCTURAL FIX (explicitly NOT a chimera.yaml
`use_stdout` flip): the MCP path forces every log sink to stderr before
`load_config` — `observability.configure_logging(obs, force_stderr=True)` +
`mcp/server.py` `run()`/`build_server()` bootstrap, which also overrides a
config that asks for `use_stdout: true`. Verified at HEAD:
`python3 scripts/probe_mcp_stdio.py .venv/bin/chimera-mcp` AND
`python3 scripts/probe_mcp_stdio.py .venv/bin/chimera mcp` both report
`NON_JSON_RPC_STDOUT_LINES=0` with initialize as stdout line 1. Regression
gate: `tests/test_mcp_stdio_purity.py` spawns both real entry points over
stdio with a config that FORCES `use_stdout: true` and asserts every stdout
line is JSON-RPC 2.0 (fails on pre-fix code, passes at HEAD). Re-run
anytime: `python3 scripts/probe_mcp_stdio.py <path-to-chimera-mcp>` — the
probe now exits non-zero on any non-JSON-RPC stdout line and prints
`NON_JSON_RPC_STDOUT_LINES=0` at HEAD.

**Deploy-drift forensics (recurrence #3).** `systemctl show chimera -p
ActiveEnterTimestamp` + the `/health` commit field: process from Aug 28
(b087769) vs HEAD 8a3d4ea = 30 commits. This run classified the delta:
CLI/packaging/board-only — and live-verified the deployed REST contract
anyway (stream 400 / max_tokens honored / 404 / real deliberation all
correct). Lesson: the drift is now chronic because restart is manual;
visibility (AGENTS.md procedure + /health commit) demonstrably does not
prevent it — CH-GAP-039/047 closed twice and it recurred. Enforcement
(a scheduler-driven deploy step) is the filed fix (DF-CHIMERA-0906-4),
not a third reopen.

**Bunker leg skip (SKIPPED-install-bunker).** bunkerd is active but its
port pool is exhausted: spawn → "port range allocation: no free port ranges
available (pool exhausted: 10 ranges)" (4th+ byte-identical recurrence;
journal shows SpawnAgent 500s). Independently, ssh :22 to bunker-las-03
times out while root SSH (bunker3-root alias) and ICMP work — partial
network degradation. Chimera-side installability was still verified
locally; what remains unproven is the bare-Debian no-toolchain-from-zero
path. Infra fixes filed in DF-CHIMERA-0906-6 (bunkerd allocation
recycling, sshd :22 reachability).

**Run B evidence files** (ephemeral, /tmp/dogfood-chimera/):
fresh-user-run.sh, live-rest-probe.sh, mcp-probe.sh, timed-install.sh,
run-pypi021.out, run-head023.out, stream.out, mt.out, bogus.out, real.out,
chimera_deliberation-0.2.3-py3-none-any.whl. Re-runnable verbatim.

## 2026-09-11 (7th run) — wheel-vs-HEAD bisection, real-client MCP proof, bunker transport forensics

**How the MCP pollution was finally cornered on the published artifact.**
The repo's purity gate (probe + test) was real-call depth, so the remaining
question was "what does a fresh user actually get from PyPI?" Method: one
raw stdio client (`/tmp/dogfood-chimera/mcp_probe.py`) that speaks
initialize → tools/list → tools/call over a pipe, classifies EVERY stdout
line as JSON-RPC vs pollution, and exits non-zero on any pollution. Run
against both binaries same hour:

| Binary | stdout lines | pollution | result |
|---|---|---|---|
| HEAD venv `chimera-mcp` (post-27f0b35) | 3 | 0 | initialize=line 1, tools/list=line 2, tools/call=line 3, answer "17 × 23 = 391" |
| PyPI 0.2.3 wheel `chimera-mcp` | 11 | 8 | handshake clean (lines 1-2); LiteLLM INFO lines (#3-#10) start lazily on the first real tools/call; response buried at line 11 |

Two lessons encoded here. (1) **Pollution is lazy**: it begins when the
first deliberation triggers LiteLLM, so initialize-only smoke checks pass
green on a broken wheel — purity probes MUST make a real call. (2) **The
release gate tests the checkout, not the artifact**: 0.2.3 published 09-08,
fix landed 09-10, nobody ran the existing probe against the wheel. Both
lesson-objects are filed (DF-CHIMERA-0911-1 publish, DF-CHIMERA-0911-2
release canary).

**Real external client proof (what "works" should mean).** Hermes' own MCP
client drove the repo wrapper (`bin/chimera-mcp-hermes`) end-to-end:
`chimera_deliberate(prompt, formation="simple")` on a DuckDB-vs-SQLite
question → dispatcher selected 2× `deepseek/deepseek-v4-pro` workers +
`deepseek/deepseek-v4-flash` aggregator, wrote two genuinely different
worker prompts (engine-level brief vs decision-criteria brief) and merge
instructions enforcing exactly-3-sentences; merged answer complied;
66.1s, $0.0162, 26,795 tokens, `worker_failures: []`. Trace trust note:
the full dispatcher/workers/aggregator transcript is returned in the
response — auditable without server logs.

**Deploy parity (recurrence #3) resolved this run.** Live `/health` commit
e4c7a30 vs HEAD 3b6ae77: the 2-commit delta is board/gitreins chores only —
all REST contract behavior re-verified correct on the deployed binary
(stream 400, unknown-model 404, auto chat 200 "42" 14.2s). DF-CHIMERA-0906-4
(chronic drift) is now fixed in practice: deployed commit is current, and
`/health` made the check trivial. Also verified at HEAD: `chimera models`
legible (DF-CHIMERA-V2-2 fix), `chimera run` stdout = answer box only,
0 stray lines, 18 stderr lines (DF-CHIMERA-V2-3 fix), `test_mcp.py` 13/13
(09-07 drift failure gone).

**Bunker transport forensics (new signature, 7th skip).** Prior skips were
`port range allocation: pool exhausted` at spawn. This run got further:
`bunker list --server bunker-las-03` succeeds (bunkerd :19090 reachable,
CLI 0.1.3/4af949d), then `bunker spawn` fails one hop deeper —
`deadline_exceeded: Post http://bunker-las-03:10001/bunker.v1.Bunkerd/SpawnAgent:
dial tcp bunker-las-03:10001: i/o timeout` — while ssh :22 times out during
banner exchange (ICMP fine). Two agent transports down + bunkerd API up =
firewall/ACL regression on the host, not bunkerd health. Filed
DF-CHIMERA-0911-4 (supersedes the port-pool framing in DF-CHIMERA-0906-6).
Installability evidence this run is local: fresh venv →
`pip install chimera-deliberation[full]==0.2.3` = 95s, `chimera config init`
works from the wheel template, `chimera run` → "Paris" boxed, 14s, exit 0.

**OpenAI drop-in semantics wrinkle.** `model:"deepseek/deepseek-v4-flash"`
on /v1/chat/completions → 404 `model_not_found` even though the ID is a
valid GET /v1/models key; `model` accepts formations only, per-model force
lives in `worker_model`/`stage_models`/`allowed_models`. Docs are
self-consistent (OPENAI_API.md field table) — the surprise is the
reflex, not a contradiction; minor doc drift: the doc says unknown model
names "return 400" (line 183), reality is 404. Filed DF-CHIMERA-0911-3.

**Run evidence files** (ephemeral, /tmp/dogfood-chimera/): mcp_probe.py
(raw stdio classifier), rest_battery.py (urllib REST battery),
fresh-venv/ (the PyPI 0.2.3 install), fresh-run-stderr.log,
head-cli-stdout.log / head-cli-stderr.log (HEAD CLI purity proof).
Re-runnable verbatim.

---

## 2026-09-20 (run 10) — the web UI: how the live-DAG promise is wired, and why it cannot be kept

This section explains the `/web/` surface — how a session, a chat and an SSE
stream fit together, what the code actually broadcasts, and why a reader
watching the browser sees a static panel. It is written so the next person can
reason about the surface without re-deriving it.

### How the web surface is built (and why it exists at all)

`src/chimera/web/` is a thin, deliberately separate layer beside the REST API:
`routes.py` owns sessions and chat, `session.py` holds turn history,
`sse.py` is a broadcaster, `trace_viz.py` turns a `DeliberationTrace` into a
mermaid graph, and `static/index.html` is the whole SPA (one file, inline JS).
It is mounted on the same FastAPI app as `/v1/*`, and since INT-API-001 its
router carries the same `require_api_key` dependency — with `auth.enabled:
false` (the default here) that resolves to "anonymous" before any header is
read, which is why every probe below works keyless on this host.

The design intent is a **push** architecture: the browser opens
`EventSource('/web/sse/<sid>')` once, and the server pushes events as the
deliberation progresses; the SPA's listeners update the DAG, the tiles and the
chat bubbles in response. `POST /web/sessions/<sid>/chat` returns the same
answer synchronously as a *fallback* — the frontend even comments it that way
("Update DAG if SSE didn't (fallback)").

### The three things that must line up — and the one that does not

1. **Events must exist.** ✓ the SPA registers listeners for
   `deliberation_started`, `dag_designed` and `deliberation_done`.
2. **Events must be transported.** ✓ curl on a fresh session receives a stream
   with `text/event-stream`, `X-Accel-Buffering: no`, and real frames.
3. **Events must be produced DURING the run.** ✗ **this is the gap.**

`grep -c '.broadcast(' src/chimera/web/routes.py` → **3**. The first fires
before `await engine.deliberate(...)`; the other two fire after it returns, back
to back. `src/chimera/web/sse.py`'s module docstring advertises two further
event kinds — `stage_started` ("a worker/aggregator stage began executing") and
`stage_completed` ("a stage finished (model, tokens, latency, cost)") — and the
frontend listens for both. They are defined in the format layer
(`tests/test_web.py` builds a synthetic `stage_completed` frame) and **never
emitted by any code path in `src/`**. Nothing in `engine.py` or the stage
runner knows a broadcaster exists.

So the honest reading of the pipeline is:

> a browser-side dashboard with no server-side feed, whose synchronous fallback
> works so well that the suite never notices the feed is missing.

That is why the timeline measured on this run shows 53 s of silence between the
first and last event, and why the two trailing frames arrive in the same
millisecond as the HTTP response.

### Why the suite is green anyway (the generalisable lesson)

Every layer is individually correct and separately tested. `sse.py` correctly
formats an event, `routes.py` correctly broadcasts the three it has, the SPA
correctly listens, and `trace_viz.py` correctly renders a mermaid string from a
real trace. A test that drives the **whole user-visible path** — "start a real
deliberation, assert a mid-run event arrives before the POST returns" — does
not exist, so no test can fail. Same shape as the sibling lesson already in this
file: *a component seam that each side tests separately is where the wiring
goes missing.*

### The second mechanism: the 30-second replay gate

`sse_stream()` in `routes.py` does something reasonable-sounding that produces a
user-visible defect:

- if the session's newest turn is **< 30 s old**, it queues
  `session.last_sse_events` for the late subscriber, then closes the stream;
- otherwise it just pushes the `None` sentinel — **an instant, zero-byte close**.

Measured: aged session `CLOSED_AFTER=0.0014s bytes=0`; fresh session
`CLOSED_AFTER=30.00s` (that 30 s is `event_stream`'s idle timeout in `sse.py`).
The frontend cannot distinguish "stream closed because nothing more is coming"
from "connection dropped": `onerror` reconnects every 3 s unless
`deliberationComplete` is set, and only a `deliberation_done` **event** sets it —
which a replay-suppressed aged session never sends. Result: reload the page on a
session with history and the UI enters a 3-second reconnect loop that it
describes, accurately and permanently, as `⏳ SSE reconnecting…` — 138 requests
in 40 minutes of wall clock, all of them answered `200`.

**The right way to read this pair of defects:** the *capability* is present
(stored events exist, the replay branch is written, the listeners are
registered); the *policy* is what makes it useless — a 30 s window that excludes
exactly the sessions a returning user has.

### The dangerous one: a test hook on the public surface

`POST /web/debug/reset` rebinds the module-global `_session_manager` and
`_sse_broadcaster` — i.e. it deletes **every** session in flight. It carries no
guard beyond the router-level auth dependency, which is inert when
`auth.enabled: false`; the unit binds `0.0.0.0`; and `docs/SECURITY.md:64–66`
lists it among the paths that "require the key" and asserts an anonymous request
is refused with 401 "never 404". Observed: anonymous, 200, and a session that
had been returning real turns minutes earlier then answered
`404 Session '...' not found`.

**Right way:** a destructive test fixture belongs behind a test/dev flag (or out
of the shipped app entirely, resetting via a pytest fixture instead), and any
endpoint that can drop other users' state should be documented with its blast
radius rather than listed as protected.

### Reproducing all of it

```bash
# timeline proof (fresh session)
SID=$(curl -s -X POST localhost:8765/web/sessions | sed 's/.*"session_id":"//;s/".*//')
curl -sN "localhost:8765/web/sse/$SID" &          # watch frame arrival times
curl -s -X POST "localhost:8765/web/sessions/$SID/chat" \
  -H 'Content-Type: application/json' -d '{"prompt":"PONG","formation":"simple"}'
# -> only deliberation_started early; dag_designed + deliberation_done at the end

# aged-session instant close (needs a session with turns > 30 s old)
time curl -sN -o /dev/null "localhost:8765/web/sse/$SID"   # ~0.001 s, 0 bytes

# the destructive hook (do this on a host you do not mind resetting)
curl -s -X POST localhost:8765/web/debug/reset
```

Working evidence from this run (ephemeral `/tmp`): `sse-time.txt`,
`chat-time.txt` (the timestamped frame log), `aged2-meta.txt`,
`sse-compare.txt`, `bunker-install2.log`.

## 2026-09-22 (run 11) — the custom-formation surface: how stages resolve, and what degrades silently

**Why this run exists.** Runs 1–10 always consumed shipped formations. A user
who writes their own is the deepest test of the DAG machinery, because nothing
pre-validates their config: the dispatcher never intervenes (the formation is
static), so every assumption the engine makes about stages/edges/models is
exercised with user-shaped input.

**How the pieces actually fit (learned by driving them, not reading):**

1. `config.py` loads formations as plain data — a `dag:` block with
   `stages[]`/`edges[]` goes in verbatim. There is no schema validation step a
   user sees; bad references surface later at execution, not at load
   (`chimera formations` listing proves only that YAML parsed).
2. At run time the engine topologically executes stages by `depends_on`;
   `--stage-models` overrides are a dict keyed by stage id applied after
   dispatch resolution. The matching is by exact id with no unmatched-key
   check — that is why a typo is invisible (DF-CHIMERA-V2-32). The override
   path itself is correct and user-shaped: custom ids resolve as well as
   shipped ones.
3. Degradation is per-stage and cooperative: a stage that exceeds
   `timeout.per_stage_s` (request header → config → 120.0 code default in
   engine.py `DEFAULT_STAGE_TIMEOUT_S`) is cancelled, recorded via
   `_degraded_stage`, and downstream merge/aggregator stages run with a
   "partial inputs" note in the log stream. The design intent (one slow model
   cannot block the deliberation) is sound; the gap is that on the CLI the
   degradation note is a structlog JSON line, not the human `warning:` line
   USAGE.md's contract table promises (DF-CHIMERA-V2-34).
4. The default-formation resolution is "formation named `auto` must exist in
   config" — it is not a built-in singleton. Minimal configs therefore exit 2
   on the bare `run` form (DF-CHIMERA-V2-33). This is the one place where the
   docs example and the engine disagree, and the error message papers over it
   well enough that recovery is fast.

**Port discipline note for future probes:** :8765 is the live systemd unit
(dogfood never touches it), :8766 is the off-by-one pre-solve lab (NOT
chimera — its /health says so), so scratch chimera servers should pick an
empty port like :8777 and be killed after. A scratch-server /health carrying
`commit` equal to checkout HEAD is the fastest deploy-parity probe.

**Evidence (ephemeral /tmp/dogfood-chimera/, not committed):** user config,
answer1.txt (the 87s review), sm.json (override + timeout run), dag.json
(inline --dag), rest.json (REST run), serve8777.log. Bunker install leg:
agent 4dfc08f3, venv+pip install 54s, config init from packaged example ok,
first answer 30s; agent destroyed, 0 remaining. No credentials in any
artifact; scratch config uses ${DEEPSEEK_API_KEY} indirection only.

## Run 12 addendum (2026-09-23) — why the web UI lies, and how the pieces fit

**How the web surface is assembled (the mental model a maintainer needs):**
one FastAPI app, three layers. (1) The ENGINE (`Engine.deliberate`) is
stateless and returns a `DeliberationTrace` — every stage span, plus
`worker_failures` for stages that died and a `source` field for
fallback/degraded runs. (2) The WEB layer (`src/chimera/web/`) wraps the
engine in an in-memory `SessionManager` (turn history → a context preamble
injected into the NEXT turn's dispatcher prompt), broadcasts SSE events as
the run progresses, and converts the finished trace to mermaid
(`trace_viz.trace_to_mermaid`) plus per-turn history JSON. (3) The SPA
(`web/static/index.html`, one file of inline JS) renders bubbles, the stats
bar and the DAG, and keeps only `chimera_session_id` in localStorage.

**Why a failed worker still renders green:** the trace records the failure
in `worker_failures`, but the stage span of a failed worker still exists
(with 0 tokens), and `trace_to_mermaid` colors nodes by stage KIND only —
the `_FALLBACK_COLOUR` grey exists but is only for unknown kinds. The SPA's
SSE stream actually carries a worker-failure event, so the data needed to
honestify the DAG is already on the wire; only the styling consumer is
missing (DF-CHIMERA-V2-42).

**Why "None" can be an answer:** the aggregator merges whatever worker
inputs survived. When zero survive it logs `aggregator_partial_inputs`
(warning) and merges nothing; the web route then stores the resulting
Python `None` answer as if it were text and answers 200. The REST surface
has the same hole; the UI just makes it visible as a normal-looking turn
(DF-CHIMERA-V2-44). The right way per the resilience docs is to fail the
turn loudly when `healthy == 0`.

**Why auth killed the browser:** `require_api_key` was (correctly) attached
at the ROUTER level (INT-API-001's fix), which includes the SPA-shell and
asset routes. But the SPA predates auth and has no notion of a key — no
prompt, no header — so enabling auth removes the UI entirely rather than
gating it (DF-CHIMERA-V2-41). Serving static HTML unauthenticated while the
data routes enforce the key would keep the hardening AND the UI.

**Run-10 correction, for the record:** the "the DAG is NOT live" finding
(all SSE broadcasts fire after the engine returns) no longer holds at
e231b14: a real browser saw "Running aggregator… — deepseek/deepseek-v4-flash"
and a ticking stats bar DURING the run. The mermaid graph itself still
arrives with the completed trace, which is fine.

**Fresh-hardware notes (bunker, Debian + Python 3.13):** editable install
73s; `chimera config init` works from the packaged template; `--formation`
is a ROOT-level flag — `chimera --formation simple run "..."` works while
`chimera run --formation ...` exits 2 ("No such option"), a flag-order trap
that cost one smoke retry. `/tmp` on the bunker agent is not writable by the
agent user (pip redirect failed with EACCES) — write scratch to ~ there.

**Evidence (ephemeral /tmp/dogfood-chimera/, not committed):** CDP drivers
`drive_webui.py` / `drive_webui_phase2.py` / `drive_webui_phase3.py`,
`webui-run.json` (the :8765 401 capture), serve8791.log. Bunker artifacts
lived on agent d50a7727 (destroyed). No credentials in any artifact.

## Docker deploy leg (run 13, 2026-09-24) — why the container path is shaped
like it is, and how to test it

The container path is deliberately **release-based**: the Dockerfile does
`pip install chimera-deliberation[full]>=0.2.0` (latest wheel, 0.2.7), while
the repo itself is ahead. That means a container runs the *published*
artifact, not the checkout — repo-level fixes reach the image only after the
next PyPI release. Anyone debugging "my fix isn't in the container" should
check the release chain first, not the image build. The bind-mount of a live
`chimera.yaml` is opt-in for the same fresh-clone reason the repo is shipped
config-less: a bind-mount source that doesn't exist makes docker create a
directory in its place and the container never starts — that trap is written
into docker-compose.yml itself (volumes: [] until the user opts in), and it
matches reality on a fresh clone.

**How the env-key contract was proven without a real key:** set
`DEEPSEEK_KEY` to an obviously-fake key and re-`compose up`. The /v1/health
provider probe flips from `missing-credentials` to `auth: ... Your api key:
****-leg is invalid` — a real DeepSeek API round-trip. That distinguishes
"env var never reached the engine" from "key invalid" in one step, and needs
no secret at all. This is the cheapest credential-path probe available for
any config that feeds provider keys from env.

**Bunker runtime note (for whoever runs the docker leg next):** on
bunker-las-03 the per-agent docker daemon lives at
`/run/bunker/<agent>/docker.sock` (bunkerd-managed), NOT
`/run/user/<uid>/docker.sock`; the agent's user `docker.service` unit is
failed-idle and `docker context` does not know the bunker socket. Point the
CLI at it explicitly (`docker -H unix:///run/bunker/<agent>/docker.sock ...`)
or pass it through a script; the socket exists from spawn and works with the
shipped compose + the compose v5.5 plugin already on the agent. No sudo, no
plugin install needed.

**Evidence:** clone→build→up→smoke transcript in
`docs/dogfood/2026-09-24-integration.md`; agent 5d1b8e8e destroyed; the fake
key `sk-ds-...OBE-...` and the real key both lived only in
`~/appkey` on the agent (gone with the agent). No credentials committed.

## 2026-09-25 — run 14: the PyPI wheel leg and the MCP stdio leg

The 13 earlier runs all exercised chimera from a REPO checkout (or a compose
image built from one). Two surfaces had never been touched: the wheel that a
`pip install chimera-deliberation[full]` user actually runs, and the MCP
stdio server driven by a client that is not the repo's own probe.

How it works, why, and the right way:

- **The wheel is the product a PyPI user runs; this run proved it equals the
  repo.** Installed `[full]` from PyPI in a throwaway venv (36s, py3.11) and
  on a bare Debian 3.13.5 bunker agent (266s): both give 0.2.7, `python -m
  chimera` works, `chimera config init` finds the template INSIDE
  site-packages — so the wheel force-includes of `chimera.yaml.example` are
  load-bearing and verified. The errors I hit were both MY tooling, not the
  product: `uv venv` ships no pip (use `python3 -m venv`), and `uv` defaults
  to the newest CPython (pass `--python 3.11`).
- **MCP interop is real, not probe-shaped.** A hand-rolled JSON-RPC-over-
  stdio client (initialize → notifications/initialized → tools/list →
  tools/call) gets 3 tools with correct schemas and full deliberations
  (12.8s local / 45.5s on the fresh agent), protocol 2024-11-05. The client
  lives in the run-14 report; it is ~60 lines and is the model for any
  harness integration. The repo's own `scripts/mcp-liveness-check.sh` cannot
  run on such machines (npx missing — DF-CHIMERA-V2-52).
- **The error I hit that is NOT mine:** `bunker-qa.sh launch` shipped a
  0-byte qa-run.sh to the agent (DETECT_UP_PREV_DIR unbound at line 846
  aborts script generation after the sync; `docker pull requires 1 argument`
  warning precedes it) — the collect phase then reports `pull-failed`, which
  looks like a network fault but is a driver defect. Diagnosis: `wc -c
  ~/qa-run.sh` on the agent (0 bytes) + `bash -n` (syntax OK on an empty
  file). The fix belongs in the QA driver (hermes-infra), filed as
  DF-CHIMERA-V2-51; the install leg was completed by hand per the skill and
  PASSED (config init → real deliberation → MCP battery, agent c26d8af2
  destroyed and verified gone).
- Deployment parity: `smoke_live.py` classifies the live deployment
  CODE-CURRENT (ee8ad95, bookkeeping-only gap to HEAD) with a class-aware
  zai quota warning and a live merged answer — the same one-command proof
  every run ends with.

**Evidence:** numbers in `docs/dogfood/2026-09-25-integration.md`; agent
c26d8af2 destroyed; the real key lived only in `~/dfkey` on the agent (gone).
No credentials committed.
