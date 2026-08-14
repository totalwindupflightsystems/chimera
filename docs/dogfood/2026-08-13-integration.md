# Chimera Dogfood Integration Report — 2026-08-13

**Verdict: 🟡 PROMISING-BUT-ROUGH (second run).** Promise vs reality: the core
promise ("One API call. A team of models. One answer.") **holds and the
engine-level fixes from the 2026-08-03 run are real** — but the two most
documented entry paths (Python bare install, REST on :8765) are still broken
for a fresh user, for deployment/packaging reasons rather than engine reasons.

Run by: coding-hermes-dogfood cron (real use, not test suite). All commands
below were executed for real on 2026-08-13 against current `main`
(f1dc0f0+dirty), Python 3.11 venv at `/home/kara/chimera-v2/.venv`,
`OPENROUTER_API_KEY` from repo `.env`.

## What works (verified by real use today)

| Path | Command | Result |
|---|---|---|
| CLI | `chimera run "What is the capital of France?"` | ✅ "Paris", 37s first call (provider catalog refresh), ~20s warm |
| REST OpenAI-compat | `POST :8790/v1/chat/completions` `{"model":"auto",...}` | ✅ "Tokyo", 21s, HTTP 200, proper `choices`/`usage` shape |
| REST full | `POST :8790/v1/deliberate` `{"prompt":..., "formation":"auto"}` | ✅ 3-stage auto DAG (worker_perf + 1 more + aggregator), merged answer, full trace, `source=auto`, $0.053, 116s |
| Custom DAG | `POST :8790/v1/chat/completions` `{"model":"custom","allow_custom_dag":true,"dag":{...}}` | ✅ exact README contract works, merged answer |
| Health | `GET /v1/health` | ✅ `healthy`, all 12 configured providers probed with real calls |
| Health alias | `GET /health` | ✅ 200 `{"status":"alive","uptime_models":36}` (CH-GAP-022 fix REAL) |
| Ready | `GET /v1/health/ready` | ✅ 200 (was false-503 on the old server) |
| Web UI | `GET /web/` | ✅ served, title "Chimera — Multi-Model Deliberation" |
| Library | wheel 0.2.0 + `[full]` deps in scratch venv, `Engine(config, LiteLLMGateway(config))` → `await engine.deliberate(...)` | ✅ `{"result": 12}`, `source=auto`, $0.003, 17s |
| MCP standalone | `chimera-mcp` + JSON-RPC initialize handshake | ✅ serverInfo + tools capability |
| Errors | `POST /v1/deliberate` with unknown stage model | ✅ clean HTTP 400 JSON error |
| Tests | `.venv/bin/python -m pytest -q` | ✅ 648 passed / 62 skipped in **17.5s** (the "suite green" claim is TRUE and fast) |
| Docs fixes | grep `chimera deliberate` README.md docs/USAGE.md | ✅ 0 occurrences (CH-GAP-001/003 hold); `dist/` has only 0.2.0 (CH-GAP-002 holds) |

## What broke (each = a board task, CH-GAP-025..029)

