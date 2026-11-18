# v0.3.0 artifact acceptance evidence — chimera-v2

VERDICT: PASS

Artifact under test: `chimera_deliberation-0.3.0-py3-none-any.whl` (1,224,866 bytes,
sha256 `c80cd2c9f67e65aea3439e2b741e783fe7bf4ed8dd33cc12468622f7ba5491a3`), built from
worktree `wt/RELEASE-PARITY-2026-11-16` at HEAD `f7cf034`.
Fresh venv: `/home/kara/.hermes/cache/scratch/rel030venv` (CPython 3.14.5).
Port used: `8790` (verified free before bind, verified closed after kill).
Every step below exited 0; the quickstart battery reported 4/4 PASS at version 0.3.0;
`GET /metrics` answered 200 from the wheel-installed server with all three metric
families present and one real request counted.

Scope note (why this artifact represents the release): worktree HEAD `f7cf034` is an
ancestor of `origin/main`/`github/main` at `7a6a564`, and the only tree delta between
them is board/state (` .coding-hermes/board/{events,tasks}.jsonl`, a foreman run JSON,
`.gitreins/tasks.yaml`). None of those paths are packaged (verified: 0 wheel entries
match `coding-hermes|gitreins`), so this wheel carries the same packaged content a tag
cut at `7a6a564` would build.

## Step table

| # | Step | Command (literal) | Observed result | Exit |
|---|------|-------------------|-----------------|------|
| 0 | Worktree state | `git log --oneline -1 && git status --short` | `f7cf034 chore(release): version prep 0.3.0 (Prometheus /metrics feature release)`; working tree clean | 0 |
| 0b | Scope/parity check | `git rev-parse HEAD^{tree} origin/main^{tree} github/main^{tree}` | HEAD tree `f2cce22`, origin/main `b7d923a`, github/main `b7d923a`; `merge-base --is-ancestor HEAD origin/main` = YES; delta = 4 board/state files only | 0 |
| 1 | Build wheel | `uv build --wheel --out-dir /home/kara/.hermes/cache/scratch/rel030` | `Successfully built /home/kara/.hermes/cache/scratch/rel030/chimera_deliberation-0.3.0-py3-none-any.whl` | 0 |
| 1b | Wheel identity | `sha256sum` / `stat -c '%s'` on the wheel | sha256 `c80cd2c9f67e65ae…7ba5491a3`, 1,224,866 bytes | 0 |
| 2 | Fresh venv | `uv venv /home/kara/.hermes/cache/scratch/rel030venv` | `Using CPython 3.14.5` / `Creating virtual environment at: …/rel030venv` | 0 |
| 2b | Install wheel (as briefed) | `uv pip install --python …/rel030venv/bin/python /home/kara/.hermes/cache/scratch/rel030/*.whl` | base deps installed; `chimera-deliberation 0.3.0`, `litellm 1.99.4` (cap `<1.100` honoured) | 0 |
| 2c | Install wheel + documented `[server]` extra | `uv pip install --python …/rel030venv/bin/python "/…/chimera_deliberation-0.3.0-py3-none-any.whl[server]"` | `Installed 7 packages`; `fastapi 0.164.0`, `uvicorn 0.54.0`; chimera still 0.3.0 from the wheel | 0 |
| 3 | README quickstart battery | `…/rel030venv/bin/python scripts/quickstart_battery.py --venv /home/kara/.hermes/cache/scratch/rel030venv --expected-version 0.3.0` | `CHECKS_PASSED=4 CHECKS_FAILED=0`; `QUICKSTART BATTERY OK: 4/4 … (version 0.3.0)` | 0 |
| 4a | Version surface of installed artifact | `…/rel030venv/bin/chimera --version` | `chimera 0.3.0` | 0 |
| 4b | Free-port probe | `ss -tln` filtered for 8790–8794 | `8790 FREE` (8791–8794 also free) | 0 |
| 4c | Start API from the venv | `CHIMERA_BLOCKED_MODELS_PATH=<scratch> …/rel030venv/bin/chimera serve --host 127.0.0.1 --port 8790` (background, pid 583473) | `Application startup complete.` / `Uvicorn running on http://127.0.0.1:8790`; listener up within 6 polls | 0 |
| 4d | Scrape endpoint status | `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8790/metrics` | `200` | 0 |
| 4e | Metric families present | `curl -s …/metrics \| grep -c '^# TYPE'` | `3` (`chimera_requests_total`, `chimera_request_errors_total`, `chimera_request_duration_seconds`) | 0 |
| 4f | Middleware actually counts (not just declarations) | `curl … /v1/health` then re-scrape `/metrics` | `chimera_requests_total{method="GET",route="/v1/health",status="2xx"} 1`; histogram `_count 1`, `_sum 1.5053774429998157` | 0 |
| 4g | Scrape excluded from its own counters | `curl -s …/metrics \| grep -c 'metrics'` | `0` — no `/metrics` time series minted by scraping | 1 (grep: no match — expected) |
| 4h | Kill server + port closed | `kill 583473`; poll `ss -tln` | `PORT_CLOSED after 2 polls`, `NO_LISTENER_ON_8790`, `PROCESS_GONE`; post-kill `curl` = `000` (exit 7, connection refused) | 0 (curl 7 by design) |
| 5a | No tag on gitlab origin | `git ls-remote origin 'refs/tags/v0.3.0*'` | empty output | 0 |
| 5b | No tag on github | `git ls-remote github 'refs/tags/v0.3.0*'` | empty output | 0 |
| 5c | No local tag | `git tag -l '*0.3*'` | empty output | 0 |

