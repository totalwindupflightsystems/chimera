# The GitReins quality gate — lanes, verdicts, and the ordering trap

Every commit in this repo runs the static guards configured in
[`.gitreins/config.yaml`](../.gitreins/config.yaml). This page is the reference
for what those guards check and how to read the verdict they print. The quick
command itself lives in [AGENTS.md](../AGENTS.md) under "GitReins Quality
Harness (MANDATORY)".

## Running it

```bash
pip install -e ".[dev]"                                              # ruff, pytest, pylsp
PATH="$(git rev-parse --show-toplevel)/.venv/bin:$PATH" gitreins guard
```

The repo venv **first on PATH** is load-bearing, not cosmetic. GitReins resolves
each entry of `guards.lsp_tools` with `shutil.which()`, i.e. from PATH alone, and
the `dev` extra is what provides that binary — so `pip install -e ".[dev]"` plus
this PATH is the difference between the lane working and the lane not working.

Measured on this host, same staged file, only PATH changed:

```
~ lsp — skipped (no LSP tool on PATH (pylsp not installed))     # repo venv NOT first
✓ lsp                                                          # repo venv first
```

## Which engine you are running (`gitreins --version`)

Skip reporting is a **0.13.0** feature. The pipx-installed engine is 0.12.1 on
some hosts and has no skip vocabulary at all, so the same absent tool reads
differently:

| Engine | pylsp absent, files staged | Tells |
| --- | --- | --- |
| 0.13.0+ | `~ lsp — skipped (no LSP tool on PATH (pylsp not installed))`, run is DEGRADED | the `~` summary line |
| 0.12.1 | `✓ lsp`, run is PASS (exit 0) — a vacuous green | stderr line `gitreins.lsp: WARNING: LSP tool 'pylsp' not found on PATH — skipping` |

On 0.12.1 that warning is the *only* signal: it is printed during the run and is
not written to any persisted log (0.12.1 writes no run log into `.gitreins/logs/`
at all). Either way the remedy is identical — the dev extra plus the repo-venv
PATH above — and `guards.allow_skips` does not exist in 0.12.1, so the policy
below applies to 0.13.0+.

## The lanes

| Lane | Tool | On failure |
| --- | --- | --- |
| `secrets` | gitleaks, else the built-in scanner (it warns when gitleaks is missing) | BLOCKS |
| `lint` | `ruff check` over the staged Python files | BLOCKS — a failing lint lane makes the run FAIL (exit 1). The pre-commit hook delegates to this same command, so a lint finding blocks a commit too (see "The pre-commit hook" below). |
| `tests` | `pytest` (see test mode) | BLOCKS |
| `lsp` | `pylsp` over the staged files | BLOCKS |

`test_mode: diff` grades the **staged diff**, not the working tree: the file list
comes from `git diff --cached`. **Stage before you guard** (`git add <files>`) —
with an empty index the lanes have nothing to grade. Two exceptions make the full
suite run as a safety net: a safety-trigger file in the staged set
(`pyproject.toml`, `Makefile`, `.gitreins/config.yaml`, other config — the run
then prints `full suite — safety trigger`), and the `guard --full` flag.

## The pre-commit hook

Every commit runs `.gitreins/pre-commit` (installed into `.git/hooks/`). It has
two arms, and only the second is the harness this page describes:

1. **The built-in secrets scan** — self-contained, always runs, and BLOCKS the
   commit (exit 1) on a match, honouring `.gitreins/secrets-ignore`. It is
   deliberately independent of the engine: it is the only gate still available
   where `gitreins` is not installed.
