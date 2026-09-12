"""Regression tests for DF-CHIMERA-0906-3.

Default ``auto`` formation must only assign worker models whose provider
has resolved credentials, so a fresh install with e.g. only
``DEEPSEEK_API_KEY`` never burns calls on guardrail-blocked OpenRouter
models (``model_blocked_guardrail`` → ``aggregator_partial_inputs``).

Covered:
* credential resolution helper (api_keys / Provider.api_key / F8 fallback)
* dispatcher prompt catalog filtering (auto only, opt-out, empty-set fallback)
* engine-side remap safety net (auto only) + worker-prompt sync
* explicit overrides (allowed_models / worker_model / stage_models) stay
  authoritative
* preset and custom DAGs are never rewritten
"""

from __future__ import annotations

import copy
import json
from typing import Any

import pytest
import yaml

from chimera import blocked_models
from chimera.config import (
    ChimeraConfig,
    DeliberationOverrides,
    credentialed_enabled_models,
    load_config,
    provider_credential_resolved,
)
from chimera.dispatcher import (
    build_dispatcher_prompt,
    build_preset_dag,
    parse_dispatch_result,
)
from chimera.engine import Engine
from tests.conftest import CONFIG_DICT, FakeGateway, dispatch_json, resp

DS_FLASH = "deepseek/deepseek-v4-flash"
DS_CHAT = "deepseek/deepseek-chat"  # provider: openrouter in CONFIG_DICT
QWEN = "openrouter/qwen/qwen3-coder"
GEMINI = "openrouter/google/gemini-2.5-flash"
ZAI_GLM = "zai-coding-plan/glm-5.2"


@pytest.fixture(autouse=True)
def _clear_blocked_registry():
    """Isolate tests from the process-global guardrail block registry."""
    blocked_models.shared_registry._blocked_until.clear()
    yield
    blocked_models.shared_registry._blocked_until.clear()


def _make_config(
    api_keys: dict[str, str] | None = None,
    *,
    restrict: bool = True,
) -> ChimeraConfig:
    doc = copy.deepcopy(CONFIG_DICT)
    doc["api_keys"] = dict(api_keys or {})
    doc["auto_formation"] = {"restrict_to_credentialed_providers": restrict}
    return ChimeraConfig.model_validate(doc)


def _prompt_catalog(config: ChimeraConfig, **kwargs: Any) -> str:
    return build_dispatcher_prompt("Design an e-commerce backend", config, **kwargs)[0][
        "content"
    ]


def _engine_responder(payload: str):  # type: ignore[no-untyped-def]
    """Dispatcher/worker/aggregator-distinguishing FakeGateway responder."""

    def _responder(model, messages, response_format=None, **kw):  # type: ignore[no-untyped-def]
        if response_format is not None:  # dispatcher call
            return resp(payload, model, tok_in=120, tok_out=180)
        joined = json.dumps(messages)
        if "Upstream outputs" in joined:  # aggregator/merge/audit
            return resp(f"[FINAL from {model}]", model, tok_in=60, tok_out=90)
        return resp(f"[worker output {model}]", model, tok_in=25, tok_out=35)

    return _responder


def _worker_models(result) -> list[str]:  # type: ignore[no-untyped-def]
    return sorted(w.model for w in result.trace.workers)


@pytest.fixture
def remap():  # type: ignore[no-untyped-def]
    """The engine-side credential remap helper (lazy import: absent pre-fix)."""
    from chimera import engine as engine_mod

    return engine_mod._apply_credentialed_worker_models


# --------------------------------------------------------------------------- #
# provider_credential_resolved / credentialed_enabled_models
# --------------------------------------------------------------------------- #


def test_credential_resolved_via_api_keys() -> None:
    cfg = _make_config({"deepseek": "sk-x"})
    assert provider_credential_resolved(cfg, "deepseek") is True
    assert provider_credential_resolved(cfg, "openrouter") is False
    assert provider_credential_resolved(cfg, "zai") is False
    assert provider_credential_resolved(cfg, "anthropic") is False


def test_credential_resolved_empty_string_key_is_not_a_credential() -> None:
    # ${VAR} substitution yields "" for unset vars — must not count.
    cfg = _make_config({"deepseek": ""})
    assert provider_credential_resolved(cfg, "deepseek") is False


