# Project Brief — Chimera

## What
A dynamic multi-model deliberation gateway. Takes a user prompt, designs a custom
formation of models to solve it, and returns a merged answer.

## Why
OpenRouter Fusion runs a fixed panel of models with the same prompt. Chimera's
dispatcher analyzes the task, picks the best models by category-weighted domain
strength, writes custom prompts for each worker, and tells the judge how to merge.

This makes weak models useful: a model bad at code but good at design gets
design-only subtasks. Budget models handle simple pieces, premium models do
complex work.

## Core Principle
**One model (Dispatcher) designs the entire deliberation in one shot.**
It reads the user prompt + model catalog → designs formation DAG → writes all
worker prompts + judge instructions simultaneously.

## Success Criteria
- OpenAI-compatible `/v1/chat/completions` endpoint (drop-in replacement)
- Full deliberation completes with correct merged output
- Category-weighted domain routing works (right model for right subtask)
- Dispatcher-written judge instructions produce quality merges
- Traceability: every stage logged (prompt, response, tokens, cost)
- Config-driven: add models via YAML with category weights
