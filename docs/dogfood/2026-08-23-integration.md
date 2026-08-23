# Chimera Integration Report — 2026-08-23 (third dogfood run)

Real-use run against chimera-v2 HEAD (486a409) + the live :8765 deployment.
Everything below was executed for real; every command ran to completion.
Placeholder note: keys were loaded from the machine's env file — never commit
real keys; use `${VAR}` tokens in chimera.yaml as documented.

## What was tested and what works

| Path | Result | Evidence |
|---|---|---|
| CLI `chimera run` (fresh `[full]` wheel) | ✅ | "capital of France" → correct answer, 17.7s, $0.004 trace |
| CLI `-v` trace | ✅ | full per-stage trace printed (tokens/cost/latency) |
| `chimera formations` / `chimera models` | ✅ | rich table, 6 presets, 36 configured models |
| REST `POST /v1/chat/completions` (live :8765) | ✅ | real answer + usage; unknown model → 404 `model_not_found` with helpful valid-values hint |
| REST `POST /v1/deliberate` | ✅ | unknown formation → 422 with detail |
| REST health battery | ✅ | `/health`, `/v1/health` (7/7 providers, per-provider `model_tested`), `/v1/health/ready` 200, `/v1/health/live` |
| Web UI + OpenAPI docs | ✅ | `/web/` 200, `/docs` 200 |
| MCP `chimera mcp` (subcommand) | ✅ | initialize handshake returns serverInfo (CH-GAP-028 fix verified in wheel) |
| **Library** (fresh wheel, `[full]` extra) | ✅ | custom 3-stage DAG (researcher→critic→final) via `Engine.deliberate(formation="custom", dag=..., allow_custom_dag=True)` → excellent merged answer + full trace |

## The working library recipe (the "aha")

```python
import asyncio
from chimera import Engine, LiteLLMGateway, load_config

async def main():
    config = load_config()            # CHIMERA_CONFIG env or ./chimera.yaml in cwd
    engine = Engine(config, LiteLLMGateway(config))
    result = await engine.deliberate(
        "Compare SQLite vs PostgreSQL for a single-user notes app. Recommend one.",
        formation="custom",
        dag={"stages": [
            {"id": "researcher", "kind": "worker", "model": "deepseek/deepseek-v4-flash", "depends_on": []},
            {"id": "critic", "kind": "aggregator", "model": "deepseek/deepseek-v4-flash", "depends_on": ["researcher"]},
            {"id": "final", "kind": "aggregator", "model": "deepseek/deepseek-v4-flash", "depends_on": ["critic"]},
        ], "edges": [["researcher", "critic"], ["critic", "final"]]},
        allow_custom_dag=True,
    )
    print(result.answer)              # str
    t = result.trace.model_dump()     # DeliberationTrace is pydantic — use model_dump()

asyncio.run(main())
```

Result: a genuinely strong, nuanced recommendation (SQLite with WAL +
synchronous=FULL reasoning). **Wall time: 4m15s** for this 3-stage sequential
DAG — plan for minutes, not seconds, on custom DAGs (auto mode was 17–34s).

## Errors hit and their causes (all real)

1. **`ModuleNotFoundError: No module named 'fastapi'`** — bare `pip install
   chimera-deliberation` (PyPI 0.2.0, published Jul 19) then `from chimera
   import Engine`. The CH-GAP-026 fix exists only in unreleased HEAD; the
   published artifact is still broken. **Workaround:** install
   `chimera-deliberation[full]`, or build the wheel from HEAD.
2. **`ModuleNotFoundError: No module named 'rich'`** — bare install of the
   FRESH HEAD wheel then `chimera --help`. The console scripts ship in the
   base package but their deps (click/rich/mcp) are extras-only.
   **Workaround:** install `[full]`.
3. **`dispatcher_parse_failed ... 'dispatch produced no aggregator/merge/audit
   stage'`** → `source=fallback` on 1 of 2 auto runs. The dispatcher emitted
   edges referencing an aggregator stage it didn't define; engine silently
   degraded to a 1-worker formation. The answer is still correct — the trace
   (`source`) is the only signal. **Check `trace.source`; retry once.**
4. **Live server ignores `stream:true` and `max_tokens`** (200 non-stream
   full completion; 3548-token essay for max_tokens:1). Root cause: the
   systemd service on :8765 has been running since 2026-08-14 14:53 — before
   the CH-GAP-030/031 fixes landed. HEAD code rejects stream with 400 and
   honors max_tokens. **Check service start time before trusting live
   behavior** (`systemctl show chimera -p ActiveEnterTimestamp`); restart to
   get HEAD behavior.
5. **`/home/kara/.hermes/.env: line 39: Agent: command not found`** when
   sourcing the env file — a malformed line in that file, not a chimera bug;
   the shell `source` aborts that line but the keys still load.

## Deployment reality (read before relying on :8765)

- The supervised service runs **Aug-14 code**, ~9 days behind HEAD. Board
  fixes were verified on throwaway servers (:8790/:8799), never restarted
  into production. There is no documented deploy step (AGENTS.md has none).
- `pip install chimera-deliberation` from PyPI gives you the **July product**
  (0.2.0): broken bare import, silent stream/max_tokens, no model 404, port
  8000 default. All fixed in HEAD, none released, 186 commits unpushed.

## Verdict snapshot

Core engine: real and valuable (multi-model deliberation with honest traces,
~$0.004–0.02/run). Distribution is the weak layer: published artifact stale,
live deployment stale, bare-install entry points crash. See
`docs/dogfood/diagnostics.md` for the full diagnostic trail and the board
(CH-GAP-039..044) for the filed tasks.
