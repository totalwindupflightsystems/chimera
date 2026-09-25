# Chimera Dogfood Log

## 2026-08-03 — 🟡 PROMISING-BUT-ROUGH

**Promise:** "One API call. A team of models. One answer." — a multi-model
deliberation gateway where one dispatcher call designs a DAG of scoped
worker prompts, workers run in parallel, and an aggregator merges them with
dispatcher-written instructions. Entry points: CLI, REST API (OpenAI-compat),
MCP server for agents, web UI.

**Reality:** The core engine is real and works — 4 real deliberations run
across MCP + CLI + REST. The MCP path (what Hermes agents use) is excellent:
auto formation produced a real 2-worker + aggregator DAG with a genuinely
merged answer, and custom DAGs execute exactly as specified. The CLI works
with a nice boxed trace. BUT the REST server on :8765 runs with no provider
credentials — every deliberation fails with "Missing credentials" and the API
returns HTTP 200 with the error text as the "answer". `/v1/health` reports
all providers down while the same models work via CLI/MCP (false negatives).

**Top 3 findings:**
1. P0 `dogfood-http-server-no-creds` — `chimera serve` has no creds; README curl quickstart is dead.
2. P0 `dogfood-error-200-as-success` — failed deliberations return 200 + error-string as assistant content.
3. P1 `dogfood-health-lies` — health/ready claims "no providers reachable" while providers demonstrably work.

**Time-to-first-success:** ~15 min from start (docs reading + first MCP
deliberation; the call itself took 69s wall). **Friction count:** 9.

**Verdict:** PROMISING-BUT-ROUGH. Value is real (multi-model deliberation
with honest traces, ~$0.003–0.02/call), usability is the blocker (dead HTTP
deployment, lying health endpoint, silent override precedence).

**Board:** 8 tasks added (2 P0, 3 P1, 3 P2) via DuckDB board v2.1. Foreman
cooldown dropped 43200s → 900s to work them.

## 2026-08-13 — 🟡 PROMISING-BUT-ROUGH (second run)

**Promise:** "One API call. A team of models. One answer." — multi-model
deliberation gateway; entry points: CLI, REST (OpenAI-compat + full),
library, MCP, web UI.

**Reality:** The core promise holds everywhere I ran it — CLI (Paris, 37s),
REST chat/completions (Tokyo, 21s), REST deliberate (3-stage auto DAG,
merged answer, $0.053, 116s), custom DAG, library from the 0.2.0 wheel
($0.003), `chimera-mcp` handshake. The run-1 P0s are FIXED in code: /v1/health
honest (12/12 providers healthy), /health alias 200, deliberate 400s on
unknown models, suite 648 pass/62 skip in 17.5s. **But the two most
documented fresh-user paths are still dead:** (a) bare `pip install` +
README Python snippet → ModuleNotFoundError: fastapi; (b) `chimera serve` →
"address already in use" because a root-owned pre-fix zombie (PID 21212, Aug
2) squats :8765 and serves the old "Missing credentials as 200 answer"
behavior to every curl.

**Top 3 findings:**
1. P1 CH-GAP-025 — zombie server on :8765 makes the documented REST quickstart dead.
2. P1 CH-GAP-026 — base wheel import crashes without [full] extra; README Python quickstart fails.
3. P1 CH-GAP-027 — chat/completions silently substitutes a real model for unknown model names (200 + wrong-model answer).

**Time-to-first-success:** ~5 min (CLI; 37s of it was the call).
**Friction count:** 7.

**Verdict:** PROMISING-BUT-ROUGH — value real and engine fixes verified, but
deployment (zombie port) and packaging (bare wheel) block the documented
paths. 5 tasks added (3 P1, 2 P2). Cooldown 7200s — below wake threshold;
foreman will pick tasks up on its normal 2h tick.

## 2026-08-23 — 🟡 PROMISING-BUT-ROUGH (third run)

**Promise:** "One API call. A team of models. One answer." — multi-model
deliberation gateway; entry points CLI, REST (OpenAI-compat + full),
library, MCP, web UI.

**Reality:** The engine is in excellent shape at HEAD — CLI deliberation
(correct answer, 17.7s, $0.004), REST chat/completions + deliberate with
proper 404/422 errors, web UI + /docs live, MCP handshake works, and the
LIBRARY path is now genuinely good: a real consumer tool built on
Engine+LiteLLMGateway with a custom 3-stage DAG produced an excellent
merged answer with full trace (4m15s wall — budget minutes for sequential
DAGs). BUT the distribution layer is broken in two independent ways:
(a) the live :8765 systemd service has run Aug-14 code since Aug 14 14:53 —
`stream:true` returns 200 non-stream and `max_tokens:1` returns a 3548-token
essay, i.e. board-closed fixes CH-GAP-030/031 never reached users; (b) PyPI
0.2.0 (Jul 19) still crashes on bare import (`ModuleNotFoundError: fastapi`),
and even a fresh HEAD wheel's bare install ships console scripts that crash
(`No module named 'rich'`). README also ends with a literal `# test comment`.

