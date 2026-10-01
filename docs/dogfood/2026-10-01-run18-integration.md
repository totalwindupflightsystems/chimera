# Dogfood Run 18 — 2026-10-01 (Web UI Scripted Multi-Turn, Real Keys)

**Promise:** "A real user creates a web session, holds a MULTI-TURN conversation, and Chimera's session memory carries context across turns — every turn dispatched to a panel, merged, and recorded with per-turn tokens and cost."

This run retried the surface run 17 (2026-09-28) abandoned as blocked: run 17 could not
authenticate the `/web/*` endpoints at all and its browser tool died. Run 18 scripts the
same surface with a real Authorization header, no browser needed — exactly the way
USAGE.md's "Scripted path (no browser)" recipe documents it.

**Verdict:** ✅ SHIPPABLE for the scripted multi-turn web surface (the surface run 17
called blocked works once the documented auth is provided).

## Scenario (real use, three turns, one session)

Key from the operator's env (auth.mode=env). Session `91d6baedcf6b`:

1. Turn 1 — "In one sentence: why is the sky blue?" → 57.6s wall, correct Rayleigh answer，
  panel = dispatcher deepseek-v4-flash + workers openai/gpt-5.6-luna and qwen3.7-max,
  26,486 tokens, $0.0384 (trace cost fields populated).
2. Turn 2 — "What did I just ask you, and what color did that question concern?" → 12.1s,
  answer quoted the previous turn correctly: "You just asked why the sky is blue…".
  Multi-turn memory WORKS through the session-preamble context (conversation context
  22,826 tokens).
3. Turn 3 — "Combining both turns, one sentence: what physical quantity decreases with the
  fourth power of wavelength?" → 23.4s, correctly fused both turns into Rayleigh
  σ ∝ 1/λ⁴.

`GET /web/sessions/{id}` returned turn_count=3 with full per-turn history: user_prompt,
answer, formation, dispatch/worker/aggregator models, total_tokens, total_cost — a real
audit trail per turn.

## Negative cases (all held)

- No key on POST /web/sessions → 401 (run 17's DF-CHIMERA-V2-64 behavior re-confirmed).
- Wrong key → 401.
- Unknown formation on chat → HTTP 422 with the available-formations detail (contract
  holds on the web surface as documented).
- Unknown session id → 404.

## Findings (downgrades, then filed as rows)

- **No session DELETE** (DF-CHIMERA-V2-69 P2): the API exposes no way to close a
  session — `DELETE /web/sessions/{id}` → 405, and `SessionManager.delete()` exists in
  `src/chimera/web/session.py:125` with no route wired to it. A user's only cleanup path
  is the global destructive `/web/debug/reset`. `curl localhost:8765/openapi.json` lists
  only GET on `/web/sessions/{session_id}`.
- Run 17's "blocked" sting is re-graded: the block was a missing documented auth step,
  not a product dead-end. USAGE.md's scripted recipe is the correct path and it works.

## Timing (PERF — nothing user-felt)

- Turn-2 wall 12.1s vs trace ms 10,088 → ≥83% pure LLM call time; 3 turns ≈ 93s total for
  a real 3-question conversation. Warm box, model-bound. No PERF row filed: nothing to
  optimize that a user would feel — the numbers are the price of a multi-model panel.

## Install leg

SKIPPED-install-bunker — runs 2–14 proved install on bunker-las-03 repeatedly; last
PROVEN leg (run 14, agent c26d8af2, install 266s + real deliberation, destroyed). No
repo file relevant to install changed since. Cross-referenced as the documented skip.

## What a maintainer should fix first

Delete route for sessions — sessions are created in one call but live forever except via
the destructive global reset.
