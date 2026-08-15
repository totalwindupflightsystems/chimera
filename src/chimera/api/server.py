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
import os
import time
from contextlib import asynccontextmanager
from typing import Annotated, Any

import structlog
from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from chimera import __version__
from chimera.api.dependencies import require_api_key
from chimera.api.rate_limit import RateLimiter
from chimera.config import ChimeraConfig, load_config
from chimera.engine import Engine
from chimera.gateway import LiteLLMGateway
from chimera.observability import configure_logging

log = structlog.get_logger("chimera.api")


class _NoUsableAnswerError(Exception):
    """Raised when a deliberation produced no usable answer — the answer
    stage degraded and only a placeholder was returned. Translated into
    HTTP 502 with an OpenAI-compatible structured error body."""

    def __init__(self, message: str, request_id: str) -> None:
        super().__init__(message)
        self.message = message
        self.request_id = request_id


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

    app = FastAPI(title="Chimera", version=__version__, lifespan=lifespan)

    from fastapi.responses import JSONResponse

    @app.exception_handler(_NoUsableAnswerError)
    async def _no_answer_handler(request: Request, exc: _NoUsableAnswerError) -> JSONResponse:
        """HTTP 502 with an OpenAI-compatible structured error body."""
        log.warning(
            "deliberation_no_answer",
            request_id=exc.request_id,
            error=exc.message,
        )
        return JSONResponse(
            status_code=502,
            content={
                "error": {
                    "message": exc.message,
                    "type": "upstream_error",
                    "request_id": exc.request_id,
                }
            },
        )

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
    prompt: str = Field(..., min_length=1)
    formation: str = Field("auto", min_length=1)
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
    model: str = Field(..., min_length=1)
    messages: list[ChatMessage] = Field(..., min_length=1)
    temperature: float | None = None
    response_format: dict[str, Any] | None = None  # OpenAI-compatible structured output
    stream: bool | None = None  # OpenAI-compat field — rejected (streaming not supported, CH-GAP-030)
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
    from fastapi.responses import JSONResponse

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

    @app.get("/health")
    async def health_alias(request: Request) -> dict[str, Any]:
        """Bare ``/health`` alias for the liveness probe.

        Monitoring stacks commonly probe ``/health`` by default; without
        this alias a healthy server would answer 404. Delegates to the same
        liveness semantics as ``/v1/health/live`` (always 200 when alive).
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
                "enabled": entry.enabled,
                "cost_per_1k_input": entry.cost_per_1k_input,
                "cost_per_1k_output": entry.cost_per_1k_output,
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
            cfg: ChimeraConfig = request.app.state.config
            if body.formation not in cfg.formations:
                raise HTTPException(
                    status_code=422,
                    detail=f"Unknown formation: {body.formation}",
                )
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
            # Per-request timeout overrides via X-Chimera-Timeout header.
            # Format: "total=300,per_stage=180". Values cannot exceed admin ceiling.
            timeout_header = request.headers.get("X-Chimera-Timeout", "")
            if timeout_header:
                timeout_cfg = request.app.state.config.timeout
                for part in timeout_header.split(","):
                    part = part.strip()
                    if "=" not in part:
                        continue
                    key, _, val = part.partition("=")
                    try:
                        parsed = float(val.strip())
                    except ValueError:
                        continue
                    if key == "total":
                        if timeout_cfg.total_s > 0 and parsed > timeout_cfg.total_s:
                            raise HTTPException(
                                status_code=400,
                                detail=f"total={parsed} exceeds admin ceiling {timeout_cfg.total_s}s",
                            )
                        overrides.timeout_total_s = parsed if parsed > 0 else None
                    elif key == "per_stage":
                        if timeout_cfg.per_stage_s > 0 and parsed > timeout_cfg.per_stage_s:
                            raise HTTPException(
                                status_code=400,
                                detail=f"per_stage={parsed} exceeds admin ceiling {timeout_cfg.per_stage_s}s",
                            )
                        overrides.timeout_per_stage_s = parsed if parsed > 0 else None
            try:
                result = await engine.deliberate(
                    body.prompt, body.formation, overrides=overrides,
                    dag=body.dag, allow_custom_dag=body.allow_custom_dag,
                )
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            if result.answer_degraded:
                raise _NoUsableAnswerError(
                    message=(
                        "Deliberation failed: no usable answer produced. "
                        f"Upstream error: {result.answer_error or 'unknown'}"
                    ),
                    request_id=result.trace.request_id,
                )
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
    ) -> Response | ChatCompletionResponse:
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
            # OpenAI-compat contract: an unknown model is a hard error, NOT a
            # silent substitution (CH-GAP-027). Valid values: "auto", a
            # configured formation preset, or "custom" (only with a DAG).
            cfg: ChimeraConfig = request.app.state.config
            if formation not in cfg.formations and formation != "auto" and not (
                formation == "custom" and body.dag is not None
            ):
                return JSONResponse(
                    status_code=404,
                    content={
                        "error": {
                            "message": (
                                f"The model `{formation}` does not exist. "
                                "Valid values: 'auto', a formation preset "
                                "(GET /v1/formations), or 'custom' with a DAG "
                                "via POST /v1/chat/completions."
                            ),
                            "type": "invalid_request_error",
                            "param": "model",
                            "code": "model_not_found",
                        }
                    },
                )
            from chimera.config import DeliberationOverrides
            # OpenAI-compat contract: streaming is NOT supported (CH-GAP-030).
            # A drop-in client sending stream:true must get an explicit 400
            # naming the field — never a silent non-stream 200.
            if body.stream:
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": {
                            "message": (
                                "Streaming is not supported by this server. "
                                "Omit `stream` or set it to false."
                            ),
                            "type": "invalid_request_error",
                            "param": "stream",
                            "code": "stream_not_supported",
                        }
                    },
                )
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
            if result.answer_degraded:
                raise _NoUsableAnswerError(
                    message=(
                        "Deliberation failed: no usable answer produced. "
                        f"Upstream error: {result.answer_error or 'unknown'}"
                    ),
                    request_id=result.trace.request_id,
                )
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

#: Env-var fallbacks per provider, mirroring ``gateway.resolve_litellm_model``
#: and ``_apply_env_overrides`` so the missing-credentials pre-check matches
#: the key the gateway would actually use.
_PROVIDER_ENV_KEYS: dict[str, tuple[str, ...]] = {
    "deepseek": ("DEEPSEEK_API_KEY", "DEEPSEEK_KEY"),
    "zai": ("ZAI_API_KEY", "ZAI_KEY"),
    "anthropic": ("ANTHROPIC_API_KEY", "ANTHROPIC_KEY"),
    "openrouter": ("OPENROUTER_API_KEY", "OPENROUTER_KEY"),
    "openai": ("OPENAI_API_KEY", "OPENAI_KEY"),
    "google": ("GEMINI_API_KEY", "GEMINI_KEY", "GOOGLE_API_KEY"),
    "xai": ("XAI_API_KEY", "XAI_KEY"),
}

#: How many different models per provider are probed before a non-timeout
#: failure marks the provider unhealthy (one model may be blocked by a
#: privacy guardrail / quota while the provider itself works).
_MAX_PROBE_MODELS = 3


def _provider_has_credentials(config: ChimeraConfig, provider_name: str) -> bool:
    """True when the gateway can resolve an API key for *provider_name*.

    Mirrors the key resolution the gateway actually uses: ``config.api_keys``
    (env-var shortcuts) → resolved ``Provider.api_key`` (``api_key_env``) →
    per-provider environment fallbacks.  Anthropic gets the F8 OpenRouter
    fallback the gateway applies when no Anthropic key is configured.
    """
    if config.api_keys.get(provider_name):
        return True
    provider = config.providers.get(provider_name)
    if provider is not None and provider.api_key:
        return True
    for env_var in _PROVIDER_ENV_KEYS.get(provider_name, ()):
        if os.environ.get(env_var):
            return True
    if provider_name == "anthropic":
        # F8: the gateway routes Anthropic models via OpenRouter when no
        # Anthropic key is configured but an OpenRouter key exists.
        if config.api_keys.get("openrouter"):
            return True
        or_provider = config.providers.get("openrouter")
        if or_provider is not None and or_provider.api_key:
            return True
    return False


def _classify_provider_error(exc: BaseException) -> str:
    """Classify a provider failure as ``timeout`` | ``auth`` | ``api``."""
    status_code = getattr(exc, "status_code", None)
    if status_code is None:
        response = getattr(exc, "response", None)
        if response is not None:
            status_code = getattr(response, "status_code", None)
    if status_code in (401, 403):
        return "auth"
    message = str(exc).lower()
    if "timeout" in message or "timed out" in message:
        return "timeout"
    if any(
        token in message
        for token in (
            "401", "403", "unauthorized", "authentication",
            "invalid api key", "api key", "forbidden", "permission denied",
        )
    ):
        return "auth"
    return "api"


async def _check_providers(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str, ...}.

    Provider checks run concurrently under ``config.server.health_timeout_s``
    (default 10.0 s).  Providers without resolvable credentials are reported
    immediately as ``missing-credentials`` (no live call).  For non-timeout
    failures (``auth`` / ``api``) up to ``_MAX_PROBE_MODELS`` models from the
    provider are tried before it is marked unhealthy; the last model attempted
    is reported in ``model_tested``.  A timeout is terminal per provider —
    one model is enough to prove connectivity.
    """
    async def check_one(provider_name: str) -> tuple[str, dict[str, Any]]:
        model_names = [
            name for name, entry in config.models.items()
            if entry.provider == provider_name
        ]
        if not model_names:
            return provider_name, {
                "healthy": True,
                "note": "no models configured for provider",
            }
        if not _provider_has_credentials(config, provider_name):
            return provider_name, {
                "healthy": False,
                "error": (
                    "missing-credentials: no API key resolved "
                    f"for provider '{provider_name}'"
                ),
            }

        last_error: BaseException | None = None
        last_model = model_names[0]
        for test_model in model_names[:_MAX_PROBE_MODELS]:
            last_model = test_model
            try:
                await gateway.complete(
                    test_model,
                    [{"role": "user", "content": "ping"}],
                    temperature=1,
                    max_tokens=1,
                )
                return provider_name, {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except Exception as exc:
                last_error = exc
                if _classify_provider_error(exc) == "timeout":
                    # Timeout is terminal for the provider within this check.
                    break
        assert last_error is not None
        error_class = _classify_provider_error(last_error)
        return provider_name, {
            "healthy": False,
            "error": f"{error_class}: {str(last_error)[:200]}",
            "model_tested": last_model,
        }

    if not config.providers:
        return {"_none": {"healthy": True, "note": "no providers configured"}}

    tasks = {
        asyncio.create_task(check_one(provider_name)): provider_name
        for provider_name in config.providers
    }
    done, pending = await asyncio.wait(
        tasks, timeout=config.server.health_timeout_s,
    )

    timeout_error = (
        f"timeout: no response within {config.server.health_timeout_s:.1f}s"
    )
    status: dict[str, dict[str, Any]] = {}
    for task in done:
        provider_name = tasks[task]
        if task.cancelled():
            status[provider_name] = {"healthy": False, "error": timeout_error}
            continue
        try:
            _, result = task.result()
            status[provider_name] = result
        except Exception as exc:  # defensive — check_one catches everything
            status[provider_name] = {
                "healthy": False,
                "error": f"api: {str(exc)[:200]}",
            }
    for task in pending:
        task.cancel()
        status[tasks[task]] = {"healthy": False, "error": timeout_error}

    if pending:
        await asyncio.gather(*pending, return_exceptions=True)

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
