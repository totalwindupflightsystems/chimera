# Evidence — run 31 (provider resilience), tick `chimera-v2-dogfood-2026-11-20-06-01-48`

Measured on a repo checkout at HEAD `d274585` (origin/main == HEAD). Deployed product code
== HEAD product code: the running build reports `commit=f0a34a2`, which is an ancestor of
HEAD with **0** non-`.coding-hermes` files changed in between.

Every number below was produced by the commands in this file, on this box, on 2026-11-20.

## 1. Real use — the headline operation, four arms, timed

Command shape (documented CLI, JSON output):

    .venv/bin/chimera run -f quick-panel --json '<a real CFO decision question>'

| arm | formation / aggregator | wall | exit | answer_degraded |
|---|---|---|---|---|
| run1 | `quick-panel`, aggregator `deepseek/deepseek-v4-flash` | 82,577 ms | 2 | true |
| run2 | same, immediate retry | 186,852 ms | 2 | true |
| survivor1 | scratch config, dispatcher → `openrouter/qwen/qwen3-coder`, aggregator `qwen3.7-plus` | 113,729 ms | 2 | true |
| survivor2 | scratch config, aggregator `google/gemini-3.1-pro-preview` | 94,877 ms | 0 | false |

`exit` is not incidental: `src/chimera/cli/main.py:399-407` maps a degraded answer to
`sys.exit(2)`, and on that path the `.answer` field carries the engine's failure placeholder
(`[stage aggregator (...) unavailable: ...]`), not an answer — see `runs-summary.jsonl`.

The scratch config (`survivor.yaml`) is a copy of `chimera.yaml` with added formations; the
repo config was never edited. Files: `runs-summary.jsonl`.

## 2. Operator surface — cold-cache asymmetry, reproduced 3/3

A fresh `chimera serve` on a scratch port (`CHIMERA_PORT=8801`), cold probe cache, no other
traffic. Same second, two documented endpoints:

    cold-repro.log:
      /v1/health        -> 200 in 1.519 s   {"status":"healthy","in_flight":13,"unhealthy":0}
      /v1/health/ready  -> 503 in 1.517 s   "Not ready — probes still in flight (in_flight: anthropic, ...)"
      ... repeated 3x, same verdicts, both endpoints returning at the same ~1.50 s budget

Raw payloads: `cold-health-{1,2,3}.json`, `cold-ready-{1,2,3}.json`.
Steady state is fine and was measured separately: 367 one-second probes over 420 s,
**0 x 503**, mean 0.114 s, max 1.503 s (24 samples over 1 s) — `readiness-1hz-420s.tsv`.
So this is the cold/refresh path only, not a rolling flap.

## 3. Token accounting — provider-reported usage, unvalidated

`survivor2.json` (clean run): worker_3 `hermes/glm-5.3-flash` reports
`tokens_input=149511` for a **352-character** prompt, i.e. 98.2% of the run's 152,271 input
tokens; the aggregator reports `tokens_input=2562` for a 68-character traced prompt (the
traced `prompt` is only the stage label — upstream context does reach the model, so there is
no "starved aggregator" claim here). `trace` carries no `total_tokens_input`/`total_tokens_output`
at all (`runs-summary.jsonl`).

## 4. Install leg

- **Ephemeral bunker: SKIPPED, not silent.** `ssh -o BatchMode=yes root@<bunker-host>` →
  `Permission denied (publickey,password)` — the host answers, this box has no accepted key,
  and minting one is forbidden by the lane rules. Filed as `SKIPPED-INSTALL-CHIMERA-V2-21`.
- **Local compensation (real, fresh environment):** `uv build` at HEAD → wheel
  `chimera_deliberation-0.3.0-py3-none-any.whl`; `uv venv` (CPython 3.14) + install of that
  wheel alone; `chimera --version` → `chimera 0.3.0` rc=0; `chimera config init` → writes
  `chimera.yaml` from the packaged example; one real `simple` run → rc=2 in 10.7 s with
  `Insufficient Balance` from the config-init default aggregator. Transcripts and the wheel
  contents listing: `install-local.txt`.
- The wheel ships only `chimera/chimera.yaml.example` and `chimera/chimera.yaml.docker` —
  no operator/fleet config (checked with `unzip -l`).

## 5. Board rows filed off this evidence

`DF-CHIMERA-V2-120` (P1) single dead aggregator destroys the run · `-121` (P2) trace token
accounting · `-122` (P2) health-vs-readiness cold-cache asymmetry · `-123` (P3) operations.md
readiness timeout guidance · `-124` (P3) blocked-models `UserWarning` on every fresh-install
invocation · `SKIPPED-INSTALL-CHIMERA-V2-21` (P2) install-leg skip.

`boardctl validate .coding-hermes/board/tasks.jsonl` → 0 errors after filing; ids minted with
`~/.hermes/scripts/board_next_id.py`, never hand-chosen, never re-used.

## Re-run recipe

    cd <repo> && .venv/bin/chimera run -f quick-panel --json '<prompt>'; echo "rc=$?"
    CHIMERA_PORT=8801 .venv/bin/chimera -c chimera.yaml serve &
    curl -s -o /dev/null -w '%{http_code} %{time_total}\n' http://127.0.0.1:8801/v1/health
    curl -s -o /dev/null -w '%{http_code} %{time_total}\n' http://127.0.0.1:8801/v1/health/ready
