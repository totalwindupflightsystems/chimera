"""Unit tests for ``_check_providers`` — the provider health probe.

Covers the dogfood P1 fix (health false negatives):
* configurable ``health_timeout_s`` (default 10.0, no hardcoded 3.0),
* cheap ping (``max_tokens=1``) and error classes
  (``timeout`` | ``missing-credentials`` | ``auth`` | ``api`` | ``quota``),
* multi-model retry for non-timeout failures with ``model_tested``
  reflecting the last attempt.

Covers INT-ZAI-002 (probe hygiene):
* the probe call carries ``probe=True`` so the gateway does not report its own
  1-token cap as a provider token-limit event, and
* a quota/billing failure (429, or the INT-ZAI-001 "Insufficient balance or no
  resource package." prose) is classified ``quota`` — reachable-and-
  authenticated-but-unfunded — instead of the useless catch-all ``api``.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from chimera.api.server import _check_providers
from chimera.config import ChimeraConfig, ServerConfig
from chimera.gateway import GatewayResponse, _build_response


def _config(
    *,
    models: dict[str, str],
    health_timeout_s: float = 5.0,
    api_keys: dict[str, str] | None = None,
) -> ChimeraConfig:
    """Build a minimal config mapping model name → provider name."""
    first_model = next(iter(models))
    cfg_dict = {
        "providers": {
            name: {"base_url": f"https://{name}.example/v1"}
            for name in set(models.values())
        },
        "models": {
            name: {"provider": provider, "cost_tier": "budget"}
            for name, provider in models.items()
        },
        "defaults": {
            "dispatcher": first_model,
            "default_worker": first_model,
            "default_aggregator": first_model,
        },
        "server": {
            "host": "127.0.0.1",
            "port": 8000,
            "health_timeout_s": health_timeout_s,
        },
    }
    cfg = ChimeraConfig.model_validate(cfg_dict)
    if api_keys:
        cfg.api_keys.update(api_keys)
    return cfg


class _StatusError(RuntimeError):
    """Provider error carrying an HTTP status code, like litellm's."""

    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


#: The INT-ZAI-001 quota/billing prose (litellm.RateLimitError), verbatim.
_QUOTA_MESSAGE = "Insufficient balance or no resource package. Please recharge."


class _ProbeGateway:
    """Scriptable gateway: per-model behavior + recorded probe calls."""

    def __init__(self, behavior: dict[str, str]) -> None:
        # model name → "ok" | "slow" | "auth" | "api" | "quota" | "quota_msg"
        self.behavior = behavior
        self.calls: list[tuple[str, list[dict[str, str]]]] = []
        self.kwargs_seen: list[dict[str, object]] = []

    async def complete(
        self,
        model: str,
        messages: list[dict[str, str]],
        **kwargs: object,
    ) -> GatewayResponse:
        self.calls.append((model, messages))
        self.kwargs_seen.append(kwargs)
        action = self.behavior.get(model, "ok")
        if action == "ok":
            return GatewayResponse(
                text="pong", model=model, tokens_input=1, tokens_output=1,
            )
        if action == "slow":
            await asyncio.sleep(30)
            raise AssertionError("unreachable")
        if action == "auth":
            raise RuntimeError("AuthenticationError: 401 invalid api key")
        if action == "api":
            raise RuntimeError("upstream 500: provider exploded")
        if action == "quota":
            raise _StatusError("RateLimitError: rate limited", status_code=429)
        if action == "quota_msg":
            raise RuntimeError(_QUOTA_MESSAGE)
        raise AssertionError(f"unknown behavior {action!r}")


class _TruncatingProbeGateway:
    """A gateway that answers through the REAL ``_build_response``.

    It replays what :class:`~chimera.gateway.LiteLLMGateway` does for the
    health ping: a 1-token completion whose ``finish_reason`` is ``"length"``.
    Passing the received ``probe`` kwarg (defaulting to ``False``, exactly like
    the real method's signature) makes the warning behaviour OBSERVABLE from
    the health path: if the probe call site stopped sending ``probe=True``,
    the warning would come back and these assertions fail.
    """

    def __init__(self) -> None:
        self.kwargs_seen: list[dict[str, object]] = []
        self.responses: list[GatewayResponse] = []

    async def complete(
        self,
        model: str,
        messages: list[dict[str, str]],
        **kwargs: object,
    ) -> GatewayResponse:
        self.kwargs_seen.append(kwargs)
        result = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    finish_reason="length",
                    message=SimpleNamespace(content="p"),
                )
            ],
            usage=SimpleNamespace(prompt_tokens=7, completion_tokens=1),
        )
        response = _build_response(result, model, probe=bool(kwargs.get("probe", False)))
        self.responses.append(response)
        return response


# --------------------------------------------------------------------------- #
# Fast provider → healthy
# --------------------------------------------------------------------------- #


