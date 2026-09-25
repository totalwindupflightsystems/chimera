---
name: chimera-usage
description: >-
  How to actually USE the Chimera multi-model deliberation gateway (CLI, MCP,
  REST). Entry points, working recipes, common failure modes and their fixes.
  Load this before running any deliberation. Written from the 2026-08-03
  dogfood run — everything here was executed for real. v1.1.0 adds the
  2026-09-16 run-9 lessons: OpenAI SDK compatibility limits, the MCP
  keep-stdin-open harness rule, fresh-clone config gotcha, bunker install.
  v1.2.0 adds the 2026-09-20 run-10 web-UI section (`/web/` recipes, the
  not-live DAG, the reconnect banner, the destructive debug hook).
  v1.3.0 adds the 2026-09-22 run-11 custom-formation section: authoring a
  user formation, `--stage-models` on custom stage ids, the degraded-merge
  observability gap, and the fresh-install quickstart proof on 0.2.7.
  v1.4.0 adds the 2026-09-23 run-12 REAL-BROWSER web-UI section: a
  headless-Chrome CDP recipe for driving the SPA, what live-updates mid-run,
  the auth.lockout of the browser, the green-failed-node DAG, the doubled
  answer bubble, and the "None" degraded turn.
  v1.5.0 adds the 2026-09-24 run-13 DOCKER deployment section: compose
  build/up/smoke numbers on fresh hardware, the DEEPSEEK_KEY vs
  ${DEEPSEEK_API_KEY} naming split, the fake-key credential probe, the
  release-based image caveat, and the bunker docker-socket recipe.
  v1.6.0 adds the 2026-09-25 run-14 PYPI-WHEEL + INDEPENDENT-MCP section:
  installing from PyPI (no repo) on this box and a bare 3.13 agent, config
  init from the wheel's site-packages template, and a ~60-line raw
  JSON-RPC stdio client that proves MCP interop without npx or the repo's
  own probe.
version: 1.6.0
category: software-development
---

# Chimera Usage — Field-Tested Recipes

Chimera = one prompt → dispatcher designs a DAG of scoped LLM worker tasks →
workers run in parallel → aggregator merges with dispatcher-written
instructions → one answer + a full trace (per-stage model/tokens/cost).

## Entry points (fastest → slowest)

| Entry | Command / tool | Verdict (2026-08-20 re-verified) |
|---|---|---|
| **MCP** (for agents) | `chimera_deliberate(prompt=..., formation="auto")` | ✅ best path — full trace, works |
| **CLI** | `chimera run "prompt"` (or `-v` for trace) | ✅ works, boxed trace table |
| **REST** | `POST :8765/v1/deliberate` / `/v1/chat/completions` | ✅ works — live-verified 2026-08-20: `/v1/health` healthy (7/7 providers), `/v1/health/ready` 200, real deliberation answered |
| Web UI | `http://localhost:8765/web/` | ✅ served (HTTP 200); SSE session-based |

## Working recipes

### MCP (agent integration) — the flagship

```python
# auto formation: dispatcher designs the whole deliberation
r = chimera_deliberate(prompt="Compare X and Y for use case Z", formation="auto")
answer = r["answer"]          # merged answer
r["trace"]["total_cost"]      # ~$0.003–0.02 per small run
r["trace"]["source"]          # "auto" = dispatcher designed it; "fallback" = degraded

# custom DAG: you define structure, dispatcher writes the prompts
r = chimera_deliberate(
    prompt="...",
    formation="custom",
    allow_custom_dag=True,
    dag={"stages": [
        {"id": "researcher", "kind": "worker",     "model": "deepseek/deepseek-v4-flash", "depends_on": []},
        {"id": "critic",     "kind": "aggregator", "model": "deepseek/deepseek-v4-flash", "depends_on": ["researcher"]},
        {"id": "final",      "kind": "aggregator", "model": "deepseek/deepseek-v4-flash", "depends_on": ["critic"]},
    ], "edges": [["researcher","critic"], ["critic","final"]]},
)
```

### CLI

```bash
cd <path-to-chimera-v2>   # .env must be here and in the process env
chimera run "Your prompt"
chimera -v run "Your prompt"    # trace table: stage | model | tokens | latency | cost
chimera formations              # simple, debate, audit, speed, spec-writer, auto
chimera serve                   # REST + web UI on :8765
```

### REST (verified working 2026-08-20)

```bash
curl -X POST http://127.0.0.1:8765/v1/deliberate \
  -H 'Content-Type: application/json' \
  -d '{"prompt": "Your prompt", "formation": "auto"}'
# NOTE: body uses "prompt" (string), NOT OpenAI-style "messages" — that 422s.
```

## Pitfalls (all hit for real)

