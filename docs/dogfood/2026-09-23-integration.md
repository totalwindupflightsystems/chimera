# Dogfood Integration Report — Run 12 (2026-09-23): the web UI in a REAL browser

**Target:** chimera-v2 @ e231b14 (deployed :8765 commit == HEAD), package 0.2.7.
**Angle:** runs 1-11 swept CLI / REST / MCP / library / custom formations / wheel
install. Run 10 touched `/web/` with curl only ("Scripted path (no browser)").
This run drove the SPA in an actual browser — the one surface no prior run had
exercised end-to-end.

**Promise under test:** "Open http://localhost:8765/web/ for the web UI with
live DAG visualization" — a user opens the URL, types a prompt, watches the
DAG, gets a merged answer, keeps a multi-turn session.

## What a real browser run looks like (the technique)

No browser tooling was assumed available; a stock headless Chrome + CDP is
enough, and this recipe is reusable for any future web-surface dogfood:

```bash
/usr/bin/google-chrome --headless=new --remote-debugging-port=9333 \
  --remote-allow-origins=* --user-data-dir=/tmp/<profile> about:blank
# then over the DevTools websocket: Page.navigate to /web/, Runtime.evaluate
# to fill #prompt-input (use the prototype value setter + input event so the
# SPA's listeners fire), click #send-btn, poll the #stat-* bar for completion.
```

Traps hit while wiring this (all mine, all cheap to avoid): the CDP websocket
403s without `--remote-allow-origins=*`; a leftover chrome process holding the
profile dir makes a fresh launch silently join the OLD process (and inherit the
missing flag); clicking the first button whose text matches /send/i selects the
hamburger menu, not `#send-btn`.

Because the deployed :8765 has `auth.enabled=true`, the scratch instance for
this run ran the shipped default config on :8791
(`CHIMERA_CONFIG=/tmp/... CHIMERA_PORT=8791 chimera serve`, keys resolving via
`~/.hermes/.env` substitution — never copied, never printed).

## What works (verified in-browser, not curl)

- First paint: title, form picker (auto/simple/debate/audit), prompt box,
  DAG panel with vendored mermaid loaded, stats bar, hamburger.
- Session lifecycle: POST /web/sessions on load, id in
  `localStorage.chimera_session_id`, survives reload (reused across chrome
  relaunches), "+ New" creates a fresh session.
- Live SSE: mid-run the status line showed "Running aggregator… —
  deepseek/deepseek-v4-flash" while the run was still executing, and the
  stats bar ticked up (322 tok → 21,749) BEFORE the answer landed. This
  updates run 10's "the DAG is NOT live (DF-CHIMERA-V2-18)": at HEAD
  e231b14 the event stream DOES carry mid-run stage status. The mermaid DAG
  itself still renders after completion.
- Turn 1 (auto, cold): answer "Paris", 21,749 tok, $0.003984, 10.5s engine.
- Multi-turn context: turn 2 "What capital city did I just ask about?" →
  "Paris" with no restatement. Session-context injection works from the UI.
- Formation switch + debate in-UI: 26,268 tok, $0.008731, 25.0s engine /
  33s wall, 5-stage DAG rendered.
- Server restart with a saved session: old session 404s, the SPA
  auto-creates a new one instead of hanging — good recovery for an
  in-memory session store.

## What broke (rows filed; details on the board)

| Row | Finding | Severity |
|---|---|---|
| DF-CHIMERA-V2-41 | `auth.enabled=true` locks the BROWSER out entirely: the SPA shell route sits behind `require_api_key`, so GET /web/ renders the 401 JSON as the page, and the SPA has no key-entry surface at all | P1 |
| DF-CHIMERA-V2-42 | Failed workers render as green success nodes in the DAG (same palette, fake latency, no marker); `trace_viz.py` never reads `trace.worker_failures` | P1 |
| DF-CHIMERA-V2-44 | A fully degraded turn (all workers failed) stores answer literally "None", returns 200, takes full token credit, renders as a normal turn | P1 |
| DF-CHIMERA-V2-43 | One completed turn renders its answer bubble twice with divergent stage counts ("1 stages" vs "5 stages") — SSE path and POST path both call `addMessageBubble` | P2 |

The auth lockout is deployment-relevant TODAY: :8765 flipped auth on 09-22
(the INT-API-001 fix), which silently disabled the README's flagship web UI
for every browser user. The engine underneath is fine — this is a
surface-glue defect cluster, exactly the kind green tests never catch.

## Performance (Step 2b; no profiling warranted)

| Operation | Cold | Warm | Notes |
|---|---|---|---|
| Auto turn, UI (engine time) | 10.5s | 6.0s | dispatch span alone: 8,137ms cold / 3,951ms warm, 18-21k input tokens each turn |
| Auto turn, UI (wall) | ~13s | 8.0s | |
| Debate turn, UI | 25.0s engine / 33s wall | — | 5 stages |
| Fresh `pip install -e .[full]` (bunker, Python 3.13) | 73s | — | |
| CLI first answer after install (bunker) | 14s | — | `chimera --formation simple run ...` |

Nothing a user would call slow for what it does (a multi-LLM deliberation);
the dispatch span is the structural cost (one big design call per turn) and
is inherent to the architecture, not a defect. No PERF rows: no number here
is a problem worth a maintainer's hour.

## Install leg (ephemeral bunker, las-bunker-03, agent d50a7727, destroyed)

Fresh Debian user, Python 3.13.5, no toolchains: `git clone` (public GitHub,
depth 50) → `python3 -m venv` → `pip install -e '.[full]'` = 73s, rc=0 →
`chimera config init` (packaged template) → `chimera --version` = 0.2.7 →
CLI quickstart answered "pong" in 14s (key via env; note `--formation` goes
BEFORE the `run` word — root-level flag; `chimera run --formation` exits 2
"no such option", a flag-order trap, docs show the correct form) → `chimera
serve` booted, /web/ 200, session + chat answered "pong" with a full
dispatch→workers→aggregator trace. Developer-path installability: PROVEN.

## Evidence

- Scratch run: /tmp/dogfood-chimera/ (ephemeral; drivers `drive_webui*.py`,
  server log, phase transcripts). No credentials in any artifact — the
  bunker key was piped via stdin/env only.
- Board rows: DF-CHIMERA-V2-41..44 (appended, validate OK, 207 rows).
- Live :8765 untouched; scratch server on :8791 killed; bunker agent destroyed.
