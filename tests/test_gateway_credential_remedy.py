"""DF-CHIMERA-V2-8 — a credential failure must name THAT provider's env var.

The verbatim upstream text used below is what a real ``chimera "..."`` run
printed in an isolated HOME with no resolvable DEEPSEEK_API_KEY: LiteLLM
serves DeepSeek over the OpenAI SDK, so its "Missing credentials" prose names
``OPENAI_API_KEY`` — a variable that cannot fix a DeepSeek call.  Every
surface (CLI warning line, REST body, MCP tool result, structlog stream)
renders the ``GatewayError`` message, so the fix lives at the seam that builds
it: :func:`chimera.gateway.credential_remedy` + the two raise sites in
``LiteLLMGateway._complete_with_retry``.

Hard constraints covered here (see the DF-CHIMERA-V2-8 brief):

* an unresolvable key for provider X never names provider Y's variable;
* a keyless local endpoint (loopback ``base_url``, no ``api_key_env``) keeps
  the raw upstream text — no invented ``LMSTUDIO_API_KEY``;
* non-credential failures (timeout / 429 / plain 5xx) stay untouched;
* the rewritten message is still credential-class, so the CLI's existing
  credential hint (DF-CHIMERA-V2-6) keeps firing.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import litellm
import pytest

from chimera.blocked_models import is_credential_error
from chimera.config import ChimeraConfig, provider_api_key_env
from chimera.gateway import GatewayError, LiteLLMGateway, credential_remedy
from tests.conftest import CONFIG_DICT

#: Byte-for-byte what LiteLLM emitted for `deepseek/deepseek-v4-flash` with no
#: key present (captured from a real run, not paraphrased).
UPSTREAM_MISSING_CREDENTIALS = (
    "litellm.InternalServerError: InternalServerError: OpenAIException - "
    "Missing credentials. Please pass an `api_key`, `workload_identity`, "
    "`admin_api_key`, or set the `OPENAI_API_KEY` or `OPENAI_ADMIN_KEY` "
    "environment variable."
)

#: Env vars that belong to OTHER providers — naming one of these for a
#: DeepSeek failure is exactly the reported defect.
OTHER_PROVIDER_ENVS = (
    "OPENAI_API_KEY",
    "OPENAI_ADMIN_KEY",
    "ANTHROPIC_API_KEY",
    "ZAI_API_KEY",
    "XAI_API_KEY",
    "OPENROUTER_API_KEY",
    "GEMINI_API_KEY",
)

_FAST_RETRY = {"max_attempts": 2, "base_delay_ms": 1, "max_delay_ms": 5}


def _config(
    *,
    providers: dict[str, dict[str, str]] | None = None,
    models: dict[str, dict[str, Any]] | None = None,
    retry: dict[str, Any] | None = None,
) -> ChimeraConfig:
    """CONFIG_DICT plus test-local providers/models (no provider discovery)."""
    cfg_dict: dict[str, Any] = dict(CONFIG_DICT)
    cfg_dict["providers"] = {**CONFIG_DICT["providers"], **(providers or {})}
    cfg_dict["models"] = {**CONFIG_DICT["models"], **(models or {})}
    cfg_dict["retry"] = retry or _FAST_RETRY
    return ChimeraConfig.model_validate(cfg_dict)


def _internal_server_error(text: str) -> Exception:
    """A real LiteLLM 500 (retryable → exercises the retry-exhausted raise)."""
    return litellm.exceptions.InternalServerError(
        message=text, model="deepseek-v4-flash", llm_provider="openai",
    )


# --------------------------------------------------------------------------- #
# credential_remedy — the unit seam
# --------------------------------------------------------------------------- #

def test_remedy_names_the_providers_own_env_var() -> None:
    """The remedy names DEEPSEEK_API_KEY and no other provider's variable."""
    remedy = credential_remedy(
        UPSTREAM_MISSING_CREDENTIALS,
        model="deepseek/deepseek-v4-flash",
        provider="deepseek",
        config=_config(),
    )
    assert "provider 'deepseek'" in remedy
    assert "DEEPSEEK_API_KEY" in remedy
    for other in OTHER_PROVIDER_ENVS:
        assert other not in remedy, f"remedy must not name {other}"
    assert remedy.endswith("upstream error: ")


