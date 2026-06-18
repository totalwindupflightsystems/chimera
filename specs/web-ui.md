# Chimera Web Interface — Specification

> Delegated build target for MiniMax M3 via Hermes CLI.
> Source: `src/chimera/web/static/index.html`
> Backend already built and verified. This spec covers frontend polish ONLY.

## Current State

The web UI backend is complete and verified:

- `POST /web/sessions` — create session
- `POST /web/sessions/{id}/chat` — deliberate with context pipe (returns mermaid DAG)
- `GET /web/sessions/{id}` — session history
- `GET /web/sse/{session_id}` — SSE stream (dag_designed, deliberation_done events)
- `GET /web/` — serves `static/index.html`

The existing frontend works but needs visual polish.

## Target Deliverable

A single `src/chimera/web/static/index.html` file that is:

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
  All JS inline. Mermaid loaded from CDN.
- **No new Python dependencies** — the backend stays as-is.
- **SSE, not WebSocket** — uses the existing `/web/sse/` endpoint.
- **Zero-config** — works immediately after `pip install chimera-deliberation[web]`
  and `chimera serve`.

### Chrome DevTools + Vision QA

After building:
1. Start the server: `chimera serve`
2. Open Chrome DevTools to the web UI
3. Run a deliberation and verify:
   - SSE events arrive (check Network tab → EventSource)
   - Mermaid renders without errors (Console tab)
   - Layout doesn't break at 375px, 768px, 1280px, 1920px widths
   - All interactive elements are keyboard-accessible
4. Take screenshots at each breakpoint for visual review

### Success Criteria

1. [ ] Single HTML file at `src/chimera/web/static/index.html`
2. [ ] Dark theme with polished visual design
3. [ ] Mobile-responsive (hamburger menu at <768px)
4. [ ] Live DAG rendering via SSE with fade transitions
5. [ ] Chat-style multi-turn interface
6. [ ] Token/cost dashboard with real-time updates
7. [ ] Clickable DAG nodes showing stage details
8. [ ] Session persistence across refresh
9. [ ] Keyboard-accessible (Tab, Enter, Escape)
10. [ ] No console errors, no layout breakage at any breakpoint

## Reference: Existing Backend Endpoints

```
POST /web/sessions                    → {"session_id": "..."}
POST /web/sessions/{id}/chat          → {"answer": "...", "trace": {...}, "mermaid": "...", "turn_number": N}
GET  /web/sessions/{id}               → {"session_id": "...", "turn_count": N, "turns": [...]}
GET  /web/sse/{session_id}            → SSE stream
```

SSE events:
```
event: deliberation_started   data: {"prompt": "..."}
event: dag_designed           data: {"mermaid": "...", "formation": "...", "stage_count": N}
event: deliberation_done      data: {"answer": "...", "total_tokens": N, "total_cost": 0.X, "elapsed_ms": N}
```

## Reference: Existing Files

- Backend routes: `src/chimera/web/routes.py`
- Session manager: `src/chimera/web/session.py`
- SSE broadcaster: `src/chimera/web/sse.py`
- Mermaid generator: `src/chimera/web/trace_viz.py`
- Current frontend: `src/chimera/web/static/index.html` (functional but basic)
