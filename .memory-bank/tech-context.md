# Tech Context — Chimera

> **Current as of 2026-10-19** · `chimera-deliberation` **0.2.7**
> Versions below are the declared ranges in `pyproject.toml`; the locked set is
> `uv.lock`.

## Language

Python **3.11+** with full type hints and Pydantic v2 models. CI runs the suite on
3.11, 3.12 and 3.13.

## Key dependencies

| Dependency | Role | Range |
|------------|------|-------|
| `litellm` | provider gateway / protocol translation | `>=1.50.0,<1.100` |
| `pydantic` v2 | all data models and config validation | `>=2.0` |
| `fastapi` + `uvicorn` | REST API and web UI (`server`, `web`, `dev` extras) | `>=0.115`, `>=0.30` |
| `click` + `rich` | CLI (in the BASE install, so a bare wheel's `--help` works) | `>=8.0`, `>=13.0` |
| `mcp` | MCP stdio server for agent integration | `>=1.0.0,<2.0` |
| `structlog` | structured JSON logging | `>=24.0` |
| `httpx`, `httpx2` | async HTTP client | `>=0.27`, `>=2.0` |
| `jsonschema` | validates answers against a caller `output_schema` | `>=4.0` |
| `pyyaml` | config loading | `>=6.0` |
| `pytest`, `pytest-asyncio`, `pytest-cov`, `pytest-timeout` | tests (`dev` extra) | see pyproject |

Two upper bounds are load-bearing, not cosmetic — do not "upgrade past" them
without re-reading the comments in `pyproject.toml`:

- **`litellm <1.100`** — 1.100.0 routes every sub-WARNING record to stdout,
  which corrupts the MCP stdio JSON-RPC wire. The cap is not sufficient alone:
  `chimera.gateway.ensure_litellm_quiet()` also sets `suppress_debug_info` /
  `set_verbose(False)` before **every** completion, because in-range releases
  still bare-`print()` a provider banner and a feedback block.
- **`mcp <2.0`** — 2.x removes the pydantic-settings / `MCP_*` env surface and
  changes the FastMCP handler signatures `src/chimera/mcp/server.py` relies on.

## Packaging

Hatchling build, MIT, published to PyPI as **`chimera-deliberation`**.
Extras: `server`, `cli`, `mcp`, `web`, `full`, `dev`. Console scripts:
`chimera`, `chimera-mcp`. The wheel force-includes `chimera.yaml.example` and
`chimera.yaml.docker` (so a release build needs them in the checkout) and
deliberately does **not** include `chimera.yaml.fleet`.

## Layout

```
src/chimera/
  engine.py        — DAG execution, stage timeouts, degraded stages
  dispatcher.py    — prompt → formation design (auto + presets)
  selector.py      — category-weighted, price-aware model selection
  gateway.py       — provider calls via LiteLLM + generic OpenAI-compatible
  aggregator.py    — merge strategies (fuse, best_of_n, …)
  config.py        — Pydantic config tree, DeliberationOverrides, env/.env refs
  circuit_breaker.py, blocked_models.py, provider_discovery.py,
  task_router_registry.py, observability.py, exceptions.py
  api/             — FastAPI app, rate limit, auth dependencies
  web/             — session store, SSE broker, trace visualisation, SPA routes
  cli/             — click CLI
  mcp/             — FastMCP stdio server
tests/             — flat test_*.py + integration/ + compat/
```

## Testing

```bash
.venv/bin/python -m pytest -x -q                     # full suite
.venv/bin/python -m pytest tests/test_engine.py -x   # one file
.venv/bin/python -m pytest --cov=src/chimera --cov-report=term-missing
```

Quality gate is GitReins (`gitreins guard`), with the repo venv first on PATH so
the `lsp` lane finds `pylsp` instead of skipping. `test_mode: diff` grades the
**staged** diff, so stage before guarding.

## Config

Single `chimera.yaml`: model catalog with category maps, providers with
`base_url` + credential env refs, formations, selector, timeouts, auth,
rate-limit, circuit-breaker and observability sections. `${ENV_VAR}` references
resolve from the environment or a `.env` beside the config. The live file is
gitignored; `chimera.yaml.example` is the minimal shipped starter and
`chimera.yaml.fleet` the full operator reference.

## Logging

structlog JSON. The CLI writes to stdout; the MCP transport forces every sink to
stderr (`configure_logging(force_stderr=True)`) so stdout stays a clean JSON-RPC
wire. `trace_enabled` logs full prompts/responses; Langfuse tracing is optional
and only activates when configured and importable.