def test_remedy_uses_canonical_env_var_over_convention() -> None:
    """`google` resolves GEMINI_API_KEY, not the GOOGLE_API_KEY convention.

    The alias map mirrors ``_apply_env_overrides`` — the table that actually
    supplies the key — so the hint cannot name a var nothing reads.
    """
    remedy = credential_remedy(
        "litellm.AuthenticationError: invalid api key",
        model="google/gemini-2.5-flash",
        provider="google",
        config=_config(providers={"google": {"base_url": "https://generativelanguage.googleapis.com/v1beta"}}),
    )
    assert "GEMINI_API_KEY" in remedy
    assert "GOOGLE_API_KEY" not in remedy


def test_remedy_prefers_configured_api_key_env() -> None:
    """An explicit providers.<name>.api_key_env wins over the convention."""
    config = _config(
        providers={
            "acme": {"base_url": "https://api.acme.example/v1", "api_key_env": "ACME_TOKEN"},
        },
    )
    remedy = credential_remedy(
        "litellm.AuthenticationError: 401 unauthorized",
        model="acme/big-model",
        provider="acme",
        config=config,
    )
    assert "ACME_TOKEN" in remedy
    assert "ACME_API_KEY" not in remedy


def test_remedy_resolves_provider_from_the_catalog() -> None:
    """With no provider passed, the catalog entry supplies it."""
    remedy = credential_remedy(
        UPSTREAM_MISSING_CREDENTIALS,
        model="deepseek/deepseek-v4-flash",
        provider=None,
        config=_config(),
    )
    assert "provider 'deepseek'" in remedy
    assert "DEEPSEEK_API_KEY" in remedy


def test_remedy_empty_when_no_provider_can_be_resolved() -> None:
    """No provider → no claim (never guess another provider's env var)."""
    assert credential_remedy(
        UPSTREAM_MISSING_CREDENTIALS,
        model="mystery/model",
        provider=None,
        config=_config(),
    ) == ""


def test_remedy_empty_for_non_credential_failures() -> None:
    """Timeouts, 429s and plain 5xx are not key problems."""
    for error in (
        "litellm.Timeout: Request timed out",
        "litellm.RateLimitError: rate limit exceeded",
        "litellm.InternalServerError: InternalServerError: upstream exploded",
        "litellm.APIConnectionError: Connection error.",
    ):
        assert credential_remedy(
            error,
            model="deepseek/deepseek-v4-flash",
            provider="deepseek",
            config=_config(),
        ) == "", error


def test_keyless_local_provider_cannot_name_an_env_var() -> None:
    """A loopback provider with no configured key is keyless, not keyless-broken."""
    config = _config(
        providers={
            "lmstudio": {"base_url": "http://localhost:1234/v1"},
            "ollama": {"base_url": "http://127.0.0.1:11434/v1"},
        },
    )
    assert provider_api_key_env(config, "lmstudio") is None
    assert provider_api_key_env(config, "ollama") is None
    assert credential_remedy(
        UPSTREAM_MISSING_CREDENTIALS,
        model="lmstudio/local-model",
        provider="lmstudio",
        config=config,
    ) == ""


def test_local_provider_with_explicit_api_key_env_still_names_it() -> None:
    """A local endpoint that DOES need a token gets the token's name."""
    config = _config(
        providers={
            "vllm": {
                "base_url": "http://127.0.0.1:8000/v1",
                "api_key_env": "VLLM_TOKEN",
            },
        },
    )
    assert provider_api_key_env(config, "vllm") == "VLLM_TOKEN"


