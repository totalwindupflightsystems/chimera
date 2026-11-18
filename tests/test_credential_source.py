"""Credential-source observability (DF-CHIMERA-V2-90).

A provider key missing from the process env silently falls back to
``~/.hermes/.env`` — on a host that happens to carry that file a deliberation
SUCCEEDS with zero user-visible indication of where the credential came from,
which makes "did I configure credentials?" undiagnosable on a fresh install.

These tests pin the additive observability:

* every provider key carries a source label — ``process_env`` /
  ``repo_dotenv`` / ``hermes_dotenv_fallback`` / ``api_keys`` /
  ``provider.api_key`` / ``missing`` — recorded at
  load time on ``ChimeraConfig.credential_sources``;
* the hermes-dotenv fallback additionally emits a WARNING naming the
  provider and the fallback path (never the value);
* the deliberation trace exposes the map (``trace.credential_sources``) and
  the REST surface carries it on both the trace JSON and ``/v1/health``
  ``details``;
* no key material ever appears in logs, trace, or health output.

Resolution ORDER is not changed by any of this — only recorded.

Warning capture uses ``structlog.testing.capture_logs()`` (repo convention,
see tests/test_config_scale.py): warnings go through the structlog pipeline,
which stdlib ``caplog`` does not hook, so caplog can never observe them.
All tests strip ``HOME``/seed the dotenv cache — none reads the real
``~/.hermes/.env``, so they pass on any host.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
import structlog.testing
import yaml

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from chimera import config as chimera_config  # noqa: E402
from chimera.api.server import create_app  # noqa: E402
from chimera.config import (  # noqa: E402
    CREDENTIAL_SOURCE_API_KEYS,
    CREDENTIAL_SOURCE_HERMES_DOTENV_FALLBACK,
    CREDENTIAL_SOURCE_MISSING,
    CREDENTIAL_SOURCE_PROCESS_ENV,
    CREDENTIAL_SOURCE_PROVIDER_API_KEY,
    CREDENTIAL_SOURCE_REPO_DOTENV,
    ChimeraConfig,
    load_config,
    provider_credential_source,
)
from chimera.engine import Engine  # noqa: E402
from chimera.gateway import LiteLLMGateway  # noqa: E402
from tests.conftest import CONFIG_DICT, FakeGateway, dispatch_json, resp  # noqa: E402
from tests.test_gateway_custom_base_url import _compat_stub  # noqa: E402

#: Env var whose absence forces the hermes-dotenv fallback in these tests.
#: Deliberately NOT a name a real host exports (the delenv makes even that
#: impossible), except in the deepseek-named test that mirrors the filed
#: scenario verbatim.
ENV_KEY = "DF90_TEST_PROVIDER_KEY"

#: The hermes-dotenv fallback value used in fallback tests. Any appearance of
#: this sentinel in trace / health / log output is a leak — asserted nowhere.
SECRET_SENTINEL = "df90-secret-value-xyzzy"

#: A literal key written on a provider entry in fixture configs — never real
#: material; the tests that use it assert it appears in no observable output.
PROVIDER_ENTRY_KEY = "df90-provider-entry-literal"

PROVIDER_DICT: dict = {
    "providers": {"df90prov": {"base_url": "https://df90.example/v1", "api_key_env": ENV_KEY}},
    "models": {},
    "defaults": {
        "dispatcher": "m",
        "default_worker": "m",
        "default_aggregator": "m",
    },
}


@pytest.fixture(autouse=True)
def _isolated_credential_env(monkeypatch, tmp_path):  # type: ignore[no-untyped-def]
    """Never read the real ~/.hermes/.env; keep module state per-test.

    * the env var under test is absent from the process environment,
    * HOME points at an empty tmp dir (belt), and
    * the hermes dotenv cache starts cold (suspenders — belt and suspenders
      because ``Path.home()`` and the cache are two independent ways the real
      host file could leak in),
    * the per-load provenance bookkeeping is cleared so no earlier test's
      repo-dotenv load can mislabel this test's process-env key.
    """
    monkeypatch.delenv(ENV_KEY, raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(chimera_config, "_hermes_dotenv_cache", None)
    monkeypatch.setattr(chimera_config, "_REPO_DOTENV_VARS", set())
    monkeypatch.setattr(chimera_config, "_SUBSTITUTION_SOURCES", {})
    yield


def _write_hermes_dotenv(monkeypatch, tmp_path, var: str, value: str) -> None:
    """Seed a fake ~/.hermes/.env under tmp HOME and cold the cache."""
    hermes_dir = tmp_path / ".hermes"
    hermes_dir.mkdir(exist_ok=True)
    (hermes_dir / ".env").write_text(f"{var}={value}\n", encoding="utf-8")
    monkeypatch.setattr(chimera_config, "_hermes_dotenv_cache", None)


def _deliberation_responder(payload: str | None = None):  # type: ignore[no-untyped-def]
    """FakeGateway responder distinguishing dispatcher / worker / aggregator."""
    _payload = payload or dispatch_json(
        workers=[("worker_1", "deepseek/deepseek-chat"), ("worker_2", "openrouter/google/gemini-2.5-flash")],
        aggregator_instructions="Merge.",
    )

    def _responder(model, messages, response_format=None, **kw):  # type: ignore[no-untyped-def]
        if response_format is not None:
            return resp(_payload, model, 100, 200)
        joined = json.dumps(messages)
        if "Upstream outputs" in joined:
            return resp("FINAL ANSWER", model, 60, 90)
        return resp(f"worker {model}", model, 20, 40)

    return _responder


def _full_config_dict() -> dict:
    """The shared working catalog + one provenance-carrying provider.

    The deliberation DAG uses the shared catalog models; ``df90prov`` rides
    along purely so the load-time resolver records a source for it.
    """
    cfg_dict = copy.deepcopy(CONFIG_DICT)
    # Keep the DAG deterministic: no credentialed-model remap interaction.
    cfg_dict["auto_formation"] = {"restrict_to_credentialed_providers": False}
    cfg_dict["providers"]["df90prov"] = {
        "base_url": "https://df90.example/v1",
        "api_key_env": ENV_KEY,
    }
    return cfg_dict


def _loaded_working_config(monkeypatch, tmp_path):  # type: ignore[no-untyped-def]
    """load_config() over a tmp chimera.yaml with a working catalog.

    Returns (config, path). The env var under test is set so ``df90prov``
    resolves from the process environment.
    """
    monkeypatch.setenv(ENV_KEY, "from-process-env")
    path = tmp_path / "chimera.yaml"
    path.write_text(yaml.safe_dump(_full_config_dict()), encoding="utf-8")
    return load_config(path), path


# --------------------------------------------------------------------------- #
# 1. Provider api_key_env resolver — source labels
# --------------------------------------------------------------------------- #


def test_process_env_key_labeled_process_env(monkeypatch) -> None:
    """A key present in the process env is labeled ``process_env``."""
    monkeypatch.setenv(ENV_KEY, "from-process-env")
    cfg = ChimeraConfig.model_validate(PROVIDER_DICT)
    assert cfg.providers["df90prov"].api_key == "from-process-env"
    assert cfg.credential_sources["df90prov"] == CREDENTIAL_SOURCE_PROCESS_ENV
    assert provider_credential_source(cfg, "df90prov") == CREDENTIAL_SOURCE_PROCESS_ENV


def test_missing_key_labeled_missing_and_no_crash() -> None:
    """A key absent everywhere is labeled ``missing`` — no crash, key None."""
    with structlog.testing.capture_logs() as logs:
        cfg = ChimeraConfig.model_validate(PROVIDER_DICT)
    assert cfg.providers["df90prov"].api_key is None
    assert cfg.credential_sources["df90prov"] == CREDENTIAL_SOURCE_MISSING
    # Nothing resolved → no fallback warning either.
    assert [entry for entry in logs if entry["event"] == "api_key_source_fallback"] == []


def test_provider_literal_api_key_labeled_provider_api_key() -> None:
    """A literal key on the provider entry is labeled ``provider.api_key``
    when no api_keys shortcut covers the provider (CHIMERA-V2-REVIEW-08):
    the gateway's fallback reads exactly this value, so the trace must name
    the surface instead of leaving the provider unlabeled."""
    cfg_dict = copy.deepcopy(PROVIDER_DICT)
    cfg_dict["providers"]["df90prov"] = {"base_url": "https://df90.example/v1", "api_key": PROVIDER_ENTRY_KEY}
    cfg = ChimeraConfig.model_validate(cfg_dict)
    assert cfg.providers["df90prov"].api_key == PROVIDER_ENTRY_KEY
    assert cfg.credential_sources["df90prov"] == CREDENTIAL_SOURCE_PROVIDER_API_KEY


def test_provider_literal_api_key_defers_to_api_keys_shortcut(tmp_path) -> None:
    """Gateway order pinned: with BOTH a provider-entry literal and an
    ``api_keys`` shortcut, the shortcut's label wins — that is the key the
    gateway consults first (the validator records nothing for a
    shortcut-covered provider)."""
    cfg_dict = _api_keys_cfg_dict(provider_api_key_env=False, raw_value=SECRET_SENTINEL)
    cfg_dict["providers"]["df90prov"]["api_key"] = PROVIDER_ENTRY_KEY
    config_path = tmp_path / "chimera.yaml"
    config_path.write_text(yaml.safe_dump(cfg_dict), encoding="utf-8")
    cfg = load_config(config_path)
    assert cfg.api_keys["df90prov"] == SECRET_SENTINEL
    assert cfg.credential_sources["df90prov"] == CREDENTIAL_SOURCE_API_KEYS


def test_provider_empty_literal_api_key_labeled_missing() -> None:
    """An empty-string literal on the provider entry is configured but
    unusable (the gateway would pass "") — honest ``missing``, not an
    invented surface name."""
    cfg_dict = copy.deepcopy(PROVIDER_DICT)
    cfg_dict["providers"]["df90prov"] = {"base_url": "https://df90.example/v1", "api_key": ""}
    cfg = ChimeraConfig.model_validate(cfg_dict)
    assert cfg.credential_sources["df90prov"] == CREDENTIAL_SOURCE_MISSING


def test_deepseek_hermes_fallback_labeled_and_warns(monkeypatch, tmp_path) -> None:
    """The filed scenario, verbatim: DEEPSEEK_API_KEY unset, a hermes-dotenv
    fallback present → source ``hermes_dotenv_fallback`` and a WARNING naming
    the provider (structlog capture_logs — see module docstring for why not
    caplog)."""
    _write_hermes_dotenv(monkeypatch, tmp_path, "DEEPSEEK_API_KEY", SECRET_SENTINEL)
    cfg_dict = copy.deepcopy(PROVIDER_DICT)
    cfg_dict["providers"] = {
        "deepseek": {"base_url": "https://api.deepseek.com/v1", "api_key_env": "DEEPSEEK_API_KEY"},
    }
    with structlog.testing.capture_logs() as logs:
        cfg = ChimeraConfig.model_validate(cfg_dict)
    assert cfg.providers["deepseek"].api_key == SECRET_SENTINEL
    assert cfg.credential_sources["deepseek"] == CREDENTIAL_SOURCE_HERMES_DOTENV_FALLBACK
    records = [entry for entry in logs if entry["event"] == "api_key_source_fallback"]
    assert len(records) == 1, logs
    assert records[0]["log_level"] == "warning"
    assert records[0]["provider"] == "deepseek"
    assert records[0]["env_var"] == "DEEPSEEK_API_KEY"
    assert records[0]["source"] == CREDENTIAL_SOURCE_HERMES_DOTENV_FALLBACK
    assert records[0]["path"] == "~/.hermes/.env"
    # A4: the warning names provider + path — never the value.
    assert SECRET_SENTINEL not in json.dumps(records)


def test_process_env_key_emits_no_fallback_warning(monkeypatch) -> None:
    """A normally-resolved key must not produce the fallback warning."""
    monkeypatch.setenv(ENV_KEY, "from-process-env")
    with structlog.testing.capture_logs() as logs:
        ChimeraConfig.model_validate(PROVIDER_DICT)
    assert [entry for entry in logs if entry["event"] == "api_key_source_fallback"] == []


def test_repo_dotenv_key_labeled_repo_dotenv(tmp_path) -> None:
    """A key the repo-level .env injected is labeled ``repo_dotenv``, not
    ``process_env`` — load-time metadata distinguishes the two."""
    (tmp_path / ".env").write_text(f"{ENV_KEY}=from-repo-dotenv\n", encoding="utf-8")
    config_path = tmp_path / "chimera.yaml"
    config_path.write_text(yaml.safe_dump(PROVIDER_DICT), encoding="utf-8")
    with structlog.testing.capture_logs() as logs:
        cfg = load_config(config_path)
    assert cfg.providers["df90prov"].api_key == "from-repo-dotenv"
    assert cfg.credential_sources["df90prov"] == CREDENTIAL_SOURCE_REPO_DOTENV
    assert [entry for entry in logs if entry["event"] == "api_key_source_fallback"] == []


def test_process_env_beats_repo_dotenv_label(monkeypatch, tmp_path) -> None:
    """Precedence unchanged: with the var in BOTH places the label is
    ``process_env`` (the repo .env never injected it — precedence held)."""
    (tmp_path / ".env").write_text(f"{ENV_KEY}=from-repo-dotenv\n", encoding="utf-8")
    config_path = tmp_path / "chimera.yaml"
    config_path.write_text(yaml.safe_dump(PROVIDER_DICT), encoding="utf-8")
    monkeypatch.setenv(ENV_KEY, "from-process-env")
    cfg = load_config(config_path)
    assert cfg.providers["df90prov"].api_key == "from-process-env"
    assert cfg.credential_sources["df90prov"] == CREDENTIAL_SOURCE_PROCESS_ENV


def test_repo_dotenv_beats_hermes_fallback_label(monkeypatch, tmp_path) -> None:
    """Precedence unchanged: repo .env present AND hermes fallback seeded →
    the key resolves from the repo .env and is labeled ``repo_dotenv``."""
    (tmp_path / ".env").write_text(f"{ENV_KEY}=from-repo-dotenv\n", encoding="utf-8")
    config_path = tmp_path / "chimera.yaml"
    config_path.write_text(yaml.safe_dump(PROVIDER_DICT), encoding="utf-8")
    _write_hermes_dotenv(monkeypatch, tmp_path, ENV_KEY, SECRET_SENTINEL)
    cfg = load_config(config_path)
    assert cfg.providers["df90prov"].api_key == "from-repo-dotenv"
    assert cfg.credential_sources["df90prov"] == CREDENTIAL_SOURCE_REPO_DOTENV


# --------------------------------------------------------------------------- #
# 2. api_keys shortcut path (the shipped-template shape)
# --------------------------------------------------------------------------- #


def _api_keys_cfg_dict(provider_api_key_env: bool, raw_value: str | None = None) -> dict:
    """Template-shaped config: ``api_keys: {<prov>: ${VAR}}``.

    ``provider_api_key_env=False`` isolates the substitution path (the
    per-provider validator contributes nothing).  ``raw_value`` replaces the
    ``${VAR}`` token with a literal key — the api_keys-only credential shape
    of CHIMERA-V2-REVIEW-08.
    """
    provider: dict = {"base_url": "https://df90.example/v1"}
    if provider_api_key_env:
        provider["api_key_env"] = ENV_KEY
    return {
        "api_keys": {"df90prov": raw_value if raw_value is not None else "${" + ENV_KEY + "}"},
        "providers": {"df90prov": provider},
        "models": {},
        "defaults": {
            "dispatcher": "m",
            "default_worker": "m",
            "default_aggregator": "m",
        },
    }


def test_api_keys_substitution_from_process_env_labeled(monkeypatch, tmp_path) -> None:
    """Shipped-template shape: the key arrives via ``${VAR}`` substitution
    from the process env → provider labeled ``process_env`` even though the
    provider entry itself has no ``api_key_env``."""
    monkeypatch.setenv(ENV_KEY, "from-process-env")
    config_path = tmp_path / "chimera.yaml"
    config_path.write_text(yaml.safe_dump(_api_keys_cfg_dict(provider_api_key_env=False)), encoding="utf-8")
    cfg = load_config(config_path)
    assert cfg.api_keys["df90prov"] == "from-process-env"
    assert cfg.credential_sources["df90prov"] == CREDENTIAL_SOURCE_PROCESS_ENV


def test_api_keys_substitution_hermes_fallback_labeled_and_warns(monkeypatch, tmp_path) -> None:
    """Template shape + unset env + hermes fallback → labeled
    ``hermes_dotenv_fallback`` with the provider-naming warning (this is the
    exact dogfood run-23 shape: untouched example config, key only in
    ~/.hermes/.env)."""
    _write_hermes_dotenv(monkeypatch, tmp_path, ENV_KEY, SECRET_SENTINEL)
    config_path = tmp_path / "chimera.yaml"
    config_path.write_text(yaml.safe_dump(_api_keys_cfg_dict(provider_api_key_env=False)), encoding="utf-8")
    with structlog.testing.capture_logs() as logs:
        cfg = load_config(config_path)
    assert cfg.api_keys["df90prov"] == SECRET_SENTINEL
    assert cfg.credential_sources["df90prov"] == CREDENTIAL_SOURCE_HERMES_DOTENV_FALLBACK
    records = [entry for entry in logs if entry["event"] == "api_key_source_fallback"]
    assert len(records) == 1, logs
    assert records[0]["provider"] == "df90prov"
    assert SECRET_SENTINEL not in json.dumps(records)


def test_api_keys_missing_substitution_labeled_missing(tmp_path) -> None:
    """Template shape + key absent everywhere → ``missing`` (no crash)."""
    config_path = tmp_path / "chimera.yaml"
    config_path.write_text(yaml.safe_dump(_api_keys_cfg_dict(provider_api_key_env=False)), encoding="utf-8")
    cfg = load_config(config_path)
    assert cfg.api_keys["df90prov"] == ""
    assert cfg.credential_sources["df90prov"] == CREDENTIAL_SOURCE_MISSING


def test_api_keys_literal_value_labeled_api_keys(tmp_path) -> None:
    """A literal key in the ``api_keys`` shortcut is labeled ``api_keys``
    (CHIMERA-V2-REVIEW-08): that exact value is what the gateway consults
    first, so a successful route must name this source instead of reporting
    ``missing``."""
    config_path = tmp_path / "chimera.yaml"
    config_path.write_text(
        yaml.safe_dump(_api_keys_cfg_dict(provider_api_key_env=False, raw_value=SECRET_SENTINEL)),
        encoding="utf-8",
    )
    cfg = load_config(config_path)
    assert cfg.api_keys["df90prov"] == SECRET_SENTINEL
    assert cfg.credential_sources["df90prov"] == CREDENTIAL_SOURCE_API_KEYS


def test_api_keys_literal_empty_labeled_missing(tmp_path) -> None:
    """An empty literal in the shortcut contributes no usable key — honest
    ``missing`` (the gateway would pass "")."""
    config_path = tmp_path / "chimera.yaml"
    config_path.write_text(
        yaml.safe_dump(_api_keys_cfg_dict(provider_api_key_env=False, raw_value="")),
        encoding="utf-8",
    )
    cfg = load_config(config_path)
    assert cfg.credential_sources["df90prov"] == CREDENTIAL_SOURCE_MISSING


def test_api_keys_substitution_beats_provider_entry_label(monkeypatch, tmp_path) -> None:
    """Gateway order pinned: provider-entry literal + ``${VAR}`` shortcut →
    the substitution's provenance wins, because ``config.api_keys`` is what
    the gateway consults first."""
    monkeypatch.setenv(ENV_KEY, "from-process-env")
    cfg_dict = _api_keys_cfg_dict(provider_api_key_env=False)
    cfg_dict["providers"]["df90prov"]["api_key"] = PROVIDER_ENTRY_KEY
    config_path = tmp_path / "chimera.yaml"
    config_path.write_text(yaml.safe_dump(cfg_dict), encoding="utf-8")
    cfg = load_config(config_path)
    assert cfg.credential_sources["df90prov"] == CREDENTIAL_SOURCE_PROCESS_ENV


# --------------------------------------------------------------------------- #
# 3. Trace surfacing (engine)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_trace_carries_credential_sources(monkeypatch) -> None:
    """A deliberation's trace exposes the load-time source map."""
    monkeypatch.setenv(ENV_KEY, "from-process-env")
    cfg = ChimeraConfig.model_validate(PROVIDER_DICT)
    result = await Engine(cfg, FakeGateway(_deliberation_responder())).deliberate("task", "auto")
    assert result.trace.credential_sources == {"df90prov": CREDENTIAL_SOURCE_PROCESS_ENV}


