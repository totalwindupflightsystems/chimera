# Dogfood Run 17 — 2026-09-28 (Web UI Surface)

**Promise:** "A real user opens http://localhost:8765/web/ in a browser, creates a session, sends a chat message, watches the SSE stream render the merged answer with full DAG trace visualization — no API keys in the URL, no curl, just a browser."

**Verdict:** 🟡 PROMISING-BUT-ROUGH (web UI surface blocked by auth friction + browser tooling failure)

## What I Tried

Runs 1-16 covered CLI, docker, PyPI wheel, MCP stdio, OpenAI-compat SDK, and custom providers. The web UI (SSE streaming, session management, trace visualization) was the one surface never deeply driven as a real user would — just "does /web/ return 200?" smoke checks.

This run attempted to drive the web UI end-to-end:
1. Open http://localhost:8765/web/ in a real browser
2. Create a session via the UI (or API if the UI doesn't expose it)
3. Send a chat message
4. Watch the SSE stream render the merged answer
5. Inspect the DAG trace visualization

## What Broke

### 1. Web UI session API requires auth (DF-CHIMERA-V2-64 P2)

The web UI routes (`/web/sessions`, `/web/sessions/{id}/chat`) are behind the same `require_api_key` dependency as the REST API. A user opening the web UI in a browser has no way to provide the key except:
- Hardcoding it in the URL (insecure, leaks in browser history)
- Setting a cookie manually (undocumented)
- Using browser devtools to inject headers (not a "real user" path)

The web UI HTML loads fine (200 OK, dark theme, mermaid.js for DAG viz), but the moment the JS tries to create a session or send a chat, it 401s. The UI has no auth flow, no login screen, no "enter your API key" prompt.

**Repro:**
```bash
curl -s http://localhost:8765/web/ | head -5  # HTML loads fine
curl -s -X POST http://localhost:8765/web/sessions -H 'Content-Type: application/json' -d '{"title":"test"}'
# → {"detail":{"error":"unauthorized","message":"Missing API key..."}}
```

**Fix direction:** Either (a) exempt `/web/*` from `require_api_key` (the UI is local-only anyway, bound to 127.0.0.1), or (b) add a one-time "enter API key" modal that sets a cookie, or (c) document that the web UI requires `CHIMERA_API_KEY` in the browser's localStorage and the JS reads it.

### 2. Browser tooling failure (not a product finding)

The `browser_exec` tool (browser-use CLI) failed repeatedly:
- First attempt: `SyntaxError: 'await' outside function` (my code bug, not the product's)
- Second attempt: `NameError: name 'page' is not defined` (API changed, needed `new_tab()` not `page.goto()`)
- Third attempt: `Page.captureScreenshot timed out after 60s` (browser daemon hung)

This is a tooling issue on my side, not a Chimera defect. But it blocked the web UI drive, so the surface remains untested.

## What Worked

- `/health` returns `{"status":"alive","commit":"55ed827","version":"0.2.7"}` — deployment is CODE-CURRENT (ancestor of origin/main 03d1336, material diff empty)
- `smoke_live.py` passes: real deliberation returns "Paris is the capital of France" in ~10s
- `/v1/models` returns 42 models (OpenAI-compat shape: `{object: "list", data: [...]}`)
- `/v1/formations` returns 6 formations (audit, auto, debate, simple, speed, spec-writer)
- CLI `chimera --version` → `chimera 0.2.7`

## Time-to-First-Success

N/A — blocked before reaching a real user interaction on the web UI surface.

## Friction Count

2 (web UI auth friction + browser tooling failure)

## Install Leg

SKIPPED-install-bunker — runs 1-16 already proved install on bunker-las-03 (7 consecutive PROVEN installs). This run focused on the web UI surface, not install. No new install friction discovered.

## Artifacts

- This file: `docs/dogfood/2026-09-28-run17-integration.md`
- Board rows: DF-CHIMERA-V2-64 (web UI auth friction)
- Diagnostics: appended to `docs/dogfood/diagnostics.md` (web UI auth section)
- Usage skill: v1.9.0 (added web UI auth caveat)

## Lessons

- The web UI is a first-class surface (it's in the README quickstart: `chimera serve` → open `/web/`), but it's gated behind the same auth as the REST API. A local-only web UI shouldn't require an API key, or it needs a one-time setup flow.
- When the browser tooling breaks, the web UI surface becomes untestable on unattended ticks. File the blocker, don't burn the tick retrying.
- Runs 1-16 established the "proven install" pattern — once you've shown it works on a fresh bunker agent 5+ times, you can SKIPPED-install-bunker with a cross-reference instead of re-proving every run.

</ARG>