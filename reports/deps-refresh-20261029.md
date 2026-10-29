# Dependency refresh 2026-10-29 — SUP-DEPS-20261029-CHV2

Worktree: `/home/kara/worktrees/chimera-v2-SUP-DEPS-20261029-CHV2`,
branch `wt/SUP-DEPS-20261029-CHV2`, base `bb23b99` (origin/main).

Census environment: uv-built worktree venv, **CPython 3.11.15** (same interpreter
line as the repo venv gate records), pip 26.2.2. Prior sweeps established the
census is only meaningful with its environment label; note that uv venvs carry no
setuptools, so setuptools never appears in these numbers.

## Before-census (first pass, 26 entries)

```
Package            Version     Latest     Type
------------------ ----------- ---------- -----
boto3              1.43.116    1.43.121   wheel
botocore           1.43.116    1.43.121   wheel
certifi            2026.10.19  2026.10.23 wheel
coverage           7.16.2      7.17.0     wheel
fastapi            0.156.5     0.162.0    wheel
hatchling          1.32.4      1.33.0     wheel
hf-xet             1.7.0       1.7.1      wheel
huggingface_hub    1.33.0      2.3.0      wheel
importlib_metadata 8.9.0       10.1.0     wheel
jiter              0.17.0      0.18.0     wheel
litellm            1.99.4      1.106.6    wheel
mcp                1.30.0      2.3.0      wheel
multidict          6.9.1       7.2.1      wheel
openai             2.54.0      3.41.0     wheel
platformdirs       4.13.5      4.14.0     wheel
pycodestyle        2.12.1      2.15.0     wheel
pycparser          3.11        3.12       wheel
pydantic-settings  2.16.1      2.16.2     wheel
pyflakes           3.2.0       4.1.0      wheel
pytest             9.1.1       9.2.0      wheel
pytest-asyncio     1.4.0       1.4.1      wheel
python-dateutil    2.9.0.post0 3.0.0      wheel
ruff               0.17.1      0.17.3     wheel
sse-starlette      3.5.0       3.6.0      wheel
starlette          1.9.0       1.10.0     wheel
zipp               4.1.1       4.1.2      wheel
```

Baseline suite BEFORE any change: `2174 passed, 64 skipped, 0 failed` (exit 0,
124.82s) — the post-upgrade numbers below must match it.

## Disposition — the seven board-named majors (all HOLD)

Every hold was re-verified this tick against **installed metadata**
(`importlib.metadata.requires()`), never from the pyproject comment alone. The
2026-10-21 notes listed only six cap-refusals; this tick's probe found one more:
litellm 1.99.4 also caps python-dateutil.

| Package | old -> new available | Disposition | Reason (verified source) |
|---|---|---|---|
| openai | 2.54.0 -> 3.41.0 | **HOLD** | litellm 1.99.4 requires `openai>=2.20.0,<3.0.0`; resolver-refused while litellm is capped <1.100 |
| mcp | 1.30.0 -> 2.3.0 | **HOLD** | this pyproject's own base+extras cap `mcp>=1.0.0,<2.0` (2.x removes pydantic-settings/MCP_* env vars and changes FastMCP handler signatures used by src/chimera/mcp/server.py) |
| huggingface_hub | 1.33.0 -> 2.3.0 | **HOLD** | policy-held major (CHANGED vs 10-21 notes): tokenizers 0.23.3 now allows `huggingface-hub>=0.16.4,<3.0`, so it RESOLVES freely — but nothing in chimera, litellm or tokenizers imports huggingface_hub at all (grep of src/, tests/, litellm package: zero importers), so the bump buys nothing testable; per doctrine, re-taking a major to buy nothing is not a fix |
| importlib_metadata | 8.9.0 -> 10.1.0 | **HOLD** | litellm 1.99.4 requires `importlib-metadata>=8.0.0,<9.0`; resolver-refused |
| pyflakes | 3.2.0 -> 4.1.0 | **HOLD** | python-lsp-server[pyflakes] (dev extra, load-bearing for the gitreins lsp guard lane) requires `pyflakes>=3.2.0,<3.3.0` |
| python-dateutil | 2.9.0.post0 -> 3.0.0 | **HOLD** | TWO parent caps (NEW finding vs 10-21 notes): litellm 1.99.4 requires `python-dateutil>=2.1,<3.0` AND botocore 1.43.116 requires `python-dateutil<3.0.0,>=2.1` — resolver-refused |
| litellm | 1.99.4 -> 1.106.6 | **HOLD** | this pyproject's own cap `litellm>=1.50.0,<1.100`: 1.100.0 replaced the stderr StreamHandler with LevelRoutingStreamHandler (sub-warning records to stdout) — fatal for the MCP stdio JSON-RPC wire |

