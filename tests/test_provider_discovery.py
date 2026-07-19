"""Tests for provider auto-discovery via models.dev."""

from __future__ import annotations

import json
import time
from unittest.mock import MagicMock, patch

import pytest

from chimera.config import load_config
from chimera.provider_discovery import (
    CACHE_TTL,
    _fetch_models_dev,
    _load_cache,
    _mtok_to_per_1k,
    _resolve_model_id,
    _save_cache,
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
        ), patch(
            "chimera.provider_discovery._save_cache",
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
        ), patch(
            "chimera.provider_discovery._save_cache",
        ):
            providers, _pricing = discover_providers(force_refresh=True)

        assert providers["deepseek"]["base_url"] == "https://api.deepseek.com/v1"

    def test_model_pricing_converted_to_per_1k(self, monkeypatch):
        """Model pricing is converted from $/MTok to $/1k tokens."""
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")

        with patch(
            "chimera.provider_discovery._fetch_models_dev",
            return_value=SAMPLE_API_JSON,
        ), patch(
            "chimera.provider_discovery._save_cache",
        ):
            _providers, pricing = discover_providers(force_refresh=True)

        v4f = pricing["deepseek/deepseek-v4-flash"]
        assert v4f["input"] == pytest.approx(0.00014)  # 0.14 / 1000
        assert v4f["output"] == pytest.approx(0.00028)  # 0.28 / 1000

    def test_returns_empty_when_no_keys(self, monkeypatch):
        """When no API keys are set, providers empty but pricing still extracted."""
        # Ensure no keys
        for v in ["DEEPSEEK_API_KEY", "GEMINI_API_KEY", "OPENAI_API_KEY"]:
            monkeypatch.delenv(v, raising=False)

        with patch(
            "chimera.provider_discovery._fetch_models_dev",
            return_value=SAMPLE_API_JSON,
        ), patch(
            "chimera.provider_discovery._save_cache",
        ):
            providers, pricing = discover_providers(force_refresh=True)

        assert providers == {}, f"Should be empty: {providers}"
        # Pricing is always extracted — it's public data, no auth needed
        assert len(pricing) == 4, f"All 4 models should have pricing: {pricing}"
        assert "deepseek/deepseek-v4-flash" in pricing
        assert "deepseek/deepseek-v4-pro" in pricing
        assert "google/gemini-3-flash-preview" in pricing
        assert "unknown-provider/some-model" in pricing

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
        ), patch(
            "chimera.provider_discovery._save_cache",
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
        ), patch(
            "chimera.provider_discovery._save_cache",
        ):
            providers, _pricing = discover_providers(force_refresh=True)

        assert providers == {}, "Unresolved env var should be treated as unset"

    def test_fallback_to_stale_cache_on_fetch_failure(self, monkeypatch, tmp_path):
        """When fetch fails and cache is stale, fall back to stale cache."""
        import time

        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")

        # Write a stale cache (age > CACHE_TTL)
        stale_data = {}
        stale_data.update(SAMPLE_API_JSON)
        stale_data["_fetched_at"] = time.time() - CACHE_TTL - 3600  # 1h past TTL
        cache_path = tmp_path / "stale-cache.json"
        cache_path.write_text(json.dumps(stale_data), encoding="utf-8")

        with patch(
            "chimera.provider_discovery._fetch_models_dev",
            side_effect=ConnectionError("network down"),
        ), patch(
            "chimera.provider_discovery.CACHE_PATH",
            str(cache_path),
        ):
            providers, pricing = discover_providers()

        assert "deepseek" in providers, (
            f"DeepSeek should be discovered from stale cache: {providers}"
        )
        assert len(pricing) == 4, f"Pricing should be extracted from stale cache: {pricing}"


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


# ═══════════════════════════════════════════════════════════════════════════
#  Direct coverage of internals (cache + http helpers)
# ═══════════════════════════════════════════════════════════════════════════