@pytest.mark.asyncio
async def test_trace_credential_sources_empty_on_programmatic_config() -> None:
    """A config built programmatically carries no provenance → the trace
    field stays an empty dict (additive, never fabricated)."""
    cfg = ChimeraConfig.model_validate(copy.deepcopy(CONFIG_DICT))
    result = await Engine(cfg, FakeGateway(_deliberation_responder())).deliberate("task", "auto")
    assert result.trace.credential_sources == {}


# --------------------------------------------------------------------------- #
# 4. REST surfacing — trace JSON and /v1/health details
# --------------------------------------------------------------------------- #


def _rest_client(monkeypatch, tmp_path):  # type: ignore[no-untyped-def]
    """Working REST app whose config carries df90prov provenance."""
    cfg, _path = _loaded_working_config(monkeypatch, tmp_path)
    engine = Engine(cfg, FakeGateway(_deliberation_responder()))
    app = create_app(config=cfg, engine=engine)
    return TestClient(app)


def test_rest_trace_includes_credential_sources(monkeypatch, tmp_path) -> None:
    """A3: the trace JSON of a gateway request carries the source map."""
    client = _rest_client(monkeypatch, tmp_path)
    r = client.post("/v1/deliberate", json={"prompt": "hello", "formation": "auto"})
    assert r.status_code == 200, r.text
    trace = r.json()["trace"]
    assert trace["credential_sources"]["df90prov"] == CREDENTIAL_SOURCE_PROCESS_ENV


