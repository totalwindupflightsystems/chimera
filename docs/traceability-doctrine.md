# Traceability doctrine — the `ch:trace` marker and the contributor contract

Every piece of work in this repository must be traceable from claim to proof.
The scheduler requires it for every row it closes; this document is the
contract: the marker grammar, the evidence and witness rules, and the
close-out tiers that decide when work is actually done. A change without a
traceable chain is not "done" — it is unverified work that happens to have a
commit message.

## The marker

`ch:trace` is a single-line, machine-greppable marker. It appears in commit
subjects and bodies, in board rows (`.coding-hermes/board/tasks.jsonl` and
`events.jsonl`), and in PR descriptions. Grammar:

```
ch:trace row=<ID> spec=<spec-ref> wave=<wave-id> test=<test-ref> doc=<doc-path> prompt=<prompt-ref> evidence=<evidence-path> witness=<witness-type> verdict=<verdict-id> commit=<commit-hash> memory=<memory-id>
```

| field | meaning | example |
|---|---|---|
| `row=<ID>` | the board row this work closes (required) | `row=DOC-11` |
| `spec=<spec-ref>` | spec or design doc governing the work | `spec=docs/design-decisions.md` |
| `wave=<wave-id>` | dispatch wave file, when foreman-dispatched | `wave=.coding-hermes/waves/coding-hermes-scheduler-foreman-2026-10-04-12-47-21.json` |
| `test=<test-ref>` | test that pins the behavior | `test=tests/test_engine.py::test_timeout_excluded` |
| `doc=<doc-path>` | documentation created or changed | `doc=docs/traceability-doctrine.md` |
| `prompt=<prompt-ref>` | prompt/brief that dispatched the work | `prompt=~/.hermes/skills/coding-hermes-docs/SKILL.md` |
| `evidence=<evidence-path>` | where the proof lives | `evidence=commit:bea0155f`, `evidence=.coding-hermes/board/tasks.jsonl#REVIEW-CHIMERA-001` |
| `witness=<witness-type>` | how the claim was observed (below) | `witness=live:smoke` |
| `verdict=<verdict-id>` | close-out verdict, or `none:<reason>` | `verdict=none:not-judged` |
| `commit=<commit-hash>` | the commit carrying the change | `commit=board-filing` |
| `memory=<memory-id>` | memory key written from this work | `memory=none:not-written` |

Fields that do not apply still must appear, with the value `none:<reason>`:

```
verdict=none:not-judged      memory=none:not-written
spec=none:pm-ledger-finding  witness=none:static-source-and-doc-read-no-live-service
```

A bare `none` without a reason is a malformed marker. A narrative tail after
the marker (separated by `|` in board rows) is allowed and encouraged — the
marker proves, the prose explains.

Find all markers with `git log --grep='ch:trace'` or
`grep -o 'ch:trace[^"]*' .coding-hermes/board/tasks.jsonl`.

## Value conventions

- **`none:<reason>`** — the field is genuinely absent; the reason is
  mandatory and must be specific enough to act on.
- **`live:<observation>`** — witness values describing direct observation of
  a running system, e.g. `witness=live:ps-eo-pid,ppid,etime-rss-7-procs-all-parents-alive`
  or `witness=live:pytest-test_collaborative_evals`.
- **`commit:<sha>`** — evidence pointing at a git object.
- **`gh-run-<id>-<date>`** — a CI run witnessed the claim on the exact commit,
  e.g. `witness=gh-run-38362578606-2026-10-10`.

## Close-out tiers

Tiers measure how close the proof came to the real thing:

| tier | name | proof shape |
|---|---|---|
| **T0** | exists | the artifact exists (file, endpoint, flag) |
| **T1** | imports | it is wired into the system: imported, mounted, routed, called by real code |
| **T2** | unit tests | hermetic tests pin its behavior |
| **T3** | invoked live | the real thing was invoked in the real system and returned a real, observed result |
| **T4** | judged | T3 plus an independent judge (LLM panel or human) graded the evidence |

