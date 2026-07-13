"""Coverage-focused tests for chimera.gateway — LiteLLM integration,
format negotiation, retry logic, error classification, and text extraction.

External dependencies (litellm, httpx, openai) are mocked — no real API calls.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from chimera.config import (
    ChimeraConfig,
    ModelEntry,
)
from chimera.exceptions import BudgetExhaustedError
from chimera.gateway import (
    FormatCapability,
    GatewayError,
    GatewayResponse,
    LiteLLMGateway,
    _build_response,
    _extract_text,
    _get_format_capability,
    _is_budget_exhausted,
    _is_retryable,
    _litellm_acomplete,
    _litellm_sync_complete,
    _sleep_ms,
    negotiate_response_format,
    resolve_litellm_model,
)
from tests.conftest import CONFIG_DICT

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _entry(provider: str, litellm_model: str | None = None) -> ModelEntry:
    return ModelEntry(categories={}, cost_tier="standard", provider=provider,
                      litellm_model=litellm_model)


def _litellm_result(
    text: str = "hello",
    *,
    finish_reason: str = "stop",
    prompt_tokens: int = 10,
    completion_tokens: int = 20,
    reasoning_content: str | None = None,
    reasoning: str | None = None,
) -> SimpleNamespace:
    """Build a SimpleNamespace that quacks like a LiteLLM completion result."""
    message = SimpleNamespace(content=text)
    if reasoning_content is not None:
        message.reasoning_content = reasoning_content
    if reasoning is not None:
        message.reasoning = reasoning
    return SimpleNamespace(
        choices=[SimpleNamespace(finish_reason=finish_reason, message=message)],
        usage=SimpleNamespace(prompt_tokens=prompt_tokens,
                              completion_tokens=completion_tokens),
    )


# =========================================================================== #
# F6: Format capability classification
# =========================================================================== #

class TestGetFormatCapability:
    """Cover _get_format_capability for every provider tier."""

    @pytest.mark.parametrize("provider", ["openai", "anthropic", "google", "zai", "deepseek"])
    def test_json_schema_providers(self, provider: str) -> None:
        assert _get_format_capability(provider) == FormatCapability.JSON_SCHEMA

    @pytest.mark.parametrize("provider", ["moonshot"])
    def test_json_object_providers(self, provider: str) -> None:
        assert _get_format_capability(provider) == FormatCapability.JSON_OBJECT

    def test_unknown_provider_is_none(self) -> None:
        assert _get_format_capability("unknown") == FormatCapability.NONE

    def test_case_insensitive(self) -> None:
        assert _get_format_capability("OpenAI") == FormatCapability.JSON_SCHEMA
        assert _get_format_capability("DEEPSEEK") == FormatCapability.JSON_SCHEMA


# =========================================================================== #
# F6: Response format negotiation
# =========================================================================== #

class TestNegotiateResponseFormat:
    """Cover negotiate_response_format branches."""

    def test_none_requested_returns_none(self) -> None:
        assert negotiate_response_format(None, "openai") is None

    def test_json_schema_provider_keeps_format(self) -> None:
        fmt = {"type": "json_schema", "json_schema": {"name": "x", "schema": {}}}
        assert negotiate_response_format(fmt, "openai") is fmt

    def test_json_schema_downgrades_for_json_object_provider(self) -> None:
        fmt = {"type": "json_schema", "json_schema": {"name": "x", "schema": {}}}
        result = negotiate_response_format(fmt, "moonshot")
        assert result == {"type": "json_object"}

    def test_json_object_passthrough_for_json_object_provider(self) -> None:
        fmt = {"type": "json_object"}
        result = negotiate_response_format(fmt, "moonshot")
        assert result == fmt

    def test_unknown_type_falls_back_to_json_object(self) -> None:
        fmt = {"type": "weird_format"}
        result = negotiate_response_format(fmt, "moonshot")
        assert result == {"type": "json_object"}

    def test_text_only_provider_strips_json_schema(self) -> None:
        fmt = {"type": "json_schema", "json_schema": {"name": "x"}}
        assert negotiate_response_format(fmt, "groq") is None

    def test_text_only_provider_strips_json_object(self) -> None:
        assert negotiate_response_format({"type": "json_object"}, "groq") is None

    def test_text_only_provider_with_none_type_returns_none(self) -> None:
        assert negotiate_response_format({"type": None}, "groq") is None


# =========================================================================== #
# Model resolution — additional branches
# =========================================================================== #

class TestResolveLiteLLMModel:
    """Cover every provider branch in resolve_litellm_model."""

    def test_openai_provider_adds_prefix(self) -> None:
        model, extra = resolve_litellm_model("gpt-4o", _entry("openai"))
        assert model == "openai/gpt-4o"
        assert extra == {}

    def test_openai_provider_already_prefixed(self) -> None:
        model, extra = resolve_litellm_model("openai/gpt-4o", _entry("openai"))
        assert model == "openai/gpt-4o"
        assert extra == {}

    def test_anthropic_already_prefixed(self) -> None:
        model, _ = resolve_litellm_model(
            "anthropic/claude-sonnet-4", _entry("anthropic"),
        )
        assert model == "anthropic/claude-sonnet-4"

    def test_unknown_provider_returns_bare_model(self) -> None:
        model, extra = resolve_litellm_model("some-model", _entry("mistral"))
        assert model == "some-model"
        assert extra == {}

    def test_api_key_passthrough(self) -> None:
        model, extra = resolve_litellm_model(
            "gpt-4o", _entry("openai"), api_key="sk-test",
        )
        assert extra == {"api_key": "sk-test"}

    def test_api_key_passthrough_with_litellm_override(self) -> None:
        model, extra = resolve_litellm_model(
            "anything",
            _entry("zai", litellm_model="custom/model"),
            api_key="sk-test",
        )
        assert model == "custom/model"
        assert extra == {"api_key": "sk-test"}

    def test_zai_falls_back_to_env_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ZAI_API_KEY", "env-zai-key")
        model, extra = resolve_litellm_model("zai-coding-plan/glm-5.2", _entry("zai"))
        assert extra["api_key"] == "env-zai-key"

    def test_deepseek_falls_back_to_env_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DEEPSEEK_API_KEY", "env-ds-key")
        model, extra = resolve_litellm_model("deepseek-chat", _entry("deepseek"))
        assert extra["api_key"] == "env-ds-key"
        assert model == "openai/deepseek-chat"
        assert extra["api_base"] == "https://api.deepseek.com/v1"


# =========================================================================== #
# F7: _is_retryable classification
# =========================================================================== #

class TestIsRetryable:
    """Cover _is_retryable across httpx, generic, and non-retryable cases."""

    def test_httpx_429_retryable(self) -> None:
        import httpx
        req = httpx.Request("POST", "https://api.test.com/v1")
        resp = httpx.Response(429, request=req)
        exc = httpx.HTTPStatusError("rate limited", request=req, response=resp)
        assert _is_retryable(exc) is True

    def test_httpx_503_retryable(self) -> None:
        import httpx
        req = httpx.Request("POST", "https://api.test.com/v1")
        resp = httpx.Response(503, request=req)
        exc = httpx.HTTPStatusError("unavailable", request=req, response=resp)
        assert _is_retryable(exc) is True

    def test_httpx_401_not_retryable(self) -> None:
        import httpx
        req = httpx.Request("POST", "https://api.test.com/v1")
        resp = httpx.Response(401, request=req)
        exc = httpx.HTTPStatusError("unauthorized", request=req, response=resp)
        assert _is_retryable(exc) is False

    def test_httpx_400_not_retryable(self) -> None:
        import httpx
        req = httpx.Request("POST", "https://api.test.com/v1")
        resp = httpx.Response(400, request=req)
        exc = httpx.HTTPStatusError("bad request", request=req, response=resp)
        assert _is_retryable(exc) is False

    def test_httpx_timeout_retryable(self) -> None:
        import httpx
        assert _is_retryable(httpx.TimeoutException("timeout")) is True

    def test_httpx_network_error_retryable(self) -> None:
        import httpx
        assert _is_retryable(httpx.NetworkError("conn reset")) is True

    def test_httpx_connect_error_retryable(self) -> None:
        import httpx
        assert _is_retryable(httpx.ConnectError("refused")) is True

    def test_generic_exception_not_retryable(self) -> None:
        assert _is_retryable(ValueError("bad value")) is False
        assert _is_retryable(RuntimeError("oops")) is False
        assert _is_retryable(KeyError("missing")) is False


# =========================================================================== #
# _litellm_sync_complete (mocked litellm.completion)
# =========================================================================== #

class TestLitellmSyncComplete:
    """Cover _litellm_sync_complete by mocking litellm.completion."""

    def test_calls_litellm_completion_with_kwargs(self) -> None:
        fake_result = _litellm_result("test output")
        call_kwargs = {"model": "openai/gpt-4o", "messages": []}

        with patch("litellm.completion", return_value=fake_result) as mock:
            result = _litellm_sync_complete(call_kwargs)

        assert result is fake_result
        mock.assert_called_once_with(**call_kwargs)

    def test_propagates_exception_from_litellm(self) -> None:
        with (
            patch("litellm.completion", side_effect=RuntimeError("boom")),
            pytest.raises(RuntimeError, match="boom"),
        ):
            _litellm_sync_complete({"model": "x", "messages": []})


class TestLitellmAComplete:
    """Cover _litellm_acomplete preferring litellm.acompletion."""

    @pytest.mark.asyncio
    async def test_uses_acompletion_when_available(self) -> None:
        fake_result = _litellm_result("async ok")
        call_kwargs = {"model": "openai/gpt-4o", "messages": []}

        async def _fake_acomplete(**kwargs: Any) -> Any:
            return fake_result

        with patch("litellm.acompletion", side_effect=_fake_acomplete) as mock:
            result = await _litellm_acomplete(call_kwargs)

        assert result is fake_result
        mock.assert_called_once_with(**call_kwargs)

    @pytest.mark.asyncio
    async def test_accepts_non_coroutine_mock_return(self) -> None:
        """Mocks that return a plain value (not a coroutine) are accepted."""
        fake_result = _litellm_result("plain")
        with patch("litellm.acompletion", return_value=fake_result):
            result = await _litellm_acomplete({"model": "x", "messages": []})
        assert result is fake_result

    @pytest.mark.asyncio
    async def test_falls_back_to_sync_on_type_error(self) -> None:
        fake_result = _litellm_result("sync fallback")

        def _raise_type(**kwargs: Any) -> Any:
            raise TypeError("acompletion not supported for this provider")

        with (
            patch("litellm.acompletion", side_effect=_raise_type),
            patch("litellm.completion", return_value=fake_result) as sync_mock,
        ):
            result = await _litellm_acomplete({"model": "x", "messages": []})

        assert result is fake_result
        sync_mock.assert_called_once()


# =========================================================================== #
# _build_response + _extract_text edge cases
# =========================================================================== #

class TestBuildResponseEdgeCases:
    """Cover _build_response and _extract_text edge cases."""

    def test_build_response_sets_all_fields(self) -> None:
        result = _litellm_result("hi", prompt_tokens=11, completion_tokens=22)
        resp = _build_response(result, "openai/gpt-4o")
        assert resp.text == "hi"
        assert resp.model == "openai/gpt-4o"
        assert resp.tokens_input == 11
        assert resp.tokens_output == 22
        assert resp.total_tokens == 33
        assert resp.finish_reason == "stop"
        assert resp.is_empty is False
        assert resp.raw is result

    def test_build_response_missing_usage(self) -> None:
        result = SimpleNamespace(
            choices=[SimpleNamespace(
                finish_reason="stop",
                message=SimpleNamespace(content="x"),
            )],
        )
        resp = _build_response(result, "m")
        assert resp.tokens_input == 0
        assert resp.tokens_output == 0
        assert resp.total_tokens == 0

    def test_build_response_empty_choices(self) -> None:
        result = SimpleNamespace(choices=[], usage=None)
        resp = _build_response(result, "m")
        assert resp.is_empty is True
        assert resp.text == ""
        assert resp.finish_reason == ""

    def test_extract_text_reasoning_field_fallback(self) -> None:
        """Cover the 'reasoning' attribute (MiniMax/Kimi)."""
        result = SimpleNamespace(
            choices=[SimpleNamespace(
                finish_reason="stop",
                message=SimpleNamespace(content=None, reasoning="kimi thought"),
            )],
        )
        assert _extract_text(result) == "kimi thought"

    def test_extract_text_non_string_content_coerced(self) -> None:
        """Cover the non-string content branch in _extract_text.

        Non-string content falls through to the str() coercion at the end.
        """
        result = SimpleNamespace(
            choices=[SimpleNamespace(
                finish_reason="stop",
                message=SimpleNamespace(content=42),
            )],
        )
        # Non-string content is coerced via str()
        assert _extract_text(result) == "42"

    def test_extract_text_choices_not_list(self) -> None:
        """Cover the non-list/tuple choices branch."""
        result = SimpleNamespace(choices="not a list")
        assert _extract_text(result) == ""

    def test_extract_text_none_choice(self) -> None:
        """Cover the None-choice branch."""
        result = SimpleNamespace(choices=[None])
        assert _extract_text(result) == ""

    def test_extract_text_message_none(self) -> None:
        """Cover the missing-message branch."""
        result = SimpleNamespace(choices=[SimpleNamespace()])
        assert _extract_text(result) == ""

    def test_extract_text_whitespace_content_is_empty(self) -> None:
        result = SimpleNamespace(
            choices=[SimpleNamespace(
                finish_reason="stop",
                message=SimpleNamespace(content="   "),
            )],
        )
        assert _extract_text(result) == "   "


# =========================================================================== #
# _is_budget_exhausted — additional keyword coverage
# =========================================================================== #

class TestIsBudgetExhaustedKeywords:
    """Cover remaining keywords in _is_budget_exhausted."""

    @pytest.mark.parametrize("kw", [
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
    ])
    def test_all_keywords_detected(self, kw: str) -> None:
        assert _is_budget_exhausted(f"Error: {kw} happened") is True

    def test_empty_string(self) -> None:
        assert _is_budget_exhausted("") is False


# =========================================================================== #
# _sleep_ms helper
# =========================================================================== #

def test_sleep_ms_divides_by_1000() -> None:
    """Cover _sleep_ms — verifies it actually awaits."""
    async def _run() -> float:
        import time
        start = time.monotonic()
        await _sleep_ms(50)
        return time.monotonic() - start

    elapsed = asyncio.run(_run())
    assert elapsed >= 0.04  # at least ~50ms (allowing scheduling slack)


# =========================================================================== #
# LiteLLMGateway.complete — integration with mocked litellm
# =========================================================================== #

def _gateway_config(**overrides: Any) -> ChimeraConfig:
    """Build a config suitable for LiteLLMGateway tests."""
    cfg_dict = dict(CONFIG_DICT)
    if "retry" in overrides:
        cfg_dict["retry"] = overrides["retry"]
    if "circuit_breakers" in overrides:
        cfg_dict["circuit_breakers"] = overrides["circuit_breakers"]
    return ChimeraConfig.model_validate(cfg_dict)


class TestLiteLLMGatewayComplete:
    """Test the full LiteLLMGateway.complete() flow with mocked litellm."""

    @pytest.mark.asyncio
    async def test_success_returns_response(self) -> None:
        config = _gateway_config()
        gw = LiteLLMGateway(config)
        fake_result = _litellm_result("answer", prompt_tokens=5, completion_tokens=10)

        with patch("litellm.acompletion", return_value=fake_result):
            resp = await gw.complete(
                "deepseek/deepseek-chat",
                [{"role": "user", "content": "hi"}],
            )

        assert resp.text == "answer"
        assert resp.model == "deepseek/deepseek-chat"
        assert resp.tokens_input == 5
        assert resp.tokens_output == 10
        assert resp.is_empty is False

    @pytest.mark.asyncio
    async def test_empty_response_sets_is_empty(self) -> None:
        config = _gateway_config()
        gw = LiteLLMGateway(config)
        fake_result = _litellm_result("", completion_tokens=0)

        with patch("litellm.acompletion", return_value=fake_result):
            resp = await gw.complete(
                "deepseek/deepseek-chat",
                [{"role": "user", "content": "hi"}],
            )

        assert resp.is_empty is True
        assert resp.text == ""

    @pytest.mark.asyncio
    async def test_format_negotiation_downgrade_applied(self) -> None:
        """JSON schema request for a JSON-object provider is downgraded."""
        config = _gateway_config()
        # Add a model whose provider is 'moonshot' (JSON_OBJECT capability)
        config.models["moonshot/test-chat"] = ModelEntry(
            categories={"code": 0.9}, cost_tier="budget", provider="moonshot",
        )
        gw = LiteLLMGateway(config)
        fake_result = _litellm_result('{"answer": "x"}')
        captured_kwargs: dict[str, Any] = {}

        def capture(**kwargs: Any) -> Any:
            captured_kwargs.update(kwargs)
            return fake_result

        with patch("litellm.acompletion", side_effect=capture):
            await gw.complete(
                "moonshot/test-chat",
                [{"role": "user", "content": "hi"}],
                response_format={"type": "json_schema",
                                 "json_schema": {"name": "x", "schema": {}}},
            )

        assert captured_kwargs["response_format"] == {"type": "json_object"}

    @pytest.mark.asyncio
    async def test_format_negotiation_strips_for_text_only(self) -> None:
        """JSON schema request for a text-only provider is stripped."""
        fake_result = _litellm_result("plain text")
        captured_kwargs: dict[str, Any] = {}

        def capture(**kwargs: Any) -> Any:
            captured_kwargs.update(kwargs)
            return fake_result

        config = _gateway_config()
        # Add a text-only model (mistral → NONE capability)
        config.models["test/mistral"] = ModelEntry(
            categories={"code": 0.5}, cost_tier="standard", provider="mistral",
        )
        gw = LiteLLMGateway(config)

        with patch("litellm.acompletion", side_effect=capture):
            await gw.complete(
                "test/mistral",
                [{"role": "user", "content": "hi"}],
                response_format={"type": "json_schema",
                                 "json_schema": {"name": "x", "schema": {}}},
            )

        assert "response_format" not in captured_kwargs

    @pytest.mark.asyncio
    async def test_non_retryable_error_raises_gateway_error(self) -> None:
        """400 error → GatewayError immediately, no retry."""
        import httpx
        config = _gateway_config(retry={"max_attempts": 3, "base_delay_ms": 1})
        gw = LiteLLMGateway(config)

        req = httpx.Request("POST", "https://api.test.com/v1")
        resp_400 = httpx.Response(400, request=req)
        exc = httpx.HTTPStatusError("bad request", request=req, response=resp_400)

        with (
            patch("litellm.acompletion", side_effect=exc),
            pytest.raises(GatewayError, match="call failed"),
        ):
            await gw.complete(
                "deepseek/deepseek-chat",
                [{"role": "user", "content": "hi"}],
            )

    @pytest.mark.asyncio
    async def test_retryable_error_retries_then_succeeds(self) -> None:
        """503 → retry → success on second attempt."""
        import httpx
        config = _gateway_config(retry={
            "max_attempts": 3, "base_delay_ms": 1, "max_delay_ms": 5,
        })
        gw = LiteLLMGateway(config)

        req = httpx.Request("POST", "https://api.test.com/v1")
        resp_503 = httpx.Response(503, request=req)
        exc = httpx.HTTPStatusError("unavailable", request=req, response=resp_503)
        fake_result = _litellm_result("recovered")

        call_count = 0
        def flaky(**kwargs: Any) -> Any:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise exc
            return fake_result

        with patch("litellm.acompletion", side_effect=flaky):
            resp = await gw.complete(
                "deepseek/deepseek-chat",
                [{"role": "user", "content": "hi"}],
            )

        assert call_count == 2
        assert resp.text == "recovered"

    @pytest.mark.asyncio
    async def test_retry_exhausted_raises_gateway_error(self) -> None:
        """All retries fail → GatewayError."""
        import httpx
        config = _gateway_config(retry={
            "max_attempts": 2, "base_delay_ms": 1, "max_delay_ms": 5,
        })
        gw = LiteLLMGateway(config)

        req = httpx.Request("POST", "https://api.test.com/v1")
        resp_503 = httpx.Response(503, request=req)
        exc = httpx.HTTPStatusError("unavailable", request=req, response=resp_503)

        with (
            patch("litellm.acompletion", side_effect=exc) as mock,
            pytest.raises(GatewayError, match="after 2 attempts"),
        ):
            await gw.complete(
                "deepseek/deepseek-chat",
                [{"role": "user", "content": "hi"}],
            )

        assert mock.call_count == 2

    @pytest.mark.asyncio
    async def test_budget_exhausted_raises_immediately(self) -> None:
        """Quota error → BudgetExhaustedError, no retry."""
        config = _gateway_config(retry={"max_attempts": 3, "base_delay_ms": 1})
        gw = LiteLLMGateway(config)

        exc = RuntimeError("insufficient_quota: you exceeded your limit")

        with (
            patch("litellm.acompletion", side_effect=exc) as mock,
            pytest.raises(BudgetExhaustedError),
        ):
            await gw.complete(
                "deepseek/deepseek-chat",
                [{"role": "user", "content": "hi"}],
            )

        # No retry — single call
        assert mock.call_count == 1

    @pytest.mark.asyncio
    async def test_circuit_breaker_fast_fail_when_open(self) -> None:
        """When circuit breaker is OPEN, returns fast-fail response."""
        cfg_dict = dict(CONFIG_DICT)
        cfg_dict["circuit_breakers"] = {
            "default": {
                "failure_threshold": 1,
                "recovery_timeout_s": 9999,
                "half_open_max_requests": 1,
            },
        }
        config = ChimeraConfig.model_validate(cfg_dict)
        gw = LiteLLMGateway(config)

        # Open the breaker by triggering a failure
        breaker = gw._get_circuit_breaker("openrouter")
        assert breaker is not None
        breaker.on_failure()
        from chimera.circuit_breaker import CircuitState
        assert breaker.state == CircuitState.OPEN

        # Now the next call should fast-fail without hitting litellm
        with patch("litellm.acompletion") as mock:
            resp = await gw.complete(
                "deepseek/deepseek-chat",
                [{"role": "user", "content": "hi"}],
            )

        mock.assert_not_called()
        assert "[circuit open" in resp.text
        assert resp.tokens_input == 0

    @pytest.mark.asyncio
    async def test_circuit_breaker_success_marks_on_success(self) -> None:
        """Successful call marks the circuit breaker on_success."""
        cfg_dict = dict(CONFIG_DICT)
        cfg_dict["circuit_breakers"] = {
            "default": {"failure_threshold": 5, "recovery_timeout_s": 30},
        }
        config = ChimeraConfig.model_validate(cfg_dict)
        gw = LiteLLMGateway(config)

        breaker = gw._get_circuit_breaker("openrouter")
        assert breaker is not None
        breaker.on_failure()
        assert breaker.failure_count == 1

        with patch("litellm.acompletion", return_value=_litellm_result("ok")):
            await gw.complete(
                "deepseek/deepseek-chat",
                [{"role": "user", "content": "hi"}],
            )

        assert breaker.failure_count == 0

    @pytest.mark.asyncio
    async def test_circuit_breaker_failure_on_error(self) -> None:
        """Gateway error marks the circuit breaker on_failure."""
        import httpx
        cfg_dict = dict(CONFIG_DICT)
        cfg_dict["circuit_breakers"] = {
            "default": {"failure_threshold": 5, "recovery_timeout_s": 30},
        }
        config = ChimeraConfig.model_validate(cfg_dict)
        gw = LiteLLMGateway(config)

        breaker = gw._get_circuit_breaker("openrouter")
        assert breaker is not None
        assert breaker.failure_count == 0

        req = httpx.Request("POST", "https://api.test.com/v1")
        resp_400 = httpx.Response(400, request=req)
        exc = httpx.HTTPStatusError("bad", request=req, response=resp_400)

        with patch("litellm.acompletion", side_effect=exc), pytest.raises(GatewayError):
            await gw.complete(
                "deepseek/deepseek-chat",
                [{"role": "user", "content": "hi"}],
            )

        assert breaker.failure_count == 1


class TestGetCircuitBreaker:
    """Cover _get_circuit_breaker lazy-init logic."""

    def test_returns_none_when_no_default_configured(self) -> None:
        config = _gateway_config()  # no circuit_breakers in CONFIG_DICT
        gw = LiteLLMGateway(config)
        assert gw._get_circuit_breaker("nonexistent") is None

    def test_lazy_init_from_default(self) -> None:
        cfg_dict = dict(CONFIG_DICT)
        cfg_dict["circuit_breakers"] = {
            "default": {"failure_threshold": 5, "recovery_timeout_s": 30},
        }
        config = ChimeraConfig.model_validate(cfg_dict)
        gw = LiteLLMGateway(config)

        breaker = gw._get_circuit_breaker("openrouter")
        assert breaker is not None
        assert breaker.name == "openrouter"
        # Cached
        assert gw._get_circuit_breaker("openrouter") is breaker

    def test_explicit_breaker_returned(self) -> None:
        cfg_dict = dict(CONFIG_DICT)
        cfg_dict["circuit_breakers"] = {
            "openrouter": {"failure_threshold": 10, "recovery_timeout_s": 60},
        }
        config = ChimeraConfig.model_validate(cfg_dict)
        gw = LiteLLMGateway(config)

        breaker = gw._get_circuit_breaker("openrouter")
        assert breaker is not None
        assert breaker.name == "openrouter"


class TestGatewayResponseProtocol:
    """Verify GatewayResponse properties and Gateway protocol satisfaction."""

    def test_total_tokens_sums(self) -> None:
        r = GatewayResponse(text="x", model="m", tokens_input=100, tokens_output=200)
        assert r.total_tokens == 300

    def test_default_values(self) -> None:
        r = GatewayResponse(text="x", model="m", tokens_input=0, tokens_output=0)
        assert r.raw is None
        assert r.finish_reason == ""
        assert r.is_empty is False

    def test_empty_text_sets_is_empty_via_build_response(self) -> None:
        result = _litellm_result("")
        resp = _build_response(result, "m")
        assert resp.is_empty is True
