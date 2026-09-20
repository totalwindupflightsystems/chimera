# Dogfood run 10 — the web UI (`/web/`), 2026-09-20

**Verdict: 🟡 PROMISING-BUT-ROUGH** — the Chimera engine, the CLI, the REST
surface and the fresh install all deliver; the **web UI's headline feature is
not wired**. This run deliberately took the one surface no prior run had driven
(runs 1–9 exercised the CLI, REST, MCP, the Python SDK, the published wheels
and the bunker install). The web UI is the surface the README leads a new user
to, and it is the only one where the promise and the behaviour disagree.

## The promise under test

README.md:103 and :326, and docs/INTEGRATION.md:109, all say the same thing:

> Open <http://localhost:8765/web/> for the web UI with **live DAG
> visualization**.

and the SPA's own empty state says:

> Ask a complex question and **watch as multiple AI models collaborate, debate,
> and synthesize an answer — with live DAG visualization**.

Null hypothesis: *a user opens `/web/`, types a prompt, and watches the DAG
grow node by node as the workers run.*

## What actually happened

Everything below was run against the live systemd service on `:8765`
(HEAD `4b89a9c`, `/health` commit matching `git rev-parse --short HEAD`) and
reproduced on a **fresh install** on an ephemeral bunker box.

### 1. The DAG is not live — it is post-hoc (P1, filed `DF-CHIMERA-V2-18`)

Timestamps of the SSE stream on one session, with the chat POST in the same
timeline (curl, not browser):

```
CHAT_START 216.74
deliberation_started            216.75   <- immediately
                                  ...    <- 53.1 s of nothing
dag_designed                    269.84
deliberation_done               269.86
CHAT_END                        269.85   <- the POST returns HERE
```

Both surviving events land at the instant the request completes. In the browser,
sampling the DOM every 500 ms for a whole 85 s run: the DAG panel stays on
`Send a prompt to begin`, `#dag-live-indicator` stays `display:none`, and
TOKENS / COST / TIME / STAGES stay `—` for the entire run. The answer then pops
in fully formed.

Root cause (read, then confirmed): `src/chimera/web/routes.py` calls
`_sse_broadcaster.broadcast()` exactly **3** times — `deliberation_started`
before `await engine.deliberate(...)`, and `dag_designed` +
`deliberation_done` after it returns. Nothing in the engine or the stage runner
can emit an event while work is in flight. Meanwhile `src/chimera/web/sse.py`'s
docstring documents `stage_started` and `stage_completed` events, and the
frontend already has listeners registered for both — they are simply never
emitted. The suite is green because `tests/test_web.py` exercises the
`stage_completed` *format string* via a synthetic event; no test asserts that a
real deliberation emits a mid-run event.

