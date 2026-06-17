# Chimera — Architecture Specification (v2)

> Based on Bane's voice memo, June 17 2026. This is the source of truth.

## Core Concept

Chimera is a multi-model deliberation gateway. Not a jury voting on the same prompt —
a dispatcher designs a custom formation, writes tailored prompts for every stage,
and a aggregator merges the results using dispatcher-written instructions.

**One model (the Dispatcher) designs the entire deliberation in one shot.**

## Architecture Flow

```
User Prompt
    │
    ▼
┌─────────────────────────────────────────────────┐
│ ① DISPATCHER (one model call)                    │
│                                                 │
│ Input: user prompt + config file                 │
│ Output:                                          │
│   • Formation DAG (which models, how many)       │
│   • Worker prompts (tailored per worker)          │
│   • Aggregator merge instructions                     │
│                                                 │
│ The dispatcher reads the config, understands     │
│ model strengths via weighted category offsets,   │
│ and designs the ENTIRE formation at once.        │
│ Worker prompts and aggregator instructions are        │
│ designed TOGETHER — the aggregator is told what each   │
│ worker was asked to do so it can merge correctly. │
└───────────────────┬─────────────────────────────┘
                    │
        ┌───────────┼───────────┐
        ▼           ▼           ▼
┌──────────┐ ┌──────────┐ ┌──────────┐
│ WORKER A │ │ WORKER B │ │ WORKER C │  ← 1 to N workers
│ model X  │ │ model Y  │ │ model X  │     (parallel)
│ prompt A │ │ prompt B │ │ prompt C │     each gets a CUSTOM prompt
└────┬─────┘ └────┬─────┘ └────┬─────┘     from the dispatcher
     │            │            │
     └────────────┼────────────┘
                  ▼
┌─────────────────────────────────────────────────┐
│ ② AGGREGATOR (one model call)                         │
│                                                 │
│ Input: worker outputs + merge instructions       │
│ Output: final merged answer for the user         │
│                                                 │
│ The dispatcher told the aggregator:                   │
│ "Worker A was asked to do X — here's their output│
│  Worker B was asked to do Y — here's their output│
│  Merge these together to produce Z for the user" │
└───────────────────┬─────────────────────────────┘
                    ▼
              Final Answer
```

## Key Design Principles

### 1. Dispatcher writes ALL prompts at once
The dispatcher doesn't just pick models — it writes every prompt in the formation:
- Each worker's prompt (tailored to that worker's subtask)
- The aggregator's merge instructions (explaining what each worker was asked to do)

This is what makes weak models work together: each one gets a task scoped to what it can do well.

### 2. Config: Weighted Category Offsets
```yaml
models:
  deepseek-chat:
    categories:
      code: 0.95          # excellent at code
      analysis: 0.85      # good at analysis
      design: 0.40        # mediocre at design
      audit: 0.60         # OK at audit
    cost_tier: budget

  claude-sonnet-4:
    categories:
      code: 0.90
      analysis: 0.92
      design: 0.88
      audit: 0.85
    cost_tier: premium

  gemini-2.5-flash:
    categories:
      code: 0.70
      analysis: 0.75
      design: 0.90        # great at design
      audit: 0.50
    cost_tier: budget
```

Think of it like bandwidth provider weighting — this model in this category has this relative weight. The dispatcher uses these scores to decide who gets what.

### 3. Dynamic DAG formations
Not just 1-X-1. The dispatcher can design:
```
1 → [A, B, C] → 1        (simple fan-out)
1 → [A, B] → D → [E, F] → 1    (multi-layer)
1 → [A, B, C] → [D, E] → 1     (fan-in to multiple aggregators, then merge)
```

The dispatcher decides the DAG structure at runtime based on the task.

### 4. Workers can be duplicated
Same model running multiple times with different prompts. Three instances of DeepSeek, each working on a different subtask of the same problem.

### 5. Direct pass-through for tool calls
If a coding agent is calling Chimera, the final merged output can include tool calls that get passed back to the agent. Extension feature, not v1.

## Interfaces

### REST API (OpenAI-compatible)
```
POST /v1/deliberate
  → Full pipeline: dispatcher → workers → aggregator
  → Request: {
      "prompt": "...",
      "formation": "auto|simple|debate",
      // Request-level overrides (all optional):
      "allowed_models": ["deepseek/deepseek-chat"],
      "disallowed_models": ["openrouter/anthropic/claude-sonnet-4"],
      "dispatcher_model": "zai-coding-plan/glm-5.2",
      "aggregator_model": "deepseek/deepseek-chat",
      "worker_model": "deepseek/deepseek-chat"
    }
  → Response: {"answer": "...", "trace": {...}, "request_id": "..."}

POST /v1/chat/completions   ← OpenAI-compatible endpoint
  → Same as deliberate but drop-in replacement for any OpenAI client
  → model field maps to formation preset or "auto"
  → Supports same override fields

GET /v1/formations
  → List available formation presets

GET /v1/models
  → List available models with category weights

GET /v1/health
  → Health check
```

### CLI
```
chimera "prompt"                          # Full pipeline with auto formation
chimera -f debate "prompt"                # Specific formation
chimera formations                        # List formations
chimera models                            # List models with weights
chimera --verbose "prompt"                # Full trace output
```