def test_health_details_include_credential_sources(monkeypatch, tmp_path) -> None:
    """Health details already carry config-derived info → the source map
    joins ``details`` additively."""
    client = _rest_client(monkeypatch, tmp_path)
    r = client.get("/v1/health")
    assert r.status_code == 200, r.text
    details = r.json()["details"]
    assert details["credential_sources"]["df90prov"] == CREDENTIAL_SOURCE_PROCESS_ENV


# --------------------------------------------------------------------------- #
# 5. Hygiene — no key material anywhere; exclusion from serialization
# --------------------------------------------------------------------------- #


def test_no_key_material_in_trace_health_or_logs(monkeypatch, tmp_path) -> None:
    """A4: with the key resolving from the hermes fallback, the sentinel
    value appears nowhere in the REST trace, the health body, or any warning
    record — labels only."""
    _write_hermes_dotenv(monkeypatch, tmp_path, ENV_KEY, SECRET_SENTINEL)
    config_path = tmp_path / "chimera.yaml"
    config_path.write_text(yaml.safe_dump(_full_config_dict()), encoding="utf-8")
    with structlog.testing.capture_logs() as logs:
        cfg = load_config(config_path)
        assert cfg.credential_sources["df90prov"] == CREDENTIAL_SOURCE_HERMES_DOTENV_FALLBACK
        engine = Engine(cfg, FakeGateway(_deliberation_responder()))
        client = TestClient(create_app(config=cfg, engine=engine))
        deliberation = client.post("/v1/deliberate", json={"prompt": "hello", "formation": "auto"})
        health = client.get("/v1/health")
    assert deliberation.status_code == 200
    assert health.status_code == 200
    assert SECRET_SENTINEL not in deliberation.text
    assert SECRET_SENTINEL not in health.text
    assert SECRET_SENTINEL not in json.dumps(logs)
    # And the map itself carries only labels.
    assert set(cfg.credential_sources.values()) <= {
        CREDENTIAL_SOURCE_PROCESS_ENV,
        CREDENTIAL_SOURCE_REPO_DOTENV,
        CREDENTIAL_SOURCE_HERMES_DOTENV_FALLBACK,
        CREDENTIAL_SOURCE_API_KEYS,
        CREDENTIAL_SOURCE_PROVIDER_API_KEY,
        CREDENTIAL_SOURCE_MISSING,
    }