**What still works well** (this is why the verdict is "rough", not "does not
deliver"): once the run ends the DAG renders correctly — 8 nodes with per-node
model, tokens and latency; the **click-a-node detail modal works beautifully**
(kind badge, model, latency, input/output tokens, and the stage's actual output
text); the token/cost/time/stages tiles populate; the chat bubbles are readable.
The dashboard is built — only the event source is missing.

### 2. Permanent "SSE reconnecting…" on any session with turns (P2, filed `DF-CHIMERA-V2-19`)

Reload the page on a session that has turns: history is restored correctly
(good), but the status line immediately reads `⏳ SSE reconnecting…` and stays
there. Measured in-page: every SSE connection goes `open` → `error` in 1–4 ms.
Server log over 40 minutes: **138** `GET /web/sse/<sid> 200 OK` lines, 84 of
them for a single session — one request every 3.0 s, forever.

Mechanic: `sse_stream()` only replays `session.last_sse_events` when the newest
turn is **younger than 30 s**; otherwise it pushes the `None` sentinel at once.
Measured close times — aged session: `CLOSED_AFTER=0.0014s bytes=0`; fresh
session: `CLOSED_AFTER=30.00s`. The frontend's `onerror` reconnects every 3 s
unless `deliberationComplete` is set, which a replay-only stream never sets.
The stored-event replay that would fix this already exists and is simply not
used for aged sessions.

### 3. `POST /web/debug/reset` is an unauthenticated destructive endpoint (P2, filed `DF-CHIMERA-V2-20`)

The unit binds `0.0.0.0:8765`. On a default deployment:

```
$ curl -X POST localhost:8765/web/debug/reset
{"status":"ok","message":"singletons reset"}
```

That handler rebinds the module-global session manager and SSE broadcaster, so
**every live session is destroyed**. I hit this myself: a session returning real
turns minutes earlier began answering `404 Session '106df1d09f7f' not found`.
docs/SECURITY.md:64–66 lists this path among those that "require the key" and
states that an anonymous request is refused with 401 "never 404" — the observed
behaviour is both anonymous **and** 200, and no doc anywhere describes the
endpoint's blast radius.

### 4. Install leg — PASSED on a fresh machine (bunker)

`las-bunker-03` (`bunker3`, tailnet `100.69.3.13`), ephemeral agent
`488a7c16`, destroyed after the run. The documented path, from zero:

| Step | Result |
|---|---|
| `git clone https://github.com/totalwindupflightsystems/chimera.git` (the documented public origin) | **OK** — fresh user can fetch the code; `4b89a9c`, matching HEAD |
| `python3 -m venv .venv && .venv/bin/pip install ".[full]"` | **OK — 73 s**, wheel `chimera_deliberation-0.2.6` built from source |
| `chimera --version` | `chimera 0.2.6` |
| `chimera config init` | OK — wrote `chimera.yaml` from `chimera.yaml.example` |
| `chimera formations` | OK — 5 formations listed (plus `spec-writer` with a DAG) |
| `chimera serve` + `GET /health` | `{"status":"alive","uptime_models":43,"commit":"4b89a9c"}` |
| `GET /web/` | 200, `text/html`, 43 427 bytes |

Then the skill's rule — *if it promises "works on a fresh machine", test the
headline feature on the fresh machine*: on that same box the aged-session SSE
closed in exactly 30.00 s and the chat endpoint answered a real 200, i.e. the
findings above are properties of the product, not of this host's config.

### 5. Smaller items (filed `DF-CHIMERA-V2-21`, `DF-CHIMERA-V2-22`)

- The DAG renderer is a hard CDN dependency (`cdn.jsdelivr.net/.../mermaid@11`)
  with no vendored copy, no SRI and no fallback — on a host without egress the
  flagship panel is silently blank, which is exactly the deployment
  docs/INTEGRATION.md describes as supported.
- `POST /web/sessions/{id}/chat` runs the same engine as `/v1/deliberate` but
  never calls `_check_rate_limit()` or `queue.acquire()`, so the configured
  `max_concurrent` / `max_queue_depth` backpressure covers only the `/v1`
  surface.

## Time-to-first-success and friction

- **Time-to-first-success: ~2 min** (page load → formation picker understood →
  first answer, 17 s of deliberation). The SPA is legible without docs.
- **Friction count: 5** — (1) the live DAG never updates; (2) the "reconnecting"
  banner on every reload; (3) no indication during a 50–85 s run that anything
  is happening at all (the send button is the only feedback and it is easy to
  miss); (4) the expander labelled `▸ Show DAG visualization` appears on
  *completed* turns while the side panel shows the newest one, so it is not
  obvious which turn is which; (5) the DAG renders twice in the DOM (two 8-node
  SVGs for one run) — harmless visually, but it doubled the click-handler scope.

## What was NOT exercised (stated plainly, not passed silently)

- **Streaming/multi-tab behaviour under concurrent users.** Two clients were
  observed sharing the deployed `:8765` (stale stats in the open tab until the
  next send) but no load or concurrency test was run.
- **The formation picker's `audit` path inside the UI** was driven and returned
  a correct audited answer (41 343 tokens, weakest-claim line present); the
  `debate`/`speed`/`spec-writer` presets were not driven through the UI.
- **Mobile layout** was not exercised.

## Evidence files

Ephemeral, under `/tmp`: `sse-time.txt` / `chat-time.txt` (the timeline proof),
`aged2-meta.txt`, `bunker-install2.log`, `sse-compare.txt`,
`board-before.jsonl` (board state before the finding append). The browser-side
samplers were in-page (`window.__L`, `window.__U`) and are reproduced above.

## Board rows filed

| Row | Pri | What |
|---|---|---|
| `DF-CHIMERA-V2-18` | P1 | The live DAG is not live — no mid-run SSE events exist |
| `DF-CHIMERA-V2-19` | P2 | Permanent reconnect loop on aged sessions |
| `DF-CHIMERA-V2-20` | P2 | Unauthenticated destructive `/web/debug/reset` on `0.0.0.0` |
| `DF-CHIMERA-V2-21` | P3 | CDN-only DAG renderer + stale cross-client stats |
| `DF-CHIMERA-V2-22` | P3 | `/web` chat bypasses the rate limiter and queue backpressure |
