# Run 15 (2026-09-25): the OpenAI-compat drop-in promise, driven by the official SDK

**Angle (first time touched in 15 runs):** README's flagship claim —
*"OpenAI-compatible: Drop it in as a replacement"* — driven by a **real
consumer using the official `openai` SDK (v3.19.2) and nothing else**. A
scratch venv OUTSIDE the repo (`/tmp/dg-openai-sdk`, `openai` the only
install) built a real tool: `panel_review.py` — paste a file, get a
schema-shaped multi-model panel review. Runs 1-14 exercised CLI, REST via
curl, MCP, library, web UI, formations, docker, PyPI wheel — none drove the
compat surface the way a migrated OpenAI user would.

**Live target:** the supervised :8765 service, deployment parity PROVEN
first (`/health` commit `ee8ad95`, ancestor of HEAD `637eb38`, material
diff `src/ scripts/ tests/ pyproject.toml` EMPTY → CODE-CURRENT per the
AGENTS.md classification; a real user with no git would have hit the same
service).

## What worked (the promise holds)

- **The tool is real.** `panel_review.py /home/kara/chimera-v2/scripts/model_sync.py`
  returned a 22-finding structured review (run 2: 14 findings) citing
  functions and snippets. Two of its findings independently match the
  board's own known defect DF-CHIMERA-V2-50 (`core_basenames` is not
  basename-reduced; the reseller path never checks the catalog) — the
  panel found the project's real, acknowledged bug from the file alone.
  The tool does something a real user would pay for.
