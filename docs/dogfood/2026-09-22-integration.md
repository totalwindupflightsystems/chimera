# Dogfood Integration Report — 2026-09-22 (run 11: custom formations)

**Angle:** the one surface none of runs 1–10 touched — a user who writes their
OWN formation. Every prior run consumed shipped presets (`simple`, `auto`,
`speed`, `spec-writer`); this run followed the docs as a new user would to
author, load, run, override, and serve a custom multi-stage formation.

**Verdict: SHIPPABLE** (3rd consecutive). Promise held: one call → team of
models → one answer, including user-authored teams. Friction count: 4.
Time-to-first-success (custom formation authored → first merged answer): ~7 min
including authoring; the CLI itself is ~2 min (54s PyPI install + 30s first
answer, measured fresh on the bunker).

## What a real user does, and what happened

### 1. Author a custom formation (CONFIG.md "my-custom-chain" style)

Wrote a scratch `chimera.yaml` (never committed) with a 3-stage review DAG:

```yaml
formations:
  code-review:
    dag:
      stages:
        - {id: security,    kind: worker, model: deepseek/deepseek-v4-flash, depends_on: []}
        - {id: performance, kind: worker, model: deepseek/deepseek-v4-flash, depends_on: []}
        - {id: verdict,     kind: merge,  model: deepseek/deepseek-v4-flash, depends_on: [security, performance]}
      edges: [[security, verdict], [performance, verdict]]
```

`chimera --config /path/chimera-user.yaml formations` → listed immediately:
`code-review │ dag: 3 stages`. Authoring worked on the first try against the
CONFIG.md example — the `my-custom-chain` block is accurate as written.

### 2. First run — hit the one docs trap

`chimera --config ... run "..."` (no formation flag) →
`error: Unknown formation: auto. Available formations: code-review. Run 'chimera formations' to list them.` exit 2.

The default run path wants an `auto` formation that a minimal config does not
define, and CONFIG.md's custom-formation example omits `auto`. The error
message is genuinely good (it names the valid list), so recovery took seconds.
Filed: **DF-CHIMERA-V2-33**.

### 3. Real deliberation through the custom formation — headline numbers

| Operation | Command shape | Result |
|---|---|---|
| Code review, 2 reviewers + merge, cold | `chimera --formation code-review --quiet run "Review this Python snippet…"` | **86.9s**, RC=0, 11 graded findings + rewritten fix |
| Same formation, warm | short prompt | **31.9s**, RC=0 |
| Inline `--dag --allow-custom-dag` | docs' exact JSON snippet | **40.2s**, RC=0, stages ran `researcher→finalizer`, cost $0.0050 |
| REST custom formation (fresh serve :8777, own config) | `POST /v1/deliberate {formation:"code-review"}` | **18.4s**, 3 stages, 0 failures, 6,814 tokens |
| CLI startup overhead (formations list, 3 runs) | `chimera --config ... formations` | 0.25s mean — the app itself is never the wait; all real-run latency is model time |

The 87s cold review output was genuinely useful (least-privilege, TOCTOU,
email-canonicalization, O(n²) findings — correct and prioritized). The merge
stage synthesized across both reviewers, not just concatenated.

### 4. Per-stage model override (`--stage-models`)

`--stage-models '{"performance":"deepseek/deepseek-v4-pro","verdict":"deepseek/deepseek-v4-pro"}'`
→ trace confirms only those stages moved to v4-pro (`performance→deepseek-v4-pro`,
`verdict→deepseek-v4-pro`, `security` untouched). **The override mechanism
targets user-authored stage ids correctly** — this is the part that makes
custom formations practical.

Negative test: `--stage-models '{"nosuchstage":"..."}'` → **silent no-op**.
RC=0, no stderr mention of the unmatched key. A typo'd stage id silently loses
its override. Filed: **DF-CHIMERA-V2-34 (silent no-op part rolled here is
DF-CHIMERA-V2-32)**.

### 5. Degradation behavior on a custom DAG (real timeout, observed live)