1. **REST creds issue — RESOLVED on this deployment (2026-08-20).** The old
   failure mode was: every request returns HTTP 200 whose content starts
   `[stage aggregator ... unavailable: ... Missing credentials ...]` because
   `serve` didn't load the repo `.env` (the MCP/CLI did). Current deployment
   runs `chimera serve` as a supervised service with full creds —
   `/v1/health` = healthy (7/7 providers), `/v1/health/ready` = ready. If a
   fresh manual `serve` ever shows the symptom again: `set -a; source .env;
   set +a; chimera serve`, then verify `curl /v1/health/ready` == ready.
   (Historical task: dogfood-http-server-no-creds; CH-GAP-037 re-verified)
2. **Failed deliberation → HTTP 502 (RESOLVED 2026-08-23).** The old failure
   mode (HTTP 200 with `[stage ... unavailable` error text as assistant
   content) is gone: `server.py` raises `_NoUsableAnswerError` when
   `result.answer_degraded` and the handler returns 502 with an
   OpenAI-compatible structured error body (both `/v1/deliberate` and
   `/v1/chat/completions`). Re-verified live 2026-08-23: unknown model →
   404 `model_not_found`, unknown formation → 422; no 200-with-bracketed-error
   path remains. (Tasks: dogfood-error-200-as-success, CH-GAP-043)
3. **`/v1/health` lies — RESOLVED 2026-08-23.** The old failure mode (health
   reporting all providers down while real calls succeed) is fixed: probes
   now run real per-provider LLM pings with the same creds/params as the
   engine. Re-verified live 2026-08-23: `/v1/health` = healthy 7/7 with
   per-provider `model_tested` in details. If it reads `degraded`, that is a
   REAL signal now (transient under concurrent probes — re-probe
   sequentially 2-3× before escalating). (Tasks: dogfood-health-lies,
   CH-GAP-043)
4. **`lock_aggregator: true` silently beats request overrides.** Set
   `aggregator_model` in the request and it will be ignored if config locks
   the aggregator. Read chimera.yaml first. (Task: dogfood-lock-aggregator-silent-override)
5. **OpenRouter 404 `No endpoints available matching your guardrail
   restrictions`** = the account's privacy settings block that model; the
   dispatcher may keep picking it. The engine degrades to a partial merge —
   usable but check `trace` for dropped workers. (Task: dogfood-model-guardrail-404)
6. **`source=fallback`** in the trace means the dispatcher's DAG was
   malformed (e.g. missing the aggregator stage) and a single-worker preset
   was used instead. Retry; usually dispatches cleanly. (Task: dogfood-dispatcher-malformed-dag-fallback)
7. **First CLI call is slow** (~30–60s): it refreshes the LiteLLM provider
   catalog (5309 models). Later calls hit the cache (~2–20s).
8. **Cost floor ~$0.003** — the dispatcher call carries the full model catalog
   in context (~17k input tokens). Per-run totals: $0.003–0.02 for small prompts.

## The "right way" patterns

- Always read `trace.source` and `trace.workers` before trusting an answer.
- For agent use, prefer MCP over REST (MCP handles creds/contract details for you).
- For deterministic pipelines, use custom DAGs + `formation="custom"` and pin
  models you know the account can reach.
- Keep prompts small unless you need the multi-model depth — each worker call
  costs money and the dispatcher always pays the catalog-token tax.

---

## Update 2026-08-13 (second dogfood run) — what changed

The engine-level P0s from run 1 are FIXED in current code (verified by real
use): `/v1/health` reports honestly (real probe calls, `healthy` with 12/12
providers), `/health` alias works, `/v1/deliberate` returns proper 400s, full
suite 648 passed / 62 skipped in 17.5s. **But three NEW traps, all hit for
real:**

### New pitfalls (2026-08-13)

9. **Port squatting on :8765 — RESOLVED.** A stale root-owned `chimera serve`
   (PID 21212, started Aug 2, pre-fix code) used to squat :8765 on this
   machine: `chimera serve` → "address already in use"; every curl on :8765
   returned HTTP 200 whose content starts `[stage aggregator ... unavailable:
   ... Missing credentials ...]`. That zombie was killed and the port is now
   owned by the supervised service (verified healthy 2026-08-20). Keep the
   habit anyway: `ss -tlnp | grep 8765` + `ps -o lstart -p <pid>` before
   trusting the port; test on `--port 8790`+ if a stranger owns it.
   (Task CH-GAP-025; CH-GAP-037 re-verified)
10. **Bare `pip install chimera-deliberation` then the README Python snippet
    crashes**: `from chimera import Engine` → `ModuleNotFoundError: fastapi`
    (web routes imported unconditionally). Must install `[full]`. (Task
    CH-GAP-026)
