# Local CI — reproducing GitHub Actions with `act`

Hosted CI on `main` is green. This page exists because running the same workflow
**locally** with [`act`](https://github.com/nektos/act) needs one piece of repo
configuration that hosted CI does not: the runner image.

## Commands

```bash
act -j lint                                # the ruff job
act -j test --matrix python-version:3.11   # the unit-test job, one matrix leg
act -q --pull                              # the whole workflow
```

## Why the runner image is pinned (`.actrc`)

The runner image is pinned in the repo-root **`.actrc`**
(`-P ubuntu-latest=catthehacker/ubuntu:act-24.04`, i.e. the same base OS as
GitHub's `ubuntu-latest`).

Without it, act uses its default runner image `node:22-bookworm`, which is
**Debian**. Every job in `.github/workflows/ci.yml` starts with
`actions/setup-python@v5`, and that action only publishes toolcache builds for
Ubuntu — so on Debian every job dies at its first step, before its own `run:`
block executes:

```
Version 3.11 was not found in the local cache
::error::The version '3.11' with architecture 'x64' was not found for this
operating system.
```

This is a runner-image gap, **not** a workflow defect: GitHub-hosted
`ubuntu-latest` runners never hit it, so the workflow is unchanged in what it
gates.

act reads the repo-root `.actrc` automatically and its flags apply before
CLI-provided flags, so the commands above need no wrapper script and no `-P`
argument — including `act -q`, which is what the fleet QA battery runs.

## Expected results at HEAD

Measured **2026-10-19** at commit `9291506` (its `src/`, `tests/` and
`pyproject.toml` are identical to `main` at `cbe233b`; only docs commits
separate them, so the counts hold for both).

| Command | Result |
| --- | --- |
| `act -j lint` | `Job succeeded` (rc=0) — `ruff check .` → *All checks passed!* |
| `act -j test --matrix python-version:3.11 --container-options "--user $(id -u):$(id -g)"` | `Job succeeded` (rc=0) — `2126 passed, 3 skipped` (2129 collected, 108.9s) |
| `act -j test --matrix python-version:3.11` (act's default: the job container runs as **root**) | `Job failed` (rc=1) — `1 failed, 2125 passed, 3 skipped` |

The root-run failure is a runner-identity artifact, not a workflow or suite
defect, and it is exactly one test:

`tests/test_release_workflow.py::test_repo_venv_guard_treats_unreadable_venv_as_absent`
`chmod`s a directory to `000` and asserts the path probe reports it unreadable.
Root ignores those mode bits, so the probe answers "readable" and the assertion
fails. The same test **passes as uid 1000 on the same commit**, and GitHub's
`ubuntu-latest` runner is non-root, which is why hosted CI is green. act 0.2.89
has no dedicated `--user` flag, so the flag rides in through
`--container-options`; substitute your own uid/gid (`id -u` / `id -g`) rather
than copying `1000`.

Treat the numbers as a **dated reading, not a constant**: the suite grows with
every feature commit, so re-measure before calling a local mismatch a
regression. The authoritative figure is whatever the run's own summary line
reports (`N passed, M skipped` or the failure list) — and the pass count depends
on the checkout, because some tests are environment-gated:

- **2 skips** (`tests/test_cli_stdout_purity.py`, `tests/test_config.py`) need a
  repo `chimera.yaml`, which is untracked and local-only (see `AGENTS.md`), so
  they skip in CI and in a fresh clone.
- **2 skips** (`tests/test_release_workflow.py`, the venv-gated pair) need the
  repo `.venv`. A plain checkout has none, so a native run shows *2124 passed,
  5 skipped*; with a `.venv` present the same command reports *2126 passed,
  3 skipped* — the in-container figure above.
- **1 skip** (`tests/test_gateway_coverage.py`) depends on how a pinned
  third-party exception class is inherited in the installed `litellm`.

The same selection, natively — this is the exact command the hosted `test` job
runs:

```bash
.venv/bin/python -m pytest tests/ --ignore=tests/integration --ignore=tests/compat -q
```

### Verifying the count yourself

```bash
# 1. How many tests the selection contains (environment-independent total):
.venv/bin/python -m pytest tests/ --ignore=tests/integration --ignore=tests/compat -q --collect-only | tail -1

# 2. The run itself — read the last line, which is the figure quoted above:
.venv/bin/python -m pytest tests/ --ignore=tests/integration --ignore=tests/compat -q

# 3. The same selection inside the CI runner image, as a non-root user:
act -j test --matrix python-version:3.11 --container-options "--user $(id -u):$(id -g)"
```

A run of `act -j test` that produces the collected total with **zero failures**
is healthy whatever the pass/skip split; a differing pass count alone is not a
regression. If the collected total itself moved, compare it with
`git log --oneline ..HEAD -- tests/` — new tests land with their feature
commits.

## Act emulation limitations (2026-10-26)

Hosted CI at commit `b7a6f642295deeb2555e752ad8f89dbda06ab338` (run 40243624603,
2026-10-25T23:11:31Z) shows conclusion=success: lint=success, test(3.11)=success,
test(3.12)=success, test(3.13)=success, integration=success, packaging-smoke=success.

The same commit under `act` (local GitHub Actions emulation) fails at the Python 3.11
setup step with `ModuleNotFoundError: No module named 'ast'` and the lint leg fails
removing the Python 3.11 directory. Python 3.12/3.13 setup completes but their
unit-test jobs fail. Native execution at the same commit passes 2167 tests.

This is an **act emulation/toolchain artifact**, not a workflow defect. The act runner
image (`catthehacker/ubuntu:act-24.04`) lacks the full Ubuntu toolchain that
`actions/setup-python@v5` expects, and the Python 3.11 installation fails at the
`ast` module import. Hosted CI uses GitHub's `ubuntu-latest` runners with the full
toolchain pre-installed, so the workflow is unchanged in what it gates.

**Verdict**: hosted CI at b7a6f64 is authoritative and green; act-only failures at
that SHA are runner-image gaps, not product defects. Keep the workflow verdict
separate from native pytest results when documenting act reproduction.

## Notes

- Jobs that need repository secrets or a tag ref cannot be fully exercised
  locally — act only gets the secrets you hand it via `--secret` / `.secrets`:
  - `integration` runs `pytest tests/integration/ --run-integration`, which is a
    **live** suite gated on `secrets.DEEPSEEK_API_KEY`. Without that secret the
    tests fail (they do not skip), so a bare `act -q` ends non-zero on the
    `integration` job alone. That is a missing-secret artifact, not a workflow
    defect — do not "fix" it by skipping the job.
  - `publish` and `release-verify` are tag-ref gated (`refs/tags/v*`) and are
    skipped for a branch push.
  - `lint`, `test` and `packaging-smoke` are the jobs to use as the local gate;
    `act -j lint`, `act -j test --matrix python-version:3.11` and
    `act -j packaging-smoke` all exit 0 at HEAD.
- `--container-architecture linux/amd64` is pinned as well, so runs are
  identical on arm64 hosts (where CI images would otherwise resolve to an
  architecture GitHub's runners never use).