**Top 3 findings:**
1. P1 CH-GAP-039 — live :8765 runs Aug-14 code; stream/max_tokens fixes never deployed (no restart/deploy step exists; fixes verified only on throwaway servers).
2. P1 CH-GAP-040 — PyPI 0.2.0 (Jul 19) still has the bare-import crash; 186 commits unpushed, every Aug fix unreleased.
3. P1 CH-GAP-041 — bare install ships crashing console scripts (rich/click/mcp extras-only); third packaging/extras mismatch this month.

**Time-to-first-success:** ~2 min (server health + formations probe; first
CLI deliberation 17.7s). **Friction count:** 6.

**Verdict:** PROMISING-BUT-ROUGH — core engine value real and the library
path finally works, but the two ways users actually get Chimera (the
deployed server, the published package) both lag HEAD by weeks. 6 tasks
added (CH-GAP-039..044). Cooldown 21600s → woken to 900s.
2026-09-01 | PROMISING-BUT-ROUGH | 15s t2fs | friction 7 | 5 findings
2026-09-04 | PROMISING-BUT-ROUGH | 6s t2fs | friction 11 | 5 findings
2026-09-04 (run B) | PROMISING-BUT-ROUGH | 18s t2fs (HEAD wheel path) | friction 4 | 6 findings | install: pypi=20s(dead-end)/headwheel=17s(ok) | bunker=SKIPPED (port-pool exhausted) | smoke=ok(live REST battery 5/5)
2026-09-07 | SHIPPABLE | 6s t2fs | friction 10 | 5 findings
2026-09-11 | SHIPPABLE (confirmed) | promise: one call -> team of models -> one answer (CLI/REST/MCP/library) | t2fs: PyPI fresh user ~2.5min (95s install + 14s answer); MCP-agent ~1min | friction 3 (was 10-11) | top: 0.2.3 wheel MCP still polluted (lazy pollution, false-green handshakes) DF-CHIMERA-0911-1; release gate never tests published artifact DF-CHIMERA-0911-2; drop-in model-ID 404 reflex DF-CHIMERA-0911-3 | install: pypi0.2.3=95s ok + head wheel ok | bunker=SKIPPED 7th (NEW: :10001 gRPC + :22 both down, :19090 OK -> firewall/ACL) DF-CHIMERA-0911-4 | smoke=ok (real MCP client deliberation $0.0162 zero failures; REST battery 3/3; HEAD probe 0 pollution) | prior fixes VERIFIED: models table legible, CLI stdout pure, deploy parity restored (e4c7a30), test_mcp 13/13
2026-09-16 | PROMISING-BUT-ROUGH | 15s t2fs | friction 12 | 5 findings

