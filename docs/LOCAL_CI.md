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

| Command | Result |
| --- | --- |
| `act -j lint` | `Job succeeded` (rc=0) — `ruff check .` → *All checks passed!* |
| `act -j test --matrix python-version:3.11` | `Job succeeded` (rc=0) — `856 passed, 1 skipped` |

Those counts match the native suite:

```bash
.venv/bin/python -m pytest tests/ --ignore=tests/integration --ignore=tests/compat -q
```

## Notes

- Jobs that need repository secrets (`integration`, which reads
  `secrets.DEEPSEEK_API_KEY`) or a tag ref (`publish`, `release-verify`) cannot
  be fully exercised locally; act only gets whatever secrets you hand it via
  `--secret` / `.secrets`. `lint`, `test` and `packaging-smoke` are the jobs to
  use as the local gate.
- `--container-architecture linux/amd64` is pinned as well, so runs are
  identical on arm64 hosts (where CI images would otherwise resolve to an
  architecture GitHub's runners never use).
