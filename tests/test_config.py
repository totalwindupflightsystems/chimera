"""Tests for config loading, env substitution, and helpers."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from chimera.config import (
    DEFAULT_COST_RATES,
    ChimeraConfig,
    ModelEntry,
    find_config_path,
    load_config,
)


def test_config_loads_from_dict(config: ChimeraConfig) -> None:
    assert "zai-coding-plan/glm-5.2" in config.models
    assert config.defaults.dispatcher == "zai-coding-plan/glm-5.2"
    assert config.formations["auto"].is_auto is True
    assert config.formations["simple"].workers == 2


def test_catalog_description_contains_weights(config: ChimeraConfig) -> None:
    desc = config.catalog_description()
    assert "zai-coding-plan/glm-5.2" in desc
    assert "deepseek/deepseek-chat" in desc
    # DeepSeek's strongest category (code=0.95) should be listed
    assert "code=0.95" in desc


def test_resolve_model_alias(config: ChimeraConfig) -> None:
    assert config.resolve_model_alias("default") == config.defaults.default_aggregator
    assert config.resolve_model_alias("default_worker") == config.defaults.default_worker
    assert config.resolve_model_alias("deepseek/deepseek-chat") == "deepseek/deepseek-chat"


def test_get_model_raises_for_unknown(config: ChimeraConfig) -> None:
    with pytest.raises(KeyError):
        config.get_model("does/not-exist")


def test_cost_rates_by_tier(config: ChimeraConfig) -> None:
    budget = config.get_model("deepseek/deepseek-chat")
    premium = config.get_model("zai-coding-plan/glm-5.2")
    assert budget.cost_rate_input() == DEFAULT_COST_RATES["budget"][0]
    assert premium.cost_rate_output() == DEFAULT_COST_RATES["premium"][1]
    # explicit override wins
    override = ModelEntry(categories={}, cost_tier="budget", provider="x",
                          cost_per_1k_input=0.5, cost_per_1k_output=1.5)
    assert override.cost_rate_input() == 0.5
    assert override.cost_rate_output() == 1.5


def test_env_substitution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHIMERA_TEST_KEY", "super-secret")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "ds-key")
    doc = {
        "api_keys": {"deepseek": "${DEEPSEEK_API_KEY}",
                      "other": "${CHIMERA_TEST_KEY}"},
        "providers": {"openrouter": {"base_url": "https://x/${MISSING_VAR}/v1"}},
        "models": {
            "deepseek/deepseek-chat": {
                "categories": {"code": 0.9}, "cost_tier": "budget", "provider": "openrouter"
            }
        },
        "defaults": {"dispatcher": "deepseek/deepseek-chat",
                     "default_worker": "deepseek/deepseek-chat",
                     "default_aggregator": "deepseek/deepseek-chat"},
        "formations": {"auto": {"mode": "auto"}},
    }
    path = tmp_path / "chimera.yaml"
    path.write_text(yaml.safe_dump(doc), encoding="utf-8")

    cfg = load_config(path)
    assert cfg.api_keys["deepseek"] == "ds-key"
    assert cfg.api_keys["other"] == "super-secret"
    # missing env var substitutes to empty string
    assert cfg.providers["openrouter"].base_url == "https://x//v1"


def test_load_config_from_file(config_file: Path) -> None:
    cfg = load_config(config_file)
    assert cfg.defaults.dispatcher == "zai-coding-plan/glm-5.2"
    assert set(cfg.formations) == {"auto", "simple", "debate", "audit"}


def test_find_config_path_walks_upwards(tmp_path: Path) -> None:
    (tmp_path / "chimera.yaml").write_text(
        'defaults: {dispatcher: "deepseek/deepseek-chat", '
        'default_worker: "deepseek/deepseek-chat", '
        'default_aggregator: "deepseek/deepseek-chat"}\n'
        'models:\n  "deepseek/deepseek-chat": {categories: {}, cost_tier: budget, provider: deepseek}\n'
        'formations: {auto: {mode: auto}}\n',
        encoding="utf-8",
    )
    nested = tmp_path / "a" / "b" / "c"
    nested.mkdir(parents=True)
    assert find_config_path(nested) == tmp_path / "chimera.yaml"


def test_find_config_path_raises_when_missing(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        find_config_path(tmp_path)


def test_load_config_rejects_non_mapping(tmp_path: Path) -> None:
    path = tmp_path / "chimera.yaml"
    path.write_text("- just\n- a\n- list\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_config(path)
