"""Provider gateway — a uniform async interface over LiteLLM.

The :class:`Gateway` protocol lets the rest of Chimera stay provider-agnostic.
:class:`LiteLLMGateway` is the production implementation; tests inject fakes.

Resilience features (F5–F8 audit):
* F7 – Exponential backoff retry for transient failures (429/5xx/network).
* F6 – Provider-aware response_format negotiation (json_schema → json_object → text).
* C3 – Token limit detection (finish_reason="length").
* C4 – Empty/null response handling (is_empty flag).
* C7 – Budget exhaustion detection (BudgetExhaustedError).
"""

from __future__ import annotations

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable

import structlog

from chimera.blocked_models import is_credential_error
from chimera.circuit_breaker import ProviderCircuitBreaker, fast_fail_response
from chimera.config import ChimeraConfig, ModelEntry, provider_api_key_env
from chimera.exceptions import BudgetExhaustedError

log = structlog.get_logger("chimera.gateway")

#: LiteLLM ships process-global debug switches whose DEFAULT state writes
#: straight to stdout:
#:   * ``suppress_debug_info=False`` makes
#:     ``litellm_core_utils.get_llm_provider_logic`` print an ANSI
#:     ``Provider List: https://docs.litellm.ai/docs/providers`` banner when a
#:     provider-less model string reaches it. LiteLLM calls that helper
#:     internally from provider transformations (e.g. OpenRouter's
#:     ``get_supported_openai_params`` -> ``utils.supports_reasoning``), where a
#:     provider-less lookup is routine — so the banner can fire on a perfectly
#:     successful deliberation.
#:   * ``exception_mapping_utils.exception_type`` prints a
#:     ``Give Feedback / Get Help`` block for every mapped provider error.
#: Stdout is the JSON-RPC wire for the MCP stdio transport (and piped output
#: for the CLI), so a single banner corrupts a live session. We flip the
#: switches on the litellm module itself — the one seam every provider call
#: already flows through — instead of patching site-packages or redirecting
#: process stdout globally.


def ensure_litellm_quiet(litellm_module: Any | None = None) -> Any:
    """Silence LiteLLM's stdout debug banners, process-wide.

    Sets ``suppress_debug_info = True`` (and ``set_verbose = False``) on the
    LiteLLM module and returns it. Idempotent and cheap, so it runs
    immediately before EVERY completion — the async path, the sync fallback,
    and therefore the exception-mapping path, which executes inside
    ``litellm.completion`` / ``acompletion``. ``litellm_module`` is injectable
    so tests can assert the ordering without importing LiteLLM.
    """
    if litellm_module is None:
        import litellm as litellm_module

    litellm_module.suppress_debug_info = True
    litellm_module.set_verbose = False
    return litellm_module


#: Dedicated pool for residual sync LiteLLM work. Sized for concurrent stage
#: waves (multiple workers + progressive wait-messages) so default-executor
#: saturation cannot serialize independent stage calls.
_GATEWAY_EXECUTOR: ThreadPoolExecutor | None = None
_GATEWAY_EXECUTOR_WORKERS = 32


def _get_gateway_executor() -> ThreadPoolExecutor:
    """Lazily create (and install as loop default) a large thread pool."""
    global _GATEWAY_EXECUTOR
    if _GATEWAY_EXECUTOR is None:
        _GATEWAY_EXECUTOR = ThreadPoolExecutor(
            max_workers=_GATEWAY_EXECUTOR_WORKERS,
            thread_name_prefix="chimera-gw",
        )
        try:
            loop = asyncio.get_running_loop()
            loop.set_default_executor(_GATEWAY_EXECUTOR)
        except RuntimeError:
            pass  # no running loop yet; to_thread will use this via run_in_executor
    return _GATEWAY_EXECUTOR


class GatewayError(Exception):
    """Raised when a provider call fails (auth, network, bad request, ...)."""