11. **`/v1/chat/completions` silently substitutes models — RESOLVED
    2026-08-23.** Unknown `model` → HTTP 404 `model_not_found` with a
    structured OpenAI-style error (re-verified live 2026-08-23); no silent
    substitution remains. (Task CH-GAP-027)
12. **Use `chimera-mcp` (standalone), NOT `chimera mcp` — FIXED in HEAD
    (2026-08-23).** The subcommand crashed with `FileNotFoundError: 'mcp'`
    (argv bug, CH-GAP-028); the handshake now works via `chimera mcp` too —
    the standalone entry point remains preferred for agent use. (Task
    CH-GAP-028)
13. **Custom DAGs go to `/v1/chat/completions` with `model:"custom"`** —
    `/v1/deliberate` rejects `formation:"custom"` with a bare 422. (Task
    CH-GAP-029)
14. **`result.trace` is a pydantic `DeliberationTrace`** — use
    `model_dump()`, not dict access.

### Updated "right way" patterns

- Server: verify port ownership first; the supervised deployment on :8765 is
  healthy (7/7 providers, live-verified 2026-08-20).
- Library consumers: always `pip install "chimera-deliberation[full]"`.
- Agent integration: MCP still best (standalone `chimera-mcp`).
- Check `trace.source` and per-stage entries; `source=auto` = dispatcher
  designed the DAG.

---

## Update 2026-08-23 (third dogfood run) — what changed

Re-ran everything for real against HEAD wheel (486a409) + live :8765.

### New pitfalls (all hit for real)

15. **The live :8765 service runs STALE code.** systemd `chimera.service` has
    been up since 2026-08-14 14:53; every fix merged after that (stream 400,
    max_tokens, port default) is NOT in the running process. Live symptoms on
    :8765: `stream:true` → 200 non-stream full completion; `max_tokens:1` →
    3548-token essay. HEAD code behaves correctly — the deployed process
    doesn't. **Always check `systemctl show chimera -p ActiveEnterTimestamp`
    before trusting live behavior; restart the unit to get HEAD.** (Task
    CH-GAP-039)
16. **PyPI 0.2.0 (Jul 19) is the July product.** `pip install
    chimera-deliberation` → `from chimera import Engine` →
    `ModuleNotFoundError: fastapi` (CH-GAP-026 fix never shipped). Install
    from a HEAD-built wheel or wait for 0.2.1. (Task CH-GAP-040)
17. **Bare install's console scripts crash**: `chimera --help` after bare
    install → `ModuleNotFoundError: rich` (click/rich/mcp are extras-only but
    the entry points ship in the base package). Always install `[full]`.
    (Task CH-GAP-041)
18. **README.md ends with a literal `# test comment`** — ignore it; it's a
    leftover artifact. (Task CH-GAP-042)

### Stale pitfalls from earlier runs — re-verified 2026-08-23 (CH-GAP-043)

- Pitfall #2 ("failed deliberation returns HTTP 200 with error text") —
  **RESOLVED**: 502 structured error now (verified above).
- Pitfall #3 ("/v1/health lies") — **RESOLVED**: health honest 7/7 with
  per-provider `model_tested` (verified above).
- Pitfall #12 ("use `chimera-mcp`, NOT `chimera mcp`") — **FIXED in HEAD**:
  `chimera mcp` handshake verified working 2026-08-23 (CH-GAP-028).
- Pitfall #11 (silent model substitution) — **RESOLVED**: 404
  `model_not_found` live-verified 2026-08-23 (CH-GAP-027).
- Pitfall #6 (`source=fallback`): observed on 1 of 2 auto runs 2026-08-23 —
  still true; more common than "rare"; retry once (Task CH-GAP-044).
- Pitfall #5 (OpenRouter guardrail 404): not re-hit 2026-08-23, but it is an
  account-setting failure mode, not a code bug — keep as-is (Task
  dogfood-model-guardrail-404).
- Pitfall #9 (port squatting): supervised service owns :8765, unit active —
  habit (ss/ps check) still recommended (CH-GAP-025/037).
- Pitfall #10 (bare install fastapi crash): FIXED at HEAD (CH-GAP-026 lazy
  import) but STILL TRUE for PyPI 0.2.0 (Jul 19) — install from a HEAD-built
  wheel until 0.2.1 publishes (Task CH-GAP-040).
- Pitfall #13 (custom DAGs only via `/v1/chat/completions` model:"custom"):
  still true 2026-08-23 — deliberate rejects formation custom with 422
  (live-verified; CH-GAP-029).
- Pitfall #14 (`result.trace` is a pydantic `DeliberationTrace`): still true
  2026-08-23 — use `model_dump()`, not dict access.