class TestLoadCache:
    def test_missing_cache_file(self, tmp_path, monkeypatch):
        """When the cache file does not exist, returns None."""
        # Point CACHE_PATH at a path inside tmp_path that we never create
        monkeypatch.setattr("chimera.provider_discovery.CACHE_PATH",
                            str(tmp_path / "does-not-exist.json"))
        assert _load_cache() is None

    def test_corrupt_json(self, tmp_path, monkeypatch):
        """Corrupt JSON in cache returns None."""
        cache = tmp_path / "cache.json"
        cache.write_text("{not valid json", encoding="utf-8")
        monkeypatch.setattr("chimera.provider_discovery.CACHE_PATH", str(cache))
        assert _load_cache() is None

    def test_oserror_on_read(self, tmp_path, monkeypatch):
        """OSError reading cache returns None."""
        # A directory masquerading as a file: read_text will raise OSError
        cache = tmp_path / "as_dir"
        cache.mkdir()
        monkeypatch.setattr("chimera.provider_discovery.CACHE_PATH", str(cache))
        assert _load_cache() is None

    def test_non_dict_data(self, tmp_path, monkeypatch, caplog):
        """Cache file containing a JSON list (not dict) returns None."""
        cache = tmp_path / "cache.json"
        cache.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
        monkeypatch.setattr("chimera.provider_discovery.CACHE_PATH", str(cache))
        assert _load_cache() is None

    def test_empty_provider_set(self, tmp_path, monkeypatch):
        """Cache with only _fetched_at → 0 provider entries → returns None."""
        cache = tmp_path / "cache.json"
        cache.write_text(json.dumps({"_fetched_at": time.time()}), encoding="utf-8")
        monkeypatch.setattr("chimera.provider_discovery.CACHE_PATH", str(cache))
        assert _load_cache() is None

    def test_valid_cache(self, tmp_path, monkeypatch):
        """Valid cache within TTL is returned unchanged (minus _fetched_at)."""
        cache = tmp_path / "cache.json"
        data = {"deepseek": {"id": "deepseek", "env": ["K"], "models": {"x": {}}},
                "_fetched_at": time.time()}
        cache.write_text(json.dumps(data), encoding="utf-8")
        monkeypatch.setattr("chimera.provider_discovery.CACHE_PATH", str(cache))
        loaded = _load_cache()
        assert loaded is not None
        assert "deepseek" in loaded

    def test_stale_cache_respects_ttl_by_default(self, tmp_path, monkeypatch):
        """Without ignore_ttl, stale cache returns None."""
        cache = tmp_path / "cache.json"
        data = {"deepseek": {"id": "deepseek", "env": ["K"], "models": {"x": {}}},
                "_fetched_at": time.time() - CACHE_TTL - 100}
        cache.write_text(json.dumps(data), encoding="utf-8")
        monkeypatch.setattr("chimera.provider_discovery.CACHE_PATH", str(cache))
        assert _load_cache() is None

    def test_stale_cache_usable_with_ignore_ttl(self, tmp_path, monkeypatch):
        """With ignore_ttl=True, stale cache is still returned."""
        cache = tmp_path / "cache.json"
        data = {"deepseek": {"id": "deepseek", "env": ["K"], "models": {"x": {}}},
                "_fetched_at": time.time() - CACHE_TTL - 100}
        cache.write_text(json.dumps(data), encoding="utf-8")
        monkeypatch.setattr("chimera.provider_discovery.CACHE_PATH", str(cache))
        loaded = _load_cache(ignore_ttl=True)
        assert loaded is not None


class TestSaveCache:
    def test_save_writes_atomic(self, tmp_path, monkeypatch):
        """``_save_cache`` writes a JSON file with _fetched_at, atomically."""
        cache = tmp_path / "sub" / "cache.json"
        monkeypatch.setattr("chimera.provider_discovery.CACHE_PATH", str(cache))
        data = {"deepseek": {"id": "deepseek"}}
        before = time.time()
        _save_cache(data)
        after = time.time()
        assert cache.is_file()
        saved = json.loads(cache.read_text(encoding="utf-8"))
        assert "_fetched_at" in saved
        assert before <= saved["_fetched_at"] <= after
        assert saved["deepseek"] == {"id": "deepseek"}


class TestFetchModelsDev:
    def test_fetch_uses_urllib(self):
        """``_fetch_models_dev`` calls urllib.request.urlopen and parses JSON."""
        fake_resp = MagicMock()
        fake_resp.read.return_value = b'{"hello": "world"}'
        fake_resp.__enter__ = lambda self_: self_
        fake_resp.__exit__ = lambda self_, *a: None

        with patch("urllib.request.urlopen", return_value=fake_resp) as urlopen_mock:
            data = _fetch_models_dev()

        assert data == {"hello": "world"}
        urlopen_mock.assert_called_once()
        # The Request object should target the canonical URL.
        req = urlopen_mock.call_args.args[0]
        assert req.full_url == "https://models.dev/api.json"
        assert "Chimera/" in req.headers["User-agent"]