2026-09-16 (run B) | SHIPPABLE | 25s t2fs (SDK 'Paris' 27.4s call; bunker box 11s) | friction 4 | 5 findings (2 verify-closes, 3 new) | install: pypi0.2.5 venv=26s ok | bunker=PROVEN 1st time (las-bunker-03 agent 62a41be8: clone 77a1b9d → pip -e .[full] 68s → real answer 11s; destroyed) | smoke=ok | prior fixes VERIFIED on published wheel: MCP stdout purity (DF-CHIMERA-0911-1), drop-in 404 teaching msg (DF-CHIMERA-0911-3); bunker streak closed (DF-CHIMERA-0911-4) | NEW: official OpenAI SDK models.list() crashes on bare-dict /v1/models (DF-CHIMERA-0916B-2); 0.2.5 wheel lacks README-documented --version (release-lag #4, DF-CHIMERA-0916B-3); live chimera.yaml tracked in public repo breaks fresh-clone config init (DF-CHIMERA-0916B-4) | MCP harness lesson: printf-pipes close stdin → server exits pre-response; keep-stdin-open driver required
2026-09-20 | PROMISING-BUT-ROUGH | 2min t2fs | friction 5 | 5 findings (DF-CHIMERA-V2-18..22) | surface: WEB UI /web/ (first run to drive it; runs 1-9 did CLI/REST/MCP/SDK/install) | promise: "web UI with live DAG visualization" -> the DAG is NOT live: all 3 SSE broadcasts fire only after engine.deliberate() returns (dag_designed+deliberation_done land in the same ms as the chat POST at t=53.1s; panel stuck on placeholder for the whole run) DF-CHIMERA-V2-18 | aged sessions close SSE in 1.4ms/0 bytes -> permanent "SSE reconnecting..." loop, 138 req/40min, replay gate is 30s DF-CHIMERA-V2-19 | POST /web/debug/reset unauthenticated+destructive on 0.0.0.0: wiped every live session, docs/SECURITY.md claims 401-never-404 DF-CHIMERA-V2-20 | install: bunker PROVEN (agent 488a7c16 destroyed; clone 4b89a9c + pip install .[full] 73s -> chimera 0.2.6 + config init + formations + serve /health + /web/ 200; headline feature re-tested on the fresh box) | smoke=ok | confirmed-working: DAG renders 8 nodes post-hoc, node-click detail modal correct, session memory across reload, audit formation answers
2026-09-22 (run 11) | SHIPPABLE | 7min t2fs custom formation (author→first answer); CLI-only ~2min (54s install + 30s answer) | friction 4 | 5 findings (DF-CHIMERA-V2-32..36) | surface: USER-AUTHORED FORMATIONS (first run to write one; runs 1-10 all used shipped presets) | promise: custom multi-stage formations work as docs describe → HELD (author→load→run→override→serve all worked; 2+1 DAG 86.9s cold/31.9s warm; REST 18.4s 0 failures; --stage-models targets custom stage ids correctly) | top: --stage-models silent no-op on unknown stage ids DF-CHIMERA-V2-32; degraded merge = RC=0 plain answer, degradation only as JSON log lines not the documented warning: contract DF-CHIMERA-V2-34; default run wants formation auto that minimal configs lack (CONFIG.md example omits it) DF-CHIMERA-V2-33 | install: bunker PROVEN (agent 4dfc08f3 destroyed; pypi 0.2.7 venv 54s → config init from PACKAGED example ok — DF-CHIMERA-0916B-4 fix VERIFIED on the published artifact → first answer 30s; no sudo/compose/toolchain needed) | smoke=ok | no PERF row: CLI overhead 0.25s mean, all real latency is model-bound; the 120s per-stage timeout is configurable (timeout.per_stage_s, undocumented for users — folded into -34) | PyPI 0.2.7 == repo == live server commit faf78b4: release-lag chain closed for this artifact

## 2026-09-23 — SHIPPABLE (4th consecutive) — run 12, real-browser web UI

**Promise:** "One API call. A team of models. One answer." — this run tested
the README's flagship entry point in an ACTUAL browser (headless Chrome via
CDP), the surface run 10 had only curl-probed.

