# Verdict: config-loading

**Task:** Config loading and env override defense
**Evaluated:** 2026-06-21T12:12:29.423828
**Result:** ✗ FAIL

## Pipeline Stages

- ✓ **tier1**
  -   ✓ guard: Tier 1 Guards: PASS  (test mode: diff, full suite — safety trigger)
  ✓ secrets — clean
  ✓ lint — o
- ✗ **tier2**
  - INCOMPLETE
  ✓ ChimeraConfig loads chimera.yaml and parses all model entries with scores: src/chimera/config.py:289-312 — load_config() reads YAML, substitutes env vars, validates via ChimeraConfig.model_validate(raw). ChimeraConfig (line 198) has models: dict[str, ModelEntry]. ModelEntry (line 30-38) has categories: dict[str, float]. Tests test_config_loads_from_dict and test_load_config_from_file confirm models with category scores are parsed.
  ✓ _apply_env_overrides() activates providers from environment variables: src/chimera/config.py:326-396 — _apply_env_overrides() handles CHIMERA_HOST/PORT, CHIMERA_DISPATCHER/WORKER/AGGREGATOR, CHIMERA_LOG_LEVEL, CHIMERA_AUTH_ENABLED, CHIMERA_RATE_LIMIT_ENABLED, and API key env vars (DEEPSEEK_KEY, OPENROUTER_KEY, ZAI_KEY, ANTHROPIC_KEY, GEMINI_KEY) that set config.api_keys. Also triggers provider auto-discovery from models.dev when provider_discovery=True. TestEnvOverrides class (tests/test_config.py:189+) comprehensively tests all env-to-config bindings.
  ✓ Missing chimera.yaml raises a clear error, not a cryptic KeyError: src/chimera/config.py:274-282 — find_config_path() raises FileNotFoundError('No chimera.yaml found. Copy chimera.yaml.example to chimera.yaml.'). Test test_find_config_path_raises_when_missing (tests/test_config.py:62-64) confirms FileNotFoundError is raised with the clear message.
  ✗ Unknown fields in model config log a warning, don't crash: src/chimera/config.py — No import logging, no model_config with extra field handling, no logger.warn() calls exist anywhere in the file. Pydantic v2 default is extra='ignore' which silently discards unknown fields without logging any warning. The code does not log warnings for unknown fields.
  ✓ auto_discover_providers=false skips models.dev fetch entirely: src/chimera/config.py:214 — ChimeraConfig.provider_discovery: bool = True. Line 376: 'if config.provider_discovery:' gates the entire discover_providers() call. When False, the block is skipped entirely. Test test_discovery_disabled_respected (tests/test_provider_discovery.py:387-408) confirms that provider_discovery=False results in empty providers dict.
4 of 5 criteria pass — criterion 4 FAILS because unknown fields in model config are silently ignored (Pydantic v2 default extra='ignore') rather than logged as warnings, as no logging infrastructure exists in config.py.

## Summary

Judge Result: config-loading

Stage tier1: PASS
    ✓ guard: Tier 1 Guards: PASS  (test mode: diff, full suite — safety trigger)
  ✓ secrets — clean
  ✓ lint — o

Stage tier2: FAIL
  INCOMPLETE
  ✓ ChimeraConfig loads chimera.yaml and parses all model entries with scores: src/chimera/config.py:289-312 — load_config() reads YAML, substitutes env vars, validates via ChimeraConfig.model_validate(raw). ChimeraConfig (line 198) has models: dict[str, ModelEntry]. ModelEntry (line 30-38) has categories: dict[str, float]. Tests test_config_loads_from_dict and test_load_config_from_file confirm models with category scores are parsed.
  ✓ _apply_env_overrides() activates providers from environment variables: src/chimera/config.py:326-396 — _apply_env_overrides() handles CHIMERA_HOST/PORT, CHIMERA_DISPATCHER/WORKER/AGGREGATOR, CHIMERA_LOG_LEVEL, CHIMERA_AUTH_ENABLED, CHIMERA_RATE_LIMIT_ENABLED, and API key env vars (DEEPSEEK_KEY, OPENROUTER_KEY, ZAI_KEY, ANTHROPIC_KEY, GEMINI_KEY) that set config.api_keys. Also triggers provider auto-discovery from models.dev when provider_discovery=True. TestEnvOverrides class (tests/test_config.py:189+) comprehensively tests all env-to-config bindings.
  ✓ Missing chimera.yaml raises a clear error, not a cryptic KeyError: src/chimera/config.py:274-282 — find_config_path() raises FileNotFoundError('No chimera.yaml found. Copy chimera.yaml.example to chimera.yaml.'). Test test_find_config_path_raises_when_missing (tests/test_config.py:62-64) confirms FileNotFoundError is raised with the clear message.
  ✗ Unknown fields in model config log a warning, don't crash: src/chimera/config.py — No import logging, no model_config with extra field handling, no logger.warn() calls exist anywhere in the file. Pydantic v2 default is extra='ignore' which silently discards unknown fields without logging any warning. The code does not log warnings for unknown fields.
  ✓ auto_discover_providers=false skips models.dev fetch entirely: src/chimera/config.py:214 — ChimeraConfig.provider_discovery: bool = True. Line 376: 'if config.provider_discovery:' gates the entire discover_providers() call. When False, the block is skipped entirely. Test test_discovery_disabled_respected (tests/test_provider_discovery.py:387-408) confirms that provider_discovery=False results in empty providers dict.
4 of 5 criteria pass — criterion 4 FAILS because unknown fields in model config are silently ignored (Pydantic v2 default extra='ignore') rather than logged as warnings, as no logging infrastructure exists in config.py.

Overall: FAIL ✗
