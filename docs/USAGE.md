# Chimera Usage Guide

## Command-Line

```bash
# Quick deliberation
chimera run "Explain the CAP theorem"

# With a specific formation (flags go BEFORE the subcommand)
chimera --formation debate run "Compare Kubernetes vs Nomad"

# Custom DAG as an inline JSON string (requires --allow-custom-dag)
chimera --dag '{"stages":[{"id":"researcher","kind":"worker","model":"deepseek/deepseek-v4-flash"},{"id":"finalizer","kind":"aggregator","model":"deepseek/deepseek-v4-pro","depends_on":["researcher"]}],"edges":[["researcher","finalizer"]]}' \
  --allow-custom-dag run "Audit this architecture decision"

# Restrict models to budget tier (per-stage overrides)
chimera --stage-models '{"worker_1":"deepseek/deepseek-v4-flash","aggregator":"deepseek/deepseek-v4-flash"}' \
  run "Write a Python decorator tutorial"

# Override specific stages
chimera --stage-models '{"worker_1":"zai-coding-plan/glm-5.2","aggregator":"deepseek/deepseek-v4-pro"}' \
  run "..."

# Print the full deliberation trace
chimera --verbose run "..."

# Machine-readable output (flags go BEFORE the subcommand)
chimera --quiet run "..."            # stdout = the raw answer + one newline
chimera --json run "..."             # stdout = one JSON object (answer + trace)

# List available models
chimera models

# List formation presets
chimera formations

# Start API server
chimera serve --port 8080

# With custom config path
chimera --config /path/to/chimera.yaml run "..."
```

### Quiet and JSON output

`--quiet` and `--json` are mutually exclusive group flags, so they are
written before the subcommand. Both work with the implicit-prompt form
(`chimera "..."`, same as `chimera run "..."`):

```bash
# stdout is EXACTLY the answer plus one trailing newline — no panel, no
# ANSI, no trace, no warning text. Everything diagnostic goes to stderr.
chimera --quiet "Summarize this changelog"
chimera --quiet run "Summarize this changelog"

# Capture it
ANSWER=$(chimera --quiet "Name one HTTP status code for 'not found'")

# stdout is EXACTLY one JSON object: {"answer": ..., "trace": {...}}
chimera --json "Compare React and Vue" > out.json
jq -r .answer out.json
jq .trace.total_tokens out.json

# Explicit run form is identical
chimera --json run "Compare React and Vue"
```

The `trace` value is the complete trace serialization
(`DeliberationTrace.model_dump(mode="json")`) — every field the REST API
returns, including `dispatch`, `stages`, `worker_failures`, `dispatch_note`,
token and cost totals. Unicode is preserved (`ensure_ascii=False`), so
`café` is written as `café`, never `caf\u00e9`.

Streams and exit codes:

| Situation | stdout | stderr | exit |
|---|---|---|---|
| `--quiet`, healthy run | the answer + `\n` | logs only | 0 |
| `--quiet`, dropped worker or degraded dispatch | the answer + `\n` | `warning: ...` lines | 0 |
| `--json`, healthy run | one JSON object + `\n` | logs only | 0 |
| `--json`, dropped worker or degraded dispatch | one JSON object + `\n` | `warning: ...` lines | 0 |
| `--quiet --json` together | (empty) | `Error: --quiet and --json are mutually exclusive` | 2 |
| missing `chimera.yaml` | `error: ...` one-liner | logs only | 2 |

Notes:

- Operational truth is never hidden: the dropped-worker and
  dispatch-degradation/repair warnings that human mode prints beside the
  panel are written to **stderr** in the machine modes (the JSON's
  `trace.worker_failures` / `trace.dispatch_note` carry the same facts
  machine-readably).
- `--verbose` is ignored under `--quiet` / `--json` — the trace is already in
  the JSON, and `--quiet` stays a single line.
- The flags govern DELIBERATION output (the `run` path). `chimera models` and
  `chimera formations` keep their human tables unchanged — for a
  machine-readable catalog use the REST API (`GET /v1/models`,
  `GET /v1/formations`) or the MCP tools.
- Default (no flag) and `--verbose` human output are unchanged: boxed answer
  panel on stdout, warnings beside it, optional trace table.

## REST API

```mermaid
flowchart LR
    subgraph "Any OpenAI SDK"
        SDK[openai Python SDK]
        SDK2[openai Node SDK]
        SDK3[curl / HTTP]
    end

    SDK --> API
    SDK2 --> API
    SDK3 --> API

    subgraph Chimera
        API["POST /v1/chat/completions"]
        API2["POST /v1/deliberate"]
        API3["GET /v1/models"]
        API4["GET /v1/formations"]
    end

    API --> Engine
    API2 --> Engine
    Engine --> D[Dispatcher]
    Engine --> W[Workers]
    Engine --> A[Aggregator]
```

