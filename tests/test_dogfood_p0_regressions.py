"""Regression tests for dogfood P0 bugs.

* Bug 1 (dogfood-http-server-no-creds): provider credential resolution must
  fall back to the repo ``.env`` (next to chimera.yaml) and then to
  ``~/.hermes/.env`` when the process environment lacks the variable.
  Precedence: process env > repo .env > ~/.hermes/.env.

* Bug 2 (dogfood-error-200-as-success): when a deliberation produces no
  usable answer (the answer stage degraded), ``/v1/deliberate`` and
  ``/v1/chat/completions`` must return HTTP 502 with an OpenAI-compatible
  structured error body instead of 200 with a placeholder string.
  Partial degradation (real merged answer) must still return 200.
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

import chimera.config as chimera_config  # noqa: E402
from chimera.api.server import create_app  # noqa: E402
from chimera.config import ChimeraConfig  # noqa: E402
from chimera.engine import Engine  # noqa: E402
from chimera.gateway import GatewayError, GatewayResponse  # noqa: E402
from tests.conftest import FakeGateway, dispatch_json  # noqa: E402


def _resp(text, model, ti=10, to=10):  # type: ignore[no-untyped-def]
    return GatewayResponse(text=text, model=model, tokens_input=ti, tokens_output=to)


# --------------------------------------------------------------------------- #
# Bug 1 — credential resolution fallbacks
# --------------------------------------------------------------------------- #

_ENV_KEY = "DOGFOOD_TEST_API_KEY"
_PROVIDER_DICT = {
    "providers": {
        "dogfood": {"base_url": "https://example.invalid/v1", "api_key_env": _ENV_KEY},
    },
    "models": {},
    "defaults": {
        "dispatcher": "m",
        "default_worker": "m",
        "default_aggregator": "m",
    },
}


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):  # type: ignore[no-untyped-def]
    """Ensure the test variable is never present in the process env and the
    hermes dotenv cache starts cold for each test."""
    monkeypatch.delenv(_ENV_KEY, raising=False)
    monkeypatch.setattr(chimera_config, "_hermes_dotenv_cache", None)
    yield


def _provider_key(cfg: ChimeraConfig) -> str | None:
    return cfg.providers["dogfood"].api_key


def test_provider_key_from_process_env(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv(_ENV_KEY, "from-process-env")
    cfg = ChimeraConfig.model_validate(_PROVIDER_DICT)
    assert _provider_key(cfg) == "from-process-env"


def test_provider_key_falls_back_to_hermes_dotenv(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """No process env var → resolve from ~/.hermes/.env."""
    hermes_dir = tmp_path / ".hermes"
    hermes_dir.mkdir()
    (hermes_dir / ".env").write_text(f"{_ENV_KEY}=from-hermes-dotenv\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(tmp_path))
    cfg = ChimeraConfig.model_validate(_PROVIDER_DICT)
    assert _provider_key(cfg) == "from-hermes-dotenv"


def test_load_config_reads_repo_dotenv(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """No process env var → repo .env next to chimera.yaml is loaded."""
    import yaml

    (tmp_path / "chimera.yaml").write_text(
        yaml.safe_dump({**_PROVIDER_DICT, "models": {}, "formations": {}}),
        encoding="utf-8",
    )
    (tmp_path / ".env").write_text(f"{_ENV_KEY}=from-repo-dotenv\n", encoding="utf-8")
    cfg = chimera_config.load_config(tmp_path / "chimera.yaml")
    assert _provider_key(cfg) == "from-repo-dotenv"


def test_process_env_beats_repo_dotenv(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Precedence: an explicit process env var wins over the repo .env."""
    import yaml

    (tmp_path / "chimera.yaml").write_text(
        yaml.safe_dump({**_PROVIDER_DICT, "models": {}, "formations": {}}),
        encoding="utf-8",
    )
    (tmp_path / ".env").write_text(f"{_ENV_KEY}=from-repo-dotenv\n", encoding="utf-8")
    monkeypatch.setenv(_ENV_KEY, "from-process-env")
    cfg = chimera_config.load_config(tmp_path / "chimera.yaml")
    assert _provider_key(cfg) == "from-process-env"