class TestDiscoverProvidersEdgeCases:
    def test_skip_internal_fetched_at_key(self, monkeypatch):
        """``_fetched_at`` key in data dict is treated as metadata, not a provider."""
        # Provide data with _fetched_at in it; the provider loop must skip it.
        data = {
            "deepseek": {
                "id": "deepseek",
                "env": ["DEEPSEEK_API_KEY"],
                "api": "https://api.deepseek.com",
                "models": {},
            },
            "_fetched_at": time.time(),
        }
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        with patch("chimera.provider_discovery._fetch_models_dev",
                   return_value=data), patch("chimera.provider_discovery._save_cache"):
            providers, _pricing = discover_providers(force_refresh=True)
        assert "deepseek" in providers

    def test_provider_value_not_a_dict(self, monkeypatch):
        """``md_provider`` that isn't a dict is skipped over."""
        data = {"bogus_provider": "not a dict"}
        with patch("chimera.provider_discovery._fetch_models_dev",
                   return_value=data), patch("chimera.provider_discovery._save_cache"):
            providers, pricing = discover_providers(force_refresh=True)
        assert providers == {}
        assert pricing == {}

    def test_model_value_not_a_dict(self, monkeypatch):
        """When models dict has a non-dict entry, skip it in pricing extraction."""
        data = {
            "deepseek": {
                "id": "deepseek",
                "env": ["DEEPSEEK_API_KEY"],
                "api": "https://api.deepseek.com",
                "models": {"good-model": "not a dict"},
            },
        }
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        with patch("chimera.provider_discovery._fetch_models_dev",
                   return_value=data), patch("chimera.provider_discovery._save_cache"):
            providers, pricing = discover_providers(force_refresh=True)
        assert pricing == {}
        assert "deepseek" in providers

    def test_cost_field_not_a_dict(self, monkeypatch):
        """If ``cost`` is not a dict on a model, skip pricing extraction for it."""
        data = {
            "deepseek": {
                "id": "deepseek",
                "env": ["DEEPSEEK_API_KEY"],
                "api": "https://api.deepseek.com",
                "models": {
                    "weird-model": {
                        "id": "weird-model",
                        "cost": "not a dict",
                    },
                },
            },
        }
        with patch("chimera.provider_discovery._fetch_models_dev",
                   return_value=data), patch("chimera.provider_discovery._save_cache"):
            _providers, pricing = discover_providers(force_refresh=True)
        assert pricing == {}

    def test_env_var_field_is_string_not_list(self, monkeypatch):
        """Some providers may expose ``env`` as a single string — should still work."""
        data = {
            "deepseek": {
                "id": "deepseek",
                "env": "DEEPSEEK_API_KEY",  # string, not list
                "api": "https://api.deepseek.com",
                "models": {},
            },
        }
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        with patch("chimera.provider_discovery._fetch_models_dev",
                   return_value=data), patch("chimera.provider_discovery._save_cache"):
            providers, _pricing = discover_providers(force_refresh=True)
        assert "deepseek" in providers
        assert providers["deepseek"]["api_key_env"] == "DEEPSEEK_API_KEY"

    def test_env_var_field_falsy(self, monkeypatch):
        """If ``env`` is some falsy value, the list-coercion fallback yields []
        and no env var is checked."""
        data = {
            "deepseek": {
                "id": "deepseek",
                "env": None,  # falsy
                "api": "https://api.deepseek.com",
                "models": {},
            },
        }
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        with patch("chimera.provider_discovery._fetch_models_dev",
                   return_value=data), patch("chimera.provider_discovery._save_cache"):
            providers, _pricing = discover_providers(force_refresh=True)
        # Without any env match and without api_keys, provider is not registered.
        assert "deepseek" not in providers

    def test_api_keys_fallback_when_env_unset(self, monkeypatch):
        """When env var is unset, the api_keys dict provides the key."""
        data = {
            "deepseek": {
                "id": "deepseek",
                "env": ["DEEPSEEK_API_KEY"],
                "api": "https://api.deepseek.com",
                "models": {},
            },
        }
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        with patch("chimera.provider_discovery._fetch_models_dev",
                   return_value=data), patch("chimera.provider_discovery._save_cache"):
            providers, _pricing = discover_providers(
                force_refresh=True, api_keys={"deepseek": "yaml-supplied-key"},
            )
        assert "deepseek" in providers
        assert providers["deepseek"]["api_key_env"] == "DEEPSEEK_API_KEY"

    def test_fetch_failure_without_stale_cache_returns_empty(self, monkeypatch, tmp_path):
        """When network fails AND no stale cache exists, returns ({},{})."""
        # Ensure no cache
        monkeypatch.setattr("chimera.provider_discovery.CACHE_PATH",
                            str(tmp_path / "no-cache-here.json"))
        with patch("chimera.provider_discovery._fetch_models_dev",
                   side_effect=ConnectionError("network down")):
            providers, pricing = discover_providers(force_refresh=True)
        assert providers == {}
        assert pricing == {}
