# Chimera Dogfood — Integration Report (2026-08-03)

Real-use run against the live deployment on this machine. Everything below
was executed for real; nothing is simulated.

## What was tested

| Path | Result | Evidence |
|---|---|---|
| MCP `chimera_deliberate` (auto) | ✅ Works | 2-worker DAG (gpt-5.6-sol + qwen3.7-max), merged 3-sentence answer, `source=auto`, 68.9s, $0.019 |
| MCP custom DAG (researcher→critic→final) | ✅ Works | `source=custom`, sequential execution, per-stage instructions written by dispatcher, 29s, $0.0033 (answer wrapped in ```json fence — minor) |
| CLI `chimera run` (auto) | ✅ Works | Boxed answer + per-stage trace table; graceful fallback when dispatcher output malformed; auto plaintext retry on json-mode rejection |
| REST `GET /v1/models`, `/v1/formations`, `/web/` | ✅ Works | 36 models / 5 providers catalog; 6 formation presets; web UI served (HTTP 200) |
| REST `POST /v1/chat/completions` | 🔴 Broken | HTTP 200 but content is `[stage aggregator (deepseek/deepseek-v4-flash) unavailable: ... Missing credentials ...]` |
| REST `POST /v1/deliberate` | 🔴 Broken | Same 200+error-string; `aggregator_model` override silently ignored |
| REST `GET /v1/health`, `/v1/health/ready` | 🔴 Lying | "degraded" / "Not ready — no providers reachable", while the same providers succeed via CLI/MCP |

## The working recipe (MCP — the agent path)

```python
# From any MCP client (Hermes/Claude Code) with the chimera server attached:
result = chimera_deliberate(
    prompt="<real task>",
    formation="auto",          # dispatcher designs the DAG
)
answer = result["answer"]      # merged output
trace  = result["trace"]       # per-stage model/tokens/cost/latency
```

- `formation="auto"` = dispatcher picks workers + writes their prompts + merge
  instructions. Verified: genuinely diverse team (different providers), and the
  merge actually combines both workers' strengths.
- Custom DAG: pass `dag={"stages":[...],"edges":[...]}` + `allow_custom_dag=True`.
  The dispatcher keeps writing the prompts but honors YOUR structure exactly.
- Every response includes `trace` with per-stage `model`, `tokens_input`,
  `tokens_output`, `latency_ms`, `cost` — the single best feature of this
  project. Cost accounting matched reality (~$0.003–0.02 per small run).

## The CLI recipe

```bash
cd <repo>                     # needs .env next to chimera.yaml
chimera run "Your prompt"     # prints boxed answer
chimera -v run "Your prompt"  # + full trace table (stage | tokens | latency | cost)
chimera formations            # list presets
chimera serve                 # REST + web UI on :8765
```

## Errors hit and what they mean

1. **`[stage X unavailable: ... Missing credentials ...]`** (HTTP server only)
   → the `serve` process has no provider keys in its env. The CLI and MCP
   paths load the repo `.env`; `serve` evidently does not. Workaround: start
   it with `set -a; source .env; set +a` or export `OPENROUTER_API_KEY`
   before `chimera serve`.
2. **`No endpoints available matching your guardrail restrictions`** (OpenRouter
   404) → the account's OpenRouter privacy/guardrail settings block some
   models (e.g. qwen3.7-plus). The dispatcher will happily pick them; the
   engine degrades to a partial merge. Fix at https://openrouter.ai/settings/privacy
   or accept the degraded merge (it is handled gracefully).
3. **`dispatcher_parse_failed: dispatch produced no aggregator/merge/audit stage`**
   → the dispatcher LLM emitted a DAG without the aggregator in `stages[]`.
   Engine falls back to a single-worker preset (`source=fallback`). Not fatal,
   but you lose the multi-model promise for that call; retry usually fixes it.
4. **`This response_format type is unavailable now`** → provider rejected
   `json_object` mode; engine auto-retries plaintext and succeeds. Noise, not
   breakage.
5. **HTTP 422 on `/v1/deliberate`** with `messages:[...]` → the endpoint wants
   `prompt` (string), not OpenAI-style `messages`. Check `/openapi.json`.

## What a new user needs that isn't documented

- `.env` must sit next to `chimera.yaml` AND be loaded into the process env
  (the CLI/MCP do it; `serve` may not — see finding #1).
- `lock_aggregator: true` in chimera.yaml silently overrides request-level
  `aggregator_model` overrides. Read the config before overriding.
- The first CLI call triggers a LiteLLM provider-catalog refresh (179
  providers, ~1–2s); subsequent calls hit the cache.
- Dispatcher calls are token-heavy (~17k input tokens) because the model
  catalog is in context — that's the ~$0.003 floor per run.
