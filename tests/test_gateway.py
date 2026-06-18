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