An eighth major-shaped entry, pycodestyle 2.12.1 -> 2.15.0, is held by
python-lsp-server[pycodestyle] `pycodestyle>=2.12.0,<2.13.0` (it was part of the
8-entry hold set in every prior sweep; the board row's "seven majors" names the
ones above). multidict 6.9.1 -> 7.2.1 remains policy-held (aiohttp allows
`<8.0`, yarl uncapped, zero importers beyond aiohttp/yarl; C-extension paths
probe-tested green on 2026-10-13). Both appear in the full table below.

## Disposition — full 26-package table

| Package | old -> new | Disposition | Reason |
|---|---|---|---|
| boto3 | 1.43.116 -> 1.43.121 | UPGRADED | litellm allows `boto3>=1.43.1,<2.0`; pairs with botocore pin |
| botocore | 1.43.116 -> 1.43.121 | UPGRADED | boto3 1.43.121 pins `botocore>=1.43.121,<1.44.0`; pair moves together |
| certifi | 2026.10.19 -> 2026.10.23 | UPGRADED | requests/httpx/httpcore require it uncapped |
| coverage | 7.16.2 -> 7.17.0 | UPGRADED | pytest-cov requires `coverage[toml]>=7.10.6` uncapped; 7.17 dropped the tomli backport dep on py>=3.11 |
| fastapi | 0.156.5 -> 0.162.0 | UPGRADED | extras declare it with no upper bound; floor moved `>=0.156.5` -> `>=0.162.0` in server/web/dev/full extras AND in the pin test tests/test_dev_extra_deps.py `_SERVER_RUNTIME_SPECS` in the same commit |
| hatchling | 1.32.4 -> 1.33.0 | UPGRADED | dev/full extra floor `>=1.21`; in-bounds minor |
| hf-xet | 1.7.0 -> 1.7.1 | UPGRADED | huggingface_hub 1.33.0 allows `hf-xet>=1.6.0,<2.0` |
| huggingface_hub | 1.33.0 -> 2.3.0 | HOLD (policy) | see majors table |
| importlib_metadata | 8.9.0 -> 10.1.0 | HOLD (cap) | see majors table |
| jiter | 0.17.0 -> 0.18.0 | UPGRADED | openai 2.54.0 allows `jiter<1,>=0.10.0` |
| litellm | 1.99.4 -> 1.106.6 | HOLD (cap) | see majors table |
| mcp | 1.30.0 -> 2.3.0 | HOLD (cap) | see majors table |
| multidict | 6.9.1 -> 7.2.1 | HOLD (policy) | major with no importer in this tree beyond aiohttp/yarl; no concrete need |
| openai | 2.54.0 -> 3.41.0 | HOLD (cap) | see majors table |
| platformdirs | 4.13.5 -> 4.14.0 | UPGRADED | black requires `platformdirs>=2` uncapped |
| pycodestyle | 2.12.1 -> 2.15.0 | HOLD (cap) | pylsp[pycodestyle] requires `>=2.12.0,<2.13.0` |
| pycparser | 3.11 -> 3.12 | UPGRADED | cffi requires pycparser uncapped |
| pydantic-settings | 2.16.1 -> 2.16.2 | UPGRADED | litellm/mcp require `>=2.5.2` uncapped; patch bump |
| pyflakes | 3.2.0 -> 4.1.0 | HOLD (cap) | see majors table |
| pytest | 9.1.1 -> 9.2.0 | UPGRADED | dev floor `>=8.0`; pytest-cov/asyncio/timeout floors all satisfied |
| pytest-asyncio | 1.4.0 -> 1.4.1 | UPGRADED | requires `pytest<10,>=8.4`; patch bump |
| python-dateutil | 2.9.0.post0 -> 3.0.0 | HOLD (cap) | see majors table |
| ruff | 0.17.1 -> 0.17.3 | UPGRADED | dev floor `>=0.16.10`; patch bump |
| sse-starlette | 3.5.0 -> 3.6.0 | UPGRADED | requires `starlette>=0.49.1` uncapped |
| starlette | 1.9.0 -> 1.10.0 | UPGRADED | fastapi `>=0.46.0`, sse-starlette `>=0.49.1`, mcp `>=0.27` — no active upper cap |
| zipp | 4.1.1 -> 4.1.2 | UPGRADED | importlib_metadata requires `zipp>=3.20` uncapped |