- **Metadata via SDK:** `client.models.list()` → 42 models, typed objects
  (run 6's bare-dict crash is fixed in the deployed code).
- **Error contracts match the docs exactly, 5/5** (probe_errors.py):
  `stream:true` → 400 `stream_not_supported` naming the param;
  model-id-as-formation → 404 `model_not_found` with the teaching message
  pointing at GET /v1/formations; wrong key → 401; `model:""` → 422;
  `messages:[]` → 422. FastAPI `detail`-shaped 401/422 are documented
  ("error bodies are not uniformly OpenAI-shaped") and behave as written.
- **Multi-turn history works** through the compat endpoint (memory probe:
  "What capital did I just mention?" → "Paris", 10.5s).
- **Documented no-ops never error:** `temperature`, `top_p`, `n=2` (single
  choice back, as promised), `max_completion_tokens` alias accepted.
- **Schema-binding contract verified live with a canary:** on `speed`
  (deepseek aggregator) a `const: "format-bind-proof"` marker did NOT
  survive — the docs' capability table (deepseek = schema REMOVED) is
  accurate.
- **Fresh-box install + headline feature (bunker-las-03, agent 6963ad23,
  destroyed + verified gone):** clone of the PUBLIC repo 8s →
  `pip install "chimera-deliberation[full]"` **71s** (py3.13.5) →
  `chimera config init` 0s (site-packages template) → serve up → drop-in
  call over curl on localhost → **proper OpenAI-shaped answer in 10s** →
  project's own `smoke_live.py` **SMOKE PASS** with merged answer. The
  headline feature works ON the fresh machine, not just the install.

## Defects found (filed as board rows; details in tasks.md)

1. **DF-CHIMERA-V2-53 (P1) — schema stripped with ZERO signal.** The docs
   say deepseek gets `response_format` removed before the call. That is
   exactly what happens — but an OpenAI-shaped client has NO WAY to know:
   `chat.completions.create(..., response_format=json_schema)` returns 200
   with `finish_reason:"stop"` and JSON-shaped content whose `severity`
   enum (P0/P1/P2) came back as `high/medium/low/nit/n/a`. Both structured
   runs of panel_review.py were silently unvalidated. Nothing in the
   response (no warning header, no field, no `system_fingerprint`-style
   hint) marks the downgrade; you learn it only by reading server logs or
   the docs' capability table. Fix direction: surface a response-side
   marker (e.g. a `chimera_format_negotiation` field or warning) or 400
   when `strict:true` cannot be honored.
2. **DF-CHIMERA-V2-54 (P1) — truncation invisible to drop-in clients.**
   `max_tokens:60` IS honored per call (CH-GAP-031 works) — so well that
   every worker truncates, and the merged final answer is the aggregator's
   raw meta-reasoning: `"We need answer user. Need combine worker_1 and
   worker_2..."` (278 chars), `finish_reason:"stop"`. Reproduced 3/3
   (simple cap60; speed cap40 → 208 chars; speed cap25 → 109 chars). The
   OpenAI contract for a truncated completion is `finish_reason:"length"`;
   the response schema hardcodes `"stop"` (`src/chimera/api/server.py:314`)
   even though the gateway tracks `length` internally
   (docs/FAILURE_RESILIENCE.md §1, `token_limit_reached` logging). Every
   drop-in client's auto-pagination/retry logic silently misfires.
3. **DF-CHIMERA-V2-55 (P2) — small-cap bounds produce garbage, not
   gracefully-degraded output.** With worker caps of 25-60 tokens the
   workers cannot even finish their design protocol, so the "answer" is
   the reasoning fragment above — worse than useless because it LOOKS
   plausible in shape. A floor on worker `max_tokens`, or an answer-quality
   marker when caps force degraded merges, would make small caps safe.
4. **DF-CHIMERA-V2-56 (P2) — fresh-install auth bootstrap has a silent
   default.** With `auth.mode: env` and no `CHIMERA_API_KEY` exported,
   `chimera serve` starts "alive" and rejects every request with
   `Invalid API key.` — the server I launched without the key did exactly
   this. `docs/INTEGRATION.md` documents the export, but the serve path
   never says "auth is on and the key env is empty"; the smoke script
   printed its `expected on a fresh install` note only because my driver
   bug hid the server from it. A one-line startup warning would close the
   #1 fresh-user dead end. (My driver's bug, not the server's — but the
   trap is real: I hit it as the documented path's first mistake.)

## Integration friction a real user feels

- The 422 my first `/v1/deliberate` call got was MY bug (guessed a
  `messages` body; the field is `prompt`) — but note the two request
  models differ: chat/completions takes OpenAI `messages`,
  /v1/deliberate takes `prompt`. Documented; just easy to cross.
- Formation discovery for an SDK client = /v1/formations (open endpoint)
  or the teaching 404. Fine once known.
- Server-side thinking text leaking into answers (finding 3) is the only
  content-level wart.

## Timing (the perf answer)

- Headline op (full-file panel review, 1218-line input, auto formation):
  **cold 292.4s, warm 266.3s** wall — with client user+sys < 1.1s, so
  ≥99% model-bound. Trace on a small speed run: dispatch 7.0s (18.7k
  catalog tokens), workers 4.3s/2.7s parallel, aggregator 1.3s; $0.0059.
- Spread 266-292s on identical input ≈ provider-side variance; a caller
  needs a generous client timeout (SDK default 600s survives; tighter
  wrappers will die).
- Verdict: SLOW BUT INHERENT. The cost is the deliberation itself
  (dispatcher must carry the whole model catalog). No user-actionable
  hotspot → no PERF row; the number belongs in the docs, not a fix list.

## Consumer artifacts (scratch, outside the repo)

- `/tmp/dg-consumer/panel_review.py` — the tool (venv + `openai==3.19.2` only)
- `probe_errors.py` (5/5 doc-contract checks), `probe_schema.py` (canary),
  `probe_max_tokens.py` + `probe_trunc_repro.py` (truncation contract),
  `probe_meta.py`, `probe_trace.py`
- Ephemeral-box drivers: `bunker_smoke2.sh`, `agent_launch.sh`,
  `agent_dropin.sh`, `stream_env.sh`