def test_credential_resolved_via_provider_api_key_env(monkeypatch) -> None:
    monkeypatch.setenv("CHIMERA_TEST_PROVIDER_KEY", "sk-env")
    doc = copy.deepcopy(CONFIG_DICT)
    doc["providers"]["zai"] = {
        "base_url": "https://api.z.ai/api/coding/paas/v4",
        "api_key_env": "CHIMERA_TEST_PROVIDER_KEY",
    }
    cfg = ChimeraConfig.model_validate(doc)
    assert provider_credential_resolved(cfg, "zai") is True


def test_credential_resolved_via_provider_api_key_direct() -> None:
    doc = copy.deepcopy(CONFIG_DICT)
    doc["providers"]["zai"] = {
        "base_url": "https://api.z.ai/api/coding/paas/v4",
        "api_key": "sk-direct",
    }
    cfg = ChimeraConfig.model_validate(doc)
    assert provider_credential_resolved(cfg, "zai") is True


def test_credential_resolved_anthropic_openrouter_fallback() -> None:
    # F8: Anthropic models route via OpenRouter when only OR is credentialed.
    cfg = _make_config({"openrouter": "sk-or"})
    assert provider_credential_resolved(cfg, "anthropic") is True
    assert provider_credential_resolved(cfg, "openrouter") is True
    assert provider_credential_resolved(cfg, "deepseek") is False


def test_credentialed_enabled_models_filters_enabled_only() -> None:
    doc = copy.deepcopy(CONFIG_DICT)
    doc["api_keys"] = {"deepseek": "sk-x"}
    doc["models"][DS_FLASH]["enabled"] = False
    cfg = ChimeraConfig.model_validate(doc)
    usable = credentialed_enabled_models(cfg)
    assert usable == {}  # the only deepseek-provider model is disabled


def test_credentialed_enabled_models_only_deepseek() -> None:
    cfg = _make_config({"deepseek": "sk-x"})
    assert set(credentialed_enabled_models(cfg)) == {DS_FLASH}


def test_credentialed_enabled_models_mixed() -> None:
    cfg = _make_config({"deepseek": "sk-x", "zai": "sk-y"})
    assert set(credentialed_enabled_models(cfg)) == {DS_FLASH, ZAI_GLM}


# --------------------------------------------------------------------------- #
# Config schema: the opt-in switch
# --------------------------------------------------------------------------- #


def test_auto_formation_restrict_defaults_true() -> None:
    cfg = _make_config({"deepseek": "sk-x"})
    assert cfg.auto_formation.restrict_to_credentialed_providers is True


def test_auto_formation_env_opt_out(tmp_path, monkeypatch) -> None:
    doc = copy.deepcopy(CONFIG_DICT)
    doc["provider_discovery"] = False
    path = tmp_path / "chimera.yaml"
    path.write_text(yaml.safe_dump(doc), encoding="utf-8")
    monkeypatch.delenv("CHIMERA_AUTO_ALLOW_ALL_CATALOG", raising=False)
    assert load_config(path).auto_formation.restrict_to_credentialed_providers is True
    monkeypatch.setenv("CHIMERA_AUTO_ALLOW_ALL_CATALOG", "true")
    assert load_config(path).auto_formation.restrict_to_credentialed_providers is False


# --------------------------------------------------------------------------- #
# Dispatcher prompt catalog filtering (auto mode only)
# --------------------------------------------------------------------------- #


def test_auto_prompt_catalog_excludes_uncredentialed() -> None:
    cfg = _make_config({"deepseek": "sk-x"})
    catalog = _prompt_catalog(cfg)
    assert DS_FLASH in catalog
    assert QWEN not in catalog
    assert GEMINI not in catalog
    assert ZAI_GLM not in catalog
    # openrouter-routed "deepseek/deepseek-chat" must not leak either
    assert DS_CHAT not in catalog


def test_auto_prompt_catalog_mixed_credentials() -> None:
    cfg = _make_config({"deepseek": "sk-x", "zai": "sk-y"})
    catalog = _prompt_catalog(cfg)
    assert DS_FLASH in catalog
    assert ZAI_GLM in catalog
    assert QWEN not in catalog
    assert GEMINI not in catalog


