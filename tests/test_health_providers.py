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
import time
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
    health_probe_grace_s: float | None = None,
) -> ChimeraConfig:
    """Build a minimal config mapping model name → provider name.

    ``health_probe_grace_s=None`` omits the key entirely (ServerConfig's own
    default applies), so every pre-existing call site builds byte-identical
    configs (DF-CHIMERA-V2-17).
    """
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
    if health_probe_grace_s is not None:
        cfg_dict["server"]["health_probe_grace_s"] = health_probe_grace_s
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
        if action == "refused":
            # The transport-level failure that must keep degrading: the
            # provider is NOT merely slow, it never answered at all
            # (DF-CHIMERA-V2-27 — the signal this fix must not swallow).
            raise RuntimeError("APIConnectionError: connection refused")
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


def test_slow_provider_class() -> None:
    """A provider that outlives the budget is ``slow``, with its latency.

    DF-CHIMERA-V2-27: this used to report ``error_class: "timeout"``, which
    said nothing about how far off the provider was — and made a permanent
    over-budget provider read exactly like a real outage.
    """
    cfg = _config(
        models={"p1/slow": "p1"},
        health_timeout_s=0.2,
        api_keys={"p1": "sk-test"},
    )
    gw = _ProbeGateway({"p1/slow": "slow"})
    status = asyncio.run(_check_providers(cfg, gw))

    info = status["p1"]
    assert info["healthy"] is False
    assert info["error_class"] == "slow"
    assert info["error"].startswith("slow:")
    # The tiny budget proves the classification comes from config, not a
    # 3.0 hardcode.
    assert "0.2s" in info["error"]
    # The measured wait is what makes the verdict actionable: a bare
    # "timeout" never said how far past the budget the provider was.
    assert isinstance(info["latency_s"], float)
    assert info["latency_s"] >= 0.2
    assert "probe waited" in info["error"]


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