def test_fast_provider_healthy() -> None:
    cfg = _config(
        models={"deepseek/deepseek-v4-flash": "deepseek"},
        api_keys={"deepseek": "sk-test"},
    )
    gw = _ProbeGateway({})
    status = asyncio.run(_check_providers(cfg, gw))

    assert status["deepseek"]["healthy"] is True
    assert status["deepseek"]["model_tested"] == "deepseek/deepseek-v4-flash"
    # The ping stays cheap: single "ping" message, max_tokens=1, temperature=1
    assert gw.calls[0][1] == [{"role": "user", "content": "ping"}]
    assert gw.kwargs_seen[0]["max_tokens"] == 1
    assert gw.kwargs_seen[0]["temperature"] == 1


def test_probe_call_carries_probe_flag() -> None:
    """INT-ZAI-002: the health ping must mark itself as a probe."""
    cfg = _config(
        models={"deepseek/deepseek-v4-flash": "deepseek"},
        api_keys={"deepseek": "sk-test"},
    )
    gw = _ProbeGateway({})
    asyncio.run(_check_providers(cfg, gw))

    assert gw.kwargs_seen[0]["probe"] is True


def test_successful_ping_logs_no_token_limit_warning(capsys) -> None:
    """INT-ZAI-002: a healthy probe must not look like a token-limit event.

    The stub answers through the real ``_build_response`` with the ping's
    actual shape (``finish_reason="length"``), so this fails if the probe flag
    stops flowing from ``_check_providers`` into the gateway.
    """
    cfg = _config(
        models={"deepseek/deepseek-v4-flash": "deepseek"},
        api_keys={"deepseek": "sk-test"},
    )
    gw = _TruncatingProbeGateway()
    status = asyncio.run(_check_providers(cfg, gw))

    assert status["deepseek"]["healthy"] is True
    assert gw.responses[0].finish_reason == "length"
    captured = capsys.readouterr().out
    assert "token_limit_reached" not in captured, f"false warning emitted: {captured}"

    # Negative control: drop the flag and the same builder warns again.
    result = SimpleNamespace(
        choices=[
            SimpleNamespace(
                finish_reason="length",
                message=SimpleNamespace(content="p"),
            )
        ],
        usage=SimpleNamespace(prompt_tokens=7, completion_tokens=1),
    )
    _build_response(result, "deepseek/deepseek-v4-flash")
    assert "token_limit_reached" in capsys.readouterr().out


def test_multiple_providers_checked_concurrently() -> None:
    cfg = _config(
        models={"p1/a": "p1", "p2/b": "p2"},
        api_keys={"p1": "sk-1", "p2": "sk-2"},
    )
    gw = _ProbeGateway({})
    status = asyncio.run(_check_providers(cfg, gw))

    assert set(status) == {"p1", "p2"}
    assert all(status[p]["healthy"] for p in ("p1", "p2"))


# --------------------------------------------------------------------------- #
# Slow provider → timeout class (config-driven budget, not a hardcoded 3.0)
# --------------------------------------------------------------------------- #


def test_slow_provider_timeout_class() -> None:
    cfg = _config(
        models={"p1/slow": "p1"},
        health_timeout_s=0.2,
        api_keys={"p1": "sk-test"},
    )
    gw = _ProbeGateway({"p1/slow": "slow"})
    status = asyncio.run(_check_providers(cfg, gw))

    info = status["p1"]
    assert info["healthy"] is False
    assert info["error"].startswith("timeout:")
    # The tiny budget proves the timeout comes from config, not a 3.0 hardcode
    assert "0.2s" in info["error"]


def test_server_config_health_timeout_default() -> None:
    """C1: ServerConfig defaults health_timeout_s to 10.0."""
    assert ServerConfig().health_timeout_s == 10.0
    assert ServerConfig(health_timeout_s=2.5).health_timeout_s == 2.5


# --------------------------------------------------------------------------- #
# Missing credentials → classified without a live call
# --------------------------------------------------------------------------- #


def test_missing_credentials_class() -> None:
    # Provider "ghost" has no config key, no api_key_env, no env fallback map.
    cfg = _config(models={"ghost/model": "ghost"})
    gw = _ProbeGateway({})
    status = asyncio.run(_check_providers(cfg, gw))

    info = status["ghost"]
    assert info["healthy"] is False
    assert info["error"].startswith("missing-credentials:")
    assert gw.calls == []  # no live call attempted


