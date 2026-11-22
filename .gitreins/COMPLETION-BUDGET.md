# Completion-path budget: closeout verdict reuse (CH-MAINT-016)

Measured on /home/kara/chimera-v2 (2026-11-22) and live-proved on a scratch
clone. Product commits: gitreins wt/chimera-v2-CH-MAINT-016 @
ce2802b6 (mechanism) + 06b5118e (consecutive-closeout fingerprint fix).

## 1. AC1 — the measured asymmetry

The closeout (`gitreins task complete`) re-judges the delivered tree under
the SAME `evaluator.max_time` wall the plain `gitreins judge` path uses
(chimera-v2 sets `max_time: 20m` deliberately — CH-MAINT-013; not changed).

Verdict records (`.gitreins/history/2026-11-22/`, read from the canonical
repo read-only) and `.gitreins/usage.jsonl` tier2 rows (`ts`, `tokens_in`):

| run | path | verdict dir / id | ended (UTC) | items graded | usage input tok | tier2 wall |
|---|---|---|---|---|---|---|
| CH-MAINT-013 | `gitreins judge` | 1fa3b609 (kimi-k3 400, infra) | 06:09:46 | 0 (infra) | — | — |
| CH-MAINT-013 | `gitreins judge` | fa427f37 | 06:34:58 | 4 (COMPLETE) | 1,636,498 | ~18m |
| CH-MAINT-013 | `task complete` | 84f17bf2 (capped) | 06:59:37 | 0 (UNVERIFIED) | 2,104,056 | 20m9s CAPPED |
| DF-CHIMERA-V2-128 | `gitreins judge` | 74152442 | 07:15:32 | 3 (COMPLETE) | 511,585 | ~10m |
| DF-CHIMERA-V2-128 | `task complete` | 3ad6e7b1 (capped) | 07:39:12 | 0 (UNVERIFIED) | 1,381,994 | 20m7s CAPPED |

- 2 of 2 closeouts capped `Time cap (20m) exceeded` INCOMPLETE 0-graded
  (~105K / ~69K input tok/min) while the plain judge graded the SAME
  criteria on the SAME tree COMPLETE 10-18m. max_iterations (300) was not
  binding (77.0 / 63.2 iterations used).
- Tier1 was NOT the asymmetry in the measured pairs: all five runs ran the
  guard as `PASS (DEGRADED — skips: lint=no staged files, tests=no staged
  files)` (clean-index closeout position); the Python lint/tests lanes
  discover the index themselves, so `grade_full_tree` (GR-218) only changes
  Go lanes. The "hook_timeout raised to 1320s" budget existed but was
  never the wall that burned.
- Token burn 10-50x under the fleet's quiet-lane norm (1-5M tok/min) —
  off-by-one answer class 2798
  (data/answers/2798-gitreins-tier2-time-cap-queue-contention-variant.json):
  a tier2 time-cap INCOMPLETE with burn far under norm is LANE WAIT, not
  work. Two-starvations rule: only raise `max_time` after a quiet-lane
  re-run also starves — 2 of 2 closeouts starved, but BOTH followed a
  plain-judge PASS of the identical tree minutes earlier, which is not a
  budget problem at all; it is duplicate grading.

## 2. Mechanism chosen: verdict REUSE (option b), not a new ceiling

Adoption identity (engine/closeout_reuse.py, all must match):

- same task id, not `superseded_by`,
- exact criteria list (`task_criteria`),
- every item graded (PASS / FAIL / NOT_VERIFIABLE — never UNVERIFIED: a
  cap leaves "Not examined" rows behind),
- same HEAD commit AND byte-identical workspace CONTENT
  (engine/fingerprint.py digest, state authoritative),
- graded by the lane model the closeout is about to use (CH-MAINT-015
  identity).

On a match the closeout adopts the stored verdict instead of re-grading:
the mirror rides `JudgeResult.tier2` so `gate.pass_class` classifies the
adoption record `judged`, and the new history record carries
`reused_from` (entry id) + `reused_from_evaluated_at`. Partial records can
never be laundered into a closeout, `--skip-tier2` keeps its no-LLM
contract, and the CH-MAINT-013 loud cap is untouched (Proof 3 below).

Alternatives noted in engine/closeout_reuse.py (not implemented):
(a) closeout-specific ceiling — a budget raise in disguise on a lane
10-50x under norm, no principled number; (c) lane-wait-aware cap
measurement — classifies only after the wall already burned.

## 3. Consecutive-closeout fingerprint fix (06b5118e)

First live probe: re-running `task complete PROBE-T1 --force` re-judged
29.67s instead of adopting. Root cause: the closeout flips
status/completed_at into the TRACKED `.gitreins/tasks.yaml` BEFORE
re-observing the tree, so the workspace content fingerprint differed
every run. The task registry is gitreins-owned state mutated INSIDE a
graded run — the same class as the already-excluded review-state files —
so `fingerprint._SELF_STATE_PATHS` now excludes `.gitreins/tasks.yaml`
from BOTH sources (index + untracked;
engine/fingerprint.py:66, engine/fingerprint.py:424). RED-proofed: a
regression test fails against the pre-fix fingerprint (digest moves on
the registry flip) and passes with the fix.

