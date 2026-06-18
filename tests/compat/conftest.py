"""Compat test fixtures — guarded by ``--run-compat`` flag.

These tests call live APIs. Without ``--run-compat`` they are automatically
skipped so normal ``pytest`` runs stay fast and offline.
"""

from __future__ import annotations

from typing import Any

import pytest

from chimera.config import ChimeraConfig
from chimera.gateway import LiteLLMGateway

# A minimal config exposing every model family we want to smoke-test.
# Model keys are the names passed to gateway.complete().
# Some models use ``litellm_model`` to bypass gateway-native routing and
# hit the exact LiteLLM provider string required.
COMPAT_CONFIG_DICT: dict[str, Any] = {
    "providers": {
        "deepseek": {"base_url": "https://api.deepseek.com/v1"},
        "zai": {"base_url": "https://api.z.ai/api/coding/paas/v4"},
        "anthropic": {"base_url": "https://api.anthropic.com/v1"},
    },
    "models": {
        # ── DeepSeek family (native routing → openai/ prefix + deepseek api_base) ──
        "deepseek-v4-flash": {
            "categories": {"code": 0.95},
            "cost_tier": "budget",
            "provider": "deepseek",
        },
        "deepseek-v4-pro": {
            "categories": {"code": 0.96},
            "cost_tier": "budget",
            "provider": "deepseek",
        },
        # ── GLM-5.2 via Z.AI (native gateway routing → openai/ + api_base) ──
        "glm-5.2": {
            "categories": {"code": 0.92},
            "cost_tier": "premium",
            "provider": "zai",
        },
        # ── Anthropic Claude ──
        "claude-sonnet-4": {
            "categories": {"code": 0.90},
            "cost_tier": "premium",
            "provider": "anthropic",
        },
        # ── Moonshot Kimi K2.7 ──
        "kimi-k2.7": {
            "categories": {"code": 0.90},
            "cost_tier": "premium",
            "provider": "moonshotai",
            "litellm_model": "moonshot/kimi-k2.7",
        },
        # ── MiniMax M3 ──
        "minimax-m3": {
            "categories": {"code": 0.88},
            "cost_tier": "standard",
            "provider": "minimax",
            "litellm_model": "minimax/minimax-m3",
        },
        # ── Google Gemini 3 Flash ──
        "gemini-3-flash-preview": {
            "categories": {"code": 0.70},
            "cost_tier": "budget",
            "provider": "google",
            "litellm_model": "gemini/gemini-3-flash-preview",
        },
    },
    "defaults": {
        "dispatcher": "deepseek-v4-flash",
        "default_worker": "deepseek-v4-flash",
        "default_aggregator": "deepseek-v4-flash",
    },
    "observability": {"log_level": "warning", "trace_enabled": False},
    "server": {"host": "127.0.0.1", "port": 8000},
}


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-compat",
        action="store_true",
        default=False,
        help="Run live model compatibility smoke tests",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "compat: live model compatibility smoke test")
    config.addinivalue_line("markers", "slow: tests that call remote APIs")


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item],
) -> None:
    if config.getoption("--run-compat"):
        return  # allow everything
    skip_compat = pytest.mark.skip(reason="need --run-compat flag to run live compat tests")
    for item in items:
        if "compat" in item.keywords:
            item.add_marker(skip_compat)


@pytest.fixture
def compat_config() -> ChimeraConfig:
    """Minimal config exposing every model in the compat smoke suite."""
    return ChimeraConfig.model_validate(COMPAT_CONFIG_DICT)


@pytest.fixture
def gateway(compat_config: ChimeraConfig) -> LiteLLMGateway:
    """Production gateway wired to the compat config (real API calls)."""
    return LiteLLMGateway(compat_config)