## Deviations from the brief (both recorded, neither bypassed a gate)

1. **The bare wheel cannot serve the API — it must be installed with the documented
   `[server]` extra.** Step 2 of the brief installs the bare wheel only; `chimera serve`
   then refused:
   `error: `chimera serve` requires the optional server dependencies (fastapi, uvicorn), but 'fastapi' is not installed. Install them with `pip install chimera-deliberation[server]``.
   The README Quickstart documents exactly that form (`pip install
   chimera-deliberation[server]  # API server only`), and the wheel's own METADATA
   declares `Requires-Dist: fastapi>=0.162.0; extra == 'server'`. I therefore installed
   the SAME built wheel with `[server]` into the same venv (step 2c) and served from
   that. No index build of chimera was used; the package under test is the local wheel.
2. **Scratch-pinned state path.** `chimera config init`/`serve` warn that
   blocked-models state falls back to machine scope (`~/.chimera/blocked-models.json`)
   outside a repo checkout, so the server run pinned
   `CHIMERA_BLOCKED_MODELS_PATH=<scratch>/blocked-models.json` to keep machine state
   untouched. Config was created in a scratch cwd
   (`/home/kara/.hermes/cache/scratch/rel030run`), never in the worktree.

No source, test, doc, `pyproject.toml`, `uv.lock`, `CHANGELOG.md`, `docker-compose.yml`,
or `reports/model_sync_weekly.md` file was modified. Nothing was pushed; no tag or
release object was created or moved.

## Raw outputs

### Wheel build

```
$ uv build --wheel --out-dir /home/kara/.hermes/cache/scratch/rel030
Building wheel...
Successfully built /home/kara/.hermes/cache/scratch/rel030/chimera_deliberation-0.3.0-py3-none-any.whl
EXIT=0
--- artifact dir ---
-rw-r--r-- 1 kara kara 1224866 Nov 18 13:49 chimera_deliberation-0.3.0-py3-none-any.whl
```

Wheel internals (39 files total):

```
$ unzip -p <wheel> '*/METADATA' | head -5
Metadata-Version: 2.5
Name: chimera-deliberation
Version: 0.3.0
Summary: Dynamic multi-model deliberation gateway
Project-URL: Homepage, https://github.com/totalwindupflightsystems/chimera

$ unzip -p <wheel> 'chimera/__init__.py' | grep -n '_FALLBACK_VERSION'
60:_FALLBACK_VERSION = "0.3.0"
65:    __version__ = _FALLBACK_VERSION

$ unzip -l <wheel> | grep -cE 'coding-hermes|gitreins'
0 (none packaged)
```

### Fresh venv + install

```
$ uv venv /home/kara/.hermes/cache/scratch/rel030venv
Using CPython 3.14.5
Creating virtual environment at: /home/kara/.hermes/cache/scratch/rel030venv
VENV_EXIT=0

$ uv pip install --python …/rel030venv/bin/python /…/rel030/*.whl
 …
 + rich==15.0.0
 + starlette==1.10.0
 + structlog==26.1.0
 + uvicorn==0.54.0
 + yarl==1.25.1
 + zipp==4.1.2
INSTALL_EXIT=0

$ uv pip list --python …/rel030venv/bin/python | grep -iE 'chimera|litellm'
chimera-deliberation      0.3.0
litellm                   1.99.4

$ uv pip install --python …/rel030venv/bin/python "/…/chimera_deliberation-0.3.0-py3-none-any.whl[server]"
Resolved 81 packages in 257ms
Installed 7 packages in 57ms
 + fastapi==0.164.0
 + httptools==0.9.0
 + opentelemetry-api==1.45.2
 + uvloop==0.23.0
 + watchfiles==1.3.0
 + websockets==17.4
 + annotated-doc==0.0.7
INSTALL_SERVER_EXIT=0

$ uv pip list --python …/rel030venv/bin/python | grep -iE '^(chimera-deliberation|fastapi|uvicorn|litellm) '
chimera-deliberation      0.3.0
fastapi                   0.164.0
litellm                   1.99.4
uvicorn                   0.54.0
```

`litellm` resolves to **1.99.4**, inside the repo's load-bearing `<1.100` cap — the
stdout-pollution class the cap exists for does not apply to this artifact.

### README quickstart battery (4/4 PASS)