### Verified-still-true (2026-08-23)

- Pitfalls #1 (creds — the supervised service has full creds; 7/7 healthy),
  #4 (lock_aggregator), #7 (first call slow), #8 (cost floor ~$0.003).
- Custom DAG via library: `engine.deliberate(prompt, formation="custom",
  dag=..., allow_custom_dag=True)` works and returns excellent results —
  but a 3-stage sequential DAG took **4m15s** wall. Budget minutes.

---

## Update 2026-09-04 (runs A + B) — MCP BROKEN, then FIXED at HEAD; REST remains a verified path

Re-verified everything live against the deployed :8765 (b087769) and a fresh
HEAD 0.2.3 wheel install. The entry-point verdict table above is STALE:

| Entry | Status 2026-09-04 | Evidence |
|---|---|---|
| **REST :8765** | ✅ **USE THIS** | stream:true→400, max_tokens:1→honored, unknown model→404, real deliberation 200 "Paris" 18.6s, health 7/7 |
| Web UI /docs | ✅ works | HTTP 200 both |
| CLI (HEAD wheel) | ✅ works, noisy | answer + loguru logs interleave on stdout; no --quiet |
| CLI (PyPI 0.2.1) | ❌ dead-end | no chimera.yaml.example in wheel + no `config init` |
| **MCP** | ✅ **FIXED at HEAD** (DF-CHIMERA-0906-2) | stdout is pure JSON-RPC again — initialize is line 1, no structlog/SDK lines; both `chimera-mcp` and `chimera mcp` verified via scripts/probe_mcp_stdio.py (NON_JSON_RPC_STDOUT_LINES=0); regression test tests/test_mcp_stdio_purity.py |
| PyPI 0.2.1 quickstart | ❌ dead-end | README `cp chimera.yaml.example` impossible; fixes unreleased (0.2.3 local only) |

### New pitfalls (2026-09-04)

19. **chimera-mcp stdout pollution — RESOLVED at HEAD (DF-CHIMERA-0906-2).**
    Root cause: provider auto-discovery logs (`provider_cache_hit` /
    `provider_discovery_done`) fire inside `load_config()`/`_apply_env_overrides`
    BEFORE `configure_logging()` runs, so structlog's unconfigured default
    wrote ConsoleRenderer lines to stdout (initialize shifted to line 3).
    Structural fix: the MCP path forces EVERY log sink to stderr before
    `load_config` (`observability.configure_logging(force_stderr=True)` +
    `mcp/server.py`), overriding even a config that asks for
    `use_stdout: true` — not a chimera.yaml flip. Regression gate:
    `tests/test_mcp_stdio_purity.py` (spawns both real entry points;
    fails on pre-fix code). Agents may resume MCP as the flagship path;
    REST `POST /v1/chat/completions` remains a verified alternative.
20. **PyPI lags HEAD by weeks — the fixes you read about may not be
    published.** PyPI latest 0.2.1 (Aug 23) still dead-ends the README
    quickstart; the repair (wheel ships example + `config init`) exists in
    HEAD 0.2.3 but is unreleased. Build/install from a HEAD wheel:
    `pip wheel --no-deps -w dist . && pip install dist/*.whl`.
21. **Auto formation picks models your key cannot reach — RESOLVED at HEAD
    (DF-CHIMERA-0906-3).** Default `auto` formation now restricts the
    dispatcher catalog AND the executed worker stages to models whose
    provider has resolved credentials (`auto_formation.restrict_to_credentialed_providers: true`
    by default), so a DEEPSEEK_API_KEY-only install designs DeepSeek-only
    formations. Named presets/custom DAGs and explicit request overrides
    (`allowed_models`/`worker_model`/`stage_models`) are unaffected. Set the
    flag to `false` (or `CHIMERA_AUTO_ALLOW_ALL_CATALOG=true`) to opt back
    into the full enabled catalog. On older builds the symptom is
    `model_blocked_guardrail` → 300s cooldown → `aggregator_partial_inputs`;
    the workaround there is pinning `worker_model`/`stage_models`.
22. **Check deploy parity before trusting live behavior.** `/health` exposes
    the running commit; compare with `git rev-parse --short HEAD`. Found
    30 commits behind on 2026-09-04 (third recurrence; delta was
    CLI/packaging-only that time, REST contract was correct — but you must
    check, not assume). Restart `chimera.service` to load HEAD.
23. **The supervised :8765 REST surface remains a verified alternative** —
    every OpenAI-compat contract behavior re-verified live 2026-09-04
    (stream 400, max_tokens honored, unknown-model 404, honest health).
    With DF-CHIMERA-0906-2 fixed, MCP is the flagship again for agents;
    REST stays verified for deployments that prefer HTTP.

