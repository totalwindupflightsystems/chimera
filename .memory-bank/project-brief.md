# Project Brief — Chimera

> **Current as of 2026-10-19** · `chimera-deliberation` **0.2.7**
> This is the product intent; the *as-built* state lives in
> `active-context.md` and `system-patterns.md`.

## What

A dynamic multi-model deliberation gateway. One user prompt goes in; a custom
formation of models — each with a scoped subtask — deliberates; one merged answer
comes out, with a per-stage trace.

## Why

A fixed panel of models answering the same prompt wastes the strongest models on
the weakest subtasks. Chimera's dispatcher analyses the task, picks models by
category-weighted domain strength, writes a custom prompt for each worker, and
tells the aggregator how to merge. That makes specialised and budget models
useful: a model bad at code but good at design gets design-only work, budget
models take the simple pieces, premium models take the hard ones.

## Core principle

**One dispatcher call designs the entire deliberation in one shot.** It reads the
user prompt plus the model catalog, then emits the formation DAG, every worker's
scoped prompt, and the aggregator's merge instructions together.

## Success criteria — status at 0.2.7

| Criterion | Status |
|-----------|--------|
| OpenAI-compatible `POST /v1/chat/completions` (drop-in) | Shipped — stateless; the `model` field selects a formation |
| A deliberation completes and returns a correct merged output | Shipped — supervised service on `:8765`, dogfood runs under `docs/dogfood/` |
| Category-weighted routing picks the right model per subtask | Shipped — `selector.py`, 0–100 scores against category paths |
| Dispatcher-written merge instructions produce quality merges | Shipped — `aggregator.py` executes them for `aggregator` / `merge` / `audit` stage kinds |
| Traceability: every stage logged (prompt, response, tokens, cost, latency) | Shipped — trace on `/v1/deliberate`, `--verbose` on the CLI |
| Config-driven: add models in YAML with category weights | Shipped — `chimera.yaml` catalog; no ids hardcoded in code |