```
$ …/rel030venv/bin/python scripts/quickstart_battery.py \
    --venv /home/kara/.hermes/cache/scratch/rel030venv --expected-version 0.3.0
VENV=/home/kara/.hermes/cache/scratch/rel030venv
EXPECTED_VERSION=0.3.0
[PASS] cli-version: /home/kara/.hermes/cache/scratch/rel030venv/bin/chimera --version -> exit 0, output contains 0.3.0
[PASS] module-version: /home/kara/.hermes/cache/scratch/rel030venv/bin/python -m chimera --version -> exit 0, output contains 0.3.0
[PASS] cli-help: /home/kara/.hermes/cache/scratch/rel030venv/bin/chimera --help -> exit 0
[PASS] config-init: /home/kara/.hermes/cache/scratch/rel030venv/bin/chimera config init -> exit 0, created chimera.yaml
CHECKS_PASSED=4 CHECKS_FAILED=0
QUICKSTART BATTERY OK: 4/4 README quickstart checks passed against /home/kara/.hermes/cache/scratch/rel030venv (version 0.3.0)
BATTERY_EXIT=0
```

(The script's real flags are `--venv` and `--expected-version`, confirmed by reading
`scripts/quickstart_battery.py`; `--expected-version` is required by design.)

### Version surface of the installed artifact

```
$ …/rel030venv/bin/chimera --version
chimera 0.3.0
VERSION_EXIT=0
```

### Free-port probe, server start, /metrics

```
$ for p in 8790 8791 8792 8793 8794; do … ss -tln …; done
8790 FREE
8791 FREE
8792 FREE
8793 FREE
8794 FREE

$ CHIMERA_BLOCKED_MODELS_PATH=<scratch>/blocked-models.json \
    …/rel030venv/bin/chimera serve --host 127.0.0.1 --port 8790
INFO:     Started server process [583473]
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8790 (Press CTRL+C to quit)
PORT_UP after 6 polls

$ curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8790/metrics
200
CURL_EXIT=0

$ curl -s http://127.0.0.1:8790/metrics | head -30
# HELP chimera_requests_total HTTP requests served, by route template and status class.
# TYPE chimera_requests_total counter
chimera_requests_total{method="GET",route="/v1/health",status="2xx"} 1
# HELP chimera_request_errors_total Failed HTTP requests, split by cause (client_error, server_error, exception).
# TYPE chimera_request_errors_total counter
# HELP chimera_request_duration_seconds HTTP request duration in seconds, by route template.
# TYPE chimera_request_duration_seconds histogram
chimera_request_duration_seconds_bucket{method="GET",route="/v1/health",le="0.005"} 0
chimera_request_duration_seconds_bucket{method="GET",route="/v1/health",le="0.01"} 0
chimera_request_duration_seconds_bucket{method="GET",route="/v1/health",le="0.025"} 0
chimera_request_duration_seconds_bucket{method="GET",route="/v1/health",le="0.05"} 0
chimera_request_duration_seconds_bucket{method="GET",route="/v1/health",le="0.1"} 0
chimera_request_duration_seconds_bucket{method="GET",route="/v1/health",le="0.25"} 0
chimera_request_duration_seconds_bucket{method="GET",route="/v1/health",le="0.5"} 0
chimera_request_duration_seconds_bucket{method="GET",route="/v1/health",le="1"} 0
chimera_request_duration_seconds_bucket{method="GET",route="/v1/health",le="2.5"} 1
chimera_request_duration_seconds_bucket{method="GET",route="/v1/health",le="5"} 1
chimera_request_duration_seconds_bucket{method="GET",route="/v1/health",le="10"} 1
chimera_request_duration_seconds_bucket{method="GET",route="/v1/health",le="30"} 1
chimera_request_duration_seconds_bucket{method="GET",route="/v1/health",le="60"} 1
chimera_request_duration_seconds_bucket{method="GET",route="/v1/health",le="+Inf"} 1
chimera_request_duration_seconds_sum{method="GET",route="/v1/health"} 1.5053774429998157
chimera_request_duration_seconds_count{method="GET",route="/v1/health"} 1
```

Metric families declared: `3` (`grep -c '^# TYPE'`). The `1.505s` histogram sample is
the health endpoint's bounded probe, i.e. a real request was measured end to end.
Scrape exclusion holds: `curl -s …/metrics | grep -c 'metrics'` → `0` (no self series).

### Server teardown

```
$ kill 583473
KILL_EXIT=0
PORT_CLOSED after 2 polls
--- port state ---
NO_LISTENER_ON_8790
--- process alive? ---
PROCESS_GONE
--- curl after kill ---
000
POST_KILL_CURL_EXIT=7
```

### Tag / release state (must be empty)

```
$ git remote -v
github  git@github.com:totalwindupflightsystems/chimera.git (fetch/push)
origin  git@gitlab.readydedis.com:totalwindup/chimera.git (fetch/push)

$ git ls-remote origin 'refs/tags/v0.3.0*'
ORIGIN_EXIT=0
(no output — no matching ref)

$ git ls-remote github 'refs/tags/v0.3.0*'
GITHUB_EXIT=0
(no output — no matching ref)

$ git tag -l '*0.3*'
LOCAL_TAG_EXIT=0
(no output — no local tag)
```

No tag and no release object exists on either remote; this work created none.
