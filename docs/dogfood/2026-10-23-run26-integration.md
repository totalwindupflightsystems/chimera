# Chimera-v2 dogfood run 26 — 2026-10-23 — the fix wave a user can actually get

**Surface:** not a new endpoint this time, but the one a real user experiences after every
fix wave: **which build am I running, and does the artifact I install carry the fixes?**
Three builds were graded side by side — the published PyPI wheel (0.2.7), the supervised
deployment on :8765 (635d282), and a checkout at HEAD (5455172) driven as a scratch
instance on :8866. Runs 1–25 covered CLI, REST, MCP, web UI, docker, custom formations,
custom DAG, idempotency, SSE, concurrency, custom providers, the PyPI wheel and the
task-router catalog source; the delivery chain between "merged" and "what a user gets" was
the untouched surface.

**Verdict: 🟡 PROMISING-BUT-ROUGH.** The code at HEAD is in good shape — every fix filed by
run 25 behaves as its commit claims when it is actually run (5/5 re-proofs). The delivery
chain is not: the wheel on PyPI is a month old and still leaks the operator config
(DF-CHIMERA-V2-97, P1), the deployed service predates every fix in the wave
(DF-CHIMERA-V2-98, P2), and the documented `[full]` extra produces a red suite on a fresh
box (DF-CHIMERA-V2-99, P3).

Everything below was executed for real on 2026-10-23. No repo visibility, permission or
credential was changed; no product code was modified.

---

## 1. What the chain promises

- `README.md:22` — `pip install chimera-deliberation[full]` is the user install, `pipx`
  the isolated variant; the release is what a user gets.
- `AGENTS.md` — "New code is NOT loaded until the unit restarts … a plain `git pull` leaves
  the running process on the OLD code"; `/health` exposes the running commit exactly so the
  gap is visible; `scripts/smoke_live.py` classifies it STALE / CODE-CURRENT / CURRENT /
  UNVERIFIABLE.
- The repo's own boundary rule: `chimera.yaml.fleet` is checkout-only and "is NOT shipped
  in the wheel" (`chimera.yaml.example` header, checked by
  `tests/test_yaml_example_sanitized.py`).

## 2. The three builds, measured

| build | identity | what a user gets |
|---|---|---|
| PyPI `chimera-deliberation==0.2.7` | uploaded 2026-09-21 | the fleet config; none of the 09-23…10-21 fixes |
| deployed `:8765` | `/health` commit **635d282**, unit started 2026-10-19 15:42 (-05) | pre-wave code (12 material paths behind) |
| checkout HEAD | **5455172** | all of DF-63/92/93/94/96; verified here |

```
$ curl -s localhost:8765/health
{"status":"alive","uptime_models":43,"commit":"635d282","version":"0.2.7"}
$ git rev-parse --short origin/main
5455172
$ python scripts/smoke_live.py     # exit 1
deployment: STALE — running commit 635d282 is behind expected commit origin/main and
12 material path(s) changed under src/, scripts/, tests/, pyproject.toml
```

That is **4 days of deployment drift and ~30 days of release drift**, and it is the
difference between the run-25 rows being "fixed" and a user receiving the fix.

## 3. Re-proof matrix — every run-25 fix, executed

All legs run against a scratch instance started from the working tree at 5455172
(`:8866`, `/health` commit 5455172), the pattern that proves a fix whose production
deployment is stale.