def test_credential_sources_excluded_from_serialization(monkeypatch, tmp_path) -> None:
    """Load-time bookkeeping stays internal (mirrors
    ``configured_provider_names``): absent from every serialization."""
    cfg, _path = _loaded_working_config(monkeypatch, tmp_path)
    assert cfg.credential_sources  # provenance recorded
    assert "credential_sources" not in cfg.model_dump(mode="python")
    assert "credential_sources" not in json.loads(cfg.model_dump_json())


def test_provider_credential_source_unknown_provider_is_none() -> None:
    """No provenance for a provider (not declared / programmatic config) →
    ``None`` — callers must treat that as unknown, not as a label."""
    cfg = ChimeraConfig.model_validate(copy.deepcopy(CONFIG_DICT))
    assert provider_credential_source(cfg, "zai") is None
    assert provider_credential_source(cfg, "not-a-provider") is None


# --------------------------------------------------------------------------- #
# 6. End-to-end: a successful generic-provider route names its REAL source
#    (CHIMERA-V2-REVIEW-08) — real socket, real LiteLLM, loopback stub
# --------------------------------------------------------------------------- #

#: Provider/model names mirroring the filed evidence: a generic
#: OpenAI-compatible provider with a locally configured literal key.
REVIEW08_PROVIDER = "mock"
REVIEW08_MODEL_ID = "mock/m1"
REVIEW08_KEY = "rev08-literal-mock-key"
#: The second fixture literal (provider-entry shape) — deliberately distinct
#: from REVIEW08_KEY so the two tests cannot pass on each other's labels.
REVIEW08_PROVIDER_ENTRY_KEY = "rev08-provider-entry-mock-key"


