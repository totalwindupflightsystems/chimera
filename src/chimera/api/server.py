"""FastAPI REST API.

Endpoints:
* ``POST /v1/deliberate``       — full pipeline, returns answer + trace.
* ``POST /v1/chat/completions`` — OpenAI-compatible drop-in.
* ``GET  /v1/formations``       — list formation presets.
* ``GET  /v1/models``           — OpenAI-shaped model list (+ chimera catalog).
* ``GET  /v1/health``           — health check (healthy/degraded/unhealthy).
* ``GET  /v1/health/ready``     — readiness probe (provider connectivity).
* ``GET  /v1/health/live``      — liveness probe (process alive).

Resilience features:
* F5 – Request queue with backpressure (max_concurrent, max_queue_depth).
* F8 – Enhanced health checks with dependency verification.
"""

from __future__ import annotations

import asyncio
import functools
import os
import subprocess
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

import structlog
from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from chimera import __version__
from chimera.api.dependencies import require_api_key
from chimera.api.rate_limit import RateLimiter
from chimera.config import ChimeraConfig, load_config, provider_credential_resolved
from chimera.engine import DeliberationTrace, Engine
from chimera.gateway import LiteLLMGateway
from chimera.observability import configure_logging

log = structlog.get_logger("chimera.api")


@functools.lru_cache(maxsize=1)
def _running_commit() -> str:
    """Short git commit the running code was built from, or 'unknown'.

    Resolved once per process from the repository HEAD. Outside a git
    checkout (e.g. pip-installed wheel) returns 'unknown' so monitoring
    can still tell staleness apart from an unknown build.
    """
    try:
        repo_root = Path(__file__).resolve().parents[3]
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=3,
        )
        commit = out.stdout.strip()
        return commit if commit else "unknown"
    except Exception:
        return "unknown"


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
        # INT-API-001: the whole /web/* surface (sessions, chat, SSE, the SPA
        # shell at GET /web/) runs deliberations through the same engine as
        # /v1/deliberate, so it gets the same authentication. The dependency is
        # attached at the ROUTER, not per-handler: one line covers every
        # current and future web route, including the SPA. With auth disabled
        # ``require_api_key`` returns "anonymous" before reading any header, so
        # the default deployment is unchanged.
        app.include_router(web_router, dependencies=[Depends(require_api_key)])
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
    # INT-API-003: `model` is OPTIONAL and defaults to the "auto" formation, so
    # the minimal documented request is just `messages`. The default is the
    # only substitution that happens here: min_length=1 keeps an explicit
    # empty string a 422, and the handler still hard-errors (404) on any other
    # explicitly supplied non-formation value — never a silent fall back.
    model: str = Field("auto", min_length=1)
    messages: list[ChatMessage] = Field(..., min_length=1)
    temperature: float | None = None
    response_format: dict[str, Any] | None = None  # OpenAI-compatible structured output
    stream: bool | None = None  # OpenAI-compat field — rejected (streaming not supported, CH-GAP-030)
    max_tokens: int | None = None  # OpenAI-compat output token cap — honored (CH-GAP-031)
    max_completion_tokens: int | None = None  # OpenAI alias — wins over max_tokens when both set
    n: int | None = None  # Accepted for drop-in compat; n>1 unsupported (documented no-op, CH-GAP-031)
    top_p: float | None = None  # Accepted for drop-in compat; sampling fixed per stage (documented no-op)
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


def aggregate_usage(trace: DeliberationTrace) -> tuple[int, int, int]:
    """Token usage of a WHOLE deliberation, as ``(prompt, completion, total)``.

    One chimera request is many upstream model calls (the dispatcher, then
    every worker/judge, then the aggregator), so the OpenAI-compatible
    ``usage`` block reports the deliberation-wide aggregate instead of any
    single stage's numbers:

    * ``prompt_tokens``     — summed ``tokens_input`` of the dispatch span plus
      every stage span;
    * ``completion_tokens`` — summed ``tokens_output`` of those same spans;
    * ``total_tokens``      — ``prompt_tokens + completion_tokens``.

    The dispatcher's design call carries the whole model catalog, so its input
    dominates ``prompt_tokens`` for a short user prompt — that is the honest
    aggregate, not a bug.

    ``trace.stages`` never contains the dispatch span (the engine keeps
    ``dispatch`` and ``stages`` disjoint), so each span is counted exactly once
    and the total matches ``trace.total_tokens``, which the engine computes
    over the identical span set.
    """
    spans = [trace.dispatch, *trace.stages]
    prompt_tokens = sum(span.tokens_input for span in spans)
    completion_tokens = sum(span.tokens_output for span in spans)
    return prompt_tokens, completion_tokens, prompt_tokens + completion_tokens


