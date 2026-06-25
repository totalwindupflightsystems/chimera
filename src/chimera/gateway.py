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
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol, runtime_checkable

import structlog

from chimera.circuit_breaker import ProviderCircuitBreaker, fast_fail_response
from chimera.config import ChimeraConfig, ModelEntry
from chimera.exceptions import BudgetExhaustedError

log = structlog.get_logger("chimera.gateway")


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
    JSON_OBJECT = "json_object"           # Generic {} only (deepseek, moonshot)
    NONE = "none"                         # Plain text only


# Providers that support full json_schema
_JSON_SCHEMA_PROVIDERS: frozenset[str] = frozenset({
    "openai", "anthropic", "google", "zai",
})

# Providers that support json_object but not json_schema
_JSON_OBJECT_PROVIDERS: frozenset[str] = frozenset({
    "deepseek", "moonshot",
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
) -> tuple[str, dict[str, Any]]:
    """Map a Chimera model to a LiteLLM model string + extra kwargs.

    Rules:
    * If the config supplies ``litellm_model`` explicitly, use it verbatim.
    * ``zai`` provider → OpenAI-compatible call against the ZAI base URL.
    * ``openrouter`` provider → ensure the ``openrouter/`` prefix.
    * ``anthropic`` / ``deepseek`` → use the native LiteLLM provider prefix.
    * When ``api_key`` is supplied, it is passed as ``api_key`` so LiteLLM
      authenticates — otherwise it falls back to env vars.
    """
    kwargs: dict[str, Any] = {}
    if api_key:
        kwargs["api_key"] = api_key
    if entry.litellm_model:
        return entry.litellm_model, kwargs

    provider = entry.provider.lower()
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

    return model_name, kwargs


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
        import litellm
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
        lm_model, extra = resolve_litellm_model(model, entry, api_key=api_key)

        # F6: Provider-aware format negotiation
        negotiated_format = negotiate_response_format(
            response_format, entry.provider
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

        log.debug(
            "gateway_call",
            model=model,
            litellm_model=lm_model,
            response_format_type=(
                negotiated_format.get("type") if negotiated_format else "none"
            ),
        )

        # F3: Circuit breaker check
        breaker = self._get_circuit_breaker(entry.provider)
        if breaker is not None and not breaker.before_call():
            log.warning("circuit_breaker_open", provider=entry.provider, model=model)
            return fast_fail_response(entry.provider)

        try:
            response = await self._complete_with_retry(call_kwargs, model)
            if breaker is not None:
                breaker.on_success()
            return response
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
        self, call_kwargs: dict[str, Any], model: str
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
        """
        retry_cfg = self.config.retry
        last_error: BaseException | None = None

        for attempt in range(1, retry_cfg.max_attempts + 1):
            try:
                result = await asyncio.to_thread(
                    _litellm_sync_complete, call_kwargs
                )
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
                        f"{model} call failed: {exc}"
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
            f"{model} call failed after {retry_cfg.max_attempts} attempts: {last_error}"
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
    import litellm

    return litellm.completion(**call_kwargs)


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
    "negotiate_response_format",
    "resolve_litellm_model",
]