During the override run, the v4-pro `performance` stage hit the 120s per-stage
timeout. Observed: stage cancelled and recorded degraded
(`engine_stage_timeout timeout_s=120.0`), merge continued with
`aggregator_partial_inputs {total_deps: 2, degraded: 1, healthy: 1}`, run
completed RC=0 with a coherent (single-reviewer) answer, `worker_failures`
present in the `--json` trace. One slow model cannot block the deliberation —
the resilience contract works as designed. **But** for a CLI user the only
signals are JSON structlog lines on stderr, not the documented plain
`warning:` lines (USAGE.md lines 79–84), and the `--quiet` answer carries no
degradation note. Filed: **DF-CHIMERA-V2-34**.

Timeout is configurable (config `timeout.per_stage_s`, engine.py resolves
request header → config → `DEFAULT_STAGE_TIMEOUT_S = 120.0`), but CONFIG.md
does not mention the knob under `formations`/`models` where a user hitting
120s timeouts would look. Folded into DF-CHIMERA-V2-34's fix direction.

### 6. REST surface with a custom config

`CHIMERA_CONFIG=<scratch> chimera serve --port 8777` → `/health`
`{"status":"alive","uptime_models":2,"commit":"faf78b4"}` (running commit
matches checkout — CH-GAP-039 parity mechanism working),
`/v1/formations` serves the custom formation,
`POST /v1/deliberate` runs it end-to-end. The live :8765 unit was never
touched; the scratch server was killed after the run.

## Perf (Step 2b summary)

Nothing here justifies a PERF row: CLI overhead is 0.25s (3-run mean),
deliberation latency is model-bound (86.9s cold / 31.9s warm for a 2+1 fan-out
on deepseek flash), and the one wait a user would notice (the 120s stage
timeout) already has a working, documented-in-code escape hatch
(`timeout.per_stage_s`). A cold-vs-warm delta of ~55s is provider latency plus
first-call provider handshakes, not application work. No hot path to profile.

## Install leg (ephemeral bunker, PROVEN — no SKIPPED row)

bunker-las-03 agent `4dfc08f3` (TTL 2h, destroyed after, 0 agents remaining):

1. `python3 -m venv ~/venv && pip install "chimera-deliberation[full]"` → **54s**, RC=0
2. `chimera --version` → `chimera 0.2.7` (PyPI == repo version: release-lag chain closed for this artifact)
3. `chimera config init` → **works from the packaged example** — the
   DF-CHIMERA-0916B-4 fix (untrack live yaml, ship the example in the wheel)
   verified on the published artifact, not just HEAD
4. `chimera formations` → 6 shipped presets
5. First real deliberation, only `DEEPSEEK_API_KEY` set → answer in **30s**, RC=0

No sudo, no compose plugin, no toolchain beyond python3-venv assumed. The
documented quickstart is complete for a bare Debian user.

## Verify-closes recorded this run

- **DF-CHIMERA-0916B-4** (config init broken by tracked live yaml) → VERIFIED
  FIXED on the published 0.2.7 wheel (row DF-CHIMERA-V2-36, complete).
- Release-lag P1 chain (DF-CHIMERA-0911-2 / 0916B-3): PyPI 0.2.7 == repo
  pyproject 0.2.7 == live server commit faf78b4 == HEAD. No new lag row filed;
  watch on next release.
- **CH-GAP-059** health-status fix confirmed deployed (HEAD commit in
  /health; row already complete — not touched).

## Findings index (board rows)

| Row | P | Finding |
|---|---|---|
| DF-CHIMERA-V2-32 | P2 | `--stage-models` silently ignores unknown stage ids |
| DF-CHIMERA-V2-33 | P3 | No implicit `auto`: default `run` exits 2 on a minimal config; CONFIG.md example omits `auto` |
| DF-CHIMERA-V2-34 | P2 | Degraded merge: RC=0, plain answer, degradation only as JSON log lines, not the documented `warning:` contract; timeout knob undocumented for users |
| DF-CHIMERA-V2-35 | P3 | CONFIG.md fractional category example (0.90) vs canonical percent scale → rescale warning every run |
| DF-CHIMERA-V2-36 | P2 | Install leg PROVEN + 0916B-4 verified (complete) |

## Scratch evidence (not in repo)

`/tmp/dogfood-chimera/` — user config, all transcripts (answer1.txt, dag.json,
sm.json, rest.json, serve logs), timing records. Credentials never written to
any artifact; the bunker key was destroyed with the agent.