Rules:

1. **T3 is the minimum for "done"** on any behavior change. Reading the code,
   importing it, or passing unit tests does not prove the feature works in the
   deployed system. For this service the standing T3 instrument is
   `scripts/smoke_live.py`, which POSTs a real `/v1/deliberate` and prints the
   merged answer.
2. **T0–T2 alone never close a row.** They are prerequisites, not proof. A row
   closed on "the file exists" (T0) or "tests pass" (T2) is not closed; it is
   asserted.
3. **T4 grades a T3 body.** A judge verdict stacked on T0–T2 evidence grades
   the paperwork, not the feature.
4. "Endpoint reachable" is not "feature works": a 200 on a health route is
   T1-class evidence at best. Real invocation with a real result is the floor.

## Evidence and witness rules

- **Every claim carries `witness=` or `witness=none:<reason>`.** This applies
  to row close-outs, commit messages that claim behavior, reports to the
  foreman, and docs that state "X works".
- **Evidence must exist and be reachable** by someone other than the author: a
  file path, a commit sha, a run URL, a command transcript. Evidence that lives
  only in the worker's context window is not evidence.
- **Self-reports are not witnesses.** "I ran the tests and they passed" is a
  claim; the log, the transcript, or the run id is the witness.
- **Negative claims need the same shape as positive ones.** "X no longer
  happens" requires a probe that demonstrates absence — a grep that found
  nothing is not a probe.
- **`witness=none:<reason>` must be honest and specific**: acceptable —
  `none:static-source-and-doc-read-no-live-service`, `none:transient`;
  unacceptable — a bare `none`, or a vague reason that hides an skipped probe.

## Worked examples (real shapes from this repo's board)

Live-observed verification row:

```
ch:trace row=REVIEW-CHIMERA-001 evidence=.coding-hermes/board/tasks.jsonl#REVIEW-CHIMERA-001 witness=live:ps-eo-pid,ppid,etime-rss-7-procs-all-parents-alive
```

CI-witnessed integration finding (recurrence, row deliberately left open):

```
ch:trace row=INT-CI-006 witness=gh-run-38362578606-2026-10-10 verdict=none:live-provider-flake-recurrence
```

Wave work with a full chain:

```
ch:trace row=SCHED-GAP-1707 spec=docs/design-decisions.md wave=.coding-hermes/waves/coding-hermes-scheduler-foreman-2026-10-04-12-47-21.json evidence=commit:bea0155f
```

Static doc work, honestly not live-verified and not closed:

```
ch:trace row=DOC-8 spec=none:repo-doctrine-missing wave=none:stand-in-scheduler-tick test=none:static-doc-audit doc=docs/USAGE.md prompt=~/.hermes/skills/coding-hermes-docs/SKILL.md evidence=/home/kara/.hermes/stand-in/docs/chimera-v2/docs-audit-2026-10-10-17-40-53.md witness=none:static-source-and-doc-read-no-live-service verdict=none:not-judged commit=board-filing memory=none:not-written
```

## Anti-patterns

- A bare `none` with no reason — malformed, the scheduler rejects the row.
- `evidence=` pointing at a conversation ("as discussed") instead of an
  artifact.
- A passing `verdict=` stacked on `witness=none:...` — an unobserved pass is a
  contradiction, not a close-out.
- Declaring T0 "done": the artifact existing is the start of the proof, never
  the end.
- Rewriting history to add a marker to an old commit — add the marker to the
  commit that carries the work.

## Relation to the GitReins gate

The guard ([docs/GITREINS.md](GITREINS.md)) checks that the code is clean at
commit time: secrets, lint, tests, LSP. The marker chain checks that the WORK
is proven: guard green plus no T3 witness is unverified work, and the
close-out stays `verdict=none:not-judged` until T3 (or T4) lands. The judge
tier is produced with `gitreins task complete <id>`, which triggers evaluation
of the evidence against the task's criteria.