def _review08_config_dict(base_url: str, *, via_api_keys: bool) -> dict:
    """A generic-provider config whose ONLY credential is a literal key."""
    provider: dict = {"base_url": base_url}
    if not via_api_keys:
        provider["api_key"] = REVIEW08_PROVIDER_ENTRY_KEY
    cfg: dict = {
        "providers": {REVIEW08_PROVIDER: provider},
        "models": {
            REVIEW08_MODEL_ID: {
                "categories": {
                    "code": 90.0,
                    "analysis": 90.0,
                    "design": 90.0,
                    "audit": 90.0,
                    "reasoning": 90.0,
                },
                "cost_tier": "budget",
                "provider": REVIEW08_PROVIDER,
            }
        },
        "defaults": {
            "dispatcher": REVIEW08_MODEL_ID,
            "default_worker": REVIEW08_MODEL_ID,
            "default_aggregator": REVIEW08_MODEL_ID,
        },
        "auto_formation": {"restrict_to_credentialed_providers": False},
        "retry": {"max_attempts": 1, "base_delay_ms": 1, "max_delay_ms": 5},
        "observability": {"log_level": "warning", "trace_enabled": False},
    }
    if via_api_keys:
        cfg["api_keys"] = {REVIEW08_PROVIDER: REVIEW08_KEY}
    return cfg


