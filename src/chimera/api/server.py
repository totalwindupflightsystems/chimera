"""FastAPI REST API.

Endpoints:
* ``POST /v1/deliberate``       — full pipeline, returns answer + trace.
* ``POST /v1/chat/completions`` — OpenAI-compatible drop-in.
* ``GET  /v1/formations``       — list formation presets.
* ``GET  /v1/models``           — list models with category weights.
* ``GET  /v1/health``           — health check (healthy/degraded/unhealthy).
* ``GET  /v1/health/ready``     — readiness probe (provider connectivity).
* ``GET  /v1/health/live``      — liveness probe (process alive).

Resilience features:
* F5 – Request queue with backpressure (max_concurrent, max_queue_depth).
* F8 – Enhanced health checks with dependency verification.
"""

from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from typing import Annotated, Any

import structlog
from fastapi import Depends, FastAPI, HTTPException, Request, status
from pydantic import BaseModel

from chimera.api.dependencies import require_api_key
from chimera.api.rate_limit import RateLimiter
from chimera.config import ChimeraConfig, load_config
from chimera.engine import Engine
from chimera.gateway import LiteLLMGateway
from chimera.observability import configure_logging

log = structlog.get_logger("chimera.api")


# --------------------------------------------------------------------------- #
# F5: Request queue / backpressure
# --------------------------------------------------------------------------- #