### MCP Server (Hermes integration)
```
chimera_deliberate(prompt, formation?)    # Full pipeline
chimera_formations()                      # List formations
chimera_models()                          # List models
```

## Config File (chimera.yaml)

```yaml
# Provider gateway
providers:
  openrouter:
    base_url: https://openrouter.ai/api/v1
  zai:
    base_url: https://api.z.ai/api/coding/paas/v4
  anthropic:
    base_url: https://api.anthropic.com/v1

# Model catalog with weighted category offsets
models:
  zai-coding-plan/glm-5.2:
    categories:
      code: 0.92
      analysis: 0.90
      design: 0.85
      audit: 0.88
      reasoning: 0.95
    cost_tier: premium
    provider: zai

  deepseek/deepseek-chat:
    categories:
      code: 0.95
      analysis: 0.85
      design: 0.40
      audit: 0.60
      reasoning: 0.80
    cost_tier: budget
    provider: openrouter

  openrouter/google/gemini-2.5-flash:
    categories:
      code: 0.70
      analysis: 0.75
      design: 0.90
      audit: 0.50
      reasoning: 0.65
    cost_tier: budget
    provider: openrouter

  openrouter/anthropic/claude-sonnet-4:
    categories:
      code: 0.90
      analysis: 0.92
      design: 0.88
      audit: 0.85
      reasoning: 0.93
    cost_tier: premium
    provider: openrouter

# Default assignments
defaults:
  dispatcher: zai-coding-plan/glm-5.2   # Strong reasoning for formation design
  default_worker: deepseek/deepseek-chat
  default_aggregator: zai-coding-plan/glm-5.2

# Formation presets
formations:
  auto:                                  # Dispatcher decides everything
    mode: auto

  simple:                                # 1 dispatcher → 2 workers → 1 aggregator
    workers: 2
    aggregator: default

  debate:                                # 1 dispatcher → 3 workers → 2 aggregators → merge
    workers: 3
    aggregators:
      - default
      - openrouter/anthropic/claude-sonnet-4
    merge: best_of_n

  audit:                                 # 1 dispatcher → 2 workers → 1 aggregator → 1 auditor
    workers: 2
    aggregator: default
    audit: openrouter/anthropic/claude-haiku-4.5

# Observability
observability:
  log_level: info
  trace_enabled: true
  langfuse:
    enabled: false
    host: https://cloud.langfuse.com

# Server
server:
  host: 0.0.0.0
  port: 8000
```

## Data Models

```python
class DispatchResult:
    """What the dispatcher produces in one call."""
    formation: FormationDAG
    worker_prompts: list[WorkerPrompt]     # One per worker
    aggregator_instructions: str               # Merge instructions for aggregator

class FormationDAG:
    """The dispatcher-designed execution graph."""
    stages: list[Stage]
    edges: list[tuple[str, str]]          # stage_id → stage_id

class Stage:
    id: str                               # "worker_1", "aggregator", "audit"
    kind: str                             # "worker" | "aggregator" | "audit"
    model: str                            # Which model to use
    depends_on: list[str]                 # Stage IDs this waits for

class WorkerPrompt:
    stage_id: str
    model: str
    prompt: str                           # Custom prompt from dispatcher
    expected_output_schema: Optional[dict] # JSON schema for structured output

class DeliberationTrace:
    request_id: str
    dispatch: StageSpan
    workers: list[StageSpan]
    aggregator: StageSpan
    total_duration_ms: int
    total_cost: float
    total_tokens: int

class StageSpan:
    stage_id: str
    model: str
    prompt: str                           # What was sent
    response: str                         # What came back
    tokens_input: int
    tokens_output: int
    latency_ms: int
    cost: float
```

## Dispatcher Prompt Template

The dispatcher is an LLM call with a structured output schema. It receives:

```
You are the Chimera dispatcher. Your job: design a multi-model deliberation
to solve the user's task.

## Available Models
[model catalog with category weights from config]

## User's Request
{user_prompt}

## Instructions
1. Analyze the task. What domains does it touch? (code, analysis, design, audit...)
2. Pick the best models for each subtask using category weights.
3. Design a formation DAG. You can use:
   - Multiple workers in parallel
   - Multiple aggregators with merge
   - Audit stages
   - Fan-out → intermediate processing → fan-in
4. Write a CUSTOM prompt for each worker. Scope their task to what they're good at.
   Don't give all workers the same prompt unless the task requires consensus.
5. Write merge instructions for the aggregator. Tell the aggregator:
   - What each worker was asked to do
   - How to combine their outputs
   - What the final answer should look like

Output a JSON object matching the DispatchResult schema.
```

## Why This Architecture

- **Weak models become useful**: A model bad at code but good at design gets a design-only subtask
- **Cost-efficient**: Use budget models for simple subtasks, premium only for complex pieces
- **Extensible**: New models added to config with category weights, dispatcher learns to use them
- **Traceable**: Every stage logged with prompt, response, tokens, cost
- **Gateway-ready**: OpenAI-compatible endpoint means any tool can use it as a drop-in replacement