def _review08_deliberation(tmp_path, cfg_dict: dict):  # type: ignore[no-untyped-def]
    """load_config → REAL LiteLLMGateway engine → POST /v1/deliberate.

    The stub's prose output is not valid dispatch JSON, so the run degrades
    to the generic fallback DAG — every stage still routes over the socket
    through the literal key, which is the filed evidence's shape (dispatch,
    worker, aggregator all on the generic provider, HTTP 200).
    """
    config_path = tmp_path / "chimera.yaml"
    config_path.write_text(yaml.safe_dump(cfg_dict), encoding="utf-8")
    cfg = load_config(config_path)
    engine = Engine(cfg, LiteLLMGateway(cfg))
    client = TestClient(create_app(config=cfg, engine=engine))
    return client.post("/v1/deliberate", json={"prompt": "hello", "formation": "auto"})


def test_successful_route_names_literal_api_keys_source(monkeypatch, tmp_path) -> None:
    """AC (CHIMERA-V2-REVIEW-08), api_keys-only literal: HTTP 200 with
    ``trace.credential_sources.mock`` naming ``api_keys`` — not ``missing``
    — while the stub received exactly the configured key on every request."""
    with _compat_stub() as (base_url, seen):
        r = _review08_deliberation(tmp_path, _review08_config_dict(base_url, via_api_keys=True))
    assert r.status_code == 200, r.text
    trace = r.json()["trace"]
    source = trace["credential_sources"][REVIEW08_PROVIDER]
    assert source == CREDENTIAL_SOURCE_API_KEYS
    assert source != CREDENTIAL_SOURCE_MISSING
    # The gateway kept using the configured literal: every request the stub
    # saw carried it as the Bearer credential.
    assert seen, "the loopback stub saw no requests"
    assert all(req["authorization"] == f"Bearer {REVIEW08_KEY}" for req in seen), [
        req["authorization"] for req in seen
    ]
    # Labels only — the key value never surfaces in the response body.
    assert REVIEW08_KEY not in r.text