| row | fix | how it was executed | result |
|---|---|---|---|
| DF-93 P2 | per-(provider, model) pricing, `19a86df` | `load_config()` on the fleet config with `CHIMERA_TASK_ROUTER_MODELS_PATH` → `cost_provenance` | **FIXED** — `deepseek/deepseek-v4-flash` tier=`provider`, `source_provider=deepseek`, 0.15/0.60 per M; `deepseek-v4-pro` 0.66/1.98; no clinepass row reaches them |
| DF-93 (served) | same, end-to-end | real `POST /v1/deliberate` formation=simple | trace stages: `api_base=https://api.deepseek.com/v1`, `total_cost=0.007037` — pricing now matches the provider the call went to |
| DF-94 P3 | loud `TASK_ROUTER_HOME` warning, `e1b4bb8` | `TASK_ROUTER_HOME=/tmp/chv2-df26/reg-empty chimera models` | **FIXED** — `task_router_home_registry_missing` at warning level, naming `missing` AND `fallback` paths |
| DF-96 P2 | pre-commit slug false positive, `be4b2df` | regex probe: kebab slug vs a real key-shaped string | **FIXED** — slug no longer matches; a key-shaped string (boundary + 20-char body with digits/caps) still matches |
| DF-89 P1 | MCP `isError:true` on no usable answer, `409f5f3` | stdio client, keyless isolated HOME + scratch config | **FIXED** — `isError: True`, failure text retained |
| DF-92 P1 | packaging boundary test, `4f9b514` | `pytest tests/test_yaml_example_sanitized.py::test_built_artifacts_exclude_fleet_config` + a fresh clone's `chimera.yaml.example` | **FIXED at HEAD** (27 tests green); the *published* artifact still leaks — see §4.1 |

Regression files green at HEAD: `test_provider_scoped_pricing.py`,
`test_task_router_registry.py`, packaging boundary test — **27 passed in 7.35s**.

## 4. New findings

### 4.1 DF-CHIMERA-V2-97 (P1) — the published wheel still ships the operator config

```bash
pip download --no-deps chimera-deliberation==0.2.7 -d .
unzip -q chimera_deliberation-0.2.7-py3-none-any.whl -d unpacked
sha256sum unpacked/chimera/chimera.yaml.example   # b50ba51dc3438f49…d34f635
sha256sum ~/chimera-v2/chimera.yaml.fleet         # b50ba51dc3438f49…d34f635  (identical)
```

The user-visible consequence, not just the bytes:

```
$ pip install "chimera-deliberation[full]==0.2.7"     # fresh venv
$ chimera config init
Created chimera.yaml from …/site-packages/chimera/chimera.yaml.example
$ wc -c chimera.yaml            # 83677
$ grep -oE 'master001:[0-9]+' chimera.yaml | sort -u
master001:20128                 # internal topology, on 2 lines
$ grep -cE '^  [a-z0-9-]+/[A-Za-z0-9._:/-]+:$' chimera.yaml
42                              # operator catalog, vs 2 models in the public example
```

The fix is merged and tested; the artifact is not. The release gate must grade the BUILT
artifact before upload.

### 4.2 DF-CHIMERA-V2-98 (P2) — the deployment is stale, so none of the wave runs

See §2. `/health` cannot distinguish "board-only" from "12 material paths"; `smoke_live.py`
can, and says STALE. A read-only lane records the **explicit deferral**: no reload was
performed this tick.

### 4.3 DF-CHIMERA-V2-99 (P3) — `[full]` is half a test environment

Fresh box, documented install + documented test command:

```
pip install -e ".[full]" && python -m pytest tests/ -q -x
1 failed, 1057 passed, 65 skipped in 78.78s
FAILED tests/test_lsp_lint_plugins.py::test_pyflakes_reports_an_undefined_name
  ModuleNotFoundError: No module named 'pylsp'

pip install -e ".[dev]" && python -m pytest tests/ -q
2163 passed, 64 skipped in 147.38s
```

`pyproject.toml:364-374` (`[full]`) ships pytest/pytest-asyncio/pytest-cov/ruff but not
`python-lsp-server` or `pytest-timeout`; `:333-362` (`[dev]`) carries them. Fix either by
mirroring the test deps into `[full]` or by making the lsp tests `importorskip`.

## 5. Install leg — fresh machine, PROVEN this run

bunker-mvp agent **chv2-df26** (public-mirror clone; destroyed and verified gone).