## 4. Live proof (AC3) — scratch clone
~/.hermes/cache/scratch/lane-probe-ch-maint-016 (cloned at 10ea6a6),
z.ai coding lane (GITREINS_LLM_BASE_URL=...api/za... model glm-5.3-flash,
key sourced by indirection, never echoed). Installed build pipx-refreshed
from wt/chimera-v2-CH-MAINT-016 @ 06b5118e (`gitreins --version` → 0.21.1).

### Proof 1 — two sequential closeouts terminate graded inside the ceiling
- `gitreins task complete PROBE-T1 --force`: 56.6s wall, exit 0, COMPLETE
  1/1 graded, verdict ded23b52 (dir 041c2840).
- `gitreins task complete PROBE-T2 --force`: 47.6s wall, exit 0, COMPLETE
  1/1 graded, verdict 082a7609.
- Both inside the configured 20m ceiling with `ungraded_criteria` empty.

### Proof 1b — the adoption seam (same task re-closed on the same tree)
Post-06b5118e build:
- first closeout re-graded live: 57.65s, COMPLETE 2 items, verdict
  2b5234ee (dir b782a606; the grader added one derived criterion).
- immediately repeated: **1.68s wall, exit 0**, printed
  `Adopting stored verdict 2026-11-22/b782a606 — identical tree, criteria
  and grading lane; the closeout re-judge is skipped (CH-MAINT-016)`,
  verdict 2af3f8a0 (dir 522eb8cc), record carries
  `reused_from=2026-11-22/b782a606` + `reused_from_evaluated_at`, same
  fingerprint d4a6c751c6, same grading `judged` class.
- vs the measured capped closeouts: minutes of tier2 burn + INCOMPLETE
  0-graded, replaced by a 1.7s graded adoption.

### Proof 2 — a real overrun still caps loudly
`evaluator.max_time: 1s` in the scratch config, one
`task complete PROBE-T1 --force`:
- exit 1 in ~29s, `Cap exceeded: Time cap (1s) exceeded (5s elapsed).
  Increase max_time or simplify criteria. Partial verdict — 0 of 1
  criteria graded, 1 ungraded.`
- persisted partial verdict 65e193e5/verdict.json: passed=false, item
  status UNVERIFIED ("Not examined — evaluation ended before this
  criterion was reached").
- config restored to `max_time: 20m`; scratch clone removed after.

### CH-MAINT-015 regression check
After the pipx refresh (`--force`), an incoherent env (z.ai base_url +
model moonshotai/kimi-k3) still refuses in ~2s:
`judge lane incoherent: base_url ... does not serve model
moonshotai/kimi-k3 (model absent from /models list: 12 models); fix
GITREINS_LLM_MODEL or GITREINS_LLM_BASE_URL (or set
GITREINS_LLM_SKIP_MODEL_CHECK=1 ...)` — exit 1, no tier-1 work, no verdict.

## 5. Code path (gitreins @ 06b5118e)

- gitreins/cli.py:2570-2600 — `cmd_task_complete` adoption block: reuse
  lookup, mirror build, `reused_from` stamp handed to `_persist_result`
  (now `_persist_result(..., extra=None)`, gitreins/cli.py:3047);
- engine/closeout_reuse.py — `find_reusable_verdict`
  (engine/closeout_reuse.py:167), `build_adopted_result`
  (engine/closeout_reuse.py:214), strict identity checks
  (`_fully_graded` :97, `_tree_match` :121, `_lane_match` :139);
- engine/fingerprint.py:66 — `_SELF_STATE_PATHS` gains
  `.gitreins/tasks.yaml`; engine/fingerprint.py:424 — excluded from both
  index and untracked at the single paths-assembly seam;
- engine/eval_cap.py:196-206 — untouched (the loud cap);
- tests: tests/test_closeout_reuse.py (15 tests) — adoption, changed
  tree/head/criteria/lane re-grades, capped-record refusal, supersession,
  CLI seam (adopt / fallback / --skip-tier2 never adopts), registry-flip
  digest stability. Full suite: 3872 collected, 0 failed.

## 6. Sequencing notes (for the next closeout-heavy tick)

- The 20m default in chimera-v2 .gitreins/config.yaml is UNTOUCHED; no new
  config keys exist — reuse is behavior, not budget.
- Closeouts whose prior verdict was graded by an OLDER gitreins build
  store fingerprints from the OLD self-state set and will not adopt until
  one fresh judgment re-records the fingerprint under the new rules
  (conservative fail-closed; measured once here: PROBE-T1 needed a 57s
  live re-grade before its next closeout adopted).