### 1. Zombie server squats the documented port :8765 (CH-GAP-025, P1)
`ps` shows a root-owned `chimera serve --host 0.0.0.0 --port 8765` started
**Aug 2** — running pre-fix code. A fresh `chimera serve` dies with
`[Errno 98] address already in use`, and every curl on :8765 hits the old
server: HTTP 200 whose `content` is
`[stage aggregator ... unavailable: ... Missing credentials ...]` — the exact
2026-08-03 P0. The current code is healthy (verified on :8790) but
unreachable at the documented address. **The README quickstart's `chimera
serve` + curl recipe is dead on this machine until the zombie is killed.**
Needs root (`sudo kill 21212`) and ideally supervision (systemd /
docker-compose restart policy) or a startup port-conflict check with a
helpful message.

### 2. Bare wheel install + README Python quickstart crashes (CH-GAP-026, P1)
`pip install chimera-deliberation` (base, no extras) then the README snippet
`from chimera import Engine, ChimeraConfig, load_config` →
`ModuleNotFoundError: No module named 'fastapi'`. Cause: `chimera/__init__.py`
unconditionally imports `chimera.web.trace_viz` → `chimera.web.routes` →
`fastapi`, which lives only in the `[server]`/`[full]` extras. The README
Python section doesn't mention an extra. Reproduced with the published
0.2.0 wheel in a fresh venv (Python 3.13, litellm 1.96.2 resolved fresh).
Workaround: `pip install "chimera-deliberation[full]"`. Fix direction:
lazy-import the web package in `__init__.py` (or add fastapi to base deps /
document the extra) + a bare-install import test.

### 3. chat/completions silently substitutes models (CH-GAP-027, P1)
`{"model":"bogus/nonexistent-model-xyz"}` → **HTTP 200** with a coherent
answer from a real model (usage 17,129+1,806 tokens billed, `model` echoed as
the bogus name). OpenAI-compat "drop-in" contract requires 400/404
`model_not_found`. Silent wrong-model output is a correctness/trust hazard
(user asked for model X, gets model Y's answer, 200 OK). `/v1/deliberate` does
this right (400 on unknown stage model). Fix: validate `model` against the
catalog in the chat/completions path.

### 4. `chimera mcp` subcommand crashes (CH-GAP-028, P2)
`chimera mcp` → traceback ending `FileNotFoundError: [Errno 2] No such file
or directory: 'mcp'`. Root cause: `src/chimera/mcp/server.py run()` re-reads
`sys.argv` when `config_path is None`; the click subcommand
(`cli/main.py:286`) passes `None`, so `run()` consumes `argv[1] == 'mcp'` as a
config path. `chimera-mcp` standalone works (handshake verified). Fix: resolve
the config path in the click wrapper (or have `run()` ignore argv when called
from click) + smoke test.

### 5. Custom-DAG docs ambiguity (CH-GAP-029, P2)
README "Custom DAGs" section shows a JSON body but never says which URL.
`POST /v1/deliberate` (the "Full control (DAG, overrides, trace)" endpoint —
its schema has `dag` + `allow_custom_dag`) rejects it with a bare 422
`Unknown formation: custom`. The working contract is `/v1/chat/completions`
with `model: "custom"`. Fix: state the URL in the README section and/or make
`/v1/deliberate` accept it, and improve the 422 detail.

## Friction log (7 items, in order hit)

1. `chimera serve` → port in use, silent redirect of all curls to a corpse (no warning anywhere).
2. Bare wheel import → ModuleNotFoundError (no doc hint).
3. `load_config()` needs `chimera.yaml` in CWD (fine for the documented `cp chimera.yaml.example` flow, but the README Python snippet doesn't say where the config comes from).
4. `result.trace` is a pydantic `DeliberationTrace`, not a dict (my consumer used `.keys()`; use `model_dump()`).
5. `formation:"custom"` on `/v1/deliberate` → unhelpful 422.
6. `chimera mcp` → cryptic traceback instead of "no chimera.yaml" guidance.
7. First call latency ~37s + ~17k prompt tokens on EVERY call (dispatcher carries the model catalog — the known "catalog tax", ~$0.003 floor).

## Time-to-first-success

~5 min from repo read to first CLI answer (37s of that was the call itself).
The prior run's 15 min included MCP setup; CLI is the fastest entry.

## Verdict evidence

- **Does it work?** Yes — every engine path I ran produced a genuine
  multi-model deliberation with honest traces. The previously-broken health
  endpoint, `/health` alias, and error handling are all fixed in current code.
- **Is it useful?** Yes — $0.003–0.05 per deliberation for genuinely merged
  multi-model answers with per-stage traces; the MCP/agent path (via
  `chimera-mcp`) is the flagship.
- **Is it usable?** No for a fresh user on the two most-documented paths:
  bare `pip install` import crashes and `chimera serve` hits a zombie. Once
  past that, friction is low.
- **Is it trustworthy?** Engine traces are honest (`source`, per-stage
  models/cost). The silent model substitution on chat/completions is the one
  trust breaker — must not ship as-is.
