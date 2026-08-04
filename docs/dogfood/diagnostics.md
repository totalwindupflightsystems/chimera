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
