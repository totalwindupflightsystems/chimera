# Product Context — Chimera

## User Experience
1. User sends a prompt: "Design a scalable microservice architecture for an e-commerce platform"
2. Chimera's dispatcher analyzes it — touches design, backend, analysis domains
3. Dispatcher picks Gemini (strong at design) for architecture design, DeepSeek (strong at code) for service boundaries, Claude (strong at analysis) for trade-off analysis
4. Each gets a custom prompt scoped to their subtask
5. Judge merges: "Here's the architecture, here are the service boundaries, here are the trade-offs"

## Stakeholders
- **Bane (totalwindupflightsystems)** — primary user, drives design
- **Hermes Agent** — dispatches Chimera stages via MCP
- **Any AI coding agent** — drop-in OpenAI-compatible endpoint

## Non-Goals (v1)
- Streaming responses
- Tool/function calling passthrough
- Response caching
- Multi-turn conversation state
