# Python dependency review — 2026-10-13

Scope: the 10 packages reported by `pip list --outdated` in the project Python 3.11 environment. Directness and constraints were checked against `pyproject.toml`, `uv.lock`, and the lock resolver. Only the compatible boto3/botocore patch pair was upgraded; no source files or workflow files were changed.

| Package | Installed → candidate | Direct / transitive | Current constraint and candidate allowance | Decision and reason |
|---|---|---|---|---|
| boto3 | 1.43.112 → 1.43.113 | Transitive, required by litellm | No project-level pin; boto3's botocore range accepts 1.43.113, confirmed by successful lock resolution. | UPGRADE — patch release; upgraded as a pair with botocore. |
| botocore | 1.43.112 → 1.43.113 | Transitive, required by boto3 (also s3transfer) | No project-level pin; boto3's current compatibility range accepts 1.43.113. | UPGRADE — patch release; kept boto3/botocore aligned. |
| huggingface_hub | 1.33.0 → 2.2.0 | Transitive, required by tokenizers | No direct project pin; tokenizers 0.23.3 permits `huggingface-hub>=0.16.4,<3.0`, so the candidate resolves. | HOLD — policy hold on an unneeded major: no code in Chimera, litellm, or tokenizers imports this package; no functional benefit justifies the major migration. |
| importlib_metadata | 8.9.0 → 9.0.1 | Transitive, required by litellm and docstring-to-markdown | litellm 1.99.4 requires `importlib-metadata>=8,<9.0`; candidate is disallowed. | DEFER — resolver constraint from the current litellm version. |
| litellm | 1.99.4 → 1.105.0 | Direct runtime dependency | `pyproject.toml`: `litellm>=1.50.0,<1.100`; candidate is disallowed. | DEFER — intentional `<1.100` cap prevents stdout logging from corrupting MCP stdio JSON-RPC; guards in `chimera.gateway` are documented alongside the cap. |
| mcp | 1.30.0 → 2.3.0 | Direct runtime dependency and repeated in mcp/full extras | `pyproject.toml`: `mcp>=1.0.0,<2.0`; candidate is disallowed. | HOLD — preserve the documented CH-GAP-005 `<2.0` hold; MCP 2.x removes MCP_* environment settings and changes handler signatures used by `src/chimera/mcp/server.py`. |
| multidict | 6.9.1 → 7.1.0 | Transitive, required by aiohttp and yarl | No project-level pin; aiohttp 3.14.5 allows `multidict>=4.5,<8.0`, and yarl adds no cap, so the candidate resolves. | HOLD — compatible by dependency constraints but a major API/extension upgrade without a direct importer or demonstrated need; defer to a targeted major-upgrade review. |
| openai | 2.54.0 → 3.29.0 | Transitive through litellm; also imported directly by `src/chimera/gateway.py` but not directly declared in project metadata | litellm 1.99.4 requires `openai>=2.20,<3.0`; candidate is disallowed. | DEFER — resolver constraint from litellm; OpenAI 3.x also changes its default HTTP client to httpx2. |
| pycodestyle | 2.12.1 → 2.15.0 | Transitive dev dependency, enabled by `python-lsp-server[pycodestyle]` | The current pylsp pycodestyle extra caps the plugin dependency below 2.13; candidate is disallowed. | DEFER — resolver constraint from the configured pylsp lint extra. |
| pyflakes | 3.2.0 → 4.0.3 | Transitive dev dependency, enabled by `python-lsp-server[pyflakes]` | The current pylsp pyflakes extra requires `pyflakes>=3.2,<3.3`; candidate is disallowed. | DEFER — resolver constraint from the configured pylsp lint extra. |

## Applied safe batch

Updated only `uv.lock`: boto3 1.43.112 → 1.43.113 and botocore 1.43.112 → 1.43.113. No `pyproject.toml` constraint changes were needed. The `mcp>=1.0.0,<2.0` cap remains unchanged.

## Verification

The worktree initially had no `.venv`; tests were run from the repository's Python 3.11.15 venv with the current directory set to this worktree, per task instructions. Installed boto3 and botocore there at the exact locked versions.

- `uv lock --check` — passed.
- `uv pip check --python /home/kara/chimera-v2/.venv/bin/python` — passed; all installed packages compatible.
- `python -m pytest -x --tb=short -q` (Python 3.11.15; worktree as cwd) — 2,082 passed, 64 skipped, 3 warnings; exit 0, 129.41 seconds.
- The skipped tests were reported by pytest as skips; no test failure was observed.