# --------------------------------------------------------------------------- #
# Route registration
# --------------------------------------------------------------------------- #

def _catalog_entry_payload(entry: Any) -> dict[str, Any]:
    """Per-model payload served by ``GET /v1/models`` (INT-API-004).

    Single source of truth for BOTH the OpenAI ``data[]`` entries and the
    chimera ``catalog`` map, so the two field sets cannot drift apart.

    ``cost_per_1k_input`` / ``cost_per_1k_output`` are the EFFECTIVE rates the
    engine bills, not the raw catalog fields (CH-GAP-055). A catalog entry
    that declares no explicit rate used to be served as ``null`` while the
    biller charged the entry's cost-tier default — the served catalog said
    "unpriceable/free" for exactly the ids that spend real money. The values
    now come from ``ModelEntry.cost_rate_input()`` / ``cost_rate_output()``,
    the SAME methods ``engine._stage_cost`` bills through, so the served
    price and the billed price cannot drift again.

    Explicit per-model rates still win — the methods read them first and only
    fall back to ``DEFAULT_COST_RATES[cost_tier]`` when the field is ``None``.
    An unrecognised tier resolves the same way the biller resolves it
    (``DEFAULT_COST_RATES["standard"]``), so a catalog entry the engine
    prices is never served as ``null``. A model the engine genuinely cannot
    price (no reservation at all — see ``engine._stage_cost``'s ``KeyError``
    path, which bills ``0.0``) has no catalog entry to serve.

    Field names, JSON types and the envelope are unchanged; only the null
    placeholder becomes the billed number.
    """
    return {
        "categories": entry.categories,
        "cost_tier": entry.cost_tier,
        "provider": entry.provider,
        "enabled": entry.enabled,
        "cost_per_1k_input": entry.cost_rate_input(),
        "cost_per_1k_output": entry.cost_rate_output(),
    }


