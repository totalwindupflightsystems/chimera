# QA-CHIMERA-V2-47 — QA battery harness classifier fixes (deployed harness edit)

Date: 2026-11-25 (tick 502, chimera-v2-foreman-2026-11-25-22-36-40)
Artifact fixed: /home/kara/.hermes/scripts/bunker-qa.sh (shared QA battery generator,
413,488 -> 414,858 bytes). NOT part of this repo; this directory is the repo-landed
evidence bundle (backup + diff + local verification transcript).

## What was wrong (from the board row)
1. disconnect_suite_counts() rejected pytest comma summaries ('2332 passed, 67 skipped
   in 153.85s') because its count-word terminator class demanded whitespace-or-EOL, so
   every pytest project graded chaos-disconnect UNVERIFIED despite a valid green suite
   log. Reproduced on real run chimera-v2-qa-2026-11-21-04-18-29.
2. chaos-shutdown could grade OK on a vacuous lifecycle: `docker compose stop/start`
   over a stack that was never actually started returns 0, so a clean rc chain
   (UP=0 STOP=0 ... KILLRECOVER=0) proved nothing.

## What changed
1. Line 4487: first alternation tail `([[:space:]]|$)` -> `([[:space:],)]|$)`.
   Go `^ok` and cargo `test result:` alternations untouched; whole-file
   NETWORK_CUT_APPLIED grep untouched.
2. Lines 4541-4545: post-up container count captured as the action counter
   (CNT=$(docker compose ps -q | wc -l); echo CONTAINERS=$CNT into sd.log).
3. Lines 4559-4580: containers read back from the sd.log marker (missing -> 0),
   sd_vacuous guard set at 0; both former OK branches emit FAIL
   "no containers were ever started — lifecycle actions are vacuous" with the
   counter block (UP=.. .. CONTAINERS=..) attached; every chaos-shutdown verdict
   now carries the counter block. Escaped agent-side per QA-BUNKER-56-R2 style.

## Local verification (no live agent; live gate arm stays open on the row)
- bash -n clean before AND after.
- classifier-tests.txt: 7/7 classifier cases + 5/5 guard cases PASS, incl. the real
  fixtures '2332 passed, 67 skipped in 153.85s' and
  '1 failed, 279 passed, 1 skipped, 1 error in 2417.92s'.
- Guard logic proven on synthetic sd.log marker sets: zero/missing containers ->
  FAIL vacuous (never-started service can no longer grade OK); CONTAINERS=3 -> OK.
- Independent foreman re-verification: extracted function re-tested (MATCH/NOMATCH
  identical), diff inspected, bash -n re-run.

## Worker
glm-5.3-flash @ opencode-go-2 (seat proven via state.db session
local-e288417ad83d4c8bac5a5e3ac21640b4c98d9fdcdf136a8e149c1e1f7ac1bfd6,
billing_base_url https://opencode.ai/zen/go/v1, cwd /home/kara/chimera-v2).
Backup: ~/.hermes/scripts/backup/bunker-qa.sh.bak-QA-CHIMERA-V2-47-20261125T224306Z

## Still open (live gate arm — named blocker: no JIT bunker agent this tick)
- AC1 live proof: chaos-shutdown run against a never-started service must grade
  FAIL/SKIPPED (logic now does; needs a real battery run to prove).
- GATE ARM: bash ~/.hermes/scripts/bunker-qa.sh collect after an act cell.
- docker-deploy AC3 gap (worker, verify-only): container UP DURATION not recorded
  (probe_windows measures poll-loop time); noted, cell not restructured.