def test_successful_route_names_provider_api_key_source(monkeypatch, tmp_path) -> None:
    """AC (CHIMERA-V2-REVIEW-08), provider.api_key-only literal: same
    contract with the key on the provider entry instead of the shortcut."""
    with _compat_stub() as (base_url, seen):
        r = _review08_deliberation(tmp_path, _review08_config_dict(base_url, via_api_keys=False))
    assert r.status_code == 200, r.text
    trace = r.json()["trace"]
    source = trace["credential_sources"][REVIEW08_PROVIDER]
    assert source == CREDENTIAL_SOURCE_PROVIDER_API_KEY
    assert source != CREDENTIAL_SOURCE_MISSING
    assert seen, "the loopback stub saw no requests"
    assert all(req["authorization"] == f"Bearer {REVIEW08_PROVIDER_ENTRY_KEY}" for req in seen), [
        req["authorization"] for req in seen
    ]
    assert REVIEW08_PROVIDER_ENTRY_KEY not in r.text


# CHIMERA-V2-REVIEW-09: exercise the documentation itself, not a lookalike dict.
LOCAL_FIXTURE_ENV = "CHIMERA_LOCAL_FIXTURE_KEY"
LOCAL_FIXTURE_KEY = "local-fixture-only"
LOCAL_FIXTURE_DOCS = ("README.md", "docs/CONFIG.md")