## Update 2026-09-11 (7th run) — MCP flagship CONFIRMED by a real external client; PyPI quickstart fixed IN THE WHEEL; wheel-MCP caveat

Re-verified every entry point live (deployed :8765 = e4c7a30, 7/7 providers
healthy; repo HEAD 3b6ae77). The entry-point verdict table as of this run:

| Entry | Status 2026-09-11 | Evidence |
|---|---|---|
| **MCP (HEAD venv / `bin/chimera-mcp-hermes`)** | ✅ **FLAGSHIP — works from a real third-party client** | Hermes' own MCP client ran `chimera_deliberate` end-to-end: correct 3-sentence merged answer, 2× v4-pro workers + v4-flash aggregator, 66.1s, $0.0162, `worker_failures: []`; raw stdio probe = 3 stdout lines, 0 pollution |
| CLI (HEAD venv) | ✅ works, CLEAN stdout | stdout = answer box only (0 non-box lines), 18 log lines on stderr; `chimera models` legible (model/provider/tier); `test_mcp.py` 13/13 |
| REST :8765 | ✅ works | stream:true→400 `stream_not_supported`; unknown model→404; `model:"auto"`→200 "42" in 14.2s |
| PyPI 0.2.3 quickstart | ✅ **FIXED IN THE PUBLISHED WHEEL** | fresh venv: install 95s → `chimera --help` → `config init` → `chimera run` → "Paris" in 14s |
| **MCP (PyPI 0.2.3 wheel)** | ❌ **STILL POLLUTED — do not use the wheel's chimera-mcp** | raw probe: handshake clean (lines 1-2), but the real tools/call response is line 11 buried under 8 LiteLLM INFO lines on stdout. Pollution is LAZY — handshake-only smoke tests give a false green. Fix 27f0b35 (09-10) postdates the 09-08 release → use repo venv MCP until 0.2.4 publishes (DF-CHIMERA-0911-1) |

### New pitfalls (2026-09-11)

24. **The published wheel can be days behind the fix you read about —
    probe the wheel, not the checkout.** 0.2.3 shipped 09-08; the MCP
    stdout fix landed 09-10. `scripts/probe_mcp_stdio.py` already does
    real-call depth (tools/call, not just initialize) and exits non-zero
    on any non-JSON-RPC stdout line — run it against a fresh
    `pip install chimera-deliberation` venv when judging what users
    actually get. Release-canary task: DF-CHIMERA-0911-2.
25. **`model` on /v1/chat/completions takes FORMATION names, not model
    IDs.** POSTing `model:"deepseek/deepseek-v4-flash"` (a valid
    GET /v1/models key) 404s with `model_not_found` — the natural
    OpenAI-drop-in reflex dead-ends (DF-CHIMERA-0911-3). To force models,
    use `worker_model` / `stage_models` / `allowed_models` (docs/OPENAI_API.md).
26. **bunker-las-03 agent transports are down (:22 banner timeout AND
    gRPC :10001 dial timeout) while bunkerd :19090 responds** — the
    ephemeral-install leg stays SKIPPED (7th run; new signature narrows it
    to firewall/ACL, not bunkerd health; DF-CHIMERA-0911-4). Local
    fresh-venv install batteries stand in.

### Verified-still-true (2026-09-11)

- The dispatcher's per-worker prompt specialization is real value: for the
  DuckDB-vs-SQLite question it wrote an engine-level brief and a
  decision-criteria brief plus "exactly 3 sentences" merge instructions —
  and the merged answer complied, first try, no worker failures.
- Cost envelope for small deliberations: $0.003–0.02 (this run: $0.0162
  for a 2-worker auto/simple formation; $0.016 total_tokens ≈ 26.8k).
- `bin/chimera-mcp-hermes` wrapper (repo-root-resolving, explicit config)
  is the durable way to wire agents to the repo venv MCP server.

### Run-9 lessons (2026-09-16, field-tested on the PUBLISHED wheel + fresh clone)

27. **Use the official OpenAI SDK, not curl, when testing "OpenAI-compatible"
    claims.** `client.models.list()` now works: GET /v1/models serves the
    OpenAI `ListModelsResponse` envelope (`object`/`data`) with the legacy
    keyed map kept, additively, under `catalog` (INT-API-004, fixing
    DF-CHIMERA-0916B-2; before it the bare map made `page.data` None →
    TypeError: NoneType has no len). chat.completions itself works through
    the SDK (model="simple" → "Paris" in 27s).
