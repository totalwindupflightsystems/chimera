"""FastAPI REST API.

Endpoints:
* ``POST /v1/deliberate``       — full pipeline, returns answer + trace.
* ``POST /v1/chat/completions`` — OpenAI-compatible drop-in.
* ``GET  /v1/formations``       — list formation presets.
* ``GET  /v1/models``           — list models with category weights.
* ``GET  /v1/health``           — health check.
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

from chimera.config import ChimeraConfig, load_config
from chimera.engine import Engine
from chimera.gateway import LiteLLMGateway
from chimera.observability import configure_logging


def create_app(
    config: ChimeraConfig | None = None,
    engine: Engine | None = None,
) -> FastAPI:
    """Build the FastAPI app.

    ``config`` / ``engine`` are injectable for tests. In production they are
    derived from ``chimera.yaml``.
    """
    cfg = config or load_config()
    configure_logging(cfg.observability)
    app = FastAPI(title="Chimera", version="0.1.0")
    app.state.config = cfg
    app.state.engine = engine or Engine(cfg, LiteLLMGateway(cfg))
    _register_routes(app)
    return app


# --------------------------------------------------------------------------- #
# Request / response models
# --------------------------------------------------------------------------- #


class DeliberateRequest(BaseModel):
    prompt: str
    formation: str = "auto"
    # Request-level overrides — maximum flexibility
    allowed_models: list[str] | None = None      # Only these models allowed
    disallowed_models: list[str] | None = None    # Exclude these models
    dispatcher_model: str | None = None           # Override dispatcher
    aggregator_model: str | None = None                # Override aggregator
    worker_model: str | None = None               # Override default worker
    output_schema: dict[str, Any] | None = None   # JSON Schema for final answer
    stage_models: dict[str, str] | None = None    # Per-stage model overrides (stage_id → model)
    # Client-defined DAG (Feature 1) — disabled unless allow_custom_dag=True
    dag: dict[str, Any] | None = None             # Full DAG definition from client
    allow_custom_dag: bool = False                # Must be True to accept client DAG


class DeliberateResponse(BaseModel):
    answer: str
    trace: dict[str, Any]
    request_id: str


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str = "auto"
    messages: list[ChatMessage]
    temperature: float | None = None
    response_format: dict[str, Any] | None = None  # OpenAI-compatible structured output
    # Request-level overrides (passed as extra fields)
    allowed_models: list[str] | None = None
    disallowed_models: list[str] | None = None
    dispatcher_model: str | None = None
    aggregator_model: str | None = None
    worker_model: str | None = None
    stage_models: dict[str, str] | None = None    # Per-stage model overrides (stage_id → model)
    # Client-defined DAG (Feature 1) — disabled unless allow_custom_dag=True
    dag: dict[str, Any] | None = None             # Full DAG definition from client
    allow_custom_dag: bool = False                # Must be True to accept client DAG


class ChatChoiceMessage(BaseModel):
    role: str = "assistant"
    content: str


class ChatChoice(BaseModel):
    index: int = 0
    message: ChatChoiceMessage
    finish_reason: str = "stop"


class ChatUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[ChatChoice]
    usage: ChatUsage


# --------------------------------------------------------------------------- #
# Route registration
# --------------------------------------------------------------------------- #


def _register_routes(app: FastAPI) -> None:
    @app.get("/v1/health")
    async def health() -> dict[str, Any]:
        return {"status": "ok"}

    @app.get("/v1/formations")
    async def formations(request: Request) -> dict[str, Any]:
        cfg: ChimeraConfig = request.app.state.config
        return {
            name: preset.model_dump(exclude_none=True)
            for name, preset in cfg.formations.items()
        }

    @app.get("/v1/models")
    async def models(request: Request) -> dict[str, Any]:
        cfg: ChimeraConfig = request.app.state.config
        return {
            name: {
                "categories": entry.categories,
                "cost_tier": entry.cost_tier,
                "provider": entry.provider,
            }
            for name, entry in cfg.models.items()
        }

    @app.post("/v1/deliberate", response_model=DeliberateResponse)
    async def deliberate(request: Request, body: DeliberateRequest) -> DeliberateResponse:
        engine: Engine = request.app.state.engine
        if body.dag is not None and not body.allow_custom_dag:
            raise HTTPException(
                status_code=400,
                detail="Custom DAG requires allow_custom_dag=true",
            )
        from chimera.config import DeliberationOverrides
        overrides = DeliberationOverrides(
            allowed_models=body.allowed_models,
            disallowed_models=body.disallowed_models,
            dispatcher_model=body.dispatcher_model,
            aggregator_model=body.aggregator_model,
            worker_model=body.worker_model,
            output_schema=body.output_schema,
            stage_models=body.stage_models,
        )
        try:
            result = await engine.deliberate(
                body.prompt, body.formation, overrides=overrides,
                dag=body.dag, allow_custom_dag=body.allow_custom_dag,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return DeliberateResponse(
            answer=result.answer,
            trace=result.trace.model_dump(mode="json"),
            request_id=result.trace.request_id,
        )

    @app.post("/v1/chat/completions", response_model=ChatCompletionResponse)
    async def chat_completions(
        request: Request, body: ChatCompletionRequest
    ) -> ChatCompletionResponse:
        engine: Engine = request.app.state.engine
        if body.dag is not None and not body.allow_custom_dag:
            raise HTTPException(
                status_code=400,
                detail="Custom DAG requires allow_custom_dag=true",
            )
        prompt = "\n".join(m.content for m in body.messages if m.role != "system")
        formation = body.model or "auto"
        from chimera.config import DeliberationOverrides
        overrides = DeliberationOverrides(
            allowed_models=body.allowed_models,
            disallowed_models=body.disallowed_models,
            dispatcher_model=body.dispatcher_model,
            aggregator_model=body.aggregator_model,
            worker_model=body.worker_model,
            stage_models=body.stage_models,
        )
        # Extract output schema from OpenAI-style response_format
        output_schema = None
        if body.response_format:
            rf = body.response_format
            if rf.get("type") == "json_schema":
                output_schema = rf.get("json_schema", {}).get("schema")
            elif rf.get("type") == "json_object":
                output_schema = {"type": "object"}  # generic object
        try:
            result = await engine.deliberate(
                prompt, formation, overrides=overrides, output_schema=output_schema,
                dag=body.dag, allow_custom_dag=body.allow_custom_dag,
            )
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=f"Unknown model/formation: {exc}")
        trace = result.trace
        completion_tokens = trace.total_tokens - trace.dispatch.tokens_input
        return ChatCompletionResponse(
            id=f"chatcmpl-{trace.request_id}",
            created=int(time.time()),
            model=formation,
            choices=[ChatChoice(message=ChatChoiceMessage(content=result.answer))],
            usage=ChatUsage(
                prompt_tokens=trace.dispatch.tokens_input,
                completion_tokens=max(completion_tokens, 0),
                total_tokens=trace.total_tokens,
            ),
        )


def run(host: str | None = None, port: int | None = None) -> None:
    """Run the API server with uvicorn (``chimera serve`` entrypoint)."""
    import uvicorn

    cfg = load_config()
    uvicorn.run(
        create_app(cfg),
        host=host or cfg.server.host,
        port=port or cfg.server.port,
    )


__all__ = ["create_app", "run"]
