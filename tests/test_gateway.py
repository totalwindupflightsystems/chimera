"""Tests for the provider gateway model resolution."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from chimera.config import ModelEntry
from chimera.gateway import GatewayResponse, LiteLLMGateway, resolve_litellm_model


def _entry(provider: str, litellm_model: str | None = None) -> ModelEntry:
    return ModelEntry(categories={}, cost_tier="standard", provider=provider,
                      litellm_model=litellm_model)


def test_zai_provider_uses_openai_compat_with_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZAI_API_KEY", "zai-key")
    model, extra = resolve_litellm_model("zai-coding-plan/glm-5.2", _entry("zai"))
    # The catalog id is stripped to the bare model name the z.ai API expects.
    assert model == "openai/glm-5.2"
    assert extra["api_base"] == "https://api.z.ai/api/coding/paas/v4"
    assert extra["custom_llm_provider"] == "openai"
    assert extra["api_key"] == "zai-key"


def test_openrouter_provider_ensures_prefix() -> None:
    model, extra = resolve_litellm_model("deepseek/deepseek-chat", _entry("openrouter"))
    assert model == "openrouter/deepseek/deepseek-chat"
    assert extra == {}
    # already-prefixed names are left alone
    model2, _ = resolve_litellm_model("openrouter/google/gemini-2.5-flash", _entry("openrouter"))
    assert model2 == "openrouter/google/gemini-2.5-flash"


def test_anthropic_and_deepseek_prefixes() -> None:
    m1, _ = resolve_litellm_model("claude-sonnet-4", _entry("anthropic"))
    assert m1 == "anthropic/claude-sonnet-4"
    m2, extra = resolve_litellm_model("deepseek-chat", _entry("deepseek"))
    assert m2 == "openai/deepseek-chat"
    assert extra.get("custom_llm_provider") == "openai"


def test_explicit_litellm_model_override() -> None:
    model, extra = resolve_litellm_model(
        "anything", _entry("zai", litellm_model="openrouter/some/model")
    )
    assert model == "openrouter/some/model"
    assert extra == {}


def test_litellm_gateway_satisfies_protocol(config) -> None:  # type: ignore[no-untyped-def]
    gw = LiteLLMGateway(config)
    assert isinstance(gw, LiteLLMGateway)
    # GatewayResponse totals
    r = GatewayResponse(text="hi", model="m", tokens_input=3, tokens_output=5)
    assert r.total_tokens == 8


def test_extract_text_handles_missing_content() -> None:
    from chimera.gateway import _extract_text

    empty = SimpleNamespace(choices=[])
    assert _extract_text(empty) == ""
    no_msg = SimpleNamespace(choices=[SimpleNamespace()])
    assert _extract_text(no_msg) == ""
    with_content = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="hello"))]
    )
    assert _extract_text(with_content) == "hello"


# --------------------------------------------------------------------------- #
# C3 — Token limit handling (finish_reason="length")
# --------------------------------------------------------------------------- #


def test_token_limit_detection_logs_warning(capsys) -> None:
    """C3: finish_reason='length' should log a WARNING with model and tokens."""

    from chimera.gateway import _build_response

    # Simulate a LiteLLM result with finish_reason="length"
    result = SimpleNamespace(
        choices=[
            SimpleNamespace(
                finish_reason="length",
                message=SimpleNamespace(content="truncated output..."),
            )
        ],
        usage=SimpleNamespace(prompt_tokens=500, completion_tokens=4096),
    )
    response = _build_response(result, "deepseek/deepseek-chat")
    assert response.finish_reason == "length"
    assert not response.is_empty
    # structlog writes to stdout — check captured output
    captured = capsys.readouterr().out
    assert "token_limit_reached" in captured, f"Expected token_limit_reached in stdout, got: {captured}"


def test_token_limit_field_on_response() -> None:
    """C3: GatewayResponse carries finish_reason from the provider."""
    from chimera.gateway import GatewayResponse

    r = GatewayResponse(
        text="partial", model="m", tokens_input=100, tokens_output=4096,
        finish_reason="length",
    )
    assert r.finish_reason == "length"
    assert r.is_empty is False


def test_normal_finish_reason_does_not_warn(caplog) -> None:
    """C3: finish_reason='stop' should NOT log a warning."""
    import logging

    from chimera.gateway import _build_response

    caplog.set_level(logging.WARNING)

    result = SimpleNamespace(
        choices=[
            SimpleNamespace(
                finish_reason="stop",
                message=SimpleNamespace(content="normal output"),
            )
        ],
        usage=SimpleNamespace(prompt_tokens=50, completion_tokens=200),
    )
    response = _build_response(result, "m")
    assert response.finish_reason == "stop"
    assert not response.is_empty
    # No token limit warning
    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert not any("token_limit_reached" in str(r.message) for r in warnings)


# --------------------------------------------------------------------------- #
# C4 — Empty/null response handling
# --------------------------------------------------------------------------- #


def test_extract_text_empty_content_no_crash() -> None:
    """C4: empty string content should not crash, returns empty string."""
    from chimera.gateway import _extract_text

    # Empty content
    result = SimpleNamespace(
        choices=[
            SimpleNamespace(
                finish_reason="stop",
                message=SimpleNamespace(content=""),
            )
        ],
    )
    assert _extract_text(result) == ""


def test_extract_text_null_content_no_crash() -> None:
    """C4: None/null content should not crash, returns empty string."""
    from chimera.gateway import _extract_text

    result = SimpleNamespace(
        choices=[
            SimpleNamespace(
                finish_reason="stop",
                message=SimpleNamespace(content=None),
            )
        ],
    )
    assert _extract_text(result) == ""


def test_extract_text_missing_choices_no_crash() -> None:
    """C4: missing choices array should not crash, returns empty string."""
    from chimera.gateway import _extract_text

    # No choices attribute
    result = SimpleNamespace()
    assert _extract_text(result) == ""

    # choices is None
    result2 = SimpleNamespace(choices=None)
    assert _extract_text(result2) == ""


def test_extract_text_stop_with_empty_content_is_empty_flag() -> None:
    """C4: finish_reason='stop' with empty content should set is_empty=True."""
    from chimera.gateway import _build_response

    result = SimpleNamespace(
        choices=[
            SimpleNamespace(
                finish_reason="stop",
                message=SimpleNamespace(content=""),
            )
        ],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=0),
    )
    response = _build_response(result, "m")
    assert response.is_empty is True
    assert response.finish_reason == "stop"
    assert response.text == ""


def test_extract_text_reasoning_content_fallback() -> None:
    """C4: content is empty but reasoning_content has text — should extract it."""
    from chimera.gateway import _extract_text

    result = SimpleNamespace(
        choices=[
            SimpleNamespace(
                finish_reason="stop",
                message=SimpleNamespace(content=None, reasoning_content="actual reasoning text"),
            )
        ],
    )
    assert _extract_text(result) == "actual reasoning text"


# --------------------------------------------------------------------------- #
# C7 — Budget exhaustion error detection
# --------------------------------------------------------------------------- #


def test_is_budget_exhausted_detects_quota_errors() -> None:
    """C7: _is_budget_exhausted returns True for budget/quota exhaustion errors."""
    from chimera.gateway import _is_budget_exhausted

    assert _is_budget_exhausted("insufficient_quota: you exceeded your limit")
    assert _is_budget_exhausted("billing issue: payment required")
    assert _is_budget_exhausted("Error: you exceeded your current quota")
    assert _is_budget_exhausted("quota exceeded for model gpt-4")
    assert _is_budget_exhausted("insufficient_credits available")
    assert _is_budget_exhausted("spending limit reached")


def test_is_budget_exhausted_ignores_normal_errors() -> None:
    """C7: _is_budget_exhausted returns False for non-budget errors."""
    from chimera.gateway import _is_budget_exhausted

    assert not _is_budget_exhausted("authentication failed")
    assert not _is_budget_exhausted("invalid api key")
    assert not _is_budget_exhausted("rate limited temporarily")
    assert not _is_budget_exhausted("internal server error")
    assert not _is_budget_exhausted("connection timeout")


def test_budget_exhausted_error_has_model_and_provider() -> None:
    """C7: BudgetExhaustedError carries model, provider, and details."""
    from chimera.exceptions import BudgetExhaustedError

    exc = BudgetExhaustedError(
        model="deepseek/deepseek-chat",
        provider="openrouter",
        details="insufficient_quota: limit $10 reached",
    )
    assert "deepseek/deepseek-chat" in str(exc)
    assert "openrouter" in str(exc)
    assert "insufficient_quota" in str(exc)
    assert exc.model == "deepseek/deepseek-chat"
    assert exc.provider == "openrouter"


# --------------------------------------------------------------------------- #
# F8: Anthropic → OpenRouter fallback
# --------------------------------------------------------------------------- #


def test_anthropic_fallback_to_openrouter() -> None:
    """F8: Anthropic models route through OpenRouter when fallback_provider=openrouter."""
    model, extra = resolve_litellm_model(
        "anthropic/claude-sonnet-4.6",
        _entry("anthropic"),
        api_key="sk-or-v1-test-key",
        fallback_provider="openrouter",
    )
    assert model == "openrouter/anthropic/claude-sonnet-4.6"
    assert extra.get("api_key") == "sk-or-v1-test-key"


def test_anthropic_no_fallback_without_provider() -> None:
    """F8: Without fallback_provider, Anthropic models resolve natively."""
    model, extra = resolve_litellm_model(
        "anthropic/claude-sonnet-4.6",
        _entry("anthropic"),
    )
    assert model == "anthropic/claude-sonnet-4.6"
    assert "api_key" not in extra
