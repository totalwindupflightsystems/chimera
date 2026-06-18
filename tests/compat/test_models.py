"""Live smoke tests — one per model family.

Each test sends a trivial prompt and asserts:
* No exception / connection error
* A non-empty text response
* Total round-trip < 30 seconds
"""

from __future__ import annotations

import time

import pytest

from chimera.gateway import LiteLLMGateway

# ── Shared prompt used by every model ──────────────────────────────────────
SIMPLE_PROMPT: list[dict[str, str]] = [
    {"role": "user", "content": "Reply with exactly one word: hello"},
]

# ── Per-model fixture that yields the model name and optional API key env ──
_MODEL_PARAMS: list[dict[str, str]] = [
    {"model": "deepseek-v4-flash", "env_var": "DEEPSEEK_API_KEY"},
    {"model": "deepseek-v4-pro", "env_var": "DEEPSEEK_API_KEY"},
    {"model": "glm-5.2", "env_var": "ZAI_API_KEY"},
    {"model": "claude-sonnet-4", "env_var": "ANTHROPIC_API_KEY"},
    {"model": "kimi-k2.7", "env_var": "MOONSHOT_API_KEY"},
    {"model": "minimax-m3", "env_var": "MINIMAX_API_KEY"},
    {"model": "gemini-3-flash-preview", "env_var": "GEMINI_API_KEY"},
]

# ── Helpers ────────────────────────────────────────────────────────────────


def _skip_if_missing_env(env_var: str, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Skip the test if the required API key env var is not set."""
    import os

    if not os.environ.get(env_var):
        pytest.skip(f"${env_var} not set — cannot run live compat test")


async def _smoke_one(gateway_instance: LiteLLMGateway, model: str) -> str:
    """Call *model* with a simple prompt and return the extracted text."""
    t0 = time.perf_counter()
    response = await gateway_instance.complete(
        model,
        SIMPLE_PROMPT,
        temperature=0.0,
    )
    elapsed = time.perf_counter() - t0

    # Assertions
    assert isinstance(response.text, str), f"text must be str, got {type(response.text)}"
    assert response.text.strip(), f"response text empty for {model}"
    assert elapsed < 30.0, f"{model} took {elapsed:.1f}s (limit 30s)"

    return response.text.strip()


# ═══════════════════════════════════════════════════════════════════════════
#  Smoke tests
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.slow
@pytest.mark.compat
@pytest.mark.asyncio
async def test_deepseek_v4_flash(gateway: LiteLLMGateway, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """DeepSeek V4 Flash — budget reasoning model."""
    _skip_if_missing_env("DEEPSEEK_API_KEY", monkeypatch)
    text = await _smoke_one(gateway, "deepseek-v4-flash")
    # DeepSeek V4 may return reasoning before content; either is acceptable
    assert len(text) > 0


@pytest.mark.slow
@pytest.mark.compat
@pytest.mark.asyncio
async def test_deepseek_v4_pro(gateway: LiteLLMGateway, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """DeepSeek V4 Pro — premium reasoning model."""
    _skip_if_missing_env("DEEPSEEK_API_KEY", monkeypatch)
    text = await _smoke_one(gateway, "deepseek-v4-pro")
    assert len(text) > 0


@pytest.mark.slow
@pytest.mark.compat
@pytest.mark.asyncio
async def test_glm_5_2(gateway: LiteLLMGateway, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """GLM-5.2 via Z.AI coding endpoint."""
    _skip_if_missing_env("ZAI_API_KEY", monkeypatch)
    text = await _smoke_one(gateway, "glm-5.2")
    assert len(text) > 0


@pytest.mark.slow
@pytest.mark.compat
@pytest.mark.asyncio
async def test_claude_sonnet_4(gateway: LiteLLMGateway, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Claude Sonnet 4 via Anthropic API."""
    _skip_if_missing_env("ANTHROPIC_API_KEY", monkeypatch)
    text = await _smoke_one(gateway, "claude-sonnet-4")
    assert len(text) > 0


@pytest.mark.slow
@pytest.mark.compat
@pytest.mark.asyncio
async def test_kimi_k2_7(gateway: LiteLLMGateway, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Kimi K2.7 via Moonshot API."""
    _skip_if_missing_env("MOONSHOT_API_KEY", monkeypatch)
    text = await _smoke_one(gateway, "kimi-k2.7")
    assert len(text) > 0


@pytest.mark.slow
@pytest.mark.compat
@pytest.mark.asyncio
async def test_minimax_m3(gateway: LiteLLMGateway, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """MiniMax M3 via MiniMax API."""
    _skip_if_missing_env("MINIMAX_API_KEY", monkeypatch)
    text = await _smoke_one(gateway, "minimax-m3")
    assert len(text) > 0


@pytest.mark.slow
@pytest.mark.compat
@pytest.mark.asyncio
async def test_gemini_3_flash_preview(gateway: LiteLLMGateway, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Gemini 3 Flash Preview via Google API."""
    _skip_if_missing_env("GEMINI_API_KEY", monkeypatch)
    text = await _smoke_one(gateway, "gemini-3-flash-preview")
    assert len(text) > 0