# --------------------------------------------------------------------------- #
# Through LiteLLMGateway.complete — the messages every surface renders
# --------------------------------------------------------------------------- #

class TestGatewayCredentialMessages:
    """The composed GatewayError text, from the real retry path."""

    @pytest.mark.asyncio
    async def test_retry_exhausted_names_provider_env_before_upstream_text(self) -> None:
        config = _config()
        gateway = LiteLLMGateway(config)
        exc = _internal_server_error(UPSTREAM_MISSING_CREDENTIALS)

        with (
            patch("litellm.acompletion", side_effect=exc) as mock,
            pytest.raises(GatewayError) as excinfo,
        ):
            await gateway.complete(
                "deepseek/deepseek-v4-flash",
                [{"role": "user", "content": "hi"}],
            )

        message = str(excinfo.value)
        # Retry semantics untouched: 500 keeps retrying, then fails loudly.
        assert mock.call_count == 2
        assert "call failed after 2 attempts" in message
        assert "provider 'deepseek'" in message
        assert "DEEPSEEK_API_KEY" in message
        # The accurate remedy comes BEFORE the generic provider-blind text.
        assert message.index("DEEPSEEK_API_KEY") < message.index("OPENAI_API_KEY")
        # Still credential-class → the CLI's DF-CHIMERA-V2-6 hint keeps firing.
        assert is_credential_error(message)

    @pytest.mark.asyncio
    async def test_non_retryable_credential_error_names_provider_env(self) -> None:
        """401 → single attempt, same provider-accurate remedy."""
        config = _config()
        gateway = LiteLLMGateway(config)
        exc = litellm.exceptions.AuthenticationError(
            message="invalid api key", model="deepseek-v4-flash",
            llm_provider="deepseek",
        )

        with (
            patch("litellm.acompletion", side_effect=exc) as mock,
            pytest.raises(GatewayError) as excinfo,
        ):
            await gateway.complete(
                "deepseek/deepseek-v4-flash",
                [{"role": "user", "content": "hi"}],
            )

        message = str(excinfo.value)
        assert mock.call_count == 1
        assert "call failed" in message
        assert "provider 'deepseek'" in message
        assert "DEEPSEEK_API_KEY" in message

    @pytest.mark.asyncio
    async def test_non_credential_failure_text_is_unchanged(self) -> None:
        """A plain 500 keeps the pre-existing message shape exactly."""
        config = _config()
        gateway = LiteLLMGateway(config)
        exc = _internal_server_error("upstream exploded")

        with (
            patch("litellm.acompletion", side_effect=exc),
            pytest.raises(GatewayError) as excinfo,
        ):
            await gateway.complete(
                "deepseek/deepseek-v4-flash",
                [{"role": "user", "content": "hi"}],
            )

        assert str(excinfo.value) == (
            f"deepseek/deepseek-v4-flash call failed after 2 attempts: {exc}"
        )

    @pytest.mark.asyncio
    async def test_keyless_local_provider_message_is_unchanged(self) -> None:
        """lmstudio (loopback, no key configured) sees no invented env var."""
        config = _config(
            providers={"lmstudio": {"base_url": "http://localhost:1234/v1"}},
            models={
                "lmstudio/llama-3-local": {
                    "categories": {"code": 0.5},
                    "cost_tier": "budget",
                    "provider": "lmstudio",
                },
            },
        )
        gateway = LiteLLMGateway(config)
        exc = _internal_server_error(UPSTREAM_MISSING_CREDENTIALS)

        with (
            patch("litellm.acompletion", side_effect=exc),
            pytest.raises(GatewayError) as excinfo,
        ):
            await gateway.complete(
                "lmstudio/llama-3-local",
                [{"role": "user", "content": "hi"}],
            )

        message = str(excinfo.value)
        assert message == f"lmstudio/llama-3-local call failed after 2 attempts: {exc}"
        assert "LMSTUDIO_API_KEY" not in message
