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
  deepseek/deepseek-v4-pro:                        # provider/model-id
    categories:
      technology_code/code_generation/python: 95              # excellent at code
      technology_code/data_science/analysis: 85               # good at analysis
      creative_conversational/ux_writing/interface_copy: 40   # mediocre at design
      technology_code/testing_debugging/error_analysis: 60    # OK at audit
    cost_tier: budget

  anthropic/claude-sonnet-4.6:
    categories:
      technology_code/code_generation/python: 90
      technology_code/data_science/analysis: 92
      creative_conversational/ux_writing/interface_copy: 88
      technology_code/testing_debugging/error_analysis: 85
    cost_tier: premium

  google/gemini-3.5-flash:
    categories:
      technology_code/code_generation/python: 70
      technology_code/data_science/analysis: 75
      creative_conversational/ux_writing/interface_copy: 90   # great at design
      technology_code/testing_debugging/error_analysis: 50
    cost_tier: standard
```

**Model ids are `provider/model-id`** — one leading provider segment, then the id the
provider serves (`deepseek/deepseek-v4-flash`, `zai-coding-plan/glm-5.2`). OpenRouter-routed
models keep the vendor segment: `openrouter/anthropic/claude-fable-5`. An id is dispatchable
only when it has its own `models:` entry — a `providers.<name>` entry alone routes nothing,
and an id absent from the catalog is rejected with HTTP 400 `unknown model` before any
billed call.

**Category keys are the long-form hierarchical paths** from `selector.PATH_PATTERNS`
(`src/chimera/selector.py`), e.g. `technology_code/code_generation/python` — not the
short-form `code` / `analysis` / `design` / `audit` / `reasoning` aliases. Scores are
whole-number **percent, 0–100**: the shipped templates and the catalog served by
`GET /v1/models` all use percent, and a score on a parent path (e.g. `technology_code`)
covers every descendant through prefix fallback.

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
      // Request-level overrides (all optional, every id must be in the catalog):
      "allowed_models": ["deepseek/deepseek-v4-pro"],
      "disallowed_models": ["openrouter/x-ai/grok-4.5"],
      "dispatcher_model": "zai-coding-plan/glm-5.2",
      "aggregator_model": "deepseek/deepseek-v4-flash",
      "worker_model": "deepseek/deepseek-v4-pro"
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

The example below is a **loadable** minimal catalog: every id is
`provider/model-id`, every id referenced by `defaults:` / `formations:` has its
own `models:` entry, and every category key is a `selector.PATH_PATTERNS` path.
Check the ids a running service actually serves with `GET /v1/models`.

```yaml
# Provider gateway
providers:
  deepseek:
    base_url: https://api.deepseek.com/v1
  openrouter:
    base_url: https://openrouter.ai/api/v1
  zai:
    base_url: https://api.z.ai/api/coding/paas/v4
  anthropic:
    base_url: https://api.anthropic.com/v1
  google:
    base_url: https://generativelanguage.googleapis.com/v1beta

# Model catalog with weighted category offsets (percent scores, 0-100)
# Every id is `provider/model-id` and every id used anywhere in this file
# (defaults, formations) must have an entry here — an uncatalogued id is a 400.
models:
  zai-coding-plan/glm-5.2:
    categories:
      technology_code/system_design/architecture: 92
      technology_code/code_generation/python: 90
      complex_reasoning_agency/multi_step_planning/task_decomposition: 90
      general_knowledge/reasoning/explanation: 90
      technology_code/testing_debugging/error_analysis: 88
    cost_tier: premium
    provider: zai

  deepseek/deepseek-v4-pro:
    categories:
      technology_code/code_generation/python: 92
      technology_code/code_generation/javascript: 90
      technology_code/data_science/analysis: 85
      complex_reasoning_agency/multi_step_planning/task_decomposition: 75
      general_knowledge/reasoning/explanation: 80
    cost_tier: budget
    provider: deepseek

  deepseek/deepseek-v4-flash:
    categories:
      technology_code/code_generation/python: 88
      technology_code/testing_debugging/error_analysis: 70
      general_knowledge/reasoning/explanation: 75
    cost_tier: budget
    provider: deepseek

  google/gemini-3.5-flash:
    categories:
      technology_code/code_generation/python: 70
      technology_code/data_science/analysis: 75
      creative_conversational/ux_writing/interface_copy: 90
      technology_code/testing_debugging/error_analysis: 50
    cost_tier: standard
    provider: google

  anthropic/claude-sonnet-4.6:
    categories:
      technology_code/code_generation/python: 93
      technology_code/data_science/analysis: 92
      complex_reasoning_agency/multi_step_planning/task_decomposition: 90
    cost_tier: premium
    provider: anthropic

  anthropic/claude-haiku-4.5:
    categories:
      technology_code/testing_debugging/error_analysis: 82
      business_finance/legal_document/analysis: 78
    cost_tier: standard
    provider: anthropic

  openrouter/anthropic/claude-fable-5:
    categories:
      technology_code/code_generation/python: 97
      complex_reasoning_agency/multi_step_planning/task_decomposition: 98
      general_knowledge/reasoning/explanation: 97
      creative_conversational/creative_writing/storytelling: 92
    cost_tier: premium
    provider: openrouter

# Default assignments
defaults:
  dispatcher: zai-coding-plan/glm-5.2       # Strong reasoning for formation design
  default_worker: deepseek/deepseek-v4-pro
  default_aggregator: deepseek/deepseek-v4-flash

# Formation presets
formations:
  auto:                                     # Dispatcher decides everything
    mode: auto

  simple:                                   # 1 dispatcher → 2 workers → 1 aggregator
    workers: 2
    aggregator: default

  debate:                                   # 1 dispatcher → 2 workers → 2 aggregators → merge
    workers: 2
    aggregators:
      - default
      - anthropic/claude-sonnet-4.6
    merge: best_of_n

  audit:                                    # 1 dispatcher → 2 workers → 1 aggregator → 1 auditor
    workers: 2
    aggregator: default
    audit: anthropic/claude-haiku-4.5

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
  port: 8765
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
1. Analyze the task. What domains does it touch? Map them to category paths
   (e.g. technology_code/code_generation/python,
   complex_reasoning_agency/multi_step_planning/task_decomposition,
   creative_conversational/creative_writing/storytelling).
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