2. **`gitreins guard`** — run with the repo venv first on PATH (see "Running
   it"), its output teed to the console rather than swallowed.

The guard's exit code is a **verdict**, not just an error level, and the hook
maps it:

| `gitreins guard` exit | Verdict | What the hook does |
| --- | --- | --- |
| `0` | `Tier 1 Guards: PASS` | prints `✓ GitReins Tier 1: PASS (gitreins guard)` — the commit proceeds |
| `1` | `Tier 1 Guards: FAIL` — a lane RAN and failed (e.g. a ruff finding) | prints `COMMIT BLOCKED: gitreins guard reported FAIL` on stderr — **the commit aborts** |
| `2` | `Tier 1: DEGRADED PASS` — a substantive lane did **no work** | prints a loud warning naming each skipped lane — the commit proceeds |
| anything else, or `gitreins` not on PATH | the harness never produced a verdict | prints a loud warning naming the rc / the missing engine — the commit proceeds |

Blocking on `2` would make the repo uncommittable on any box whose PATH lacks
the `lsp` lane's tool (`pylsp`): "a gate never ran" is not "a gate FAILED".
Blocking on `1` is the point — a graded FAIL must not reach a commit.

### Installing it

```bash
bash scripts/install_hooks.sh            # install / repair (idempotent)
bash scripts/install_hooks.sh --check    # verify parity, write nothing (non-zero on drift)
bash scripts/install_hooks.sh --dry-run  # print the plan, write nothing
```

`.git/hooks/` is untracked, so the tracked gate is copied into it. The installer
deliberately does **not** set `core.hooksPath`: the same `.git/hooks/` directory
carries the fleet `prepare-commit-msg` hook that appends the `Co-authored-by:`
trailer to every commit, and `core.hooksPath` moves git's whole hook lookup —
setting it would silently shadow that trailer hook.

### The bypass

`git commit --no-verify` is the only way past the hook; there is no environment
variable that turns the gate off. AGENTS.md forbids it for code changes — use it
for a docs-only change or a GitReins self-upgrade, and expect CI to re-run the
same guards regardless.

## Reading the verdict (engine 0.13.0+)

One header line, then one summary line per lane: `✓` ran and passed, `✗` ran and
failed, `~` did no work.

| Output | Meaning | Exit |
| --- | --- | --- |
| `Tier 1 Guards: PASS` | every substantive lane did work and passed | 0 |
| `Tier 1: DEGRADED PASS (skips: …)` | a substantive lane (`lint`/`tests`/`lsp`) did **no work** | 2 |
| `Tier 1 Guards: FAIL` | a lane ran and failed | 1 |

A lane that does no work is a **SKIP, not a pass** — reported as
`~ <lane> — skipped (<reason>)` — and the run is downgraded to a DEGRADED pass.
Whether that reads green or red is the `guards.allow_skips` policy:

- `allow_skips: true` → a zero-work run exits 0.
- `allow_skips` unset (default `false`) → a zero-work run exits **2**, distinct
  from a failure's exit 1, because "a gate never ran" is not "a gate failed".

Because of that, the only proof the gates ran is the green line: grep
`Tier 1 Guards: PASS`, never a bare `PASS`. Under a DEGRADED run the console says
so in words, the summary carries the `~` lines, and the full run log — path
printed as `guard log: <file>` — records the machine-readable `skipped_steps`
list.

## Why `guards.allow_skips` is deliberately NOT enabled here

Setting `allow_skips: true` turns "the gate could not run" into a green verdict.
Measured, empty index, identical tree:

```
⚠ DEGRADED PASS: lint=no staged files, tests=no staged files, lsp=no LSP tool on PATH   → exit 2
Tier 1: DEGRADED PASS (skips: …)                                                        → exit 0   (allow_skips: true)
```

`gitreins init` writes the key for fresh repos as an ergonomic default; this repo
opts out on purpose, so a missing `pylsp` is repaired, never accepted:

```bash
pip install -e ".[dev]"                                              # installs pylsp
PATH="$(git rev-parse --show-toplevel)/.venv/bin:$PATH" gitreins guard
```

## Proving the `lsp` lane actually ran

The lane grades the **staged** Python files. On 0.13.0+ the summary line is the
proof:

```
✓ lsp                                                     # pylsp ran over the staged files
~ lsp — skipped (no LSP tool on PATH (pylsp not installed))
~ lsp — skipped (no LSP tool ran (install pylsp?))         # started, published nothing
```

On 0.12.1 `✓ lsp` is printed whether or not the tool exists, so read the stderr
warning quoted above instead — and treat `~` as unavailable on that engine.

`✓ lsp` means the server started and published over the staged files — not that
it had anything to check with. Diagnostics come from pylsp's own plugins, and the
bare `python-lsp-server` install ships none of the lint ones: measured on this
host, a staged file with a syntax error, an unused import and over-long lines
still printed `pylsp — clean`. Install the linters when you want the lane to bite:

```bash
pip install "python-lsp-server[pycodestyle,pyflakes]"
```

## The verdict-ordering trap (it has burned foreman ticks)

`gitreins task complete <ID>` runs **tier 1 against the staged diff**. Complete a
task *after* your worker has committed and the index is empty: `lint`, `tests`
and `lsp` all skip → the run is DEGRADED → overall FAIL, while tier 2's LLM
evaluation reports COMPLETE because it grades the tree. The tell is that
contradictory pair — tier 2 COMPLETE + tier 1 FAIL with `skips: lint=no staged
files, tests=no staged files`.

Two recovery recipes:

**A. Complete before you commit (preferred).**

```bash
git add <your files>          # stage the work so tier 1 has a diff to grade
gitreins task complete <ID>
git commit -m "…" -- <your files>
```

**B. Already committed? Move the pointer, then complete.**

```bash
git reset --soft <pre-work-sha>   # HEAD back before the work; the commits stay in the index
gitreins task complete <ID>       # tier 1 now grades the work as staged
git reset --soft <tip>            # HEAD forward again — index unchanged, tree unchanged
git status                        # clean: the recovery is a pointer move, not a rewrite
```

A soft reset never rewrites commits: the objects at `<tip>` were only
unreferenced for the duration of the complete. If HEAD was already moved
somewhere else and the commits must be recreated instead, replay them
(`git cherry-pick <sha>`, or `git cherry-pick -C <sha> <sha>` to reuse the
original message) and assert the result is identical with `git diff <old> <new>`
(empty).

Either way: re-verify with a real
`PATH="$(git rev-parse --show-toplevel)/.venv/bin:$PATH" gitreins guard` that the
verdict is `Tier 1 Guards: PASS`, not a DEGRADED one.
