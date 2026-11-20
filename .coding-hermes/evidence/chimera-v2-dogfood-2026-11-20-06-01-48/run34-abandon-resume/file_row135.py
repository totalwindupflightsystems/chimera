import hashlib, subprocess, pathlib, sys

REPO = pathlib.Path("/home/kara/chimera-v2")
EVD = ".coding-hermes/evidence/chimera-v2-dogfood-2026-11-20-06-01-48/run34-abandon-resume"

head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True).stdout
ls = subprocess.run(["git", "ls-files", "-s"], cwd=REPO, capture_output=True, text=True).stdout
fp = hashlib.sha256((head + "".join(sorted(ls.splitlines(True)))).encode()).hexdigest()

title = ("[P1] main is red at HEAD: a dogfood run log landed without its docs/README.md index line and the "
         "docs-index pre-commit arm did not block the commit - a clean clone fails tests/test_docs_index.py")

reasoning = """A clean checkout of HEAD cannot pass its own suite. This was measured twice, independently, on the same tree:

1. Locally, on the clean checkout: `python -m pytest tests/test_docs_index.py -x -q` -> **1 failed, 49 passed**:
   `test_tracked_docs_file_is_reachable[docs/dogfood/2026-11-20-run33-retry-resilience-integration.md]` —
   "docs/dogfood/2026-11-20-run33-retry-resilience-integration.md is referenced nowhere: link it from README.md
   (if it is current documentation) or list it in docs/README.md".
2. On a FRESH MACHINE, from the ephemeral bunker battery (`bunker-qa.sh`, agent 1434cbce, clean clone):
   the `tests` cell came back **FAIL (rc=1)** with the same first failure
   `_ test_tracked_docs_file_is_reachable[docs/do...` — so this is not a local-environment artefact, it is the
   shipped tree. `fresh-install`, `lint`, `docker_build`, `compose_config` and `toolchain-bootstrap` all passed
   on that same clean box, which is what makes the red unambiguous: the install works, the tree is red.

Scope of the orphan (detector run over `git ls-files docs/dogfood/`): exactly one file is unindexed —
`docs/dogfood/2026-11-20-run33-retry-resilience-integration.md`. Everything else is reachable from
README.md / docs/README.md.

Provenance: that file was added by commit 194dcaf ("gate: gitreins guard --full -> DEGRADED PASS, no
unknown-key WARN; mypy exit 0; tests (full) ok."). `git log -S 'run33-retry-resilience' -- docs/README.md`
returns NOTHING, so an index line for it never existed in any commit — the report and its index line did not
travel together, which is the failure mode `tests/test_docs_index.py` itself documents as having recurred five
times (CI-FIX-001, DOC-2, INT-CI-014, INT-CI-014-R2, INT-CI-014-R3).

The interesting part is not the orphan, it is the guard: `.git/hooks/pre-commit` carries the docs-index arm
(lines 148-154, calling `scripts/check_docs_index.sh`) and that script refuses exactly this shape (a dated
docs/dogfood/ run log staged without its docs/README.md line). The commit still landed, so it bypassed the
hook (--no-verify / hooksPath override is the standing fleet pattern) or the arm was not armed in that
checkout. Either way a commit message can assert "tests (full) ok" while leaving main red, and nothing
downstream re-checks it — CI red and a red HEAD are invisible to the lane that caused them.

What this lane did about main (documentation index only, no product code touched): added index lines for run 33
and for this run's report (docs/dogfood/2026-11-20-run34-abandon-resume-integration.md) to docs/README.md, so
the tree goes green. The row stays open for the guard bypass, because the index repair does not make the next
bypass visible.

Acceptance criteria:
- `python -m pytest tests/test_docs_index.py -q` passes at HEAD (the two index lines above), and the full suite
  is green on a clean clone (the bunker `tests` cell, not just a local run).
- RED-PROOF the arm: stage a new dated docs/dogfood/*.md without its index line and prove
  `scripts/check_docs_index.sh` exits non-zero on that staged index (the test file already carries a
  `git show :README.md`-based harness for this shape — reuse it rather than inventing a second one).
- Name how 194dcaf bypassed the hook, and make the bypass loud: if lanes commit with --no-verify, the guard has
  to fail closed and say so, not disappear (a guard that can be skipped silently is the defect this row is for)."""

ac = """1. `python -m pytest tests/test_docs_index.py -q` is green at HEAD.
2. Full suite green on a clean clone (bunker `tests` cell), not only locally.
3. `scripts/check_docs_index.sh` proven RED on a staged run log with no index line, and GREEN once indexed.
4. The hook bypass used by 194dcaf is identified and made loud (fail closed), not left silent."""

cmd = [ "boardctl", "-C", ".", "create",
       "--id", "DF-CHIMERA-V2-135", "--title", title, "--reasoning", reasoning,
       "--priority", "P1", "--type", "bug", "--status", "pending",
       "--capability-tags", "docs,ci,guard,dogfood",
       "--acceptance-criteria", ac,
       "--evidence-artifact", f"{EVD}/usage-section.md",
       "--evidence-fingerprint", fp,
       "--evidence-run-id", "chimera-v2-dogfood-2026-11-20-06-01-48"]

r = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
print("rc=", r.returncode)
print(r.stdout[-2000:])
print("ERR:", r.stderr[-1500:])
print("FP:", fp[:16])
