# Chimera Dogfood — 2026-09-04 (run B: release-lag + deploy-parity focus)

Sixth dogfood run; cron re-picked chimera-v2 hours after run A (same day).
Run A re-proved known breaks; run B went additive: the legs no previous run
covered — install verification (PyPI vs HEAD wheel), the ephemeral-bunker
leg, and a live REST regression battery on the deployed :8765 service.

## Promise under test

"One API call. A team of models. One answer." via CLI / REST / MCP / library.

## What I actually did (real use, not tests)

1. **PyPI fresh-user battery** (venv, `pip install chimera-deliberation[full]`
   = 0.2.1, 20s): bare import OK; `chimera --help` OK; wheel does NOT ship
   `chimera.yaml.example` (only `.docker`); `chimera config init` does not
   exist; bare `chimera run` with only DEEPSEEK_API_KEY dies with
   `error: No chimera.yaml found. Copy chimera.yaml.example to chimera.yaml.`
   — a file the wheel doesn't ship. The README Quickstart is 100% dead on the
   published artifact. **The fixes exist in HEAD and are correct — they are
   simply unreleased (PyPI latest 0.2.1 = Aug 23; local pyproject = 0.2.3).**
2. **HEAD wheel battery** (built 0.2.3 wheel, fresh venv, 17s): example
   ships; `config init` creates a working chimera.yaml; bare `chimera run`
   returned a real merged answer ("Paris") — while reproducing the known
   auto-formation guardrail problem (worker on openrouter/qwen3.7-plus
   failed, 300s cooldown, degraded merge).
3. **Live REST regression battery** against the deployed :8765 (running
   b087769): stream:true → 400 stream_not_supported ✔; max_tokens:1 →
   honored (2-char answer) ✔; unknown model → 404 model_not_found ✔; real
   deliberation → 200 "Paris" in 18.6s ✔; /v1/health healthy 7/7 ✔; web UI
   + /docs 200 ✔. The deploy is functionally sound despite the drift.
4. **MCP leg**: repo's own probe (initialize → tools/list → tools/call)
   against the HEAD 0.2.3 wheel: stdout line 1–2 are loguru log lines;
   the initialize JSON-RPC response arrives on line 3 → every conforming
   MCP client fails framing. P0 stands at HEAD.
5. **Bunker leg**: SKIPPED with evidence — bunkerd active but its port pool
   is exhausted (10/10 ranges; 4th+ recurrence), spawn 500s in the journal;
   ssh :22 to the host times out (root SSH + ICMP fine). Local fresh-venv
   batteries substituted so installability was still verified, but the
   bare-Debian-from-zero leg remains unproven for chimera.

## Verdict: 🟡 PROMISING-BUT-ROUGH

- **Does it work?** The engine and the deployed REST service: yes — every
  deployed contract behavior passed live. The published pip package: no —
  the documented quickstart dead-ends. MCP: no — unusable at HEAD.
- **Is it useful?** Yes: multi-model deliberation with honest traces at
  ~$0.003–0.02/run is real value, and the REST surface is trustworthy.
- **Is it usable?** pip users: blocked (P0). CLI users: works but noisy
  (logs interleave) and auto formation burns workers on blocked models.
- **Is it trustworthy?** Yes on traces/health/errors; the release channel
  itself is the trust gap now (fixes "verified" but never reaching users —
  4th packaging/release lag this year).

Time-to-first-success: 18s on the HEAD wheel path; PyPI path: **never**
(blocked at first run). Friction count: 4.

## Integration notes (the "right way" today)

- Install: build the wheel from HEAD (`pip wheel --no-deps .`) and install
  that — do not trust PyPI until 0.2.3 publishes.
- First run: `chimera config init` (HEAD only), export DEEPSEEK_API_KEY,
  `chimera run "..."`. Read `trace.source`; expect possible guardrail
  warnings with auto formation.
- Agents: do NOT use chimera-mcp until DF-CHIMERA-0906-2 lands; use the
  REST `/v1/chat/completions` contract instead (verified correct live).
- Ops: check `/health` commit vs `git rev-parse --short HEAD` before
  trusting live behavior; restart `chimera.service` to load HEAD.

## Tasks filed (board .coding-hermes/board/tasks.jsonl)

- DF-CHIMERA-0906-1 (P0): publish 0.2.3 + release gate testing the PUBLISHED artifact
- DF-CHIMERA-0906-2 (P0): MCP stdout purity (3rd run, still broken at HEAD)
- DF-CHIMERA-0906-3 (P1): auto formation ignores credential-reality of providers
- DF-CHIMERA-0906-4 (P1): deploy drift recurrence #3 — needs enforcement, not reopen #3
- DF-CHIMERA-0906-5 (P2): CLI stdout/log separation, --quiet/--json
- DF-CHIMERA-0906-6 (P2): SKIPPED-install-bunker + bunker infra fixes