def test_missing_credentials_resolved_from_env(monkeypatch) -> None:
    """A provider key resolvable from the environment is not missing."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-env")
    cfg = _config(models={"deepseek/deepseek-v4-flash": "deepseek"})
    gw = _ProbeGateway({})
    status = asyncio.run(_check_providers(cfg, gw))

    assert status["deepseek"]["healthy"] is True


# --------------------------------------------------------------------------- #
# Non-timeout errors → retry up to 3 models, model_tested = last attempt
# --------------------------------------------------------------------------- #


def test_auth_error_retries_all_models_then_unhealthy() -> None:
    cfg = _config(
        models={"prov/a": "prov", "prov/b": "prov", "prov/c": "prov"},
        api_keys={"prov": "sk-test"},
    )
    gw = _ProbeGateway({"prov/a": "auth", "prov/b": "auth", "prov/c": "auth"})
    status = asyncio.run(_check_providers(cfg, gw))

    info = status["prov"]
    assert info["healthy"] is False
    assert info["error"].startswith("auth:")
    assert info["model_tested"] == "prov/c"
    assert [m for m, _ in gw.calls] == ["prov/a", "prov/b", "prov/c"]


def test_auth_error_retries_then_success() -> None:
    cfg = _config(
        models={"prov/a": "prov", "prov/b": "prov"},
        api_keys={"prov": "sk-test"},
    )
    gw = _ProbeGateway({"prov/a": "auth", "prov/b": "ok"})
    status = asyncio.run(_check_providers(cfg, gw))

    info = status["prov"]
    assert info["healthy"] is True
    assert info["model_tested"] == "prov/b"
    assert [m for m, _ in gw.calls] == ["prov/a", "prov/b"]


def test_api_error_class() -> None:
    cfg = _config(
        models={"prov/a": "prov"},
        api_keys={"prov": "sk-test"},
    )
    gw = _ProbeGateway({"prov/a": "api"})
    status = asyncio.run(_check_providers(cfg, gw))

    info = status["prov"]
    assert info["healthy"] is False
    assert info["error"].startswith("api:")
    assert info["model_tested"] == "prov/a"


# --------------------------------------------------------------------------- #
# Quota / billing failures → "quota" (INT-ZAI-001 class), non-terminal
# --------------------------------------------------------------------------- #


def test_quota_429_class_retries_all_models_then_unhealthy() -> None:
    """A 429 is a quota condition and is NOT terminal (all models retried)."""
    cfg = _config(
        models={"prov/a": "prov", "prov/b": "prov", "prov/c": "prov"},
        api_keys={"prov": "sk-test"},
    )
    gw = _ProbeGateway({"prov/a": "quota", "prov/b": "quota", "prov/c": "quota"})
    status = asyncio.run(_check_providers(cfg, gw))

    info = status["prov"]
    assert info["healthy"] is False
    assert info["error"].startswith("quota:")
    assert info["model_tested"] == "prov/c"
    assert [m for m, _ in gw.calls] == ["prov/a", "prov/b", "prov/c"]


def test_quota_429_then_success_is_healthy() -> None:
    """A blocked model must not condemn a provider that still works."""
    cfg = _config(
        models={"prov/a": "prov", "prov/b": "prov"},
        api_keys={"prov": "sk-test"},
    )
    gw = _ProbeGateway({"prov/a": "quota", "prov/b": "ok"})
    status = asyncio.run(_check_providers(cfg, gw))

    info = status["prov"]
    assert info["healthy"] is True
    assert info["model_tested"] == "prov/b"
    assert [m for m, _ in gw.calls] == ["prov/a", "prov/b"]


def test_quota_message_without_status_code_class() -> None:
    """The INT-ZAI-001 balance prose alone classifies as ``quota``."""
    cfg = _config(
        models={"prov/a": "prov"},
        api_keys={"prov": "sk-test"},
    )
    gw = _ProbeGateway({"prov/a": "quota_msg"})
    status = asyncio.run(_check_providers(cfg, gw))

    info = status["prov"]
    assert info["healthy"] is False
    assert info["error"].startswith("quota:")
    # The provider's own words survive into the operator-facing detail.
    assert "recharge" in info["error"]
    assert info["model_tested"] == "prov/a"


def test_timeout_error_does_not_retry_next_model() -> None:
    """A timeout on the first model is terminal — no retry of other models."""
    cfg = _config(
        models={"prov/a": "prov", "prov/b": "prov"},
        health_timeout_s=0.2,
        api_keys={"prov": "sk-test"},
    )
    gw = _ProbeGateway({"prov/a": "slow", "prov/b": "ok"})
    status = asyncio.run(_check_providers(cfg, gw))

    info = status["prov"]
    assert info["healthy"] is False
    assert info["error"].startswith("timeout:")
    assert [m for m, _ in gw.calls] == ["prov/a"]


def test_no_models_for_provider_is_healthy_note() -> None:
    cfg = _config(models={"other/model": "other"})
    # A configured provider that has no models in the catalog.
    cfg.providers["lonely"] = cfg.providers["other"].model_copy(
        update={"base_url": "https://lonely.example/v1"},
    )
    gw = _ProbeGateway({})
    status = asyncio.run(_check_providers(cfg, gw))

    info = status["lonely"]
    assert info["healthy"] is True
    assert "no models configured" in info["note"]
    assert gw.calls == []