def _documented_local_fixture_config(doc: str) -> dict:
    text = (Path(__file__).resolve().parents[1] / doc).read_text(encoding="utf-8")
    section = text.split("#### Minimal local fixture", 1)[1]
    snippet = section.split("```yaml\n", 1)[1].split("```", 1)[0]
    raw = yaml.safe_load(snippet)
    assert raw["provider_discovery"] is False
    assert raw["providers"]["mock"] == {
        "base_url": "http://127.0.0.1:18081/v1",
        "api_key_env": LOCAL_FIXTURE_ENV,
    }
    assert "api_keys" not in raw  # no empty shortcut shadowing the provider key
    assert set(raw["models"]) == {"mock/m1"}
    return raw


@pytest.mark.parametrize("doc", LOCAL_FIXTURE_DOCS)
def test_documented_local_fixture_reaches_provider(monkeypatch, tmp_path, doc: str) -> None:
    """The copied YAML, env var, real gateway and loopback socket return 200."""
    monkeypatch.setenv(LOCAL_FIXTURE_ENV, LOCAL_FIXTURE_KEY)
    raw = _documented_local_fixture_config(doc)
    with _compat_stub() as (base_url, seen):
        # Only the ephemeral port differs from the copy-paste recipe.
        raw["providers"]["mock"]["base_url"] = base_url
        path = tmp_path / "local-fixture.yaml"
        path.write_text(yaml.safe_dump(raw), encoding="utf-8")
        cfg = load_config(path)
        assert cfg.providers["mock"].api_key == LOCAL_FIXTURE_KEY
        assert cfg.credential_sources["mock"] == CREDENTIAL_SOURCE_PROCESS_ENV
        with TestClient(create_app(config=cfg)) as client:
            response = client.post("/v1/deliberate", json={"prompt": "hello", "formation": "simple"})
    assert response.status_code == 200, response.text
    assert response.json()["answer"] == "STUB-OK"
    assert response.json()["trace"]["credential_sources"]["mock"] == CREDENTIAL_SOURCE_PROCESS_ENV
    assert seen, "the documented config never reached the fixture"
    assert all(request["path"] == "/v1/chat/completions" for request in seen)
    assert all(request["body"]["model"] == "m1" for request in seen)
    assert all(request["authorization"] == f"Bearer {LOCAL_FIXTURE_KEY}" for request in seen)
    assert LOCAL_FIXTURE_KEY not in response.text


@pytest.mark.parametrize("doc", LOCAL_FIXTURE_DOCS)
def test_documented_local_fixture_missing_credentials_is_typed(monkeypatch, tmp_path, doc: str) -> None:
    """A reachable fixture does not turn missing credentials into success."""
    import litellm

    monkeypatch.delenv(LOCAL_FIXTURE_ENV, raising=False)
    for name in ("OPENAI_API_KEY", "OPENAI_KEY", "MOCK_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(litellm, "api_key", None)
    monkeypatch.setattr(litellm, "openai_key", None)
    raw = _documented_local_fixture_config(doc)
    with _compat_stub() as (base_url, seen):
        raw["providers"]["mock"]["base_url"] = base_url
        path = tmp_path / "local-fixture.yaml"
        path.write_text(yaml.safe_dump(raw), encoding="utf-8")
        cfg = load_config(path)
        assert cfg.credential_sources["mock"] == CREDENTIAL_SOURCE_MISSING
        with TestClient(create_app(config=cfg)) as client:
            health = client.get("/v1/health").json()
            response = client.post("/v1/deliberate", json={"prompt": "hello", "formation": "simple"})
    assert health["details"]["providers"]["mock"]["error_class"] == "missing_credentials"
    assert response.status_code == 502, response.text
    assert response.json()["error"]["type"] == "upstream_error"
    assert LOCAL_FIXTURE_ENV in response.json()["error"]["message"]
    assert not seen, "a missing key unexpectedly reached the fixture"
