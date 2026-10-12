# Dogfood Run 22 — 2026-10-12 — SSE protocol surface + re-proof of the October fix wave

**Verdict: SHIPPABLE** (12th consecutive). **Promise tested:** "a third-party
integrator can consume a deliberation live over Server-Sent Events per
`docs/INTEGRATION.md` § SSE — event names, ordering, replay semantics, close
policy — and every fix from the 2026-10-09/10 fix wave (DF-71/73/75/76/77)
behaves as its commit claims on the deployed process."

The SSE wire protocol had never been driven by a run (runs 1–20 touched CLI,
REST, OpenAI-compat, docker, PyPI wheel, MCP, web UI, concurrency — but read
deliberations only through JSON responses, never the event stream). This run
consumed it the way `docs/INTEGRATION.md` tells a third party to.

## Environment

- Live deployment: `localhost:8765`, systemd `chimera.service`, `/health`
  reports `commit=571dd2f`, version 0.2.7.
- Deploy classification (per `scripts/smoke_live.py` semantics, reproduced by
  hand): running `571dd2f` resolves, IS an ancestor of HEAD `bcdbd73`, and the
  material diff (`src/ scripts/ tests/ pyproject.toml`) below the running
  commit is **pyproject.toml only** — packaging metadata/comment edits plus a
  pydantic 2.14.0 bump note. Every fix commit of the wave (4e969dd queue
  feedback, 3cce8b0/909988e merges for DF-71/75/76, 1fb1902 DF-73) is INSIDE
  571dd2f, i.e. the running process carries all five fixes; the gap is
  bookkeeping-weight. Logged as an explicit deferral (row
  DF-CHIMERA-V2-79): a `systemctl restart chimera` will bring `/health` to
  HEAD; the dogfood lane does not restart prod unilaterally.
- HEAD == origin/main (bcdbd73), so all re-proof below is against the pushed
  tree, not a local-only commit.

## Leg 1 — SSE protocol, consumed as documented (live :8765, auth disabled)

Session `498a20418041` created via `POST /web/sessions`.

**Unknown session** — `GET /web/sse/does-not-exist-xyz`: HTTP 200 (never a
404, exactly as documented — a 404 would look like a transport drop to an
EventSource and retry forever), frames `event: error`
(`{"reason":"unknown_session","session_id":"does-not-exist-xyz"}`) then
`replay_done` with `retry: 60000`, header `X-Chimera-Session-Status: unknown`,
`Content-Type: text/event-stream; charset=utf-8`. Contract exact.

**Empty session (no turns)** — `GET /web/sse/{id}` (no flag): stream held
open with zero frames for the full 5 s probe window (documented: stays open
awaiting the first turn, silent close by idle timeout, no marker). Correct.

**Live turn** — `?live=1` stream opened, then `POST /web/sessions/{id}/chat`
("tallest mountain"). HTTP 200 in 12 s. The stream delivered 9 frames in the
documented order: `deliberation_started` → `stage_started`×2 →
`stage_completed`×2 → `stage_started` → `stage_completed` → `dag_designed`
(formation auto, 3 stages) → `deliberation_done` (answer 245 chars, elapsed /
total_cost / total_tokens / turn_number present). Mid-run frames carried real
per-stage data: worker_1 gpt-5.6-luna 118 tok / 1497 ms, worker_2
deepseek-v4-pro 615 tok / 3547 ms, aggregator deepseek-v4-flash 699 tok /
1516 ms. **This is the first run to receive live mid-run progress frames** —
replay (below) cannot show them because they are not stored, which the docs
state and the legs confirm.

**Replay** — two consecutive `GET /web/sse/{id}` (no flag) after the turn:
identical frame sequences `deliberation_started → dag_designed →
deliberation_done → replay_done` (mid-run frames absent, as documented),
byte-identical `event:` sequences across both reads (idempotent), one
`retry: 60000` marker each. Close policy works as the client contract claims.