Count: 17 UPGRADED + 9 HOLD = 26. The lock also DROPPED `tomli 2.4.1` — a
consequence of coverage 7.17.0 no longer needing the tomli backport on
Python >= 3.11, not an independent change.

## Live-proof note (:8765 deliberation API)

Per the row's live-proof clause: the supervised :8765 service runs from the MAIN
checkout and was NOT touched by this worktree work — no dependency in this tree's
runtime surface moved (litellm 1.99.4, openai 2.54.0, mcp 1.30.0, fastapi floor
moves land via uv.lock only after the foreman merges+deploys). Pre-state
witnessed during this tick: `GET localhost:8765/health` -> `{"status":"alive",
"uptime_models":43,"commit":"9bdb753","version":"0.2.8"}`. The foreman runs the
before/after live probes around the merge and deploy; the FastAPI bump here is
proven compatible by the full suite (2174 passed, includes the FastAPI
TestClient app tests).

## Gate results

| Gate | Result |
|---|---|
| `uv lock --check` | `Resolved 108 packages in 1ms`, exit 0 |
| `.venv/bin/python -m pip check` | `No broken requirements found.`, exit 0 |
| `.venv/bin/ruff check .` | `All checks passed!`, exit 0 |
| `.venv/bin/ruff format --check tests/test_dev_extra_deps.py` | `1 file already formatted`, exit 0 |
| pytest BEFORE | `2174 passed, 64 skipped, 0 failed` (124.82s, exit 0) |
| pytest AFTER | `2174 passed, 64 skipped, 0 failed` (115.92s, exit 0) — identical |

Method notes (inherited from prior sweeps, all followed):
- `uv lock --upgrade-package <name>` batched, NEVER `uv lock --upgrade`.
- All parent caps read from installed metadata this tick, not from comments.
- Final census run LAST (after the green suite); it is a moving target.

## Final census (after all upgrades; the last step)

```
Package            Version     Latest  Type
------------------ ----------- ------- -----
huggingface_hub    1.33.0      2.3.0   wheel
importlib_metadata 8.9.0       10.1.0  wheel
litellm            1.99.4      1.106.6 wheel
mcp                1.30.0      2.3.0   wheel
multidict          6.9.1       7.2.1   wheel
openai             2.54.0      3.41.0  wheel
pycodestyle        2.12.1      2.15.0  wheel
pyflakes           3.2.0       4.1.0   wheel
python-dateutil    2.9.0.post0 3.0.0   wheel
```

9 rows remain; every one is a major with a HOLD disposition and a verified
reason above. Zero in-bounds drift was left unrefreshed, and no new in-bounds
release appeared between the first and final census. The row's closing condition
— "a census whose remaining major rows are all HOLD entries with reasons" — is
met.
