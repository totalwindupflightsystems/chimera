"""Provider gateway — a uniform async interface over LiteLLM.

The :class:`Gateway` protocol lets the rest of Chimera stay provider-agnostic.
:class:`LiteLLMGateway` is the production implementation; tests inject fakes.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

import structlog

from chimera.config import ChimeraConfig, ModelEntry

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

    if provider == "deepseek":
        if model_name.startswith("deepseek/"):
            return model_name, kwargs
        return f"deepseek/{model_name}", kwargs

    if provider == "openai":
        if model_name.startswith("openai/"):
            return model_name, kwargs
        return f"openai/{model_name}", kwargs

    return model_name, kwargs


class LiteLLMGateway:
    """Production gateway backed by ``litellm.acompletion``."""

    def __init__(self, config: ChimeraConfig) -> None:
        self.config = config

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
        call_kwargs: dict[str, Any] = {
            "model": lm_model,
            "messages": messages,
            "temperature": temperature,
            **extra,
            **kwargs,
        }
        if response_format is not None:
            call_kwargs["response_format"] = response_format

        log.debug("gateway_call", model=model, litellm_model=lm_model)
        try:
            result = await asyncio.to_thread(_litellm_sync_complete, call_kwargs)
        except _PROVIDER_ERRORS as exc:
            raise GatewayError(f"{model} call failed: {exc}") from exc

        text = _extract_text(result)
        usage = getattr(result, "usage", None)
        tok_in = int(getattr(usage, "prompt_tokens", 0) or 0)
        tok_out = int(getattr(usage, "completion_tokens", 0) or 0)
        return GatewayResponse(
            text=text,
            model=model,
            tokens_input=tok_in,
            tokens_output=tok_out,
            raw=result,
        )


def _build_provider_error_tuple() -> tuple[type[BaseException], ...]:
    import httpx

    types: list[type[BaseException]] = [httpx.HTTPError]
    try:
        import openai

        types.append(openai.OpenAIError)
    except ImportError:
        pass
    return tuple(types)


_PROVIDER_ERRORS: tuple[type[BaseException], ...] = _build_provider_error_tuple()


def _litellm_sync_complete(call_kwargs: dict[str, Any]) -> Any:
    import litellm

    return litellm.completion(**call_kwargs)


def _extract_text(result: Any) -> str:
    choices = getattr(result, "choices", None) or []
    if not choices:
        return ""
    message = getattr(choices[0], "message", None)
    if message is None:
        return ""
    content = getattr(message, "content", None)
    if content:
        return content
    return ""


__all__ = [
    "Gateway",
    "GatewayError",
    "GatewayResponse",
    "LiteLLMGateway",
    "resolve_litellm_model",
]