def _register_routes(app: FastAPI) -> None:
    from fastapi.responses import JSONResponse

    # ---------------------------------------------------------------- #
    # F8: Enhanced health checks
    # ---------------------------------------------------------------- #

    @app.get("/v1/health")
    async def health(request: Request) -> dict[str, Any]:
        """Health check — returns healthy or degraded.

        Verifies: config loaded, at least one provider reachable.
        Backward compatible: always returns 200 with a JSON body.

        ``unhealthy_providers`` (DF-CHIMERA-V2-14) is the machine-readable
        companion to ``status``: the sorted names of the providers whose
        probe did not succeed, so a client does not have to walk
        ``details.providers`` and string-match ``error``.  It is present in
        every response — ``[]`` exactly when ``status == "healthy"``.
        """
        cfg: ChimeraConfig = request.app.state.config
        # CH-GAP-053: count only the providers the config declared — the
        # providers map also carries auto-discovery additions, which used to
        # inflate this count. Discovery-added names are reported separately.
        configured_count, discovered_names = (
            _split_configured_and_discovered_providers(cfg)
        )
        details: dict[str, Any] = {
            "config_loaded": True,
            "models_configured": len(cfg.models),
            "providers_configured": configured_count,
            "providers_discovered": discovered_names,
            "commit": _running_commit(),
        }

        # Optional provider connectivity check
        try:
            gw = request.app.state.engine.gateway
            provider_status = await _check_providers(cfg, gw)
            details["providers"] = provider_status

            unhealthy = _unhealthy_provider_names(provider_status)
            # "healthy" is equivalent to "no provider failed"; the previous
            # two identical `degraded` branches are collapsed into this one
            # without changing the status value or the body shape.
            status = (
                "healthy"
                if all(p["healthy"] for p in provider_status.values())
                else "degraded"
            )
            return {
                "status": status,
                "unhealthy_providers": unhealthy,
                "details": details,
            }
        except Exception as exc:
            log.warning("health_check_error", error=str(exc))
            # Don't fail health check — report degraded.  No per-provider
            # result exists here, so every configured provider is named:
            # none of them was PROVEN healthy, and the field must not read
            # as "degraded with nothing wrong" (`details.error` carries the
            # real reason).
            return {
                "status": "degraded",
                "unhealthy_providers": sorted(cfg.providers),
                "details": {**details, "error": str(exc)[:200]},
            }

    @app.get("/v1/health/ready")
    async def readiness(request: Request) -> dict[str, Any]:
        """Readiness probe — checks provider connectivity.

        Returns 200 if at least one provider is reachable, 503 otherwise.
        The 200 body carries `unhealthy_providers` alongside `providers`
        (DF-CHIMERA-V2-14) with the same meaning as on `/v1/health`.
        """
        cfg: ChimeraConfig = request.app.state.config
        try:
            gw = request.app.state.engine.gateway
            provider_status = await _check_providers(cfg, gw)
            ready = any(p["healthy"] for p in provider_status.values())
            if ready:
                return {
                    "status": "ready",
                    "unhealthy_providers": _unhealthy_provider_names(provider_status),
                    "providers": provider_status,
                }
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
            "commit": _running_commit(),
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
            "commit": _running_commit(),
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
        """List models as an OpenAI ``ListModelsResponse`` (INT-API-004).

        ``object``/``data`` make the route spec-shaped so the official SDK's
        ``client.models.list()`` works: the SDK needs ``data`` to be a list,
        and the old bare ``{model_id: {...}}`` map made ``page.data`` None
        (``TypeError: object of type 'NoneType' has no len()``) for every
        proxy/UI that enumerates models through the SDK.

        The chimera catalog map is still served, additively, under
        ``catalog`` — same per-model payloads as ``data[]``, keyed by model
        id — so existing keyed lookups keep working. ``created`` is always
        ``0``: the catalog carries no per-model timestamp and inventing one
        would be a fabricated fact. ``owned_by`` is the configured provider.
        The route stays keyless (docs/SECURITY.md open-endpoint list).
        """
        cfg: ChimeraConfig = request.app.state.config
        catalog = {
            name: _catalog_entry_payload(entry) for name, entry in cfg.models.items()
        }
        return {
            "object": "list",
            "data": [
                {
                    "id": name,
                    "object": "model",
                    "created": 0,
                    "owned_by": payload["provider"],
                    **payload,
                }
                for name, payload in catalog.items()
            ],
            "catalog": catalog,
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
            # `body.model` already defaults to "auto" (INT-API-003), so an
            # omitted `model` deliberates with the auto dispatcher.
            formation = body.model or "auto"
            # OpenAI-compat contract: an unknown model is a hard error, NOT a
            # silent substitution (CH-GAP-027). Valid values: "auto", a
            # configured formation preset, or "custom" (only with a DAG).
            cfg: ChimeraConfig = request.app.state.config
            if formation not in cfg.formations and formation != "auto" and not (
                formation == "custom" and body.dag is not None
            ):
                # DF-CHIMERA-0911-3: `model` is a FORMATION selector (OpenAI
                # drop-in compatibility), NOT a catalog model ID — a key from
                # GET /v1/models sent as `model` lands here. Keep the 404
                # model_not_found contract (CH-GAP-027) but make it
                # actionable: name the override fields that DO select a
                # specific catalog model. Those fields are read straight off
                # the request body, so an OpenAI SDK caller reaches them via
                # `extra_body` — say so instead of leaving the caller to guess.
                return JSONResponse(
                    status_code=404,
                    content={
                        "error": {
                            "message": (
                                f"The model `{formation}` does not exist. "
                                "`model` selects a FORMATION (a deliberation "
                                "preset), not a catalog model ID — use GET "
                                "/v1/formations for the valid names, or GET "
                                "/v1/models for the catalog. Valid values: "
                                "'auto', a formation preset, or 'custom' with "
                                "a DAG via allow_custom_dag. To force a "
                                "specific catalog model, send model='auto' "
                                "with one of the Chimera override fields: "
                                "`worker_model` (every worker), "
                                "`stage_models` (per stage), or "
                                "`allowed_models` (restrict the pool) — "
                                "OpenAI SDK callers pass these through "
                                "extra_body. See docs/OPENAI_API.md."
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
                max_tokens=body.max_completion_tokens or body.max_tokens,
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
            # Deliberation-wide aggregate (dispatch + every stage), not the
            # dispatcher stage's numbers alone — see aggregate_usage().
            usage_prompt, usage_completion, usage_total = aggregate_usage(trace)
            return ChatCompletionResponse(
                id=f"chatcmpl-{trace.request_id}",
                created=int(time.time()),
                model=formation,
                choices=[ChatChoice(message=ChatChoiceMessage(content=result.answer))],
                usage=ChatUsage(
                    prompt_tokens=usage_prompt,
                    completion_tokens=usage_completion,
                    total_tokens=usage_total,
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

    Health-only superset of the canonical routing helper
    (:func:`chimera.config.provider_credential_resolved`, which covers
    ``config.api_keys`` → resolved ``Provider.api_key`` → F8
    Anthropic→OpenRouter fallback): additionally probes the per-provider
    environment fallbacks LiteLLM reads directly, so the connectivity
    pre-check matches every key the gateway could actually use.
    """
    if provider_credential_resolved(config, provider_name):
        return True
    return any(os.environ.get(env_var) for env_var in _PROVIDER_ENV_KEYS.get(provider_name, ()))


#: Message tokens that mean "the provider refused for auth reasons".  Checked
#: BEFORE the quota tokens so a failure that says both ("401 ... quota") stays
#: ``auth`` — an auth failure is the more actionable verdict.
_AUTH_TOKENS: tuple[str, ...] = (
    "401", "403", "unauthorized", "authentication",
    "invalid api key", "api key", "forbidden", "permission denied",
)

#: Message tokens that mean "the provider was reachable and authenticated, but
#: the account has no budget/quota left" — the INT-ZAI-001 class
#: (litellm.RateLimitError "Insufficient balance or no resource package.
#: Please recharge.").  Reported as ``quota`` so an operator sees "top up the
#: account" instead of the useless catch-all ``api``.  A 429 status code is
#: the same condition signalled structurally and is checked first.
_QUOTA_TOKENS: tuple[str, ...] = (
    "insufficient_quota", "quota", "insufficient_credits",
    "insufficient balance", "no resource package", "recharge", "billing",
    "payment required", "spending limit", "rate limit", "out of credits",
)


def _classify_provider_error(exc: BaseException) -> str:
    """Classify a provider failure as ``timeout`` | ``auth`` | ``api`` | ``quota``."""
    status_code = getattr(exc, "status_code", None)
    if status_code is None:
        response = getattr(exc, "response", None)
        if response is not None:
            status_code = getattr(response, "status_code", None)
    if status_code == 429:
        return "quota"
    if status_code in (401, 403):
        return "auth"
    message = str(exc).lower()
    if any(token in message for token in _AUTH_TOKENS):
        return "auth"
    if any(token in message for token in _QUOTA_TOKENS):
        return "quota"
    if "timeout" in message or "timed out" in message:
        return "timeout"
    return "api"


def _unhealthy_provider_names(
    provider_status: dict[str, dict[str, Any]],
) -> list[str]:
    """Sorted names of the providers whose probe did not succeed.

    The machine-readable companion to the ``/v1/health`` ``status`` field
    (DF-CHIMERA-V2-14): ``[]`` exactly when every provider reported
    ``healthy``, so a client can branch on the list instead of walking
    ``details.providers`` and string-matching ``error``.  A provider entry
    with no ``healthy`` key counts as unhealthy (nothing was proven).
    """
    return sorted(
        name
        for name, info in provider_status.items()
        if not info.get("healthy", False)
    )


def _split_configured_and_discovered_providers(
    config: ChimeraConfig,
) -> tuple[int, list[str]]:
    """Count the declared providers; name the discovery-added ones.

    ``config.providers`` is mutated in place by provider auto-discovery
    (``load_config`` → ``_apply_env_overrides``), so ``len(config.providers)``
    silently includes whatever models.dev contributed (CH-GAP-053).  This
    helper splits the map using ``declared_provider_names``:

    * returns the **configured** count = number of explicitly declared
      providers, and
    * the **discovered** names, sorted, = names in ``providers`` that the
      config did not declare.

    Names only — no credential or ``Provider`` payload is exposed.  For a
    config built programmatically (no load-time metadata) the fallback keeps
    the old contract: everything currently in the map counts as configured
    and the discovered list is empty.
    """
    declared = config.declared_provider_names
    discovered = sorted(set(config.providers) - declared)
    return len(declared), discovered


async def _check_providers(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str, ...}.

    Every FAILED provider also carries ``error_class`` (DF-CHIMERA-V2-14): a
    machine-readable reason, one of ``missing_credentials`` | ``timeout`` |
    ``auth`` | ``quota`` | ``api``.  It is ADDITIVE — the ``error`` text,
    ``healthy``, ``model_tested`` and ``note`` fields are unchanged, and a
    healthy provider keeps its exact previous shape (no ``error_class``).

    Provider checks run concurrently under ``config.server.health_timeout_s``
    (default 10.0 s).  Providers without resolvable credentials are reported
    immediately as ``missing-credentials`` (no live call).  A provider with no
    models in the catalog is never probed and proves nothing, so it is
    reported ``healthy: false`` with only a ``note`` (CH-GAP-053) — it lands
    in ``unhealthy_providers`` instead of silently reading as healthy.  For
    non-timeout failures (``auth`` / ``api`` / ``quota``) up to
    ``_MAX_PROBE_MODELS``
    models from the provider are tried before it is marked unhealthy; the last
    model attempted is reported in ``model_tested``.  A timeout is terminal per
    provider — one model is enough to prove connectivity.

    The shared budget is not a hard verdict boundary (DF-CHIMERA-V2-17): when
    it expires, probes still outstanding get
    ``config.server.health_probe_grace_s`` extra seconds to land.  One that
    finishes inside the grace reports its REAL verdict exactly as if it had
    finished in time (``quota`` / ``auth`` / ``api`` + ``model_tested``) —
    this removes the cold-start false ``timeout`` where litellm's one-off
    client/TLS/provider-discovery warm-up (measured ~10.3s on the first probe
    of a fresh process vs ~2.8-3.2s warm) briefly exceeds the budget.  A probe
    still outstanding after the grace is cancelled and reported ``timeout``
    exactly as before; ``health_probe_grace_s: 0`` disables the grace
    entirely, and a task that was already done at the deadline keeps its exact
    previous payload.  The grace only bounds how long the endpoint waits — it
    never lengthens the blocking path beyond the deadline plus the grace.

    The probe ping is sent with ``probe=True`` (INT-ZAI-002): the deliberately
    cheap ``max_tokens=1`` call always ends with ``finish_reason="length"``,
    which the gateway would otherwise report as a token-limit event.  The flag
    keeps that expected truncation out of the ``token_limit_reached`` warning
    stream, so a healthy provider no longer looks like it is out of quota.
    """
    async def check_one(provider_name: str) -> tuple[str, dict[str, Any]]:
        model_names = [
            name for name, entry in config.models.items()
            if entry.provider == provider_name
        ]
        if not model_names:
            # CH-GAP-053: nothing was probed, so nothing was proven.  A
            # note-only entry must not read as healthy — reporting it
            # unhealthy is what keeps ``status`` and ``unhealthy_providers``
            # honest (and makes the smoke script's count honest).
            return provider_name, {
                "healthy": False,
                "note": "no models configured for provider",
            }
        if not _provider_has_credentials(config, provider_name):
            return provider_name, {
                "healthy": False,
                "error": (
                    "missing-credentials: no API key resolved "
                    f"for provider '{provider_name}'"
                ),
                "error_class": "missing_credentials",
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
                    probe=True,
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
            "error_class": error_class,
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

    # DF-CHIMERA-V2-17: a probe still outstanding at the deadline gets a
    # short, bounded grace window to land.  One that finishes inside it is
    # resolved from its REAL result below (the ``done``-set handling is
    # shared), so a cold-start probe that merely needed litellm's one-off
    # warm-up reports ``quota``/``auth``/``api`` + ``model_tested`` instead of
    # a fabricated ``timeout``.  ``health_probe_grace_s: 0`` skips the wait
    # entirely and reproduces the cancel-at-deadline behaviour exactly.
    if pending and config.server.health_probe_grace_s > 0:
        late_done, pending = await asyncio.wait(
            pending, timeout=config.server.health_probe_grace_s,
        )
        done |= late_done

    status: dict[str, dict[str, Any]] = {}
    for task in done:
        provider_name = tasks[task]
        if task.cancelled():
            status[provider_name] = {
                "healthy": False,
                "error": timeout_error,
                "error_class": "timeout",
            }
            continue
        try:
            _, result = task.result()
            status[provider_name] = result
        except Exception as exc:  # defensive — check_one catches everything
            status[provider_name] = {
                "healthy": False,
                "error": f"api: {str(exc)[:200]}",
                "error_class": _classify_provider_error(exc),
            }
    for task in pending:
        task.cancel()
        status[tasks[task]] = {
            "healthy": False,
            "error": timeout_error,
            "error_class": "timeout",
        }

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
