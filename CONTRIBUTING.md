# Contributing to Chimera

Welcome! Chimera is a dynamic multi-model deliberation gateway — one dispatcher
designs a custom DAG, workers execute, an aggregator merges.

## Quick Setup

```bash
git clone https://github.com/totalwindupflightsystems/chimera.git
cd chimera
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[full]"
```

## Running Tests

```bash
# Unit tests (fast, offline — 322 tests, no API keys needed)
pytest tests/ --ignore=tests/integration --ignore=tests/compat -W error

# Integration tests (real API calls — needs --run-integration flag + API key)
# Set DEEPSEEK_API_KEY in your environment first, then:
pytest tests/integration/ --run-integration -v

# Compatibility smoke tests (needs --run-compat flag)
pytest tests/compat/ --run-compat -v

# Coverage
pytest tests/ --ignore=tests/integration --cov=src/chimera --cov-report=html
```

**Required environment variables for integration tests:**

| Variable | Provider | Required |
|---|---|---|
| `DEEPSEEK_API_KEY` | DeepSeek | Yes |
| `OPENROUTER_API_KEY` | OpenRouter | For multi-provider tests |

CI runs unit tests on every push/PR (Python 3.11/3.12/3.13 matrix).
Integration tests run on push to `main` using a dedicated CI API key.

## Configuration

```bash
cp chimera.yaml.example chimera.yaml
# Edit chimera.yaml with your API keys
```

Chimera needs API keys for at least one provider (DeepSeek, OpenRouter, etc.).
Keys are read from environment variables or the `api_keys` section of
`chimera.yaml`. See `docs/CONFIG.md` for full configuration reference.

## Project Structure

```
src/chimera/
├── dispatcher.py     # Designs DAGs, writes worker prompts
├── engine.py         # Executes stages in dependency waves
├── aggregator.py     # Merges worker outputs
├── gateway.py        # LiteLLM provider abstraction
├── config.py         # Pydantic v2 config models
├── api/server.py     # FastAPI REST API + OpenAI-compatible
├── cli/main.py       # Click + Rich CLI
├── mcp/server.py     # MCP tools for agents
└── web/              # Session-backed web UI + SSE
```

## Code Style

- Python 3.11+ with full type hints
- Pydantic v2 for all data models
- `structlog` for structured logging
- `ruff` for linting: `ruff check src/`
- Pre-commit hook enforces: secrets scan, lint, tests

## Pull Requests

1. Fork and branch from `main`
2. Write tests for your changes
3. Run `pytest tests/ -q` — must pass
4. Run `ruff check src/` — must pass
5. Open a PR with a clear description
6. CI runs Python 3.11/3.12/3.13 matrix automatically

## Commit Convention

```
category: brief description

Optional body with details.
```

Categories: `feat`, `fix`, `test`, `docs`, `ci`, `refactor`, `chore`

Examples:
- `feat: add debate formation preset`
- `fix: aggregator degrades on deepseek json_object`
- `test: multi-turn context pipe integration tests`