def test_repo_dotenv_beats_hermes_dotenv(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Precedence: repo .env wins over the ~/.hermes/.env fallback."""
    import yaml

    (tmp_path / "chimera.yaml").write_text(
        yaml.safe_dump({**_PROVIDER_DICT, "models": {}, "formations": {}}),
        encoding="utf-8",
    )
    (tmp_path / ".env").write_text(f"{_ENV_KEY}=from-repo-dotenv\n", encoding="utf-8")
    # Seed the hermes dotenv cache directly with a competing value.
    monkeypatch.setattr(
        chimera_config, "_hermes_dotenv_cache", {_ENV_KEY: "from-hermes-dotenv"}
    )
    cfg = chimera_config.load_config(tmp_path / "chimera.yaml")
    assert _provider_key(cfg) == "from-repo-dotenv"


# --------------------------------------------------------------------------- #
# Bug 2 — no usable answer → HTTP 502 with structured error
# --------------------------------------------------------------------------- #

def _make_client(config, responder):  # type: ignore[no-untyped-def]
    engine = Engine(config, FakeGateway(responder))
    app = create_app(config=config, engine=engine)
    return TestClient(app)


def _all_stages_fail(model, messages, response_format=None, **kw):  # type: ignore[no-untyped-def]
    """Dispatcher succeeds; every DAG stage (workers + aggregator) fails."""
    if response_format is not None:
        return _resp(dispatch_json(), model)
    raise GatewayError("upstream exploded")


def test_deliberate_degraded_answer_returns_502(config) -> None:  # type: ignore[no-untyped-def]
    client = _make_client(config, _all_stages_fail)
    r = client.post("/v1/deliberate", json={"prompt": "hello", "formation": "auto"})
    assert r.status_code == 502, r.text
    err = r.json()["error"]
    assert err["type"] == "upstream_error"
    assert "upstream exploded" in err["message"]
    assert len(err["request_id"]) > 0


def test_chat_completions_degraded_answer_returns_502(config) -> None:  # type: ignore[no-untyped-def]
    client = _make_client(config, _all_stages_fail)
    r = client.post(
        "/v1/chat/completions",
        json={"model": "auto", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.status_code == 502, r.text
    err = r.json()["error"]
    assert err["type"] == "upstream_error"
    assert "upstream exploded" in err["message"]
    assert len(err["request_id"]) > 0


def test_deliberate_partial_degradation_still_200(config) -> None:  # type: ignore[no-untyped-def]
    """Workers fail but the aggregator succeeds with a real merged answer → 200."""

    def responder(model, messages, response_format=None, **kw):
        if response_format is not None:
            return _resp(dispatch_json(), model)
        joined = json.dumps(messages)
        if "Upstream outputs" in joined:
            return _resp("REAL MERGED ANSWER", model, 60, 90)
        raise GatewayError("worker down")

    client = _make_client(config, responder)
    r = client.post("/v1/deliberate", json={"prompt": "hello", "formation": "auto"})
    assert r.status_code == 200, r.text
    assert r.json()["answer"] == "REAL MERGED ANSWER"


def test_chat_completions_partial_degradation_still_200(config) -> None:  # type: ignore[no-untyped-def]
    def responder(model, messages, response_format=None, **kw):
        if response_format is not None:
            return _resp(dispatch_json(), model)
        joined = json.dumps(messages)
        if "Upstream outputs" in joined:
            return _resp("REAL MERGED ANSWER", model, 60, 90)
        raise GatewayError("worker down")

    client = _make_client(config, responder)
    r = client.post(
        "/v1/chat/completions",
        json={"model": "auto", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["choices"][0]["message"]["content"] == "REAL MERGED ANSWER"


def test_health_unchanged_after_degraded_run(config) -> None:  # type: ignore[no-untyped-def]
    """The 502 change must not affect /v1/health behavior."""
    client = _make_client(config, _all_stages_fail)
    r = client.get("/v1/health")
    assert r.status_code == 200
    assert r.json()["details"]["config_loaded"] is True
