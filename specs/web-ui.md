# Chimera Web Interface — Specification

> **Status: SHIPPED** — implemented, not a build brief.
> Frontend: `src/chimera/web/static/index.html` (single file, no build step)
> Backend: `src/chimera/web/routes.py`, `session.py`, `sse.py`, `trace_viz.py`
> Coverage: `tests/test_web.py`, `tests/test_web_auth.py`; route table mirrored in `docs/INTEGRATION.md`
> Last reconciled against the code: 2026-10-19 (DOC-23)

This document began as a delegated build brief for a frontend polish pass. The
work is complete, so the sections below record the **implemented** surface and
the evidence behind each claim. The original brief is kept as design intent at
the end; where the shipped code departs from it, the departure is named in
[Deviations from the brief](#deviations-from-the-brief) instead of being
silently rewritten.

## Current State

The web UI is complete and verified end to end: `POST /web/sessions` creates a
session, `POST /web/sessions/{id}/chat` runs a deliberation inside it,
`GET /web/sessions/{id}` replays its history, `GET /web/sse/{id}` streams
progress while the turn runs, `GET /web/` serves the SPA, and
`DELETE /web/sessions/{id}` discards a session and its history.

### Route list (implemented)

Prefix `/web`, defined in `src/chimera/web/routes.py`. Two routers share the
prefix: `router` (data surface, mounted in `create_app` with
`Depends(require_api_key)`) and `ui_router` (browser carve-out, mounted **after**
the gated router, no router-level dependency).

Data surface — API key required when `auth.enabled: true`
(`Authorization: Bearer <key>` or `X-API-Key: <key>`):

| Method | Path | Response | Notes |
|---|---|---|---|
| `POST` | `/web/sessions` | `{"session_id": "..."}` | Creates a session. |
| `POST` | `/web/sessions/{id}/chat` | `{"answer", "trace", "turn_number", "mermaid"}` | Body: `prompt` (required), `formation` (default `auto`), optional `allowed_models`, `dispatcher_model`, `aggregator_model`. Past turns are injected as history; runs through the same rate limiter and request queue as `/v1/deliberate`. |
| `GET` | `/web/sessions/{id}` | `{"session_id", "turn_count", "turns": [...]}` | `404` on an unknown id. Each turn carries prompt, answer, formation, dispatch/worker/aggregator models, tokens, cost, timestamp. |
| `DELETE` | `/web/sessions/{id}` | `204`, empty body | Deletes the session and its history (`DF-CHIMERA-V2-69`). Unknown id → `404`. |
| `POST` | `/web/debug/reset` | `{"status": "ok", "message": "singletons reset"}` | Test-only: rebinds the session manager and SSE broadcaster. `404` unless the server was started with `CHIMERA_WEB_DEBUG_RESET=1`. |

Browser carve-out — public (the SSE route also accepts the key as a query
parameter, because an `EventSource` cannot set request headers):

| Method | Path | Response | Notes |
|---|---|---|---|
| `GET` | `/web/` | HTML SPA shell | Served `no-store`. Public even with auth enabled — this is where the key prompt lives (`DF-CHIMERA-V2-41`). |
| `GET` | `/web/sse/{session_id}` | `text/event-stream` | Replay-then-close for a finished/idle session; `?live=1` skips the replay and holds the stream for the next turn. Key accepted as `?api_key=`. Unknown session → `200` stream carrying an `error` frame, never a JSON `404`. |
| `GET` | `/web/{asset_path:path}` | `FileResponse` | Static assets, `.js`/`.css` only, confined to `static/` (`..` traversal → `404`). This is what serves `/web/vendor/mermaid.min.js`. |

Route invariants:

- `GET /web/sessions` (collection listing) does **not** exist: the request
  falls through to the SPA-asset catch-all and answers `404 Not Found`, while a
  method with no handler on that path (e.g. `PUT /web/sessions`) answers `405`.
  The read is per-session: `GET /web/sessions/{id}`. The `405` sentence in
  `docs/INTEGRATION.md` is stale — measured `404` in DOC-23 against the
  TestClient app.
- SSE only; there is no WebSocket endpoint.
- The whole `/web/*` surface exists only when the `web` extra is installed
  (`pip install chimera-deliberation[web]`).
- `DELETE` is server-side only: the shipped SPA has no delete control (see
  Deviations).

### SSE event contract (implemented)

| Event | Data fields | When |
|---|---|---|
| `deliberation_started` | `prompt` | Turn accepted, before dispatch. |
| `stage_started` | `stage`, `kind`, `model` | A stage begins. |
| `stage_completed` | `stage`, `kind`, `model`, `tokens`, `latency_ms`, `cost`, `degraded`, `iteration` | A stage ends. |
| `dag_designed` | `mermaid`, `formation`, `source`, `stage_count` | After the dispatcher designs the DAG. |
| `deliberation_done` | `answer`, `total_tokens`, `total_cost`, `elapsed_ms`, `turn_number` — plus the failure envelope and an empty `answer` when the turn failed | Turn finished. |
| `replay_done` | `{}` (terminal marker, `retry: 60000`) | Every deliberate close of the stream. |
| `error` | `reason`, `session_id` | Terminal stream for an unknown session id (`reason: unknown_session`). |

`replay_done` is a marker, not a dropped connection: a client must not redial on
it. A session's last-turn events are stored server-side and replayed to a late
subscriber, so a page reload reconstructs the last DAG and answer.

### Shipped frontend

`src/chimera/web/static/index.html` — one file, no npm, no build step, no
framework.

- **Theme/layout.** GitHub-dark palette (`--bg: #0d1117`, `--accent: #58a6ff`)
  with gradients, card shadows and transitions. 320px sidebar
  (header / session / history / controls / input) beside the main panel
  (live DAG, token bar, status bar, chat area).
- **Mobile.** `@media (max-width: 767px)` hides the sidebar behind a hamburger
  with an overlay; closes on tap or `Escape`. The DAG panel is scrollable.
- **Live DAG.** Mermaid rendered from `dag_designed`; node state classes are
  driven by `stage_started` / `stage_completed` with a fade-in; fit / zoom-in /
  zoom-out / collapse controls; clicking a node opens its stage detail (model,
  prompt, response, tokens, latency).
- **Multi-turn chat.** Message bubbles (user right, assistant left), each turn
  carrying its own collapsed DAG, answer and token stats; auto-scroll to the
  newest turn.
- **Dashboard.** Token bar with tokens, cost, elapsed time and stage count, plus
  cumulative session totals.
- **Session controls.** Formation selector (`auto` / `simple` / `debate` /
  `audit`), optional aggregator-model override, `+ New` session. The session id
  is kept in `localStorage`, so a refresh resumes the session and refetches its
  history from `GET /web/sessions/{id}`.
- **Auth.** The API-key dialog is driven by the server's `401`; the key is held
  in `sessionStorage` only (never a cookie, never `localStorage`) and appended
  as `?api_key=` on the `EventSource` dial.
- **Keyboard/accessibility.** `Enter` sends, `Shift+Enter` inserts a newline,
  `Escape` closes the sidebar / stage modal / key dialog; labeled controls,
  `role="dialog"`, `aria-modal`, and visible focus rings.

### Deviations from the brief

- **Mermaid is vendored, not CDN-loaded.** `index.html` loads
  `vendor/mermaid.min.js` through `GET /web/{asset_path}`. A CDN script would
  break the zero-config/offline promise, and it needed an asset route
  (`DF-CHIMERA-V2-21`); if the bundle fails to load, the DAG panel shows a
  visible "renderer unavailable" banner and the rest of the UI keeps working.
- **Auth prompt added** (not in the original brief). With `auth.enabled: true`
  the SPA shell is public and every data call is key-gated, so the shell ships
  the only place a browser can enter the key (`DF-CHIMERA-V2-41`).
- **Model overrides are partial.** The API accepts `allowed_models`,
  `dispatcher_model` and `aggregator_model`; the UI exposes only the
  aggregator override input. Dispatcher / allowed-model inputs remain unbuilt.
- **No delete control in the UI.** `DELETE /web/sessions/{id}` is implemented
  and tested server-side, but the SPA retires a session by starting a new one
  (`+ New`) rather than deleting it.
- **Failed turns render in place.** A turn whose stages all failed returns an
  empty `answer` plus a failure envelope (`worker_failures`, `tokens_billed`,
  …) instead of an error page; `deliberation_done` carries the same envelope so
  one renderer path covers success and failure.

### Success criteria — status

1. [x] Single HTML file at `src/chimera/web/static/index.html` — one tracked
   file, no build step.
2. [x] Dark theme with polished visual design — GitHub-dark tokens, gradients,
   shadows, transitions.
3. [x] Mobile-responsive — sidebar behind a hamburger below 768px.
4. [x] Live DAG rendering via SSE — `dag_designed` → Mermaid, `stage_*` → node
   state classes, fade-in.
5. [x] Chat-style multi-turn interface — bubbles plus history replay.
6. [x] Token/cost dashboard with real-time updates — `#token-bar`.
7. [x] Clickable DAG nodes showing stage details — stage modal.
8. [x] Session persistence across refresh — session id in `localStorage`,
   history refetched.
9. [x] Keyboard-accessible — `Enter` / `Shift+Enter` / `Escape`, labeled
   controls, focus states.
10. [~] No console errors, no layout breakage at 375/768/1280/1920px — asserted
    during the build's DevTools pass, not re-run during this reconciliation.
    Re-verify with the checklist below before claiming it again; the
    vendored-mermaid fallback banner is the only expected failure mode.

## Verification

Server-side suite (routes, SSE framing, session manager, SPA route, key gating):

```bash
.venv/bin/python -m pytest tests/test_web.py tests/test_web_auth.py -q
```

Live probe of the delete route (add `-H "Authorization: Bearer $CHIMERA_API_KEY"`
when auth is enabled):

```bash
base=http://localhost:8765
sid=$(curl -s -X POST "$base/web/sessions" | python3 -c 'import json,sys; print(json.load(sys.stdin)["session_id"])')
curl -s -o /dev/null -w '%{http_code}\n' -X DELETE "$base/web/sessions/$sid"   # 204
curl -s -o /dev/null -w '%{http_code}\n' -X DELETE "$base/web/sessions/$sid"   # 404
```

Browser QA checklist (manual, still the gate for criterion 10):

1. Start the server (`chimera serve`) and open `/web/`.
2. Send a prompt and confirm, in DevTools → Network, that the EventSource
   carries `deliberation_started` → `dag_designed` → `stage_started` /
   `stage_completed` → `deliberation_done` → `replay_done`.
3. Confirm the Mermaid DAG renders, nodes are clickable, and the token bar
   updates.
4. Reload mid-session: the history and last DAG come back and no new turn is
   created.
5. Check layout at 375px, 768px, 1280px and 1920px, and tab through the
   controls (`Enter`, `Shift+Enter`, `Escape`).

Live evidence for the SSE contract and the SPA route on a real deployment is
recorded in `docs/dogfood/2026-10-12-run22-integration.md` (unknown-session
terminal stream, empty-session hold, live turn, replay, `/web/` 200).

## Reference: implementation files

- Routes: `src/chimera/web/routes.py`
- Session manager: `src/chimera/web/session.py`
- SSE broadcaster: `src/chimera/web/sse.py`
- Mermaid generator: `src/chimera/web/trace_viz.py`
- Frontend: `src/chimera/web/static/index.html` (vendored renderer under
  `static/vendor/`)
- Cross-document route table: `docs/INTEGRATION.md`; auth posture:
  `docs/SECURITY.md`

## Appendix: original build brief (historical design intent)

Kept for provenance. Every requirement below is implemented except where
[Deviations from the brief](#deviations-from-the-brief) says otherwise.

### Visual Design
- **Dark theme** (current: `#0d1117` bg, `#161b22` surface, GitHub-dark palette).
  Feel free to refine colors but keep dark.
- **Professional, polished UI** — spacing, typography, visual hierarchy.
  Current is functional but sparse. Add subtle gradients, better card shadows,
  smooth transitions.
- **Mobile-responsive** — the sidebar should collapse/hide on narrow viewports
  (< 768px), with a hamburger toggle. DAG panel should be scrollable on mobile.
- **Animations** — nodes in the Mermaid DAG should appear with a subtle fade-in
  transition as stages complete. The token bar should animate value changes.

### Layout (Desktop)
```
┌──────────────┬─────────────────────────────────────────┐
│  Sidebar     │  Main Panel                              │
│  320px       │                                          │
│              │  ┌─────────────────────────────────────┐ │
│  • Header    │  │  DAG Visualization (Mermaid)         │ │
│  • Session   │  │  - Color-coded nodes by stage kind   │ │
│  • History   │  │  - Real-time updates via SSE         │ │
│  • Controls  │  │  - Zoom/pan support                  │ │
│  • Input     │  └─────────────────────────────────────┘ │
│              │                                          │
│              │  ┌─────────────────────────────────────┐ │
│              │  │  Token Bar                           │ │
│              │  │  Tokens | Cost | Time | Stages       │ │
│              │  └─────────────────────────────────────┘ │
│              │                                          │
│              │  ┌─────────────────────────────────────┐ │
│              │  │  Result Panel                        │ │
│              │  │  Final answer + per-stage outputs    │ │
│              │  └─────────────────────────────────────┘ │
└──────────────┴─────────────────────────────────────────┘
```

### Features Required

1. **Live DAG Updates via SSE**
   - Connect to `/web/sse/{session_id}` on session create
   - On `dag_designed` event: render Mermaid diagram with fade-in
   - On `deliberation_done` event: update token bar, show answer
   - Show spinner/loading state during deliberation

2. **Multi-Turn Chat**
   - Chat-style message bubbles (user on right, assistant on left)
   - Each turn shows: prompt, DAG diagram (collapsed), answer, token stats
   - Input box with Enter-to-send, Shift+Enter for newline
   - Auto-scroll to latest message

3. **Token/Cost Dashboard**
   - Real-time bar: tokens, cost, elapsed time, stage count
   - Per-stage breakdown (click a DAG node to see its stats)
   - Cumulative session totals

4. **DAG Interaction**
   - Click any DAG node to see: model, prompt, response, tokens, latency
   - Nodes color-coded: dispatch=purple, worker=green, aggregator=yellow, judge=coral
   - Zoom controls (fit, in, out) for large DAGs

5. **Session Controls**
   - Formation selector (auto, simple, debate, audit) with descriptions
   - Optional model override inputs
   - New session button
   - Session history persists on refresh (fetch from `/web/sessions/{id}`)

### Technical Constraints

- **Single HTML file** — no npm, no build step, no framework.
  All JS inline. Mermaid is vendored (was: loaded from CDN) — see Deviations.
- **No new Python dependencies** — the backend stays as-is.
- **SSE, not WebSocket** — uses the existing `/web/sse/` endpoint.
- **Zero-config** — works immediately after `pip install chimera-deliberation[web]`
  and `chimera serve`.