def test_over_budget_probe_does_not_retry_next_model() -> None:
    """A probe that outlives the budget is terminal — no retry of other models."""
    cfg = _config(
        models={"prov/a": "prov", "prov/b": "prov"},
        health_timeout_s=0.2,
        api_keys={"prov": "sk-test"},
    )
    gw = _ProbeGateway({"prov/a": "slow", "prov/b": "ok"})
    status = asyncio.run(_check_providers(cfg, gw))

    info = status["prov"]
    assert info["healthy"] is False
    assert info["error_class"] == "slow"
    assert info["error"].startswith("slow:")
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
#: failure the classifier cannot place lands in ``api``.  ``slow`` and
#: ``probe_skipped`` (DF-CHIMERA-V2-27) are the two UNMEASURED classes: the
#: probe did not produce a verdict about the provider, so neither one degrades
#: ``status``.
_ERROR_CLASSES = frozenset(
    {
        "missing_credentials", "timeout", "auth", "quota", "api", "unknown",
        "slow", "probe_skipped",
    },
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


def test_error_class_slow() -> None:
    """An over-budget probe is classed ``slow`` (proven by the 0.2s budget)."""
    cfg = _config(
        models={"p1/slow": "p1"}, health_timeout_s=0.2, api_keys={"p1": "sk-test"},
    )
    gw = _ProbeGateway({"p1/slow": "slow"})
    info = asyncio.run(_check_providers(cfg, gw))["p1"]

    assert info["error_class"] == "slow"
    assert info["healthy"] is False
    assert info["error"].startswith("slow:")
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


def _probe_status_client(
    monkeypatch: pytest.MonkeyPatch,
    cfg: ChimeraConfig,
    probe_status: dict[str, dict[str, Any]],
) -> TestClient:
    """TestClient whose ``_check_providers`` returns *probe_status* verbatim.

    The endpoint-level companion to a probe result produced by the REAL
    ``_check_providers`` (over a scripted gateway, no network): the handler is
    exercised against exactly what the probe returned, so the wiring between
    the two is what the assertion pins.  Follows the module's existing
    ``monkeypatch.setattr`` convention so the stub cannot leak between tests.
    """
    monkeypatch.setattr(
        "chimera.api.server._check_providers", _stub_probe(probe_status),
    )
    return _health_client(cfg)


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
    assert set(data) == {
        "status", "unhealthy_providers", "slow_providers",
        "probe_skipped_providers", "details",
    }
    details = data["details"]
    assert set(details) == {
        "config_loaded", "models_configured", "providers_configured",
        "providers_discovered", "commit", "providers",
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


# --------------------------------------------------------------------------- #
# DF-CHIMERA-V2-17: a late cold-start probe reports its REAL verdict, not a
# fabricated timeout
# --------------------------------------------------------------------------- #


class _DelayedProbeGateway:
    """A gateway whose completion takes ``delay_s``, then raises *error*.

    ``error=None`` answers a healthy ``pong`` after the delay instead.

    This is the measured cold-start shape (tick 247): litellm's one-off
    client/TLS/provider-discovery warm-up pushes the FIRST probe of a fresh
    process past the shared budget (10.34s vs 10.0s), and the warm probes
    answer with the provider's real condition (~2.8-3.2s).  The real verdict
    exists — it just lands a little late.
    """

    def __init__(self, delay_s: float, error: Exception | None) -> None:
        self.delay_s = delay_s
        self.error = error
        self.calls: list[str] = []

    async def complete(
        self,
        model: str,
        messages: list[dict[str, str]],
        **kwargs: object,
    ) -> GatewayResponse:
        self.calls.append(model)
        await asyncio.sleep(self.delay_s)
        if self.error is not None:
            raise self.error
        return GatewayResponse(
            text="pong", model=model, tokens_input=1, tokens_output=1,
        )


_LATE_QUOTA_ERROR = _StatusError(_ZAI_QUOTA_MESSAGE, status_code=429)


def test_late_cold_start_probe_reports_real_quota_not_timeout() -> None:
    """Criterion 1: a probe landing inside the grace reports its REAL class.

    The gateway answers later than ``health_timeout_s`` but inside
    ``health_timeout_s + health_probe_grace_s`` — the measured tick-247
    cold-start shape.  The verdict must be the provider's own ``quota`` (with
    ``model_tested`` and z.ai's reset prose), NOT the fabricated
    ``timeout: no response within ...``.
    """
    cfg = _config(
        models={"z-ai/glm-5": "zai"},
        health_timeout_s=0.2,
        health_probe_grace_s=1.5,
        api_keys={"zai": "sk-test"},
    )
    gw = _DelayedProbeGateway(0.5, _LATE_QUOTA_ERROR)
    info = asyncio.run(_check_providers(cfg, gw))["zai"]

    assert info["healthy"] is False
    assert info["error_class"] == "quota"
    assert info["model_tested"] == "z-ai/glm-5"
    assert info["error"].startswith("quota:")
    assert "Weekly/Monthly Limit Exhausted" in info["error"]
    assert "timeout: no response within" not in info["error"]
    # The cancelled-outcome set is never consulted for a grace-completed task.
    assert gw.calls == ["z-ai/glm-5"]


def test_probe_still_outstanding_after_grace_is_slow() -> None:
    """Criterion 2: the grace must not turn a genuinely hung provider vague.

    The gateway never returns inside the budget plus the grace, so the probe
    is cancelled and reported ``slow`` (DF-CHIMERA-V2-27) — with the BUDGET
    and the measured wait named in the error, and the latency in its own
    field. It is deliberately NOT ``timeout``: nothing about the provider's
    behaviour was measured beyond "slower than the budget".
    """
    cfg = _config(
        models={"p1/slow": "p1"},
        health_timeout_s=0.2,
        health_probe_grace_s=0.3,
        api_keys={"p1": "sk-test"},
    )
    gw = _DelayedProbeGateway(30.0, _LATE_QUOTA_ERROR)
    info = asyncio.run(_check_providers(cfg, gw))["p1"]

    assert info["healthy"] is False
    assert info["error_class"] == "slow"
    assert info["error"].startswith("slow: no response within 0.2s")
    assert "probe waited" in info["error"]
    # The wait includes the grace window, since that is what the endpoint
    # actually spent waiting on this probe.
    assert info["latency_s"] >= 0.2 + 0.3
    assert set(info) == {"healthy", "error", "error_class", "latency_s"}


def test_zero_grace_still_reports_slow_not_a_fabricated_timeout() -> None:
    """Criterion 3a: ``health_probe_grace_s=0`` cancels at the deadline.

    The same late probe that criterion 1 turns into ``quota`` is ``slow``
    when the knob is 0 — the probe task is cancelled at the deadline rather
    than allowed to finish, and no verdict about the provider is invented.
    """
    cfg = _config(
        models={"z-ai/glm-5": "zai"},
        health_timeout_s=0.3,
        health_probe_grace_s=0.0,
        api_keys={"zai": "sk-test"},
    )
    gw = _DelayedProbeGateway(0.6, _LATE_QUOTA_ERROR)
    info = asyncio.run(_check_providers(cfg, gw))["zai"]

    assert info["healthy"] is False
    assert info["error_class"] == "slow"
    assert info["error"].startswith("slow: no response within 0.3s")
    # No grace was granted, so the measured wait is the budget alone.
    assert info["latency_s"] < 0.5
    # The probe task was cancelled at the deadline, not allowed to finish.
    assert gw.calls == ["z-ai/glm-5"]


def test_server_config_health_probe_grace_default() -> None:
    """Criterion 3b: ServerConfig defaults health_probe_grace_s to 1.0."""
    assert ServerConfig().health_probe_grace_s == 1.0
    assert ServerConfig(health_probe_grace_s=2.5).health_probe_grace_s == 2.5
    assert ServerConfig(health_probe_grace_s=0.0).health_probe_grace_s == 0.0


def test_late_probe_lands_exactly_one_grace_window_late() -> None:
    """The grace bounds the endpoint's extra wait, it does not hang.

    A probe landing just past the deadline costs roughly the grace window on
    top of the budget — far below the gateway's own 30s ``slow`` sleep, which
    proves the second ``asyncio.wait`` is genuinely bounded by the knob.
    """
    cfg = _config(
        models={"p1/slow": "p1"},
        health_timeout_s=0.2,
        health_probe_grace_s=0.3,
        api_keys={"p1": "sk-test"},
    )
    gw = _DelayedProbeGateway(30.0, RuntimeError("never lands"))
    started = time.perf_counter()
    info = asyncio.run(_check_providers(cfg, gw))["p1"]

    elapsed = time.perf_counter() - started
    assert info["error_class"] == "slow"
    # budget + grace + scheduling slack, far below the 30s hung probe.
    assert elapsed < 0.2 + 0.3 + 1.0, f"endpoint waited {elapsed:.2f}s"


def test_grace_completed_healthy_probe_keeps_exact_previous_shape() -> None:
    """A probe that lands inside the grace keeps the warm payload verbatim.

    The additive promise extends to the grace path: a late healthy answer is
    exactly ``{"healthy": True, "model_tested": ...}`` — no new fields, no
    ``error_class``.
    """
    cfg = _config(
        models={"prov/a": "prov"},
        health_timeout_s=0.2,
        health_probe_grace_s=0.5,
        api_keys={"prov": "sk-test"},
    )
    gw = _DelayedProbeGateway(0.4, None)
    info = asyncio.run(_check_providers(cfg, gw))["prov"]

    assert info == {"healthy": True, "model_tested": "prov/a"}



# --------------------------------------------------------------------------- #
# DF-CHIMERA-V2-27: a provider that cannot answer inside the probe budget is
# ``slow`` (measured), not a permanently-degraded ``timeout`` — while a real
# failure of that same provider still surfaces as a distinct signal
# --------------------------------------------------------------------------- #

#: The measured hermes condition (tick 19-13-04): the gateway injects a
#: ~43.6k-token system prompt, so a 1-token probe takes ~108s against the 10.0s
#: budget while the same model called directly upstream answers in ~1.9s.
#: ``GET /v1/models`` returns 200 in 0.33s — the gateway IS alive; only the
#: completion is slow.  Reproduced here at compressed timescales (0.5s budget,
#: 30s "never lands") so the fake gateway needs no network and the test is
#: fast — the SHAPE is what regresses, not the constant.
_SLOW_GATEWAY_BUDGET_S = 0.5


class _SlowGateway:
    """A fake gateway whose completion never answers inside the budget.

    Stands in for the hermes gateway: alive and reachable (a discovery call
    would answer instantly), but any completion outlives the probe budget.
    No network, no litellm, no real provider.
    """

    def __init__(self) -> None:
        self.completion_calls = 0

    async def complete(
        self, model: str, messages: list[dict[str, str]], **kwargs: object,
    ) -> GatewayResponse:
        self.completion_calls += 1
        await asyncio.sleep(30)  # outlives the budget by orders of magnitude
        raise AssertionError("unreachable — the probe is cancelled first")


def _slow_only_config() -> ChimeraConfig:
    """The measured shape: one provider whose probe cannot land in budget."""
    return _config(
        models={"hermes/glm-5.3-flash": "hermes"},
        health_timeout_s=_SLOW_GATEWAY_BUDGET_S,
        api_keys={"hermes": "sk-test"},
    )


def test_slow_provider_reports_error_class_slow_with_measured_latency() -> None:
    """Acceptance 2: the response NAMES the condition, with the latency.

    ``error_class == "slow"`` plus a numeric ``latency_s`` — not a bare
    ``timeout`` whose only information is that the budget was missed.  The
    measured wait is at least the budget, because that is how long the probe
    actually ran before being cancelled.
    """
    cfg = _slow_only_config()
    gw = _SlowGateway()
    info = asyncio.run(_check_providers(cfg, gw))["hermes"]

    assert info["healthy"] is False
    assert info["error_class"] == "slow"
    assert info["error"].startswith("slow:")
    assert "no response within 0.5s" in info["error"]
    assert "probe waited" in info["error"]
    assert isinstance(info["latency_s"], float)
    assert info["latency_s"] >= _SLOW_GATEWAY_BUDGET_S
    # Nothing about the provider's VERDICT was measured — no model was proven
    # broken, so no model_tested is claimed.
    assert "model_tested" not in info


def test_slow_provider_does_not_degrade_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Acceptance 1 (first half): a slow-only payload is NOT permanently degraded.

    The standing condition must not read as a degradation, or a real outage
    becomes indistinguishable from it.  The provider is still visibly
    not-healthy in ``details.providers`` and named in its own top-level
    array, so the condition is REPORTED, just not as a degradation.
    """
    cfg = _slow_only_config()
    probe_status = asyncio.run(_check_providers(cfg, _SlowGateway()))

    client = _probe_status_client(monkeypatch, cfg, probe_status)
    r = client.get("/v1/health")

    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "healthy", data
    assert data["unhealthy_providers"] == []
    assert data["slow_providers"] == ["hermes"]
    assert data["details"]["providers"]["hermes"]["error_class"] == "slow"


def test_real_failure_of_a_slow_provider_still_degrades(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Acceptance 1 (second half): a REAL failure still surfaces distinctly.

    Same provider, same names — but now it answers with a connection failure.
    ``status`` degrades, the provider is in ``unhealthy_providers`` (its own
    signal, distinct from ``slow``), and ``slow_providers`` is empty.  This is
    the half that must NOT be swallowed by the slow path.
    """
    cfg = _slow_only_config()
    gw = _ProbeGateway({"hermes/glm-5.3-flash": "api"})
    probe_status = asyncio.run(_check_providers(cfg, gw))
    assert probe_status["hermes"]["error_class"] == "api"

    client = _probe_status_client(monkeypatch, cfg, probe_status)
    data = client.get("/v1/health").json()

    assert data["status"] == "degraded", data
    assert data["unhealthy_providers"] == ["hermes"]
    assert data["slow_providers"] == []
    assert data["details"]["providers"]["hermes"]["error_class"] == "api"


def test_connection_refused_still_degrades_exactly_as_before() -> None:
    """A refused connection keeps its previous class and verdict."""
    cfg = _slow_only_config()
    gw = _ProbeGateway({"hermes/glm-5.3-flash": "refused"})
    info = asyncio.run(_check_providers(cfg, gw))["hermes"]

    assert info["healthy"] is False
    assert info["error_class"] == "api"
    assert "connection refused" in info["error"]
    # No latency field on an ANSWERED failure — that field belongs to the
    # unmeasured (cancelled) path only.
    assert "latency_s" not in info
    assert set(info) == {"healthy", "error", "error_class", "model_tested"}


def test_slow_and_real_failure_are_distinct_signals_side_by_side(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The two conditions never collapse into one reading.

    One slow provider and one genuinely broken provider in the same payload:
    ``unhealthy_providers`` names only the broken one, and ``slow_providers``
    names only the slow one.  A consumer can therefore tell "permanently
    over-budget" from "this provider is down" without string-matching.
    """
    cfg = _config(
        models={"slow/one": "slowp", "bad/one": "badp"},
        health_timeout_s=_SLOW_GATEWAY_BUDGET_S,
        api_keys={"slowp": "sk", "badp": "sk"},
    )

    class MixedGateway:
        async def complete(
            self, model: str, messages: list[dict[str, str]], **kw: object,
        ) -> GatewayResponse:
            if model.startswith("slow/"):
                await asyncio.sleep(30)
                raise AssertionError("unreachable")
            raise RuntimeError("connection refused")

    probe_status = asyncio.run(_check_providers(cfg, MixedGateway()))

    assert probe_status["slowp"]["error_class"] == "slow"
    assert probe_status["badp"]["error_class"] == "api"

    data = _probe_status_client(monkeypatch, cfg, probe_status).get("/v1/health").json()

    assert data["status"] == "degraded"
    assert data["unhealthy_providers"] == ["badp"]
    assert data["slow_providers"] == ["slowp"]


def test_health_probe_false_skips_the_probe_and_is_named(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The opt-out control: no live probe, and the omission stays visible.

    ``providers.<name>.health_probe: false`` performs no upstream call at all
    — the last resort for a gateway whose standing latency exceeds any sane
    budget — and reports ``probe_skipped`` rather than a permanent ``slow``.
    It does NOT satisfy readiness (nothing was proven reachable).
    """
    cfg = _config(
        models={"hermes/glm-5.3-flash": "hermes"},
        api_keys={"hermes": "sk-test"},
    )
    cfg.providers["hermes"].health_probe = False
    gw = _SlowGateway()
    probe_status = asyncio.run(_check_providers(cfg, gw))

    info = probe_status["hermes"]
    assert gw.completion_calls == 0, "an opted-out provider must not be probed"
    assert info["healthy"] is False
    assert info["error_class"] == "probe_skipped"
    assert "probe_skipped:" in info["note"]

    # /v1/health: named in its own array; still not a degradation, but the
    # provider is not healthy either.
    client = _probe_status_client(monkeypatch, cfg, probe_status)
    data = client.get("/v1/health").json()
    assert data["status"] == "healthy"
    assert data["unhealthy_providers"] == []
    assert data["slow_providers"] == []
    assert data["probe_skipped_providers"] == ["hermes"]

    # /v1/health/ready: a skipped provider proves nothing, so readiness must
    # NOT come from it — 503, with the cause named.
    ready = _probe_status_client(monkeypatch, cfg, probe_status).get("/v1/health/ready")
    assert ready.status_code == 503


def test_health_probe_default_true_probes_normally() -> None:
    """The opt-out is opt-IN: the default keeps probing exactly as before."""
    cfg = _config(
        models={"p/one": "prov"}, api_keys={"prov": "sk-test"},
    )
    assert cfg.providers["prov"].health_probe is True

    gw = _ProbeGateway({})
    info = asyncio.run(_check_providers(cfg, gw))["prov"]

    assert info["healthy"] is True
    assert info["model_tested"] == "p/one"
    assert gw.calls != [], "the default must still make a live probe"


def test_ready_503_names_the_slow_condition_not_reachability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A slow-only deployment is 503 — and the reason says WHY.

    "no providers reachable" was factually wrong for this case (the gateway
    answered a discovery call fine; only the probe budget was too small), and
    pointing an operator at the wrong condition is the confusion this ticket
    removes. The status stays 503 because a probe that never landed proved
    nothing about reachability — load balancers must not route on it.
    """
    cfg = _slow_only_config()
    probe_status = asyncio.run(_check_providers(cfg, _SlowGateway()))

    r = _probe_status_client(monkeypatch, cfg, probe_status).get("/v1/health/ready")

    assert r.status_code == 503
    detail = r.json()["detail"]
    assert "Not ready" in detail
    assert "slow: hermes" in detail
    assert "health_timeout_s" in detail
    assert "no providers reachable" not in detail


def test_ready_503_keeps_the_reachability_wording_for_a_real_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The original 503 wording is preserved for the case it was written for."""
    cfg = _slow_only_config()
    probe_status = asyncio.run(
        _check_providers(cfg, _ProbeGateway({"hermes/glm-5.3-flash": "api"})),
    )

    r = _probe_status_client(monkeypatch, cfg, probe_status).get("/v1/health/ready")

    assert r.status_code == 503
    assert "no providers reachable" in r.json()["detail"]
