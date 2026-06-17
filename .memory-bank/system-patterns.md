# System Patterns — Chimera

## Dispatcher-First Architecture
All intelligence lives in the dispatcher. Workers and judges are "dumb" executors
following dispatcher-written instructions. The dispatcher reads the config (model
catalog with category weights) and designs the entire formation.

## Category-Weighted Domain Routing
Models have weighted scores per category (code, analysis, design, audit).
Like bandwidth provider weighting — this model in this category has this weight.
The dispatcher uses these to assign tasks.

## DAG Formations
Not just linear. Dispatcher can design fan-out → process → fan-in → judge,
multi-judge with merge, audit stages, whatever the task requires.

## Provider Gateway
Abstracts model providers behind a uniform interface. Supports OpenRouter,
direct provider APIs (z-ai, anthropic, deepseek, openai). LiteLLM for protocol
translation.

## Observability
Every stage logged: prompt, response, model, tokens, cost, latency.
Optional Langfuse integration for production tracing.
