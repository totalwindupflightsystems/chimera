"""Credential-source observability (DF-CHIMERA-V2-90).

A provider key missing from the process env silently falls back to
``~/.hermes/.env`` — on a host that happens to carry that file a deliberation
SUCCEEDS with zero user-visible indication of where the credential came from,
which makes "did I configure credentials?" undiagnosable on a fresh install.

These tests pin the additive observability:

* every provider key carries a source label — ``process_env`` /
  ``repo_dotenv`` / ``hermes_dotenv_fallback`` / ``missing`` — recorded at
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

import pytest
import structlog.testing
import yaml

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from chimera import config as chimera_config  # noqa: E402
from chimera.api.server import create_app  # noqa: E402
from chimera.config import (  # noqa: E402
    CREDENTIAL_SOURCE_HERMES_DOTENV_FALLBACK,
    CREDENTIAL_SOURCE_MISSING,
    CREDENTIAL_SOURCE_PROCESS_ENV,
    CREDENTIAL_SOURCE_REPO_DOTENV,
    ChimeraConfig,
    load_config,
    provider_credential_source,
)
from chimera.engine import Engine  # noqa: E402
from tests.conftest import CONFIG_DICT, FakeGateway, dispatch_json, resp  # noqa: E402

#: Env var whose absence forces the hermes-dotenv fallback in these tests.
#: Deliberately NOT a name a real host exports (the delenv makes even that
#: impossible), except in the deepseek-named test that mirrors the filed
#: scenario verbatim.
ENV_KEY = "DF90_TEST_PROVIDER_KEY"

#: The hermes-dotenv fallback value used in fallback tests. Any appearance of
#: this sentinel in trace / health / log output is a leak — asserted nowhere.
SECRET_SENTINEL = "df90-secret-value-xyzzy"

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


def _api_keys_cfg_dict(provider_api_key_env: bool) -> dict:
    """Template-shaped config: ``api_keys: {<prov>: ${VAR}}``.

    ``provider_api_key_env=False`` isolates the substitution path (the
    per-provider validator contributes nothing).
    """
    provider: dict = {"base_url": "https://df90.example/v1"}
    if provider_api_key_env:
        provider["api_key_env"] = ENV_KEY
    return {
        "api_keys": {"df90prov": "${" + ENV_KEY + "}"},
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
