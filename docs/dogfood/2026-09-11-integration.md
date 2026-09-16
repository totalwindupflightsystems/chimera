# Dogfood Integration Report — 2026-09-11 (7th run)

**Verdict: SHIPPABLE (confirmed, with one release-lag caveat)**
**Promise under test:** "One API call. A team of models. One answer." — a user can
get a multi-model deliberated answer via CLI, REST, Python library, or MCP tools
for agents.

## What this run did differently (additive to prior runs)

Prior runs established the CLI/REST/library paths and twice filed the
chimera-mcp stdout pollution as P0. This run's new ground:

1. **MCP exercised by a REAL external client, not just a probe.** Hermes (the
   primary stated user: "AI agents") called `chimera_deliberate` through its
   own MCP client against the repo's `bin/chimera-mcp-hermes` wrapper
   (repo HEAD venv, post-fix 27f0b35). Real end-to-end result:
   - Prompt: "In exactly 3 sentences: when is DuckDB a better choice than
     SQLite for an analytics workload?"
   - Result: correct, well-merged 3-sentence answer;
     formation=auto→simple, workers `deepseek/deepseek-v4-pro` ×2 +
     aggregator `deepseek/deepseek-v4-flash`;
     66.1s total, **$0.0162**, 26,795 tokens, `worker_failures: []`.
   - The dispatcher wrote genuinely specialized per-worker prompts
     (engine-level brief vs decision-criteria brief) and merge instructions
     enforcing "exactly 3 sentences" — the answer complied. This is the
     product working as designed, in production, from a third-party client.
2. **Raw stdio bisection of the published wheel vs HEAD** (details in
   diagnostics.md). HEAD: 3 stdout lines, 0 pollution. PyPI 0.2.3:
   handshake clean, **8 LiteLLM INFO lines pollute stdout around the real
   tools/call response** → 0.2.3's `chimera-mcp` is unusable by conforming
   clients. Fix exists at HEAD (09-10); wheel published 09-08 → publish 0.2.4.
3. **Fresh-user journey on PyPI 0.2.3 (the thing users actually install):**
   clean venv → `pip install chimera-deliberation[full]==0.2.3` (95s) →
   `chimera --help` works instantly → `chimera config init` creates config
   from the shipped template → `chimera run "capital of France"` → clean
   answer box "Paris" in **14s**. The 0.2.1 dead-end is fixed IN THE PUBLISHED
   artifact.
4. **Live REST contract battery** (deployed :8765 = e4c7a30, 7/7 providers
   healthy): `stream:true`→400 `stream_not_supported`; unknown model→404;
   `model:"auto"` real deliberation→200, "42", 14.2s. New wrinkle:
   `model:"deepseek/deepseek-v4-flash"` (a valid catalog ID)→404 — `model`
   takes FORMATION names only; forcing models is `worker_model`/
   `stage_models`/`allowed_models`. Consistent with docs, surprising for an
   "OpenAI drop-in" (task DF-CHIMERA-0911-3).
5. **Prior fixes verified in real use at HEAD:** `chimera models` now renders
   legible model/provider/tier columns (was 3-char truncation);
   `chimera run` stdout is ONLY the answer box, logs on stderr (18 lines,
   0 on stdout). `tests/test_mcp.py` 13/13 (the 09-07 drift failure is fixed).

## Bunker install leg

SKIPPED for the 7th consecutive run — but with a NEW, more diagnostic
failure signature: `bunker list` (bunkerd :19090) succeeds, while
`bunker spawn` dies one hop deeper (`dial tcp bunker-las-03:10001: i/o
timeout`) and ssh :22 times out during banner exchange. Both agent-transport
paths down while the bunkerd API is up → firewall/ACL regression on the
host, not bunkerd health. Filed as DF-CHIMERA-0911-4. Local fresh-venv
install batteries stand in as installability proof (95s, real answer).

## Time-to-first-success and friction

- T2FS (fresh PyPI user, install→answer): **~2.5 min** (95s install + 14s run).
- T2FS (agent via MCP at HEAD): ~1 min (wrapper works, first call answered).
- Friction count this run: **3** (wheel MCP pollution; direct-model 404
  reflex; bunker infra down). Down from 10-11 in earlier runs.

## What we'd tell the maintainer (1 hour of time)

1. Publish 0.2.4 (the fix is sitting in HEAD unreleased — again).
2. Wire the release canary: fresh venv → install published wheel → run
   `scripts/probe_mcp_stdio.py` (it already does real-call depth) → fail on
   drift (DF-CHIMERA-0911-2).
3. Make the chat/completions 404 teach the override fields.
