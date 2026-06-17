# Tech Context — Chimera

## Language
Python 3.11+ with full type hints. Pydantic v2 for all data models.

## Key Dependencies
- **LiteLLM** — provider gateway (OpenRouter, direct APIs)
- **FastAPI** — REST API server
- **Click + Rich** — CLI
- **MCP SDK** — Hermes integration
- **Pydantic v2** — data validation
- **structlog** — structured JSON logging
- **httpx** — async HTTP client
- **pytest + pytest-asyncio** — testing

## Packaging
pipx with extras: `chimera[cli]`, `chimera[server]`, `chimera[mcp]`, `chimera[full]`

## Testing
`python -m pytest tests/ -x -q` — must pass before any commit.

## Config
Single `chimera.yaml` — model catalog, provider settings, formation presets,
observability config. API keys via env vars or config file (config file is
in .gitignore).

## Logging
structlog → stderr (JSON). trace_enabled logs full prompts/responses.
Langfuse optional for production.