def test_auto_prompt_catalog_no_credentials_falls_back_to_full() -> None:
    # Empty candidate set: full catalog + actionable warning, never a crash.
    cfg = _make_config({})
    catalog = _prompt_catalog(cfg)
    for model in CONFIG_DICT["models"]:
        assert model in catalog


def test_auto_prompt_catalog_opt_out_shows_full_catalog() -> None:
    cfg = _make_config({"deepseek": "sk-x"}, restrict=False)
    catalog = _prompt_catalog(cfg)
    for model in CONFIG_DICT["models"]:
        assert model in catalog


def test_preset_prompt_catalog_not_filtered() -> None:
    # Preset/custom passes (fixed_dag) keep the full catalog: the structure
    # is already fixed by explicit config, so filtering would silently
    # rewrite it.
    cfg = _make_config({"deepseek": "sk-x"})
    dag = build_preset_dag(cfg.formations["speed"], cfg)
    catalog = _prompt_catalog(cfg, fixed_dag=dag)
    for model in CONFIG_DICT["models"]:
        assert model in catalog


# --------------------------------------------------------------------------- #
# Engine-side remap safety net
# --------------------------------------------------------------------------- #


def test_remap_helper_syncs_worker_prompt_models(remap) -> None:
    cfg = _make_config({"deepseek": "sk-x"})
    result = parse_dispatch_result(
        dispatch_json(workers=[("worker_1", QWEN), ("worker_2", DS_FLASH)]),
        cfg,
    )
    remap(result, cfg)
    stages = {s.id: s for s in result.formation.stages}
    assert stages["worker_1"].model == DS_FLASH
    assert stages["worker_2"].model == DS_FLASH
    for stage in result.formation.stages:
        if stage.kind == "worker":
            wp = result.worker_prompt_for(stage.id)
            assert wp is not None
            assert wp.model == stage.model, (
                f"worker prompt model for {stage.id} out of sync with stage model"
            )


def test_remap_helper_prefers_default_worker_when_credentialed(remap) -> None:
    doc = copy.deepcopy(CONFIG_DICT)
    doc["api_keys"] = {"deepseek": "sk-x", "openrouter": "sk-or"}
    doc["defaults"]["default_worker"] = QWEN
    cfg = ChimeraConfig.model_validate(doc)
    result = parse_dispatch_result(
        dispatch_json(workers=[("worker_1", ZAI_GLM), ("worker_2", DS_FLASH)]),
        cfg,
    )
    remap(result, cfg)
    stages = {s.id: s for s in result.formation.stages}
    assert stages["worker_1"].model == QWEN  # default_worker, credentialed
    assert stages["worker_2"].model == DS_FLASH  # already usable


def test_remap_helper_skips_preset_and_custom(remap) -> None:
    cfg = _make_config({"deepseek": "sk-x"})
    for source in ("preset", "custom", "fallback"):
        result = parse_dispatch_result(
            dispatch_json(workers=[("worker_1", QWEN), ("worker_2", DS_FLASH)]),
            cfg,
        )
        result.source = source
        remap(result, cfg)
        stages = {s.id: s for s in result.formation.stages}
        assert stages["worker_1"].model == QWEN, f"source={source} must not be remapped"


def test_remap_helper_opt_out_leaves_auto_untouched(remap) -> None:
    cfg = _make_config({"deepseek": "sk-x"}, restrict=False)
    result = parse_dispatch_result(
        dispatch_json(workers=[("worker_1", QWEN), ("worker_2", DS_FLASH)]),
        cfg,
    )
    remap(result, cfg)
    stages = {s.id: s for s in result.formation.stages}
    assert stages["worker_1"].model == QWEN


def test_remap_helper_no_credentials_leaves_auto_untouched(remap) -> None:
    cfg = _make_config({})
    result = parse_dispatch_result(
        dispatch_json(workers=[("worker_1", QWEN), ("worker_2", DS_FLASH)]),
        cfg,
    )
    remap(result, cfg)
    stages = {s.id: s for s in result.formation.stages}
    assert stages["worker_1"].model == QWEN
    assert stages["worker_2"].model == DS_FLASH


