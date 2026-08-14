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
