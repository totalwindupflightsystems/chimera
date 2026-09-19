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

Covers DF-CHIMERA-V2-14 (machine-readable degraded reason):
* every FAILED provider carries ``error_class``
  (``missing_credentials`` | ``timeout`` | ``auth`` | ``quota`` | ``api``)
  while a healthy one keeps its exact previous shape, and
* ``GET /v1/health`` exposes the top-level, sorted ``unhealthy_providers``
  list (``[]`` exactly when ``status == "healthy"``) without changing any
  pre-existing key or the always-200 contract.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from chimera.api.server import _check_providers, create_app  # noqa: E402
from chimera.config import ChimeraConfig, ServerConfig  # noqa: E402
from chimera.engine import Engine  # noqa: E402
from chimera.gateway import GatewayResponse, LiteLLMGateway, _build_response  # noqa: E402
from tests.conftest import FakeGateway  # noqa: E402


def _config(
    *,
    models: dict[str, str],
    health_timeout_s: float = 5.0,
    api_keys: dict[str, str] | None = None,
    retry: dict[str, Any] | None = None,
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
    if retry is not None:
        cfg_dict["retry"] = retry
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

#: The measured z.ai quota-exhaustion condition (DF-CHIMERA-V2-16, 2026-09-18):
#: http=429 in 0.93-1.30 s with this body while the account is exhausted.
_ZAI_QUOTA_MESSAGE = (
    "litellm.RateLimitError: Weekly/Monthly Limit Exhausted. "
    "Your limit will reset at 2026-09-20 04:07:32"
)


class _ProbeGateway:
    """Scriptable gateway: per-model behavior + recorded probe calls."""

    def __init__(self, behavior: dict[str, str]) -> None:
        # model name → "ok" | "slow" | "auth" | "api" | "quota" | "quota_msg"
        #            | "zai_quota"
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
        if action == "zai_quota":
            # The measured DF-CHIMERA-V2-16 condition: a real 429 + the
            # provider's own reset prose.
            raise _StatusError(_ZAI_QUOTA_MESSAGE, status_code=429)
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


# --------------------------------------------------------------------------- #
# DF-CHIMERA-V2-16: a quota-exhausted provider is reported as quota, not timeout
# --------------------------------------------------------------------------- #

#: The body z.ai returns while the account is quota-exhausted (measured
#: 2026-09-18: http=429, 0.93-1.30 s, while the retry ladder took 10.17-17.01 s).
_ZAI_QUOTA_BODY = (
    "Weekly/Monthly Limit Exhausted. Your limit will reset at 2026-09-20 04:07:32"
)


def _zai_quota_rate_limit_error() -> Exception:
    """The measured zai 429 as ``litellm`` raises it — real class, no network.

    ``litellm.RateLimitError`` is an ``APIStatusError``: it carries
    ``status_code=429``, and its ``str()`` is
    ``"litellm.RateLimitError: <provider body>"``.  That combination is what
    the probe must classify from, instead of counting tries until the shared
    health budget expires.
    """
    import httpx
    import litellm

    request = httpx.Request(
        "POST", "https://api.z.ai/api/coding/paas/v4/chat/completions",
    )
    response = httpx.Response(
        429, request=request, json={"error": {"code": "1310", "message": _ZAI_QUOTA_BODY}},
    )
    return litellm.RateLimitError(
        message=_ZAI_QUOTA_BODY,
        llm_provider="openai",
        model="glm-5.2",
        response=response,
    )


def test_zai_quota_429_reports_quota_with_provider_message() -> None:
    """DF-CHIMERA-V2-16 (criterion 2): quota, with the provider's own reset time.

    One upstream attempt per model means the fast 429 is what the probe sees:
    the verdict is ``quota`` (not the ``timeout`` the retry ladder fabricated),
    ``model_tested`` names the last model tried, and the operator reads z.ai's
    own words plus the reset timestamp.
    """
    models = {
        "zai-coding-plan/glm-5.2": "zai",
        "z-ai/glm-5": "zai",
        "z-ai/glm-5-turbo": "zai",
    }
    cfg = _config(
        models=models, api_keys={"zai": "sk-test"}, health_timeout_s=0.5,
    )
    gw = _ProbeGateway(dict.fromkeys(models, "zai_quota"))
    status = asyncio.run(_check_providers(cfg, gw))

    info = status["zai"]
    assert info["healthy"] is False
    assert info["error_class"] == "quota"
    assert info["model_tested"] == "z-ai/glm-5-turbo"
    assert "Weekly/Monthly Limit Exhausted" in info["error"]
    assert "2026-09-20 04:07:32" in info["error"]
    assert "timeout: no response within" not in info["error"]
    assert info["error"].startswith("quota:")
    # quota stays NON-terminal: all three models were probed (3 calls, not 1).
    assert [m for m, _ in gw.calls] == [
        "zai-coding-plan/glm-5.2", "z-ai/glm-5", "z-ai/glm-5-turbo",
    ]


def test_real_gateway_zai_quota_is_quota_not_timeout_offline() -> None:
    """DF-CHIMERA-V2-16 end-to-end over the REAL gateway, no network.

    ``litellm.acompletion`` is patched to raise the measured zai 429, the
    retry policy stays at 3 attempts with 500/1000 ms backoff, and the health
    budget is a deliberately tight 0.5 s.  Before the fix the ladder slept
    through that budget and ``/v1/health`` read ``timeout: no response within
    0.5s`` (no ``model_tested``); with one attempt per model the probe reports
    the provider's own verdict, and exactly one upstream call happens per
    model.
    """
    models = {
        "zai-coding-plan/glm-5.2": "zai",
        "z-ai/glm-5": "zai",
        "z-ai/glm-5-turbo": "zai",
    }
    cfg = _config(
        models=models,
        api_keys={"zai": "sk-test"},
        health_timeout_s=0.5,
        retry={"max_attempts": 3, "base_delay_ms": 500, "max_delay_ms": 1000},
    )
    exc = _zai_quota_rate_limit_error()
    attempts: list[str] = []

    def _always_429(**kwargs: Any) -> Any:
        attempts.append(str(kwargs.get("model")))
        raise exc

    gw = LiteLLMGateway(cfg)
    with patch("litellm.acompletion", side_effect=_always_429):
        status = asyncio.run(_check_providers(cfg, gw))

    info = status["zai"]
    assert info["healthy"] is False
    assert info["error_class"] == "quota"
    assert info["model_tested"] == "z-ai/glm-5-turbo"
    assert "Weekly/Monthly Limit Exhausted" in info["error"]
    assert "2026-09-20 04:07:32" in info["error"]
    assert "timeout: no response within" not in info["error"]
    # ONE attempt per model: 3 models → 3 upstream calls, never 3x3.
    assert len(attempts) == 3


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


def test_no_models_for_provider_is_unhealthy_note() -> None:
    """A provider with no models is never probed — proven nothing (CH-GAP-053).

    The note stays, but ``healthy`` is now false: a probe that cannot run
    must not read as a passing one.
    """
    cfg = _config(models={"other/model": "other"})
    # A configured provider that has no models in the catalog.
    cfg.providers["lonely"] = cfg.providers["other"].model_copy(
        update={"base_url": "https://lonely.example/v1"},
    )
    gw = _ProbeGateway({})
    status = asyncio.run(_check_providers(cfg, gw))

    info = status["lonely"]
    assert info["healthy"] is False
    assert "no models configured" in info["note"]
    assert gw.calls == []


# --------------------------------------------------------------------------- #
# DF-CHIMERA-V2-14 (a): error_class on every FAILED provider
# --------------------------------------------------------------------------- #

#: The vocabulary a client may branch on.  ``unknown`` is reserved as the
#: forward-compatible fallback — this endpoint never emits it today, because a
#: failure the classifier cannot place lands in ``api``.
_ERROR_CLASSES = frozenset(
    {"missing_credentials", "timeout", "auth", "quota", "api", "unknown"},
)


def test_error_class_missing_credentials() -> None:
    """A provider with no resolvable key is classed without a live call."""
    cfg = _config(models={"ghost/model": "ghost"})
    gw = _ProbeGateway({})
    info = asyncio.run(_check_providers(cfg, gw))["ghost"]

    assert info["error_class"] == "missing_credentials"
    assert info["error_class"] in _ERROR_CLASSES
    # Pre-existing fields keep their exact values on this path.
    assert info["healthy"] is False
    assert info["error"].startswith("missing-credentials:")
    assert "ghost" in info["error"]
    assert gw.calls == []


def test_error_class_timeout() -> None:
    """A probe timeout is classed ``timeout`` (proven by the 0.2s budget)."""
    cfg = _config(
        models={"p1/slow": "p1"}, health_timeout_s=0.2, api_keys={"p1": "sk-test"},
    )
    gw = _ProbeGateway({"p1/slow": "slow"})
    info = asyncio.run(_check_providers(cfg, gw))["p1"]

    assert info["error_class"] == "timeout"
    assert info["healthy"] is False
    assert info["error"].startswith("timeout:")
    assert "0.2s" in info["error"]


@pytest.mark.parametrize(
    ("behavior", "expected_class"),
    [("auth", "auth"), ("quota", "quota"), ("quota_msg", "quota"), ("api", "api")],
)
def test_error_class_for_provider_exception(
    behavior: str, expected_class: str,
) -> None:
    """Provider exceptions carry the class their ``error`` prefix names."""
    cfg = _config(models={"prov/a": "prov"}, api_keys={"prov": "sk-test"})
    gw = _ProbeGateway({"prov/a": behavior})
    info = asyncio.run(_check_providers(cfg, gw))["prov"]

    assert info["error_class"] == expected_class
    assert info["error_class"] in _ERROR_CLASSES
    assert info["error"].startswith(f"{expected_class}:")
    assert info["healthy"] is False


def test_error_class_generic_exception_is_non_empty() -> None:
    """An exception the classifier does not recognize still gets a class."""
    class _WeirdError(Exception):
        """Deliberately outside every classifier token list."""

    class _WeirdGateway:
        async def complete(self, model: str, messages: list, **kwargs: Any) -> Any:
            raise _WeirdError("the provider did something unheard of")

    cfg = _config(models={"prov/a": "prov"}, api_keys={"prov": "sk-test"})
    info = asyncio.run(_check_providers(cfg, _WeirdGateway()))["prov"]

    assert isinstance(info["error_class"], str)
    assert info["error_class"] != ""
    assert info["error_class"] in _ERROR_CLASSES
    assert info["healthy"] is False


def test_failed_provider_field_shape() -> None:
    """A failed provider adds ``error_class`` and nothing else."""
    cfg = _config(models={"prov/a": "prov"}, api_keys={"prov": "sk-test"})
    gw = _ProbeGateway({"prov/a": "api"})
    info = asyncio.run(_check_providers(cfg, gw))["prov"]

    assert set(info) == {"healthy", "error", "error_class", "model_tested"}


def test_healthy_provider_keeps_exact_previous_shape() -> None:
    """The additive change leaves a healthy provider's payload byte-identical."""
    cfg = _config(models={"prov/a": "prov"}, api_keys={"prov": "sk-test"})
    gw = _ProbeGateway({})
    info = asyncio.run(_check_providers(cfg, gw))["prov"]

    assert info == {"healthy": True, "model_tested": "prov/a"}


def test_no_models_provider_note_only_shape() -> None:
    """The note-only path carries exactly the note, nothing else (CH-GAP-053).

    No ``error_class`` — the provider did not fail a probe, it never had one
    to fail; the note is the machine-readable reason.
    """
    cfg = _config(models={"other/model": "other"})
    cfg.providers["lonely"] = cfg.providers["other"].model_copy(
        update={"base_url": "https://lonely.example/v1"},
    )
    gw = _ProbeGateway({})
    info = asyncio.run(_check_providers(cfg, gw))["lonely"]

    assert info == {"healthy": False, "note": "no models configured for provider"}


# --------------------------------------------------------------------------- #
# DF-CHIMERA-V2-14 (b): top-level unhealthy_providers on /v1/health
# --------------------------------------------------------------------------- #

def _stub_probe(
    status: dict[str, dict[str, Any]],
) -> Any:
    """An async stand-in for ``_check_providers`` returning *status*."""
    async def probe(config: ChimeraConfig, gateway: Any) -> dict[str, dict[str, Any]]:
        return status

    return probe


def _health_client(cfg: ChimeraConfig) -> TestClient:
    """TestClient for *cfg* — the probe is monkeypatched, so no real call."""
    return TestClient(create_app(config=cfg, engine=Engine(cfg, FakeGateway())))


def test_health_unhealthy_providers_lists_exactly_the_failing_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The list is sorted, exact, and absent of healthy providers."""
    cfg = _config(
        models={"alpha/1": "alpha", "beta/1": "beta", "zeta/1": "zeta"},
        api_keys={"alpha": "sk", "beta": "sk", "zeta": "sk"},
    )
    probe_status: dict[str, dict[str, Any]] = {
        "zeta": {"healthy": False, "error": "api: boom", "error_class": "api",
                 "model_tested": "zeta/m"},
        "beta": {"healthy": True, "model_tested": "beta/m"},
        "alpha": {"healthy": False,
                  "error": "timeout: no response within 0.2s",
                  "error_class": "timeout"},
    }
    monkeypatch.setattr(
        "chimera.api.server._check_providers", _stub_probe(probe_status),
    )
    r = _health_client(cfg).get("/v1/health")

    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "degraded"
    assert data["unhealthy_providers"] == ["alpha", "zeta"]
    # The per-provider detail is passed through untouched.
    assert data["details"]["providers"] == probe_status


def test_health_unhealthy_providers_empty_when_all_healthy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Healthy ⇒ [] — the field is present, never omitted."""
    cfg = _config(models={"a/1": "a"}, api_keys={"a": "sk"})
    probe_status: dict[str, dict[str, Any]] = {
        "a": {"healthy": True, "model_tested": "a/1"},
    }
    monkeypatch.setattr(
        "chimera.api.server._check_providers", _stub_probe(probe_status),
    )
    data = _health_client(cfg).get("/v1/health").json()

    assert data["status"] == "healthy"
    assert data["unhealthy_providers"] == []


def test_health_response_keeps_every_pre_existing_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Backwards compatibility: no pre-existing key moved or changed shape."""
    cfg = _config(models={"a/1": "a", "b/1": "b"},
                  api_keys={"a": "sk", "b": "sk"})
    probe_status: dict[str, dict[str, Any]] = {
        "a": {"healthy": True, "model_tested": "a/1"},
        "b": {"healthy": False, "error": "quota: recharge", "error_class": "quota",
              "model_tested": "b/1"},
    }
    monkeypatch.setattr(
        "chimera.api.server._check_providers", _stub_probe(probe_status),
    )
    r = _health_client(cfg).get("/v1/health")

    assert r.status_code == 200
    data = r.json()
    assert set(data) == {"status", "unhealthy_providers", "details"}
    details = data["details"]
    assert set(details) == {
        "config_loaded", "models_configured", "providers_configured",
        "commit", "providers",
    }
    assert details["config_loaded"] is True
    assert details["models_configured"] == len(cfg.models)
    assert details["providers_configured"] == len(cfg.providers)
    assert isinstance(details["commit"], str)
    assert details["providers"] == probe_status


def test_health_names_the_provider_a_real_probe_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-end over the REAL probe: only the failing provider is named.

    The probe output comes from ``_check_providers`` itself (scripted gateway,
    one provider failing), so this pins the wiring, not just the handler.
    """
    cfg = _config(
        models={"good/1": "good", "bad/1": "bad"},
        api_keys={"good": "sk", "bad": "sk"},
    )
    probe_gw = _ProbeGateway({"bad/1": "api"})
    real_status = asyncio.run(_check_providers(cfg, probe_gw))
    assert set(real_status) == {"good", "bad"}
    assert real_status["good"]["healthy"] is True
    assert real_status["bad"]["error_class"] == "api"

    monkeypatch.setattr(
        "chimera.api.server._check_providers", _stub_probe(real_status),
    )
    data = _health_client(cfg).get("/v1/health").json()

    assert data["status"] == "degraded"
    assert data["unhealthy_providers"] == ["bad"]


def test_health_probe_exception_names_every_configured_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the probe itself blows up, no provider was proven healthy.

    The field must not read as "degraded with nothing wrong"; the real reason
    stays in ``details.error``.
    """
    cfg = _config(models={"solo/1": "solo"}, api_keys={"solo": "sk"})

    async def exploding(config: ChimeraConfig, gateway: Any) -> dict[str, Any]:
        raise RuntimeError("probe exploded")

    monkeypatch.setattr("chimera.api.server._check_providers", exploding)
    r = _health_client(cfg).get("/v1/health")

    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "degraded"
    assert data["unhealthy_providers"] == sorted(cfg.providers)
    assert "probe exploded" in data["details"]["error"]


def test_ready_reports_unhealthy_providers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The ready body carries the same list when at least one provider works."""
    cfg = _config(models={"a/1": "a", "b/1": "b"},
                  api_keys={"a": "sk", "b": "sk"})
    probe_status: dict[str, dict[str, Any]] = {
        "a": {"healthy": True, "model_tested": "a/1"},
        "b": {"healthy": False, "error": "api: boom", "error_class": "api",
              "model_tested": "b/1"},
    }
    monkeypatch.setattr(
        "chimera.api.server._check_providers", _stub_probe(probe_status),
    )
    r = _health_client(cfg).get("/v1/health/ready")

    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ready"
    assert data["unhealthy_providers"] == ["b"]
    assert data["providers"] == probe_status