@pytest.mark.asyncio
async def test_engine_auto_excludes_uncredentialed_workers() -> None:
    cfg = _make_config({"deepseek": "sk-x"})
    payload = dispatch_json(
        workers=[("worker_1", QWEN), ("worker_2", DS_FLASH)],
        aggregator=DS_FLASH,
    )
    gw = FakeGateway(_engine_responder(payload))
    result = await Engine(cfg, gw).deliberate("Design + build a service", "auto")
    assert result.trace.source == "auto"
    assert _worker_models(result) == [DS_FLASH, DS_FLASH]


@pytest.mark.asyncio
async def test_engine_preset_not_remapped() -> None:
    # The `speed` preset pins worker_models including an uncredentialed
    # OpenRouter model — explicit config must be honored verbatim.
    cfg = _make_config({"deepseek": "sk-x"})
    payload = dispatch_json(aggregator=DS_FLASH)
    gw = FakeGateway(_engine_responder(payload))
    result = await Engine(cfg, gw).deliberate("Design + build a service", "speed")
    assert result.trace.source == "preset"
    assert _worker_models(result) == [DS_FLASH, QWEN]


@pytest.mark.asyncio
async def test_engine_custom_dag_not_remapped() -> None:
    cfg = _make_config({"deepseek": "sk-x"})
    payload = dispatch_json(aggregator=DS_FLASH)
    dag = {
        "stages": [
            {"id": "w1", "kind": "worker", "model": QWEN, "depends_on": []},
            {"id": "agg", "kind": "aggregator", "model": DS_FLASH, "depends_on": ["w1"]},
        ],
        "edges": [["w1", "agg"]],
    }
    gw = FakeGateway(_engine_responder(payload))
    result = await Engine(cfg, gw).deliberate(
        "task", "auto", dag=dag, allow_custom_dag=True
    )
    assert result.trace.source == "custom"
    assert _worker_models(result) == [QWEN]


# --------------------------------------------------------------------------- #
# Explicit request overrides remain authoritative (applied after the remap)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_explicit_worker_model_override_wins() -> None:
    cfg = _make_config({"deepseek": "sk-x"})
    payload = dispatch_json(
        workers=[("worker_1", QWEN), ("worker_2", DS_FLASH)],
        aggregator=DS_FLASH,
    )
    gw = FakeGateway(_engine_responder(payload))
    overrides = DeliberationOverrides(worker_model=GEMINI)
    result = await Engine(cfg, gw).deliberate("task", "auto", overrides=overrides)
    assert _worker_models(result) == [GEMINI, GEMINI]


@pytest.mark.asyncio
async def test_explicit_stage_models_override_wins() -> None:
    cfg = _make_config({"deepseek": "sk-x"})
    payload = dispatch_json(
        workers=[("worker_1", QWEN), ("worker_2", DS_FLASH)],
        aggregator=DS_FLASH,
    )
    gw = FakeGateway(_engine_responder(payload))
    overrides = DeliberationOverrides(stage_models={"worker_1": GEMINI})
    result = await Engine(cfg, gw).deliberate("task", "auto", overrides=overrides)
    assert _worker_models(result) == [DS_FLASH, GEMINI]


@pytest.mark.asyncio
async def test_explicit_allowed_models_wins() -> None:
    cfg = _make_config({"deepseek": "sk-x"})
    payload = dispatch_json(
        workers=[("worker_1", QWEN), ("worker_2", DS_FLASH)],
        aggregator=DS_FLASH,
    )
    gw = FakeGateway(_engine_responder(payload))
    overrides = DeliberationOverrides(allowed_models=[GEMINI])
    result = await Engine(cfg, gw).deliberate("task", "auto", overrides=overrides)
    assert _worker_models(result) == [GEMINI, GEMINI]


@pytest.mark.asyncio
async def test_engine_opt_out_keeps_dispatched_models() -> None:
    cfg = _make_config({"deepseek": "sk-x"}, restrict=False)
    payload = dispatch_json(
        workers=[("worker_1", QWEN), ("worker_2", DS_FLASH)],
        aggregator=DS_FLASH,
    )
    gw = FakeGateway(_engine_responder(payload))
    result = await Engine(cfg, gw).deliberate("task", "auto")
    assert _worker_models(result) == [DS_FLASH, QWEN]