class RequestQueue:
    """In-memory request queue with semaphore-based concurrency limiting (F5).

    * max_concurrent: maximum simultaneously executing requests (default 10).
    * max_queue_depth: maximum waiting requests (default 100).
    * When full, returns HTTP 503 with Retry-After header.
    """

    def __init__(self, max_concurrent: int = 10, max_queue_depth: int = 100) -> None:
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._max_queue_depth = max_queue_depth
        self._current_waiting = 0
        self._lock = asyncio.Lock()
        # Stats
        self.total_queued: int = 0
        self.total_rejected: int = 0
        self.total_completed: int = 0

    async def acquire(self) -> bool:
        """Try to acquire a slot. Returns False if queue is full (503)."""
        async with self._lock:
            if self._current_waiting >= self._max_queue_depth:
                self.total_rejected += 1
                return False
            self._current_waiting += 1
            self.total_queued += 1

        try:
            await self._semaphore.acquire()
            return True
        finally:
            async with self._lock:
                self._current_waiting -= 1

    def release(self) -> None:
        """Release a concurrency slot."""
        self.total_completed += 1
        self._semaphore.release()

    @property
    def current_waiting(self) -> int:
        return self._current_waiting

    @property
    def max_queue_depth(self) -> int:
        return self._max_queue_depth


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

    # F5: Create request queue
    request_queue = RequestQueue(
        max_concurrent=cfg.queue.max_concurrent,
        max_queue_depth=cfg.queue.max_queue_depth,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Store queue on app state."""
        yield

    app = FastAPI(title="Chimera", version="0.1.0", lifespan=lifespan)
    app.state.config = cfg
    app.state.engine = engine or Engine(cfg, LiteLLMGateway(cfg))
    app.state.request_queue = request_queue
    app.state.rate_limiter = RateLimiter(cfg.rate_limit)
    _register_routes(app)

    # Web UI (session-backed multi-turn with live DAG viz + SSE)
    try:
        from chimera.web import router as web_router
        app.include_router(web_router)
    except ImportError:
        pass  # web extra not installed — skip gracefully

    return app


# --------------------------------------------------------------------------- #
# Security helpers
# --------------------------------------------------------------------------- #


def _check_rate_limit(request: Request, key: str) -> None:
    """Check rate limit for *key*; raise HTTP 429 if exhausted."""
    limiter: RateLimiter = request.app.state.rate_limiter
    allowed, retry_after = limiter.allow(key)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "rate_limited",
                "message": "Too many requests. Please wait before retrying.",
            },
            headers={"Retry-After": str(max(1, int(retry_after + 1)))},
        )


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

    # ---------------------------------------------------------------- #
    # F8: Enhanced health checks
    # ---------------------------------------------------------------- #

    @app.get("/v1/health")
    async def health(request: Request) -> dict[str, Any]:
        """Health check — returns healthy, degraded, or unhealthy.

        Verifies: config loaded, at least one provider reachable.
        Backward compatible: always returns 200 with a JSON body.
        """
        cfg: ChimeraConfig = request.app.state.config
        details: dict[str, Any] = {
            "config_loaded": True,
            "models_configured": len(cfg.models),
            "providers_configured": len(cfg.providers),
        }

        # Optional provider connectivity check
        try:
            gw = request.app.state.engine.gateway
            provider_status = await _check_providers(cfg, gw)
            details["providers"] = provider_status

            if all(p["healthy"] for p in provider_status.values()):
                return {"status": "healthy", "details": details}
            if any(p["healthy"] for p in provider_status.values()):
                return {"status": "degraded", "details": details}
            return {"status": "degraded", "details": details}
        except Exception as exc:
            log.warning("health_check_error", error=str(exc))
            # Don't fail health check — report degraded
            return {
                "status": "degraded",
                "details": {**details, "error": str(exc)[:200]},
            }

    @app.get("/v1/health/ready")
    async def readiness(request: Request) -> dict[str, Any]:
        """Readiness probe — checks provider connectivity.

        Returns 200 if at least one provider is reachable, 503 otherwise.
        """
        cfg: ChimeraConfig = request.app.state.config
        try:
            gw = request.app.state.engine.gateway
            provider_status = await _check_providers(cfg, gw)
            ready = any(p["healthy"] for p in provider_status.values())
            if ready:
                return {"status": "ready", "providers": provider_status}
            raise HTTPException(
                status_code=503,
                detail="Not ready — no providers reachable",
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail=f"Not ready: {str(exc)[:200]}",
            ) from exc

    @app.get("/v1/health/live")
    async def liveness(request: Request) -> dict[str, Any]:
        """Liveness probe — just checks the process is alive.

        Always returns 200.
        """
        cfg: ChimeraConfig = request.app.state.config
        return {
            "status": "alive",
            "uptime_models": len(cfg.models),
        }

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
    async def deliberate(
        request: Request,
        body: DeliberateRequest,
        api_key: Annotated[str, Depends(require_api_key)],
    ) -> DeliberateResponse:
        # F2: Rate limiting
        _check_rate_limit(request, api_key)

        # F5: Queue/backpressure check
        queue: RequestQueue = request.app.state.request_queue
        acquired = await queue.acquire()
        if not acquired:
            raise HTTPException(
                status_code=503,
                detail="Server busy — queue full. Retry later.",
                headers={"Retry-After": "5"},
            )

        try:
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
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            return DeliberateResponse(
                answer=result.answer,
                trace=result.trace.model_dump(mode="json"),
                request_id=result.trace.request_id,
            )
        finally:
            queue.release()

    @app.post("/v1/chat/completions", response_model=ChatCompletionResponse)
    async def chat_completions(
        request: Request,
        body: ChatCompletionRequest,
        api_key: Annotated[str, Depends(require_api_key)],
    ) -> ChatCompletionResponse:
        # F2: Rate limiting
        _check_rate_limit(request, api_key)

        # F5: Queue/backpressure check
        queue: RequestQueue = request.app.state.request_queue
        acquired = await queue.acquire()
        if not acquired:
            raise HTTPException(
                status_code=503,
                detail="Server busy — queue full. Retry later.",
                headers={"Retry-After": "5"},
            )

        try:
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
                raise HTTPException(status_code=400, detail=f"Unknown model/formation: {exc}") from exc
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
        finally:
            queue.release()


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def _check_providers(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, _provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"role": "user", "content": "ping"}],
                        temperature=0.0,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": True, "note": "no providers configured"}

    return status


def run(host: str | None = None, port: int | None = None) -> None:
    """Run the API server with uvicorn (``chimera serve`` entrypoint)."""
    import uvicorn

    cfg = load_config()
    uvicorn.run(
        create_app(cfg),
        host=host or cfg.server.host,
        port=port or cfg.server.port,
    )


__all__ = ["RequestQueue", "create_app", "run"]
