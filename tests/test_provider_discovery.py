"""Tests for provider auto-discovery via models.dev."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from chimera.config import load_config
from chimera.provider_discovery import (
    _mtok_to_per_1k,
    _resolve_model_id,
    discover_providers,
)

# ═══════════════════════════════════════════════════════════════════════════
#  Unit: helpers
# ═══════════════════════════════════════════════════════════════════════════


class TestMtokConversion:
    def test_mtok_to_per_1k(self):
        """$1/MTok → $0.001/1k tokens."""
        assert _mtok_to_per_1k(1.0) == 0.001
        assert _mtok_to_per_1k(0.14) == pytest.approx(0.00014)
        assert _mtok_to_per_1k(15.0) == 0.015

    def test_mtok_zero(self):
        assert _mtok_to_per_1k(0.0) == 0.0


class TestResolveModelId:
    def test_known_map(self):
        """Known models use MODEL_ID_MAP."""
        assert _resolve_model_id("deepseek", "deepseek-v4-flash") == "deepseek/deepseek-v4-flash"
        assert _resolve_model_id("anthropic", "claude-opus-4-8") == "anthropic/claude-opus-4.8"

    def test_fallback_pattern(self):
        """Unknown models fall back to provider/model pattern."""
        assert _resolve_model_id("someprovider", "some-model") == "someprovider/some-model"

    def test_provider_mapped(self):
        """Provider ID is mapped through PROVIDER_ID_MAP."""
        assert _resolve_model_id("moonshotai", "unknown-model") == "moonshot/unknown-model"


# ═══════════════════════════════════════════════════════════════════════════
#  Unit: discover_providers (mocked)
# ═══════════════════════════════════════════════════════════════════════════


SAMPLE_API_JSON = {
    "deepseek": {
        "id": "deepseek",
        "env": ["DEEPSEEK_API_KEY"],
        "api": "https://api.deepseek.com",
        "name": "DeepSeek",
        "models": {
            "deepseek-v4-flash": {
                "id": "deepseek-v4-flash",
                "name": "DeepSeek V4 Flash",
                "cost": {"input": 0.14, "output": 0.28, "cache_read": 0.0028},
            },
            "deepseek-v4-pro": {
                "id": "deepseek-v4-pro",
                "name": "DeepSeek V4 Pro",
                "cost": {"input": 0.55, "output": 2.19, "cache_read": 0.011},
            },
        },
    },
    "google": {
        "id": "google",
        "env": ["GEMINI_API_KEY"],
        "api": "https://generativelanguage.googleapis.com/v1beta",
        "name": "Google",
        "models": {
            "gemini-3-flash-preview": {
                "id": "gemini-3-flash-preview",
                "name": "Gemini 3 Flash",
                "cost": {"input": 0.15, "output": 0.60},
            },
        },
    },
    "unknown-provider": {
        "id": "unknown-provider",
        "env": ["UNKNOWN_KEY"],
        "api": "https://unknown.example.com",
        "name": "Unknown",
        "models": {
            "some-model": {
                "id": "some-model",
                "name": "Some Model",
                "cost": {"input": 1.0, "output": 2.0},
            },
        },
    },
}


class TestDiscoverProviders:
    def test_discovers_available_providers(self, monkeypatch):
        """Providers with API keys set in env are discovered."""
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-key")
        monkeypatch.setenv("GEMINI_API_KEY", "gemini-test-key")
        # UNKNOWN_KEY is NOT set

        with patch(
            "chimera.provider_discovery._fetch_models_dev",
            return_value=SAMPLE_API_JSON,
        ):
            providers, pricing = discover_providers(force_refresh=True)

        assert "deepseek" in providers, f"DeepSeek should be discovered: {providers}"
        assert "google" in providers, f"Google should be discovered: {providers}"
        assert "unknown-provider" not in providers, "Unknown provider should NOT be discovered"

    def test_provider_has_correct_base_url(self, monkeypatch):
        """Discovered providers get correct base_url with /v1 suffix."""
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")

        with patch(
            "chimera.provider_discovery._fetch_models_dev",
            return_value=SAMPLE_API_JSON,
        ):
            providers, _pricing = discover_providers(force_refresh=True)

        assert providers["deepseek"]["base_url"] == "https://api.deepseek.com/v1"

    def test_model_pricing_converted_to_per_1k(self, monkeypatch):
        """Model pricing is converted from $/MTok to $/1k tokens."""
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")

        with patch(
            "chimera.provider_discovery._fetch_models_dev",
            return_value=SAMPLE_API_JSON,
        ):
            _providers, pricing = discover_providers(force_refresh=True)

        v4f = pricing["deepseek/deepseek-v4-flash"]
        assert v4f["input"] == pytest.approx(0.00014)  # 0.14 / 1000
        assert v4f["output"] == pytest.approx(0.00028)  # 0.28 / 1000

    def test_returns_empty_when_no_keys(self, monkeypatch):
        """When no API keys are set, returns empty."""
        # Ensure no keys
        for v in ["DEEPSEEK_API_KEY", "GEMINI_API_KEY", "OPENAI_API_KEY"]:
            monkeypatch.delenv(v, raising=False)

        with patch(
            "chimera.provider_discovery._fetch_models_dev",
            return_value=SAMPLE_API_JSON,
        ):
            providers, pricing = discover_providers(force_refresh=True)

        assert providers == {}, f"Should be empty: {providers}"
        assert pricing == {}, f"Should be empty: {pricing}"

    def test_skips_providers_without_cost_data(self, monkeypatch):
        """Models without cost data are skipped in pricing."""
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")

        data = {
            "deepseek": {
                "id": "deepseek",
                "env": ["DEEPSEEK_API_KEY"],
                "api": "https://api.deepseek.com",
                "models": {
                    "no-cost-model": {
                        "id": "no-cost-model",
                        "name": "No Cost",
                    },
                },
            },
        }

        with patch(
            "chimera.provider_discovery._fetch_models_dev",
            return_value=data,
        ):
            _providers, pricing = discover_providers(force_refresh=True)

        assert "deepseek/no-cost-model" not in pricing

    def test_env_var_with_dollar_brace_skipped(self, monkeypatch):
        """Env vars that look like unresolved ${VAR} are treated as unset."""
        monkeypatch.setenv("DEEPSEEK_API_KEY", "${DEEPSEEK_API_KEY}")
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)

        with patch(
            "chimera.provider_discovery._fetch_models_dev",
            return_value=SAMPLE_API_JSON,
        ):
            providers, _pricing = discover_providers(force_refresh=True)

        assert providers == {}, "Unresolved env var should be treated as unset"


# ═══════════════════════════════════════════════════════════════════════════
#  Integration: config loading with discovery
# ═══════════════════════════════════════════════════════════════════════════


class TestConfigDiscoveryIntegration:
    def test_discovery_adds_providers(self, tmp_path, monkeypatch):
        """When provider_discovery is enabled, discovered providers are added."""
        import yaml

        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")

        doc = {
            "api_keys": {},
            "providers": {},  # Empty!
            "models": {
                "deepseek/deepseek-v4-flash": {
                    "categories": {"code": 88.0},
                    "cost_tier": "budget",
                    "provider": "deepseek",
                },
            },
            "defaults": {
                "dispatcher": "deepseek/deepseek-v4-flash",
                "default_worker": "deepseek/deepseek-v4-flash",
                "default_aggregator": "deepseek/deepseek-v4-flash",
            },
            "formations": {"auto": {"mode": "auto"}},
            "provider_discovery": True,
        }
        path = tmp_path / "chimera.yaml"
        path.write_text(yaml.safe_dump(doc), encoding="utf-8")

        with patch(
            "chimera.provider_discovery._fetch_models_dev",
            return_value=SAMPLE_API_JSON,
        ):
            cfg = load_config(path)

        assert "deepseek" in cfg.providers, (
            f"DeepSeek should be auto-added: {list(cfg.providers.keys())}"
        )

    def test_discovery_respects_existing_providers(self, tmp_path, monkeypatch):
        """Discovered providers do NOT overwrite explicitly configured ones."""
        import yaml

        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")

        doc = {
            "api_keys": {},
            "providers": {
                "deepseek": {"base_url": "https://custom.deepseek.com/v2"},
            },
            "models": {
                "deepseek/deepseek-v4-flash": {
                    "categories": {},
                    "cost_tier": "budget",
                    "provider": "deepseek",
                },
            },
            "defaults": {
                "dispatcher": "deepseek/deepseek-v4-flash",
                "default_worker": "deepseek/deepseek-v4-flash",
                "default_aggregator": "deepseek/deepseek-v4-flash",
            },
            "formations": {"auto": {"mode": "auto"}},
            "provider_discovery": True,
        }
        path = tmp_path / "chimera.yaml"
        path.write_text(yaml.safe_dump(doc), encoding="utf-8")

        with patch(
            "chimera.provider_discovery._fetch_models_dev",
            return_value=SAMPLE_API_JSON,
        ):
            cfg = load_config(path)

        assert cfg.providers["deepseek"].base_url == "https://custom.deepseek.com/v2", (
            "Existing provider should NOT be overwritten"
        )

    def test_discovery_adds_pricing_to_models(self, tmp_path, monkeypatch):
        """Discovered pricing is applied to existing models missing cost fields."""
        import yaml

        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")

        doc = {
            "api_keys": {},
            "providers": {},
            "models": {
                "deepseek/deepseek-v4-flash": {
                    "categories": {"code": 88.0},
                    "cost_tier": "budget",
                    "provider": "deepseek",
                    # No cost_per_1k_input/output!
                },
            },
            "defaults": {
                "dispatcher": "deepseek/deepseek-v4-flash",
                "default_worker": "deepseek/deepseek-v4-flash",
                "default_aggregator": "deepseek/deepseek-v4-flash",
            },
            "formations": {"auto": {"mode": "auto"}},
            "provider_discovery": True,
        }
        path = tmp_path / "chimera.yaml"
        path.write_text(yaml.safe_dump(doc), encoding="utf-8")

        with patch(
            "chimera.provider_discovery._fetch_models_dev",
            return_value=SAMPLE_API_JSON,
        ):
            cfg = load_config(path)

        model = cfg.models["deepseek/deepseek-v4-flash"]
        assert model.cost_per_1k_input == pytest.approx(0.00014), (
            f"Pricing should be auto-filled: {model.cost_per_1k_input}"
        )
        assert model.cost_per_1k_output == pytest.approx(0.00028)

    def test_discovery_does_not_overwrite_explicit_pricing(self, tmp_path, monkeypatch):
        """Existing cost_per_1k_* values are not overwritten by discovery."""
        import yaml

        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")

        doc = {
            "api_keys": {},
            "providers": {},
            "models": {
                "deepseek/deepseek-v4-flash": {
                    "categories": {"code": 88.0},
                    "cost_tier": "budget",
                    "provider": "deepseek",
                    "cost_per_1k_input": 0.0099,
                    "cost_per_1k_output": 0.0299,
                },
            },
            "defaults": {
                "dispatcher": "deepseek/deepseek-v4-flash",
                "default_worker": "deepseek/deepseek-v4-flash",
                "default_aggregator": "deepseek/deepseek-v4-flash",
            },
            "formations": {"auto": {"mode": "auto"}},
            "provider_discovery": True,
        }
        path = tmp_path / "chimera.yaml"
        path.write_text(yaml.safe_dump(doc), encoding="utf-8")

        with patch(
            "chimera.provider_discovery._fetch_models_dev",
            return_value=SAMPLE_API_JSON,
        ):
            cfg = load_config(path)

        model = cfg.models["deepseek/deepseek-v4-flash"]
        assert model.cost_per_1k_input == 0.0099, "Explicit pricing should not be overwritten"
        assert model.cost_per_1k_output == 0.0299

    def test_discovery_best_effort_never_crashes(self, tmp_path, monkeypatch):
        """Network failures during discovery should not crash config loading."""
        import yaml

        doc = {
            "api_keys": {},
            "providers": {},
            "models": {},
            "defaults": {
                "dispatcher": "deepseek/test",
                "default_worker": "deepseek/test",
                "default_aggregator": "deepseek/test",
            },
            "formations": {"auto": {"mode": "auto"}},
            "provider_discovery": True,
        }
        path = tmp_path / "chimera.yaml"
        path.write_text(yaml.safe_dump(doc), encoding="utf-8")

        with patch(
            "chimera.provider_discovery.discover_providers",
            side_effect=ConnectionError("network down"),
        ):
            cfg = load_config(path)  # Must not raise

        assert cfg.providers == {}, "Should have no providers after failed discovery"

    def test_discovery_disabled_respected(self, tmp_path, monkeypatch):
        """When provider_discovery=false, no auto-discovery happens."""
        import yaml

        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")

        doc = {
            "api_keys": {},
            "providers": {},
            "models": {},
            "defaults": {
                "dispatcher": "deepseek/test",
                "default_worker": "deepseek/test",
                "default_aggregator": "deepseek/test",
            },
            "formations": {"auto": {"mode": "auto"}},
            "provider_discovery": False,
        }
        path = tmp_path / "chimera.yaml"
        path.write_text(yaml.safe_dump(doc), encoding="utf-8")

        cfg = load_config(path)
        assert cfg.providers == {}, "Should not have discovered providers"