**Reality:** The engine promise holds (4th consecutive SHIPPABLE): auto
("Paris", 21,749 tok, $0.004, 10.5s cold), multi-turn context ("What capital
did I just ask about?" → "Paris"), debate (26,268 tok, $0.0087, 25s), all
driven through the SPA's own controls. SSE now carries MID-RUN stage status
("Running aggregator…", ticking stats) — run 10's "DAG is NOT live" is
outdated at e231b14. But four new defects: (1) auth.enabled=true renders the
401 JSON as the whole /web/ page and the SPA has no key entry — the browser
UI is dead on the current :8765 deployment; (2) failed workers draw as green
success nodes (trace_viz ignores worker_failures); (3) a fully-degraded turn
stores/renders answer "None" with 200 + full token credit; (4) completed
turns render duplicated bubbles with divergent stage counts.

**Install leg:** PROVEN on bunker-las-03 (agent d50a7727, destroyed) — the
DEVELOPER path this time: fresh clone of the public repo → venv →
`pip install -e '.[full]'` 73s on Python 3.13 → config init → CLI "pong"
14s → `chimera serve` → /web/ 200 → session+chat "pong" with full trace.

**Time-to-first-success:** ~6 min (server up + first answer rendered in the
UI, after the driver wiring). **Friction count:** 4 (findings above) + 2
driver-side traps (CDP origins flag, hamburger/send text match).

**Board:** DF-CHIMERA-V2-41..44 filed via boardctl; dogfood findings section
in tasks.md; transcript docs/dogfood/2026-09-23-integration.md; usage skill
v1.4.0. Perf: no rows (nothing a user would feel as a defect).

2026-09-24 (run 13) | SHIPPABLE | promise: "docker compose up -d with only DEEPSEEK_KEY exported → healthy gateway, web UI + real deliberation, no YAML editing" → HELD on fresh hardware (5th consecutive SHIPPABLE; docker surface was the one runs 1-12 never touched) | t2fs: ~4 min (clone 4s + build 106s + up <1s + first answer 34s) | friction 3 (findings below; zero install friction — no sudo/compose-plugin/toolchain needed) | findings: live :8765 STALE again + smoke exits 0 on STALE (DF-CHIMERA-V2-46 P1); docker docs DEEPSEEK_KEY vs template ${DEEPSEEK_API_KEY} name split (DF-CHIMERA-V2-47); container /health commit:"unknown" no version fallback (DF-CHIMERA-V2-48) | install: bunker PROVEN (agent 5d1b8e8e destroyed; clone PUBLIC mirror 3335322 4s → compose build 106s → DEEPSEEK_KEY-only up healthy → real "Paris" 34s cold/32s/30s warm → restart healthy → container CLI 0.2.7 → destroy OK) | smoke=ok | no PERF row (model-bound 30-34s = prior runs' numbers; nothing user-felt) | artifacts: docs/dogfood/2026-09-24-integration.md, usage skill v1.5.0, diagnostics.md docker leg | fake-key probe lesson: /v1/health flipping missing-credentials→auth-invalid proves the env→engine credential path with no secret
2026-09-25 (run 14) | SHIPPABLE | promise: "pip install chimera-deliberation[full] from PyPI (no repo) → working CLI via config init; an agent speaks MCP to chimera-mcp with a plain JSON-RPC stdio client" → HELD (6th consecutive SHIPPABLE; PyPI wheel and independent-MCP surfaces were the ones runs 1-13 never touched) | t2fs: ~2 min warm box (install 36s + config + first answer 29s); ~7 min from a bare box (install 266s on Python 3.13.5 + answer 18s) | friction 2 (both tooling, not product): bunker-qa.sh launch shipped a 0-byte qa-run.sh (DETECT_UP_PREV_DIR unbound line 846 → collect misreported as pull-failed; DF-CHIMERA-V2-51 P2, hermes-infra driver) and scripts/mcp-liveness-check.sh needs npx so it cannot run on wheel-only machines (DF-CHIMERA-V2-52 P3) | credit: wheel == repo (python -m chimera works, config init finds the site-packages template, force-includes load-bearing), MCP interop real via hand-rolled ~60-line JSON-RPC client (initialize 0.5s, 3 tools, deliberations 12.8s local / 45.5s fresh agent, protocol 2024-11-05), CLI error paths exit 2 correctly | live deploy: CODE-CURRENT (ee8ad95), smoke PASS, zai quota warning class-aware | install: PROVEN by hand on bunker-las-03 agent c26d8af2 (destroyed, verified gone) after the QA driver died — venv → wheel install 266s → config init → 18s real deliberation → full MCP battery → destroy | smoke=ok | no PERF row (warm CLI 11.2s wall == trace 11314ms model-bound; MCP provider-bound; nothing user-felt) | artifacts: docs/dogfood/2026-09-25-integration.md, diagnostics.md wheel+MCP leg, usage skill v1.6.0, board rows DF-CHIMERA-V2-51/52 | tooling lessons: uv venv ships no pip (python3 -m venv), uv defaults to newest CPython (--python 3.11)

2026-09-25 (run 15) | SHIPPABLE | promise: "OpenAI-compatible — drop it in as a replacement" driven by the OFFICIAL openai SDK v3.19.2 (only dependency) from a scratch venv outside the repo, incl. a real tool (panel_review.py: file -> schema-shaped multi-model review) → HELD with 2 P1 contract defects (7th consecutive SHIPPABLE; the SDK-driven compat surface was the one runs 1-14 never touched) | t2fs: ~3 min (venv+SDK install ~30s + first call 292s cold / 266s warm — t2fs is call-bound, not install-bound) | friction 3 (format-strip invisibility, truncation-as-stop, fresh-auth silence; plus 2 driver-side traps of my own: /v1/deliberate takes prompt not messages; curl @~/hdr tilde) | findings: schema stripped with zero client signal DF-CHIMERA-V2-53 P1; truncation never finish_reason=length DF-CHIMERA-V2-54 P1; small-cap garbage answers unmarked DF-CHIMERA-V2-55 P2; fresh-install auth silent-fail DF-CHIMERA-V2-56 P2 | credit: error contracts 5/5 exact vs docs; multi-turn memory works; no-ops never error; models.list typed (run-6 crash fixed in deployed code); panel found the project's own DF-CHIMERA-V2-50 defects from the file alone; schema-strip docs VERIFIED accurate by canary const probe | live deploy: CODE-CURRENT (ee8ad95 ancestor of 637eb38, material diff empty) | install: PROVEN on bunker-las-03 agent 6963ad23 (destroyed, verified gone): public clone 8s → pip install [full] 71s py3.13 → config init → serve (needed CHIMERA_API_KEY export per INTEGRATION.md §3 — its absence is DF-CHIMERA-V2-56) → drop-in answer 10s → smoke_live.py SMOKE PASS | smoke=ok | no PERF row (≥99% model-bound; spread 266-292s on identical input is the caller-facing number) | artifacts: docs/dogfood/2026-09-25-run15-integration.md, diagnostics.md run-15 leg, usage skill v1.7.0, board rows DF-CHIMERA-V2-53..56 | tooling lessons: /v1/deliberate takes `prompt` while chat/completions takes `messages` (easy to cross); curl -H @~/file does not expand tilde mid-word; detached long servers on the agent need setsid + a launcher script, nohup& in an ssh one-liner dies with the session