28. **MCP probes MUST keep stdin open until the response lands.** A
    printf-pipe closes stdin after the request; the server hits EOF and
    exits BEFORE a long deliberation responds, so naive probes report a
    truncated session (looks like a broken server — it isn't). Driver
    pattern: Popen + background feed thread + readline loop until the
    request id answers; see docs/dogfood/2026-09-16-runB-integration.md.
29. **Fresh git clone ships the live chimera.yaml** — `chimera config init`
    refuses ("already exists. Use --force"). On a repo clone just use the
    shipped config (keys are ${VAR} refs); `config init` is for pip/wheel
    installs only. Rename tracked → gitignored is pending (DF-CHIMERA-0916B-4).
30. **Publish-vs-HEAD gap is a LIVE class again**: `chimera --version`
    documented in README works at HEAD (d6f144c) but not on the 0.2.5 wheel
    (shipped 09-12, flag added 09-14). Before trusting any README quickstart
    line against a release, check the flag exists in the PUBLISHED version.
31. **Fresh-box install is PROVEN (run 9)**: clone → venv → `pip install -e
    ".[full]"` = 68s, shipped config + one env var → real answer in 11s on
    a bare Debian box (las-bunker-03, agent destroyed after). The 7-run
    bunker SKIPPED streak was infra, not the project.

## Update 2026-09-20 (run 10) — the WEB UI: how to drive `/web/` and what not to trust

Run 10 was the first dogfood of the browser surface. The engine, CLI, REST, MCP
and the fresh install all still behave as the sections above describe. This
section adds only what a user of `/web/` needs.

### Driving it

```bash
chimera serve --host 127.0.0.1 --port 8765     # REST + SPA on one process
# open http://localhost:8765/web/  (form picker, prompt box, LIVE DAG panel)
```

The whole SPA is one file (`src/chimera/web/static/index.html`, inline JS) served
from the same app. If `/web/` answers 404 with "Static files not found", the
`[web]` extra is not installed — `pip install chimera-deliberation[full]`.

Scripted path (no browser) — session, then chat, both plain JSON:

```bash
SID=$(curl -s -X POST localhost:8765/web/sessions | sed 's/.*"session_id":"//;s/".*//')
curl -s -X POST "localhost:8765/web/sessions/$SID/chat" \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"Compare React and Vue","formation":"simple"}'
# -> {answer, trace, turn_number, mermaid}   (the mermaid string IS the DAG)
curl -s "localhost:8765/web/sessions/$SID"    # turn history + per-turn tokens/cost
```

Known-good keyboard-free recipe for a multi-turn session: reuse the same `SID`
for every `POST /chat`; past turns are injected into the dispatcher's prompt as
history. Verified live: turn 2 answered "distributed monolith" purely from turn
1's context. Session ids survive a browser reload (stored in `localStorage`).

### What works (verified 2026-09-20)

- Session creation, multi-turn memory, per-turn history with tokens + cost.
- The DAG **after** a run: correct mermaid with per-node model / tokens / latency.
- **Clicking a DAG node** opens a detail modal (kind, model, latency, input/output
  tokens, and the stage's output text). This is the nicest part of the UI.
- Node-click handlers only bind on nodes of `.mermaid svg` inside the rendered
  panel; if a click does nothing, the node was from a stale/duplicated SVG — one
  run leaves **two** SVG copies in the DOM (16 `g.node` for 8 real stages).

### What not to trust

- **The DAG is NOT live** (board `DF-CHIMERA-V2-18`). All three SSE broadcasts
  fire after `engine.deliberate()` returns, so the panel shows the placeholder
  for the whole run (measured 53 s of silence, then both trailing frames in the
  same millisecond as the HTTP response). Nothing is wrong with your prompt or
  your browser — the UI simply has no mid-run events. Wait for the answer.
- **`⏳ SSE reconnecting…` is normal on a session with turns**
  (`DF-CHIMERA-V2-19`). Sessions whose newest turn is older than 30 s get their
  SSE stream closed instantly with zero bytes, and the SPA retries every 3 s
  forever. It is a false alarm, not a degraded connection.
- **`POST /web/debug/reset` is a destructive test hook** (`DF-CHIMERA-V2-20`).
  Never call it on a server anyone is using: it rebinds the global session
  manager and wipes every live session. docs/SECURITY.md describes it as
  requiring the API key; on a default (`auth.enabled: false`) host it needs
  nothing.
- **`POST /web/sessions/{id}/chat` skips the REST queue/rate limiter**
  (`DF-CHIMERA-V2-22`), so browser sessions are not covered by
  `max_concurrent` / `max_queue_depth`.
- The DAG renderer is loaded from `cdn.jsdelivr.net` at page load
  (`DF-CHIMERA-V2-21`) — on a host with no egress the DAG panel stays blank and
  reports nothing.

### Smoke test for this surface (30 s, no browser)

```bash
curl -s localhost:8765/health                       # expect {"status":"alive","commit":"<HEAD>"}
curl -s -o /dev/null -w '%{http_code}\n' localhost:8765/web/     # expect 200
SID=$(curl -s -X POST localhost:8765/web/sessions | sed 's/.*"session_id":"//;s/".*//')
curl -s -X POST "localhost:8765/web/sessions/$SID/chat" -H 'Content-Type: application/json' \
  -d '{"prompt":"Reply with exactly: PONG","formation":"simple"}' | head -c 120
```
A 200 with an answer means the surface runs; it does **not** mean the DAG is
live — that needs the event stream timestamps, which is the run-10 finding.

## Update 2026-09-22 (run 11) — custom formations: author your own multi-stage DAG

The surface runs 1–10 never touched: a user-defined formation. Everything below
was executed for real against 0.2.7 @ faf78b4 (CLI, REST on a scratch port, and
a fresh bunker install).

### The recipe that works (custom formation)

```yaml
# chimera-user.yaml (scratch; point at it with --config or CHIMERA_CONFIG)
defaults:
  dispatcher: deepseek/deepseek-v4-flash
  default_worker: deepseek/deepseek-v4-pro
  default_aggregator: deepseek/deepseek-v4-flash
  lock_aggregator: true          # stops the dispatcher from re-picking your models
formations:
  code-review:
    dag:
      stages:
        - {id: security,    kind: worker, model: deepseek/deepseek-v4-flash, depends_on: []}
        - {id: performance, kind: worker, model: deepseek/deepseek-v4-flash, depends_on: []}
        - {id: verdict,     kind: merge,  model: deepseek/deepseek-v4-flash, depends_on: [security, performance]}
      edges: [[security, verdict], [performance, verdict]]
```

```bash
chimera --config chimera-user.yaml formations          # verify it loads (0.25s)
chimera --config chimera-user.yaml --formation code-review --json run "Review: ..."
# verify which stage ran on which model:
chimera --config ... --formation code-review --json run "..." | jq '.trace.stages'
```

Measured: 2 reviewers + merge = 86.9s cold / 31.9s warm (deepseek flash);
REST `POST /v1/deliberate {formation:"code-review"}` = 18.4s, 0 failures.
Output quality on a seeded-bug snippet was genuinely good (11 graded findings,
prioritized, plus a rewritten fixed function; the merge synthesized rather
than concatenated).

### New pitfalls (2026-09-22, all hit for real)

- **The default run path wants an `auto` formation your config may not define.**
  A minimal config with only your own formation: `chimera run "..."` →
  `error: Unknown formation: auto` exit 2. Always pass `--formation <name>` in
  scratch configs (or add `auto: {mode: auto}`). CONFIG.md's custom-formation
  example omits `auto` — copying it verbatim reproduces the exit 2.
  [DF-CHIMERA-V2-33]
- **`--stage-models` keys are matched against stage ids silently.** A typo'd
  id (`nosuchstage`) is dropped without warning, error, or exit-code change —
  the override just does not apply. After any override, check
  `.trace.stages[].model` to confirm it landed. [DF-CHIMERA-V2-32]
- **Degraded merges look like healthy answers.** If a worker stage times out
  (default 120s per stage), the merge proceeds on partial inputs, RC=0, and
  the only signals are JSON structlog lines on stderr (`engine_stage_timeout`,
  `aggregator_partial_inputs`) plus `worker_failures` in the `--json` trace —
  NOT the plain `warning:` lines USAGE.md's table promises. For pipelines
  where a half-reviewed answer is dangerous, parse `worker_failures` or gate
  on it. [DF-CHIMERA-V2-34]
- **Per-stage timeout knob:** `timeout.per_stage_s` in chimera.yaml (request
  header `X-Chimera-Timeout` overrides; engine falls back to 120.0). Not
  mentioned in CONFIG.md's formation/model sections — if your fan-out models
  are slow, raise it there. [DF-CHIMERA-V2-34 detail]
- **Category weights are percent (0–100), not fractions.** The CONFIG.md
  example itself writes 0.90 and triggers `category_scale_normalized`
  (×100 rescale) warnings on every load. Write 90. [DF-CHIMERA-V2-35]

### Verified-still-true (2026-09-22)

- Fresh-install quickstart on a bare Debian bunker: venv +
  `pip install chimera-deliberation[full]` = 54s → `config init` works from
  the PACKAGED example (run-9's already-exists trap is gone on 0.2.7) →
  first answer with only DEEPSEEK_API_KEY in 30s. [DF-CHIMERA-V2-36]
- PyPI 0.2.7 == repo version == live :8765 server commit (`/health` carries
  the running git commit; it matched checkout HEAD faf78b4).
- Custom formations serve over REST unchanged (`/v1/formations`,
  `/v1/deliberate`) when the server is started with the same scratch config.
- Inline `--dag '{"stages":[...],"edges":[...]}' --allow-custom-dag` works
  exactly as USAGE.md documents (40.2s, 2 stages, $0.005). Trace labels the
  formation `auto` — cosmetic.

## Update 2026-09-24 (run 13) — the DOCKER deployment path

**Proven end-to-end on a fresh bunker box (bare Debian user, agent 5d1b8e8e,
destroyed):** clone public repo (4s) → `docker compose build` (106s) →
`DEEPSEEK_KEY=<key> docker compose up -d` (<1s, container healthy) →
POST /v1/deliberate simple → `"Paris"` with full trace (34s cold / 32s, 30s
warm). `docker run --rm <image> --version` → `chimera 0.2.7`. No sudo, no
compose-plugin install, no toolchain prep needed — compose v5.5 is already on
bunker agents.

Recipes:

```bash
docker compose build                        # image: pip install chimera-deliberation[full]>=0.2.0
DEEPSEEK_KEY=sk-... docker compose up -d    # env keys only, no YAML edit needed
curl localhost:8765/v1/health               # degraded + per-provider classes until keys are set
curl -o /dev/null -w '%{http_code}' localhost:8765/web/   # 200
```

Pitfalls (all hit for real):

1. **The image is release-based**: it installs the latest *PyPI wheel*
   (0.2.7), not your checkout. Repo fixes reach the container only after the
   next release. Debug the release chain first when "the fix isn't in the
   container".
2. **Key-name split**: Dockerfile/compose docs say `DEEPSEEK_KEY`; the shipped
   `chimera.yaml.docker` template expands `${DEEPSEEK_API_KEY}`. Both names
   currently work (`config._apply_env_overrides` maps both), but the docker
   leg should pin the short Docker-friendly name the docs use.
3. **Credential-path probe without a secret**: put an obviously-fake key in
   `DEEPSEEK_KEY` and re-up. /v1/health flips the provider from
   `missing-credentials` to `auth: ... api key ****-x is invalid` — a real
   provider round-trip proving the env var reached the engine.
4. **`commit: "unknown"` in /health inside a container** is expected (wheel
   install has no git metadata); the container still reports model/provider
   counts and works.
5. **Sessions wipe on container restart** — in-memory by design; the compose
   `restart: unless-stopped` policy is for crashes, not data.
6. **Bunker docker socket**: `/run/bunker/<agent>/docker.sock`, not
   `/run/user/<uid>/docker.sock`; use `docker -H <socket>` (a DOCKER_HOST env
   export may trip control-host gates) — compose works as-is against it.

## Update 2026-09-25 (run 14) — the PYPI WHEEL and an INDEPENDENT MCP client

Runs 1-13 always ran chimera from a repo checkout or a compose image. Two
surfaces were never touched: the wheel a `pip install
chimera-deliberation[full]` user actually runs, and the MCP server driven by
a client that is not this repo's probe.

PyPI-wheel install (proven twice, including a bare Debian 3.13.5 agent):

```bash
python3 -m venv venv && venv/bin/pip install 'chimera-deliberation[full]'
chimera config init        # template found INSIDE site-packages — no repo needed
chimera --quiet "…"        # real merged answer; python -m chimera also works
```

- Numbers: 36s install + 29s first answer (py3.11, warm box); 266s install +
  18s answer (bare 3.13 agent). Warm CLI ≈11s, wall == trace duration_ms
  (model-bound, zero client overhead).
- Tooling traps (mine, not the product's): `uv venv` ships no pip — use
  `python3 -m venv`; `uv` defaults to the NEWEST CPython — pass
  `--python 3.11`.

Independent MCP client (no npx, no repo code): ~60 lines of stdio JSON-RPC —

```python
p = subprocess.Popen(["chimera-mcp"], stdin=PIPE, stdout=PIPE, text=True)
send {"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{...}}}
send {"jsonrpc":"2.0","method":"notifications/initialized"}          # notification, no id
send {"jsonrpc":"2.0","id":2,"method":"tools/list"}                  # 3 tools
send {"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"chimera_deliberate","arguments":{"prompt":"..."}}}
```

- initialize 0.5s; tools `chimera_deliberate` (prompt required;
  formation/stage_models/dag optional), `chimera_formations`,
  `chimera_models`; full trace comes back inside the content text.
- Full client: `docs/dogfood/2026-09-25-integration.md` (run 14). Works
  identically local and on a fresh agent — interop is not machine-specific.
- The repo's `scripts/mcp-liveness-check.sh` needs npx and cannot run on
  wheel-only machines (DF-CHIMERA-V2-52); use the raw client instead.