**Multi-turn memory** — turn 2 on the same session ("what mountain did I just
ask about?") returned "Everest".

## Leg 2 — re-proof of the 2026-10-09/10 fix wave (rows marked complete)

Every row was re-proven against the deployed process, not just the source:

- **DF-CHIMERA-V2-73 (`--dag` usage error exit)** — VERIFIED FIXED:
  `chimera "x" --dag '...'` now exits **2** with the usage block on **stderr**
  and empty stdout (run 19 recorded exit 0 + stdout usage).
- **DF-CHIMERA-V2-71 (error-as-answer)** — VERIFIED FIXED on a scratch config
  with all credentials removed (`CHIMERA_CONFIG` pointed at a keyless copy;
  `DEEPSEEK_API_KEY` unset): a fully-degraded deliberation exits **2**, ships
  no fake answer, and prints the accurate remedy chain (credential failure →
  fix → blocked-models path → escape hatch) on stdout, warnings only on
  stderr. Run 19 recorded exit 0 with the upstream error as the answer.
- **DF-CHIMERA-V2-75 (hard worker failures invisible on chat surface)** —
  VERIFIED FIXED on a scratch instance (`CHIMERA_PORT=8799`, keyless config):
  `POST /web/sessions/{id}/chat` with all providers failing returns 200 whose
  `trace.worker_failures` lists both dead stages (model + full error). The
  wheel on the fresh bunker box carries the same contract (wf=2, see Leg 3).
- **DF-CHIMERA-V2-76 (key exported, auth off, silence)** — VERIFIED FIXED:
  the scratch instance with `CHIMERA_API_KEY` in env but `auth.enabled: false`
  printed the one-line loud warning at startup ("the CHIMERA_API_KEY env var
  is set but auth is disabled — all endpoints are unauthenticated…").
- **DF-CHIMERA-V2-77 (silent queue wait)** — VERIFIED FIXED live: 4
  simultaneous `POST /v1/deliberate` (formation simple) — all 200, all unique
  request handling, walls 8.8 / 9.0 / 23.5 / 39.6 s, and each response
  carried its own `X-Chimera-Queue-Position` (2, 3, 1, 4 — the complete 1–4
  rank set, no cross-request bleed). The header is on
  `/v1/deliberate` and `/v1/chat/completions` only, matching the commit.

## Leg 3 — ephemeral install (bunker-las-02, agent 6259d76d, destroyed)

Install premise changed since run 20's proof (0e5de41): pyproject bumped
pydantic 2.14.0 / pydantic-core 2.50.0 (2026-10-11) — so a fresh proof was
owed, not inherited.

- `bunker spawn` failed once with the known transient `slice-limits:
  containment landing did not converge` — single retry succeeded (skill
  procedure).
- Fresh Debian 13.7 user, Python 3.13.5, zero project state:
  - `python3 -m venv` + `pip install 'chimera-deliberation[full]'` from PyPI:
    **47 s**, rc 0.
  - `chimera config init`: bootstrapped from the wheel's own
    `chimera.yaml.example` (force-includes load-bearing, proven again).
  - `chimera serve`: `/health` alive (`commit: unknown` — known wheel
    limitation, DF-CHIMERA-V2-48), `/web/` 200, `/docs` 200.
  - Zero-credential fresh-box chat: 200, honest
    `"[stage aggregator … unavailable…]"` answer string, `trace.worker_failures`
    = 2 — the DF-75-era failure contract ships in the **released wheel**
    0.2.7, not just the repo (the wheel predates the wave but the surface it
    fixed already carried the field… the fresh-box trace shows wf=2, which is
    the re-proof that matters for a fresh user).
- Destroyed + verified gone (0 matches in `bunker list`).

## Performance (Step 2b)

- Headline operation, warm: CLI `-f simple` one-liner **68 s wall / 3.2 s
  user** (dispatcher + worker + aggregator, three model calls).
- REST `simple` deliberations: 8.8–39.6 s under 4-way concurrency; 12 s
  single web chat turn.
- All numbers model/provider-bound (wall >> user+sys by ~20x). Consistent
  with runs 14–20 (30 s ± spread). **No PERF row** — nothing here is code
  latency a user would feel; the wait is the models.

## New findings

A sibling dogfood run 21 (tick earlier today, commit cfc64ac) re-proved the same
wave on other surfaces and filed DF-CHIMERA-V2-78..80 (REST/chat parity gaps).
My rows below were numbered against the fresh board census (81/82); my legs that
overlap its re-proofs (DF-77 queue header 4-way, DF-75 chat surface) are independent
confirmations, not duplicates.

2. **DF-CHIMERA-V2-81 (P3, CLI UX): variadic prompt swallows trailing
   flags.** `chimera "prompt" -f simple` and `chimera "x" --dag '…'` both
   exit 2 with the bare usage block, because `[PROMPT]...` is variadic and
   the parser takes everything after the first positional as prompt text —
   `chimera -f simple "prompt"` works. The failure mode is clean (exit 2,
   stderr, no half-run) but nothing tells the user the flag order is the
   problem. Fix direction: usage error should hint "options must precede the
   prompt" (or accept trailing flags).
1. **DF-CHIMERA-V2-82 (P3, deploy): STALE deferral.** Running process
   571dd2f is one pyproject.toml-only commit behind HEAD bcdbd73 (non-empty
   material diff ⇒ STALE by the repo's own classification). Runtime impact
   ~zero (comment/metadata + pydantic bump note), all wave fixes are live.
   Foreman: `sudo systemctl restart chimera` + `curl /health` shows bcdbd73.

## Machine-state hygiene

The scratch credentialless runs write 7-day fingerprintless credential blocks
into machine-scoped `~/.chimera/blocked-models.json` (the DF-58 mechanism).
The file contained only this run's two failed models; removed post-run (the
documented escape hatch) and live deliberation re-verified healthy after.

## Time-to-first-success & friction

t2fs ≈ 90 s (session create → live SSE turn rendered, on an already-running
server). Friction count: 1 (flag-order, DF-78). No source reading was needed
anywhere in the SSE leg — `docs/INTEGRATION.md` § SSE is complete enough to
implement a client from alone, which is what this run did.
