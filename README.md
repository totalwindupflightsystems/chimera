# Chimera — Dynamic Multi-Model Deliberation Gateway

NOT a jury. A TEAM.

Chimera takes a user prompt, dispatches it to a custom formation of models
(each with tailored subtask prompts chosen by category-weighted domain routing),
and a judge merges their outputs using dispatcher-written instructions.

One model call (the Dispatcher) designs the entire deliberation at once.

## Architecture

```
User Prompt
    → Dispatcher (designs formation, writes all prompts, writes judge instructions)
        → Workers (parallel, each with custom prompt)
            → Judge (merges using dispatcher's instructions)
                → User
```

## Interfaces

- **REST API**: OpenAI-compatible `/v1/chat/completions` + `/v1/deliberate`
- **CLI**: `chimera "prompt"`, `chimera -f debate "prompt"`
- **MCP**: Hermes integration tools

## Quick Start

```bash
pip install chimera[full]
cp chimera.yaml.example chimera.yaml
# Edit chimera.yaml with your API keys
chimera "Compare Rust vs Go for a high-throughput message queue"
```

## Docs

- `specs/architecture.md` — Full architecture specification
- `.memory-bank/` — Design decisions and context