## Python SDK Example

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8765/v1", api_key="local")

# Simple
r = client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "Explain monads in Haskell"}]
)
print(r.choices[0].message.content)

# With Chimera features
r = client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "Review this SQL schema for performance"}],
    extra_body={
        "allowed_models": ["deepseek/deepseek-v4-pro", "z-ai/glm-5.2"],
        "stage_models": {"aggregator": "openrouter/anthropic/claude-sonnet-4"},
    }
)
```

## MCP (Hermes Integration)

Chimera exposes three MCP tools for AI agents:

```
chimera_deliberate(prompt, formation?) → answer + trace
chimera_formations()                    → available presets
chimera_models()                        → model catalog
```

Register with Hermes:

```yaml
# ~/.hermes/config.yaml
mcp_servers:
  chimera:
    command: chimera-mcp
    args: [/path/to/chimera.yaml]
```

Then from Hermes chat:

```
> Use chimera to compare React and Svelte for our dashboard
```

## Common Patterns

### Budget-First (default)

Best for: most queries, keeping costs low

```yaml
defaults:
  dispatcher: deepseek/deepseek-v4-flash
  default_worker: deepseek/deepseek-v4-pro
  default_aggregator: deepseek/deepseek-v4-flash
  lock_aggregator: true
```

### Premium Analysis

Best for: critical decisions, complex analysis, code review

```json
{
  "model": "auto",
  "dispatcher_model": "z-ai/glm-5.2",
  "allowed_models": [
    "openrouter/anthropic/claude-sonnet-4",
    "z-ai/glm-5.2",
    "deepseek/deepseek-v4-pro"
  ],
  "stage_models": {
    "aggregator": "openrouter/anthropic/claude-sonnet-4"
  }
}
```

### Code Review Pipeline

DAG: coder → reviewer → security-auditor → merge

```yaml
code-review:
  dag:
    stages:
      - {id: coder, kind: worker, model: deepseek/deepseek-v4-pro}
      - {id: reviewer, kind: aggregator, model: z-ai/glm-5.2, depends_on: [coder]}
      - {id: security, kind: audit, model: openrouter/anthropic/claude-haiku-4.5, depends_on: [reviewer]}
    edges:
      - [coder, reviewer]
      - [reviewer, security]
```

### Research Deep-Dive

3 experts → 2 debaters → judge

```yaml
deep-research:
  dag:
    stages:
      - {id: domain_expert, kind: worker, model: deepseek/deepseek-v4-pro}
      - {id: skeptic, kind: worker, model: openrouter/anthropic/claude-sonnet-4}
      - {id: synthesizer, kind: worker, model: z-ai/glm-5.2}
      - {id: debate_1, kind: aggregator, model: openrouter/anthropic/claude-sonnet-4, depends_on: [domain_expert, skeptic]}
      - {id: debate_2, kind: aggregator, model: z-ai/glm-5.2, depends_on: [domain_expert, synthesizer]}
      - {id: judge, kind: merge, model: openrouter/anthropic/claude-sonnet-4, depends_on: [debate_1, debate_2]}
    edges:
      - [domain_expert, debate_1]
      - [skeptic, debate_1]
      - [domain_expert, debate_2]
      - [synthesizer, debate_2]
      - [debate_1, judge]
      - [debate_2, judge]
```

## Observability

### Debug Logs

```yaml
observability:
  log_level: debug
  use_stdout: true
```

With debug logging, Chimera outputs:
- Full dispatcher prompt and response
- Each worker's custom prompt
- Aggregator merge instructions
- Per-stage token counts and latency
- Response format retry attempts

### Langfuse Tracing

```yaml
observability:
  langfuse:
    enabled: true
    public_key: pk-...
    secret_key: sk-...
```

All deliberations appear as traces with nested generations per stage.

### Self-Serve Trace

Every API response includes a trace object with:
- `request_id` — unique deliberation ID
- `source` — "auto", "preset", "custom", or "fallback"
- `dispatch` — dispatcher model call details
- `workers[]` — per-worker prompts, responses, tokens, latency, cost
- `aggregator` — merge stage details
- `total_tokens`, `total_cost`, `total_duration_ms`

## Tips

1. **Start budget, escalate when needed** — default to DeepSeek, override for critical work
2. **Lock the aggregator** — prevents the dispatcher from burning budget on premium merge models
3. **Use `allowed_models` to constrain costs** — `["deepseek/deepseek-v4-pro", "deepseek/deepseek-v4-flash"]`
4. **Debug with `log_level: debug`** — see exactly what prompts each model gets
5. **Define custom formations in config** — reusable, version-controlled DAGs
6. **Always check `source` in trace** — "fallback" means the dispatcher failed and you got a basic template