| step | command | result |
|---|---|---|
| clone | `git clone --depth 50 https://github.com/totalwindupflightsystems/chimera.git` | **1.31 s**, HEAD **5455172** (== local HEAD) |
| env | `python3 -m venv .venv` | 3.6 s, Python 3.12.3 |
| install | `.venv/bin/pip install -e ".[full]"` | rc=0, `chimera 0.2.7` |
| config | `.venv/bin/chimera config init` | created from the clone's example |
| leak check | `grep -c 'master001\|8642\|20128' chimera.yaml.example` | **0** (fix holds on the public mirror) |
| serve | `chimera serve --port 8765` | `/health` → commit 5455172 |
| keyless contract | `POST /v1/deliberate` | **502** with `set DEEPSEEK_API_KEY` guidance (correct) |
| keyless CLI | `chimera "…"` | **rc=2**, no fake answer (DF-71 holds) |
| real answer | key staged by file copy, `POST /v1/deliberate` | **HTTP 200, 33.4 s**, answer `PONG`, `total_cost=0.006288` |
| MCP | stdio client: initialize → tools/list → `chimera_deliberate` | 3 tools, real answer in **53.4 s** |
| suite | `pytest tests/` under `[full]` then `[dev]` | 1 failed (pylsp) → **2163 passed** under `[dev]` |
| teardown | `bunker destroy` | destroy refused once (live serve pid), process killed, **destroyed**; exec against the id → `not_found` |

The key was staged as a 53-byte 0600 file copied with `bunker cp` (never printed, never
inlined in a command) and died with the agent.

## 6. Step 2b — what it costs

| operation | cold | warm | note |
|---|---|---|---|
| `POST /v1/deliberate` simple (HEAD :8866) | 21.3 s | 25.1 s / 46.5 s | provider-bound; spread is upstream queue, not Chimera |
| `GET /health` | — | **0.78 ms** | static |
| `chimera models` (registry source) | 1.06 s (run 25) | **614 ms ± 18 ms** (8 runs) | config load + registry + models.dev cache |
| fresh-box install (clone → serve) | ~60 s | — | see §5 |
| MCP `chimera_deliberate` (fresh box) | 53.4 s | — | model-bound |

**No PERF row.** Nothing Chimera owns is slow enough for a user to feel: HTTP overhead is
sub-millisecond, the CLI spends its time in catalog assembly (0.6 s, imperceptible), and
every multi-second number is model latency.

## 7. Repro commands (read-only)

```bash
# deployment parity
curl -s localhost:8765/health | jq -r .commit ; git -C ~/chimera-v2 rev-parse --short origin/main
cd ~/chimera-v2 && .venv/bin/python scripts/smoke_live.py ; echo rc=$?

# published-artifact leak (writes only under /tmp)
python3 -m venv /tmp/v && /tmp/v/bin/pip install -q "chimera-deliberation[full]==0.2.7"
cd /tmp && /tmp/v/bin/chimera config init && wc -c chimera.yaml && grep -c master001 chimera.yaml

# pricing provenance (HEAD)
CHIMERA_TASK_ROUTER_MODELS_PATH=~/task-router/data/tables/models.jsonl \
  .venv/bin/python -c 'from chimera.config import load_config; c=load_config("chimera.yaml"); print(c.cost_provenance["deepseek/deepseek-v4-flash"])'

# TASK_ROUTER_HOME warning (HEAD)
TASK_ROUTER_HOME=/tmp/empty-home .venv/bin/python -m chimera.cli.main models 2>&1 | grep task_router_home
```

## 8. What holds (credit)

- The fix wave itself is sound: 5/5 re-proofs pass on a scratch instance at HEAD, with
  provenance recorded (`tier="provider"`, `source_provider`, `source_model`) instead of a
  silently-rewritten price.
- `scripts/smoke_live.py` is the right instrument: it distinguished a working deliberation
  from a stale deployment in one command and refused to pass.
- The fresh-box install path is clean end to end — clone 1.3 s, config init from the
  clone's own example, real answer in 33 s, MCP interop in 53 s, and the public mirror's
  `chimera.yaml.example` carries zero internal-topology tokens.
- `[dev]` gives a genuinely green suite (2163 passed), including its own packaging
  boundary test.

## 9. Deploy parity statement

Classification: **STALE** (running 635d282 is an ancestor of HEAD 5455172, 12 material
paths changed). Per `AGENTS.md`, this tick records an **explicit deferral** — a read-only
dogfood lane does not restart the supervised service. The reload is filed as
DF-CHIMERA-V2-98 for the owning foreman/operator.
