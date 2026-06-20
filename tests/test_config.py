"""Tests for config loading, env substitution, and helpers."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from chimera.config import (
    DEFAULT_COST_RATES,
    ChimeraConfig,
    FormationPreset,
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
    models_line = (
        'models:\n'
        '  "deepseek/deepseek-chat": '
        "{categories: {}, cost_tier: budget, provider: deepseek}\n"
    )
    (tmp_path / "chimera.yaml").write_text(
        'defaults: {dispatcher: "deepseek/deepseek-chat", '
        'default_worker: "deepseek/deepseek-chat", '
        'default_aggregator: "deepseek/deepseek-chat"}\n'
        + models_line
        + "formations: {auto: {mode: auto}}\n",
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


# --------------------------------------------------------------------------- #
# Config-defined custom formations (Feature 3)
# --------------------------------------------------------------------------- #


def test_formation_preset_accepts_dag_field() -> None:
    """FormationPreset carries an optional `dag` mapping."""
    preset = FormationPreset(
        dag={
            "stages": [
                {"id": "w", "kind": "worker", "model": "m"},
                {"id": "a", "kind": "aggregator", "model": "m", "depends_on": ["w"]},
            ],
            "edges": [["w", "a"]],
        }
    )
    assert preset.has_dag is True
    assert preset.is_auto is False
    assert preset.dag is not None
    assert preset.dag["stages"][0]["id"] == "w"


def test_formation_preset_without_dag_has_dag_false() -> None:
    assert FormationPreset(workers=2, aggregator="default").has_dag is False
    assert FormationPreset(mode="auto").has_dag is False
    assert FormationPreset().has_dag is False


def test_config_dag_preset_round_trips(config_file: Path) -> None:
    """A config-defined DAG formation loads through load_config unchanged."""
    # add a dag preset to the raw dict via a fresh file
    import copy
    raw = yaml.safe_load(config_file.read_text(encoding="utf-8"))
    raw2 = copy.deepcopy(raw)
    raw2["formations"]["custom-chain"] = {
        "dag": {
            "stages": [
                {"id": "analyzer", "kind": "worker",
                 "model": "deepseek/deepseek-chat"},
                {"id": "finalizer", "kind": "aggregator",
                 "model": "zai-coding-plan/glm-5.2", "depends_on": ["analyzer"]},
            ],
            "edges": [["analyzer", "finalizer"]],
        }
    }
    custom_path = config_file.parent / "chimera_custom.yaml"
    custom_path.write_text(yaml.safe_dump(raw2), encoding="utf-8")
    cfg2 = load_config(custom_path)
    preset = cfg2.formations["custom-chain"]
    assert preset.has_dag is True
    assert preset.dag is not None
    assert preset.dag["stages"][0]["id"] == "analyzer"


def test_backward_compat_legacy_presets_still_present(config: ChimeraConfig) -> None:
    """simple/debate/audit remain available without any config changes."""
    assert set(config.formations) >= {"auto", "simple", "debate", "audit"}
    # Legacy structural fields still populated (no dag).
    assert config.formations["simple"].has_dag is False
    assert config.formations["debate"].workers == 3
    assert config.formations["audit"].audit is not None


# ── Env-var override tests ──────────────────────────────────────────────


class TestEnvOverrides:
    """Verify that ``_apply_env_overrides`` bridges env vars ↔ config."""

    @staticmethod
    def _with_env(config: ChimeraConfig, **env: str) -> ChimeraConfig:
        import os as _os

        from chimera.config import _apply_env_overrides

        # Clear any real env vars that would conflict with test mocks
        conflicts = {
            "OPENROUTER_API_KEY": _os.environ.get("OPENROUTER_API_KEY"),
        }
        for k in conflicts:
            _os.environ.pop(k, None)

        saved = {}
        try:
            for k, v in env.items():
                saved[k] = _os.environ.get(k)
                _os.environ[k] = v
            _apply_env_overrides(config)
            return config
        finally:
            for k, v in saved.items():
                if v is None:
                    _os.environ.pop(k, None)
                else:
                    _os.environ[k] = v
            # Restore conflicts
            for k, v in conflicts.items():
                if v is not None:
                    _os.environ[k] = v

    def test_host_port(self, config: ChimeraConfig) -> None:
        cfg = self._with_env(config, CHIMERA_HOST="1.2.3.4", CHIMERA_PORT="9999")
        assert cfg.server.host == "1.2.3.4"
        assert cfg.server.port == 9999

    def test_dispatcher_worker_aggregator(self, config: ChimeraConfig) -> None:
        cfg = self._with_env(
            config,
            CHIMERA_DISPATCHER="openrouter/a",
            CHIMERA_WORKER="openrouter/b",
            CHIMERA_AGGREGATOR="openrouter/c",
        )
        assert cfg.defaults.dispatcher == "openrouter/a"
        assert cfg.defaults.default_worker == "openrouter/b"
        assert cfg.defaults.default_aggregator == "openrouter/c"

    def test_log_level(self, config: ChimeraConfig) -> None:
        cfg = self._with_env(config, CHIMERA_LOG_LEVEL="debug")
        assert cfg.observability.log_level == "debug"

    def test_auth_toggle_on(self, config: ChimeraConfig) -> None:
        cfg = self._with_env(config, CHIMERA_AUTH_ENABLED="true")
        assert cfg.auth.enabled is True

    def test_rate_limit_toggle_on(self, config: ChimeraConfig) -> None:
        cfg = self._with_env(config, CHIMERA_RATE_LIMIT_ENABLED="1")
        assert cfg.rate_limit.enabled is True

    def test_auth_toggle_false_does_nothing(self, config: ChimeraConfig) -> None:
        cfg = self._with_env(config, CHIMERA_AUTH_ENABLED="false")
        assert cfg.auth.enabled is False  # unchanged from conftest default

    def test_api_key_shortcuts(self, config: ChimeraConfig) -> None:
        cfg = self._with_env(
            config,
            DEEPSEEK_KEY="sk-ds",
            OPENROUTER_KEY="sk-or",
            ZAI_KEY="sk-z",
        )
        assert cfg.api_keys["deepseek"] == "sk-ds"
        assert cfg.api_keys["openrouter"] == "sk-or"
        assert cfg.api_keys["zai"] == "sk-z"

    def test_no_env_vars_leaves_config_unchanged(self, config: ChimeraConfig) -> None:
        cfg = self._with_env(config)
        assert cfg.server.host == "127.0.0.1"
        assert cfg.server.port == 8000
        assert cfg.defaults.dispatcher == "zai-coding-plan/glm-5.2"


# ═══════════════════════════════════════════════════════════════════════════
#  REGRESSION: Formation models must exist in the model catalog
# ═══════════════════════════════════════════════════════════════════════════


def test_formation_models_exist_in_catalog() -> None:
    """Every model referenced in formations must be in the model catalog.

    REGRESSION: ``chimera.yaml`` had ``audit: openrouter/anthropic/claude-haiku-4.5``
    and ``debate`` had ``claude-sonnet-4`` — neither existed in the model catalog,
    causing 500 errors.  The fix changed them to ``default``.
    """
    from pathlib import Path

    import yaml

    config_path = Path(__file__).parent.parent / "chimera.yaml"
    if not config_path.exists():
        pytest.skip("chimera.yaml not found")
    with open(config_path) as f:
        cfg = yaml.safe_load(f)

    # Collect all known model IDs from the config
    known_models: set[str] = set()
    for provider_entry in cfg.get("providers", []):
        if isinstance(provider_entry, str):
            continue  # provider name-only entries
        for model in provider_entry.get("models", []):
            if isinstance(model, dict):
                known_models.add(model.get("id", ""))
    # Add special values
    known_models.add("default")
    known_models.add("")

    # Check every formation
    formations = cfg.get("formations", {})
    for name, fm_config in formations.items():
        if isinstance(fm_config, dict):
            if "dag" in fm_config:
                continue  # Custom DAGs have different structure
            # Check aggregator/audit model references (merge is a strategy)
            for field in ("aggregator", "audit"):
                value = fm_config.get(field)
                if isinstance(value, str) and value not in known_models:
                    raise AssertionError(
                        f"Formation '{name}.{field}' references unknown model "
                        f"'{value}'. Add it to the model catalog or use 'default'."
                    )
            # Check aggregators list
            for agg in fm_config.get("aggregators", []):
                if isinstance(agg, str) and agg not in known_models:
                    raise AssertionError(
                        f"Formation '{name}' aggregators list references "
                        f"unknown model '{agg}'."
                    )


# ═══════════════════════════════════════════════════════════════════════════
#  Model enabled/disabled
# ═══════════════════════════════════════════════════════════════════════════


class TestModelEnabled:
    """Tests for per-model enable/disable cost-control feature."""

    def test_enabled_defaults_to_true(self):
        """When not specified, enabled defaults to True."""
        entry = ModelEntry(categories={}, cost_tier="budget", provider="test")
        assert entry.enabled is True

    def test_enabled_false_parsed_from_yaml(self, tmp_path):
        """YAML with enabled: false should load correctly."""
        import yaml
        doc = {
            "api_keys": {},
            "providers": {"deepseek": {"base_url": "https://x.com/v1"}},
            "models": {
                "deepseek/test": {
                    "categories": {"code": 90.0},
                    "cost_tier": "budget",
                    "provider": "deepseek",
                    "enabled": False,
                },
                "deepseek/enabled-test": {
                    "categories": {"code": 80.0},
                    "cost_tier": "budget",
                    "provider": "deepseek",
                    "enabled": True,
                },
            },
            "defaults": {
                "dispatcher": "deepseek/test",
                "default_worker": "deepseek/test",
                "default_aggregator": "deepseek/test",
            },
            "formations": {"auto": {"mode": "auto"}},
        }
        path = tmp_path / "chimera.yaml"
        path.write_text(yaml.safe_dump(doc), encoding="utf-8")
        cfg = load_config(path)
        assert cfg.models["deepseek/test"].enabled is False
        assert cfg.models["deepseek/enabled-test"].enabled is True

    def test_enabled_models_filters_disabled(self, tmp_path):
        """enabled_models property should exclude disabled models."""
        import yaml
        doc = {
            "api_keys": {},
            "providers": {"deepseek": {"base_url": "https://x.com/v1"}},
            "models": {
                "deepseek/a": {"categories": {}, "cost_tier": "budget", "provider": "deepseek", "enabled": False},
                "deepseek/b": {"categories": {}, "cost_tier": "budget", "provider": "deepseek", "enabled": True},
                "deepseek/c": {"categories": {}, "cost_tier": "budget", "provider": "deepseek"},
            },
            "defaults": {
                "dispatcher": "deepseek/b",
                "default_worker": "deepseek/b",
                "default_aggregator": "deepseek/b",
            },
            "formations": {"auto": {"mode": "auto"}},
        }
        path = tmp_path / "chimera.yaml"
        path.write_text(yaml.safe_dump(doc), encoding="utf-8")
        cfg = load_config(path)
        enabled = cfg.enabled_models
        assert "deepseek/a" not in enabled, "Disabled model should be excluded"
        assert "deepseek/b" in enabled, "Enabled model should be included"
        assert "deepseek/c" in enabled, "Missing enabled should default to true"

    def test_catalog_description_excludes_disabled(self, tmp_path):
        """catalog_description() must not mention disabled models."""
        import yaml
        doc = {
            "api_keys": {},
            "providers": {"deepseek": {"base_url": "https://x.com/v1"}},
            "models": {
                "deepseek/disabled-one": {
                    "categories": {"code": 50.0}, "cost_tier": "budget",
                    "provider": "deepseek", "enabled": False,
                },
                "deepseek/enabled-one": {
                    "categories": {"code": 90.0}, "cost_tier": "budget",
                    "provider": "deepseek", "enabled": True,
                },
            },
            "defaults": {
                "dispatcher": "deepseek/enabled-one",
                "default_worker": "deepseek/enabled-one",
                "default_aggregator": "deepseek/enabled-one",
            },
            "formations": {"auto": {"mode": "auto"}},
        }
        path = tmp_path / "chimera.yaml"
        path.write_text(yaml.safe_dump(doc), encoding="utf-8")
        cfg = load_config(path)
        desc = cfg.catalog_description()
        assert "deepseek/enabled-one" in desc, "Enabled model must appear in catalog"
        assert "deepseek/disabled-one" not in desc, "Disabled model must NOT appear in catalog"

    def test_all_25_models_have_enabled_true(self):
        """Regression: every model in the live chimera.yaml must have enabled: true."""
        cfg = load_config()
        for name, entry in cfg.models.items():
            assert entry.enabled is True, (
                f"Model {name!r} has enabled={entry.enabled}. "
                f"All models in chimera.yaml must have enabled: true by default."
            )