@dataclass(slots=True)
class GatewayResponse:
    """A normalized completion response."""

    text: str
    model: str
    tokens_input: int
    tokens_output: int
    raw: Any = None
    finish_reason: str = ""
    is_empty: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    """Structured side-band data (e.g. ``{"degraded": True, ...}`` on
    placeholder responses fabricated by the engine when a stage fails)."""

    @property
    def total_tokens(self) -> int:
        return self.tokens_input + self.tokens_output


@runtime_checkable
class Gateway(Protocol):
    """Anything that can complete a prompt asynchronously."""

    async def complete(
        self,
        model: str,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.2,
        response_format: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> GatewayResponse: ...


# --------------------------------------------------------------------------- #
# F6: Provider-aware format negotiation
# --------------------------------------------------------------------------- #

class FormatCapability(Enum):
    """What level of structured output a provider supports."""
    JSON_SCHEMA = "json_schema"          # Full JSON Schema (openai, anthropic, google, zai)
    JSON_OBJECT = "json_object"           # Generic {} only (moonshot)
    NONE = "none"                         # Plain text only


# Providers that support full json_schema
_JSON_SCHEMA_PROVIDERS: frozenset[str] = frozenset({
    "openai", "anthropic", "google", "zai",
})

# Providers that support json_object but not json_schema
_JSON_OBJECT_PROVIDERS: frozenset[str] = frozenset({
    "moonshot",
})


def _get_format_capability(provider: str) -> FormatCapability:
    """Return the structured-output capability level for a provider."""
    p = provider.lower()
    if p in _JSON_SCHEMA_PROVIDERS:
        return FormatCapability.JSON_SCHEMA
    if p in _JSON_OBJECT_PROVIDERS:
        return FormatCapability.JSON_OBJECT
    return FormatCapability.NONE


def negotiate_response_format(
    requested: dict[str, Any] | None,
    provider: str,
) -> dict[str, Any] | None:
    """Downgrade response_format to what the provider actually supports (F6).

    * json_schema → json_object for providers that don't support schema.
    * Any format → None for text-only providers.
    * Returns None if the provider can't handle any structured format.
    """
    if requested is None:
        return None

    capability = _get_format_capability(provider)
    requested_type = requested.get("type")

    if capability == FormatCapability.JSON_SCHEMA:
        return requested  # full support

    if capability == FormatCapability.JSON_OBJECT:
        if requested_type == "json_schema":
            # Downgrade: strip schema detail, keep json_object
            log.info(
                "gateway_format_downgrade",
                from_format="json_schema",
                to_format="json_object",
                provider=provider,
            )
            return {"type": "json_object"}
        if requested_type == "json_object":
            return requested
        # unknown type — try json_object as a safe bet
        return {"type": "json_object"}

    # capability == NONE
    if requested_type is not None:
        log.info(
            "gateway_format_removed",
            requested_type=requested_type,
            provider=provider,
        )
    return None


# --------------------------------------------------------------------------- #
# Model resolution
# --------------------------------------------------------------------------- #


def resolve_litellm_model(
    model_name: str, entry: ModelEntry, api_key: str | None = None,
    fallback_provider: str | None = None,
    base_url: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """Map a Chimera model to a LiteLLM model string + extra kwargs.

    Rules:
    * If the config supplies ``litellm_model`` explicitly, use it verbatim.
    * ``zai`` provider → OpenAI-compatible call against the ZAI base URL.
    * ``openrouter`` provider → ensure the ``openrouter/`` prefix.
    * ``anthropic`` / ``deepseek`` → use the native LiteLLM provider prefix.
    * Any *other* provider with a configured ``base_url`` → a generic
      OpenAI-compatible call against that URL with the model id the endpoint
      expects.  This covers endpoints LiteLLM has no native prefix for — the
      local Hermes gateway (``hermes``), a vLLM/llama.cpp server, an internal
      proxy, the 9router fleet gateway (``router9``).  Without it such a
      provider silently falls through to LiteLLM's own default host for that
      model name (INT-PROV-HERMES-001).  The id sent upstream is the catalog
      id with ONE leading ``<provider>/`` stripped when it carries it
      (namespaced upstream ids — ``router9/ds/deepseek-v4-flash`` →
      ``ds/deepseek-v4-flash`` — keep their inner slashes); otherwise it is
      the last ``/``-segment (INT-PROV-ROUTER9-001).
    * When ``api_key`` is supplied, it is passed as ``api_key`` so LiteLLM
      authenticates — otherwise it falls back to env vars.
    * ``fallback_provider``: when set, overrides entry.provider for
      routing resolution (used for Anthropic→OpenRouter fallback).
    * ``base_url``: the serving provider's configured
      ``providers.<name>.base_url``.  Read only by the generic branch above;
      every natively handled provider keeps its own hardcoded routing.
    """
    kwargs: dict[str, Any] = {}
    if api_key:
        kwargs["api_key"] = api_key
    if entry.litellm_model:
        return entry.litellm_model, kwargs

    # Use fallback_provider if set, otherwise use the entry's provider
    provider = (fallback_provider or entry.provider).lower()
    if provider == "zai":
        # The z.ai coding endpoint expects the bare model name (e.g. "glm-5.2"),
        # not the full catalog id ("zai-coding-plan/glm-5.2").
        api_model = model_name.rsplit("/", 1)[-1]
        lm_model = f"openai/{api_model}"
        kwargs["api_base"] = "https://api.z.ai/api/coding/paas/v4"
        kwargs["custom_llm_provider"] = "openai"
        if "api_key" not in kwargs:
            kwargs["api_key"] = os.environ.get("ZAI_API_KEY")
        return lm_model, kwargs

    if provider == "openrouter":
        if model_name.startswith("openrouter/"):
            return model_name, kwargs
        return f"openrouter/{model_name}", kwargs

    if provider == "anthropic":
        if model_name.startswith("anthropic/"):
            return model_name, kwargs
        return f"anthropic/{model_name}", kwargs

    if provider == "google":
        # Strip any leading "google/" prefix so the model name is the bare
        # Gemini id (e.g. "gemini-2.5-pro"). LiteLLM's gemini/ prefix routes
        # through the Google AI Studio backend.
        bare = model_name.split("/")[-1]
        if bare.startswith("gemini/"):
            return bare, kwargs
        return f"gemini/{bare}", kwargs

    if provider == "deepseek":
        # Route through LiteLLM's OpenAI provider to avoid DeepSeek-specific
        # cost calculator that doesn't know about v4-flash/v4-pro model names.
        api_model = model_name.rsplit("/", 1)[-1]
        lm_model = f"openai/{api_model}"
        kwargs["api_base"] = "https://api.deepseek.com/v1"
        kwargs["custom_llm_provider"] = "openai"
        if "api_key" not in kwargs:
            kwargs["api_key"] = os.environ.get("DEEPSEEK_API_KEY")
        return lm_model, kwargs

    if provider == "openai":
        if model_name.startswith("openai/"):
            return model_name, kwargs
        return f"openai/{model_name}", kwargs

    if base_url:
        # Generic OpenAI-compatible endpoint (INT-PROV-HERMES-001).  The
        # provider is one LiteLLM has no native prefix for, so the configured
        # ``base_url`` has to be passed explicitly or the call lands on
        # LiteLLM's default host for this model name.  Mirrors the zai branch:
        # the catalog id is stripped to the model name the endpoint expects
        # and ``custom_llm_provider`` is pinned to openai.
        #
        # Some gateways in front of many upstreams serve their own NAMESPACED
        # model ids, so the part after the catalog prefix is itself
        # slash-separated: 9router answers to ``ds/deepseek-v4-flash`` and
        # ``openrouter/x-ai/grok-4.6``, not to their last segment.  Strip
        # exactly ONE leading ``<provider>/`` when the catalog id carries it
        # (case-insensitively); every other id keeps the old innermost-segment
        # behavior (INT-PROV-ROUTER9-001).
        prefix = f"{provider}/"
        if model_name.lower().startswith(prefix):
            api_model = model_name[len(prefix):]
        else:
            api_model = model_name.rsplit("/", 1)[-1]
        kwargs["api_base"] = base_url
        kwargs["custom_llm_provider"] = "openai"
        return f"openai/{api_model}", kwargs

    return model_name, kwargs


# --------------------------------------------------------------------------- #
# Resolved-route attribution (QA-CHIMERA-V2-16)
# --------------------------------------------------------------------------- #

#: Metadata keys carrying the route a completion was actually served by.
#: Deliberately distinct from the engine's degraded-marker keys
#: (``degraded`` / ``error`` / ``stage_id``) that ``GatewayResponse.metadata``
#: already uses.
ROUTE_PROVIDER_KEY = "provider"
ROUTE_WIRE_MODEL_KEY = "wire_model"
ROUTE_API_BASE_KEY = "api_base"


def stamp_route_attribution(
    response: GatewayResponse,
    *,
    provider: str | None,
    wire_model: str | None = None,
    api_base: str | None = None,
) -> GatewayResponse:
    """Record the resolved route on *response* and return it unchanged.

    ``provider`` is the provider that the routing decision selected — the
    *effective* provider after credential fallbacks (F8 anthropic→openrouter),
    never the catalog id's prefix.  ``wire_model`` is the model string handed
    to LiteLLM and ``api_base`` the endpoint it will be sent to (empty for
    routes that use the provider's own default host).

    Empty/None values are omitted, so a native route simply has no ``api_base``
    key.  Nothing is stamped when the caller passes no provider.

    ``GatewayResponse`` is a mutable dataclass, which is what lets the single
    point that knows the route (``LiteLLMGateway.complete``) hand the
    attribution forward on the response itself — the engine reads it back off
    ``metadata`` and puts it on the trace span.
    """
    if provider:
        response.metadata[ROUTE_PROVIDER_KEY] = provider
    if wire_model:
        response.metadata[ROUTE_WIRE_MODEL_KEY] = wire_model
    if api_base:
        response.metadata[ROUTE_API_BASE_KEY] = api_base
    return response


# --------------------------------------------------------------------------- #
# F7: Retry with exponential backoff
# --------------------------------------------------------------------------- #

# HTTP status codes that are retryable (transient failures)
_RETRYABLE_STATUS_CODES: frozenset[int] = frozenset({
    429,                      # Rate limit
    500, 502, 503, 504,       # Server errors
})


def _is_retryable(exc: BaseException) -> bool:
    """Check whether an exception indicates a transient failure worth retrying.

    Retry on: rate limit (429), server errors (5xx), network errors.
    Do NOT retry on: auth errors (401/403), bad request (400), budget exhausted.
    """
    import httpx

    # httpx.HTTPStatusError carries an HTTP response
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        return code in _RETRYABLE_STATUS_CODES

    # Network-level errors (timeout, connection refused, DNS, ...)
    if isinstance(exc, (httpx.TimeoutException, httpx.NetworkError,
                         httpx.ConnectError, httpx.ReadError,
                         httpx.WriteError, httpx.PoolTimeout)):
        return True

    # openai.OpenAIError – check for retryable HTTP subclasses
    try:
        import openai
        if isinstance(exc, openai.OpenAIError):
            # OpenAI's APIStatusError has a status_code attribute
            if hasattr(exc, "status_code"):
                code = getattr(exc, "status_code", 0)
                if code in _RETRYABLE_STATUS_CODES:
                    return True
            # APIConnectionError and APITimeoutError are transient; 401/403/400 are NOT
            return isinstance(exc, (openai.APIConnectionError, openai.APITimeoutError))
    except ImportError:
        pass

    # litellm exceptions can wrap httpx/openai
    try:
        litellm = ensure_litellm_quiet()
        if isinstance(exc, litellm.exceptions.APIError) and hasattr(exc, "status_code"):
            return getattr(exc, "status_code", 0) in _RETRYABLE_STATUS_CODES
        if isinstance(exc, litellm.exceptions.APIConnectionError):
            return True
        if isinstance(exc, litellm.exceptions.RateLimitError):
            return True
        if isinstance(exc, litellm.exceptions.Timeout):
            return True
    except ImportError:
        pass

    return False


async def _sleep_ms(ms: float) -> None:
    """Small async sleep helper."""
    await asyncio.sleep(ms / 1000.0)


def credential_remedy(
    error: object,
    *,
    model: str,
    provider: str | None,
    config: ChimeraConfig | None,
) -> str:
    """Provider-accurate remedy phrase for a credential-class failure ("" if none).

    LiteLLM's credential errors are **provider-blind**: a missing key for any
    provider served over the OpenAI SDK (every ``base_url`` provider here) is
    reported as ``Missing credentials ... set the OPENAI_API_KEY ...``, so a
    DeepSeek user was told to set ``OPENAI_API_KEY`` — a variable that could
    not fix their call.  The phrase returned here names the provider and the
    env var that actually holds its key, and callers place it **before** the
    generic upstream text so the accurate remedy is what the user reads first.

    This is the ONE seam: the ``GatewayError`` message built at the raise
    sites below is what the CLI, the REST body, the MCP tool result, the trace
    and the structlog stream all render (DF-CHIMERA-V2-8).

    Returns ``""`` — meaning "keep the raw upstream message verbatim" — when:

    * *error* is not credential-class (timeouts, 429s and 5xx are retry
      business, not a key problem);
    * no provider can be resolved, so no env var could be named honestly;
    * the provider is a keyless local endpoint (``lmstudio``/``ollama``),
      where ``provider_api_key_env`` cannot name a variable — the keyless path
      stays byte-identical to before.
    """
    if not is_credential_error(error):
        return ""
    if not provider and config is not None:
        entry = config.models.get(model)
        provider = entry.provider if entry is not None else None
    if not provider:
        return ""
    env_var = provider_api_key_env(config, provider)
    if not env_var:
        return ""
    return (
        f"provider '{provider}' rejected the credentials or none were found: "
        f"set {env_var} (or the variable named by "
        f"providers.{provider}.api_key_env). upstream error: "
    )


class LiteLLMGateway:
    """Production gateway backed by ``litellm.acompletion``.

    Resilience features:
    * F7 – Exponential backoff retry (configurable via RetryConfig).
    * F6 – Provider-aware response_format negotiation (auto-downgrade).
    * C3 – Token limit detection with WARNING log.
    * C4 – Empty/null response detection via is_empty flag.
    * C7 – Budget exhaustion detection (BudgetExhaustedError + CRITICAL log).
    """

    def __init__(self, config: ChimeraConfig) -> None:
        self.config = config
        # Track provider for format negotiation
        self._model_provider_map: dict[str, str] = {}
        # F3: Per-provider circuit breakers (lazy-init on first call)
        self._circuit_breakers: dict[str, ProviderCircuitBreaker] = {}
        # Auto-initialize breakers for configured providers
        for provider_name, cb_cfg in config.circuit_breakers.items():
            self._circuit_breakers[provider_name] = ProviderCircuitBreaker(
                name=provider_name, config=cb_cfg,
            )

    async def complete(
        self,
        model: str,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.2,
        response_format: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> GatewayResponse:
        entry = self.config.get_model(model)
        api_key = self.config.api_keys.get(entry.provider)
        effective_provider = entry.provider

        # F8: Anthropic → OpenRouter fallback.
        # When no Anthropic key is available but OpenRouter is, route
        # Anthropic models through OpenRouter so deliberation doesn't fail.
        if entry.provider == "anthropic" and not api_key:
            or_key = self.config.api_keys.get("openrouter")
            if or_key:
                api_key = or_key
                effective_provider = "openrouter"
                log.info(
                    "gateway_anthropic_fallback",
                    model=model,
                    to_provider="openrouter",
                )

        # ``api_keys`` only carries the shortcut-provider keys
        # (``_apply_env_overrides``).  A provider configured through
        # ``providers.<name>.api_key_env`` / ``api_key`` resolves at load time
        # onto the provider entry instead, so consult it as the fallback —
        # that is what lets a generic ``base_url`` provider authenticate.
        provider_cfg = self.config.providers.get(effective_provider)
        if api_key is None and provider_cfg is not None:
            api_key = provider_cfg.api_key

        lm_model, extra = resolve_litellm_model(
            model, entry, api_key=api_key, fallback_provider=effective_provider,
            base_url=provider_cfg.base_url if provider_cfg is not None else None,
        )

        # F6: Provider-aware format negotiation
        negotiated_format = negotiate_response_format(
            response_format, effective_provider
        )

        call_kwargs: dict[str, Any] = {
            "model": lm_model,
            "messages": messages,
            "temperature": temperature,
            **extra,
            **kwargs,
        }
        if negotiated_format is not None:
            call_kwargs["response_format"] = negotiated_format

        # QA-CHIMERA-V2-16: the resolved route for THIS call.  Read back from
        # the final call kwargs so a caller-supplied ``api_base`` is reflected;
        # ``extra`` (the resolver's own routing kwargs) is what lands there for
        # the zai / deepseek / generic-base_url branches.
        route_api_base = call_kwargs.get("api_base")

        log.debug(
            "gateway_call",
            model=model,
            litellm_model=lm_model,
            response_format_type=(
                negotiated_format.get("type") if negotiated_format else "none"
            ),
        )

        # F3: Circuit breaker check
        breaker = self._get_circuit_breaker(effective_provider)
        if breaker is not None and not breaker.before_call():
            log.warning("circuit_breaker_open", provider=effective_provider, model=model)
            # The route was resolved (provider / wire model / api_base are all
            # known) even though the breaker refused the CALL; the attribution
            # names the route this stage resolved to, so the trace still shows
            # which provider was skipped instead of an unattributable stage.
            return stamp_route_attribution(
                fast_fail_response(effective_provider),
                provider=effective_provider,
                wire_model=lm_model,
                api_base=route_api_base,
            )

        try:
            response = await self._complete_with_retry(
                call_kwargs, model, provider=effective_provider,
            )
            if breaker is not None:
                breaker.on_success()
            # Stamp the route that actually served the call onto the response's
            # metadata side-band; the engine copies it onto the trace span
            # (``model`` alone cannot attribute a call — its catalog prefix can
            # name a provider other than the one that served it).
            return stamp_route_attribution(
                response,
                provider=effective_provider,
                wire_model=lm_model,
                api_base=route_api_base,
            )
        except (GatewayError, BudgetExhaustedError):
            if breaker is not None:
                breaker.on_failure()
            raise

    def _get_circuit_breaker(self, provider: str) -> ProviderCircuitBreaker | None:
        """Get the circuit breaker for a provider, creating one from defaults if needed."""
        breaker = self._circuit_breakers.get(provider)
        if breaker is not None:
            return breaker
        # Try "default" config
        default_cfg = self.config.circuit_breakers.get("default")
        if default_cfg is not None:
            breaker = ProviderCircuitBreaker(name=provider, config=default_cfg)
            self._circuit_breakers[provider] = breaker
            return breaker
        return None

    # ------------------------------------------------------------------ #
    # F7: Exponential backoff retry + C7: budget exhaustion detection
    # ------------------------------------------------------------------ #

    async def _complete_with_retry(
        self,
        call_kwargs: dict[str, Any],
        model: str,
        *,
        provider: str | None = None,
    ) -> GatewayResponse:
        """Call LiteLLM with exponential backoff retry for transient failures.

        Retry policy (from RetryConfig):
        * max_attempts: max total attempts (default 3)
        * base_delay_ms: initial delay (default 500)
        * max_delay_ms: cap on delay (default 10000)
        * backoff_multiplier: multiplier each attempt (default 2.0)

        Retryable: 429, 5xx, network errors (timeout, connection refused).
        Non-retryable: 401/403, 400, budget exhausted.
        Budget exhaustion (C7): detected and raised as BudgetExhaustedError.

        *provider* is the provider that actually served the call (the caller
        resolves it, including the F8 Anthropic → OpenRouter fallback), so a
        credential failure can be reported against the right provider's env
        var instead of whichever provider LiteLLM's SDK prose happens to name
        (DF-CHIMERA-V2-8).  ``None`` falls back to the model catalog entry.
        """
        retry_cfg = self.config.retry
        last_error: BaseException | None = None

        for attempt in range(1, retry_cfg.max_attempts + 1):
            try:
                # Prefer native async acompletion so independent stages truly
                # overlap on the event loop (no thread-pool bottleneck).
                # Fall back to sync completion on a dedicated large pool if
                # acompletion is unavailable or raises TypeError/NotImplemented.
                result = await _litellm_acomplete(call_kwargs)
                return self._build_response(result, model)
            except Exception as exc:
                last_error = exc

                # C7: Detect budget/quota exhaustion before retry logic
                exc_str = str(exc).lower()
                if _is_budget_exhausted(exc_str):
                    entry = self.config.get_model(model)
                    log.critical(
                        "budget_exhausted",
                        model=model,
                        provider=entry.provider,
                        error=str(exc),
                    )
                    raise BudgetExhaustedError(
                        model=model,
                        provider=entry.provider,
                        details=str(exc),
                    ) from exc

                # Check if this is retryable
                if not _is_retryable(exc):
                    log.debug(
                        "gateway_non_retryable",
                        model=model,
                        error=str(exc),
                        attempt=attempt,
                    )
                    raise GatewayError(
                        f"{model} call failed: "
                        f"{credential_remedy(exc, model=model, provider=provider, config=self.config)}"
                        f"{exc}"
                    ) from exc

                if attempt >= retry_cfg.max_attempts:
                    log.warning(
                        "gateway_retry_exhausted",
                        model=model,
                        attempts=attempt,
                        error=str(exc),
                    )
                    break

                # Calculate exponential backoff with jitter
                delay = min(
                    retry_cfg.base_delay_ms * (retry_cfg.backoff_multiplier ** (attempt - 1)),
                    retry_cfg.max_delay_ms,
                )
                # Add ±25% jitter
                jitter = delay * 0.25 * (2 * (hash(str(attempt)) % 100) / 100.0 - 1)
                delay = delay + jitter

                log.info(
                    "gateway_retry",
                    model=model,
                    attempt=attempt,
                    next_attempt=attempt + 1,
                    delay_ms=int(delay),
                    error=str(exc)[:200],
                )
                await _sleep_ms(delay)

        raise GatewayError(
            f"{model} call failed after {retry_cfg.max_attempts} attempts: "
            f"{credential_remedy(last_error, model=model, provider=provider, config=self.config)}"
            f"{last_error}"
        ) from last_error

    def _build_response(self, result: Any, model: str) -> GatewayResponse:
        """Build a GatewayResponse from a LiteLLM result, with token limit
        and empty response detection (C3, C4)."""
        return _build_response(result, model)


def _build_response(result: Any, model: str) -> GatewayResponse:
    """Build a GatewayResponse from a LiteLLM result (standalone, testable).

    Detects token limit (C3) and empty responses (C4).
    """
    text = _extract_text(result)
    usage = getattr(result, "usage", None)
    tok_in = int(getattr(usage, "prompt_tokens", 0) or 0)
    tok_out = int(getattr(usage, "completion_tokens", 0) or 0)

    # C3: Check finish_reason for token limit
    finish_reason = ""
    choices = getattr(result, "choices", None) or []
    if choices:
        finish_reason = getattr(choices[0], "finish_reason", "") or ""

    # C4: Detect empty response
    is_empty = not bool(text)

    if finish_reason == "length":
        log.warning(
            "token_limit_reached",
            model=model,
            tokens_input=tok_in,
            tokens_output=tok_out,
        )

    return GatewayResponse(
        text=text,
        model=model,
        tokens_input=tok_in,
        tokens_output=tok_out,
        raw=result,
        finish_reason=finish_reason,
        is_empty=is_empty,
    )


def _litellm_sync_complete(call_kwargs: dict[str, Any]) -> Any:
    """Blocking LiteLLM completion (used by tests and sync fallback).

    Silences LiteLLM's stdout debug banners first (see
    :func:`ensure_litellm_quiet`) so an error-mapping or provider-lookup
    print can never reach the MCP JSON-RPC wire.
    """
    litellm = ensure_litellm_quiet()

    return litellm.completion(**call_kwargs)


async def _litellm_acomplete(call_kwargs: dict[str, Any]) -> Any:
    """Async LiteLLM completion — concurrent stages share one event loop.

    Uses ``litellm.acompletion`` when available so parallel DAG waves do not
    serialize on a thread pool. Falls back to ``asyncio.to_thread`` + sync
    ``completion`` on a dedicated large executor if acompletion is missing
    or returns a non-awaitable.

    LiteLLM's process-global debug banners are silenced first (see
    :func:`ensure_litellm_quiet`): the ANSI "Provider List" print and the
    "Give Feedback / Get Help" block are stdout writes that would corrupt the
    MCP stdio JSON-RPC stream on any provider lookup miss or mapped error.
    """
    litellm = ensure_litellm_quiet()

    acomplete = getattr(litellm, "acompletion", None)
    if acomplete is not None:
        try:
            result = acomplete(**call_kwargs)
            if asyncio.iscoroutine(result):
                return await result
            # Some mocks return a plain value — accept it.
            return result
        except TypeError:
            # Provider path may not support acompletion kwargs; fall through.
            pass

    executor = _get_gateway_executor()
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        executor, _litellm_sync_complete, call_kwargs
    )


# --------------------------------------------------------------------------- #
# C4: Empty/null response extraction
# --------------------------------------------------------------------------- #

def _extract_text(result: Any) -> str:
    """Extract text content from a LiteLLM completion result.

    Handles every known edge case without crashing (C4):
    * Empty choices array, null choices, missing choices attribute
    * Choices with no message, message with null/empty content
    * ``finish_reason="stop"`` with empty content (model stopped early)
    * Reasoning models that return text in non-standard fields
      (``reasoning_content`` for DeepSeek V4, ``reasoning`` for MiniMax/Kimi)
    """
    choices = getattr(result, "choices", None)
    if not choices:
        return ""
    if not isinstance(choices, (list, tuple)):
        return ""
    if len(choices) == 0:
        return ""

    first = choices[0]
    if first is None:
        return ""

    message = getattr(first, "message", None)
    if message is None:
        return ""

    # Primary content field
    content = getattr(message, "content", None)
    if content and isinstance(content, str) and content.strip():
        return content

    # Reasoning models put their response in non-standard fields:
    #   DeepSeek V4 series → reasoning_content
    #   MiniMax M3, Kimi K2 → reasoning
    for attr in ("reasoning_content", "reasoning"):
        val = getattr(message, attr, None)
        if val and isinstance(val, str) and val.strip():
            return val

    # If content exists but is empty/whitespace-only, return it as-is
    # so is_empty can be detected by the caller
    if content is not None:
        return content if isinstance(content, str) else str(content)

    return ""


# --------------------------------------------------------------------------- #
# C7: Budget exhaustion detection
# --------------------------------------------------------------------------- #

def _is_budget_exhausted(error_str: str) -> bool:
    """Detect provider errors indicating quota/budget exhaustion (C7)."""
    keywords = (
        "insufficient_quota",
        "billing",
        "payment required",
        "quota exceeded",
        "rate limit exceeded",
        "you exceeded your current quota",
        "insufficient_credits",
        "account balance",
        "billing issue",
        "spending limit",
    )
    return any(kw in error_str for kw in keywords)


__all__ = [
    "FormatCapability",
    "Gateway",
    "GatewayError",
    "GatewayResponse",
    "LiteLLMGateway",
    "BudgetExhaustedError",
    "_get_format_capability",
    "_is_retryable",
    "_litellm_acomplete",
    "_litellm_sync_complete",
    "credential_remedy",
    "ensure_litellm_quiet",
    "negotiate_response_format",
    "resolve_litellm_model",
    "stamp_route_attribution",
]
