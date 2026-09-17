"""Generic OpenAI-compatible provider routing — ``providers.<name>.base_url``.

Before this seam existed (INT-PROV-HERMES-001) a provider LiteLLM had no
native prefix for — the local Hermes gateway (``hermes``), a vLLM/llama.cpp
server, an internal proxy — fell through ``resolve_litellm_model`` unchanged:
the catalog id was handed to LiteLLM with NO ``api_base``, so the call went to
LiteLLM's own default host for that model string instead of the configured
endpoint.  ``providers.<name>.base_url`` was only ever read by
``_is_local_base_url``.

The coverage here is deliberately two-layered:

* ``test_gateway_completion_reaches_the_configured_base_url_endpoint`` stands up
  a stdlib ``http.server`` stub on loopback and drives a REAL completion through
  LiteLLM, so the assertion is made against bytes that actually crossed a
  socket — the bare model id and the ``Authorization: Bearer`` header are read
  off the request the stub received (no network beyond 127.0.0.1).
* The kwargs-level tests pin the same routing deterministically (model string,
  ``api_base``, ``custom_llm_provider``, resolved key) so a failure names the
  broken half without needing the socket.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import yaml

from chimera import config as chimera_config
from chimera.config import ChimeraConfig, ModelEntry
from chimera.gateway import (
    GatewayError,
    LiteLLMGateway,
    is_credential_error,
    resolve_litellm_model,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_CONFIG = REPO_ROOT / "chimera.yaml.example"

#: The provider name the shipped example config uses for the local gateway.
PROVIDER = "hermes"
MODEL_ID = "hermes/glm-5.3-flash"
BARE_MODEL = "glm-5.3-flash"
GATEWAY_BASE_URL = "http://127.0.0.1:8642/v1"
#: Obviously-fake credential — never a real key material.
FAKE_KEY = "fake-hermes-gateway-key-for-tests"

#: The 9router fleet gateway: one OpenAI-compatible endpoint in front of a
#: multi-prefix model catalog, whose own upstream ids are namespaced.
ROUTER9_PROVIDER = "router9"
ROUTER9_MODEL_ID = "router9/ds/deepseek-v4-flash"
ROUTER9_BASE_URL = "http://master001:20128/v1"
FAKE_ROUTER9_KEY = "fake-router9-gateway-key-for-tests"


def _entry(provider: str, litellm_model: str | None = None) -> ModelEntry:
    return ModelEntry(
        categories={}, cost_tier="standard", provider=provider,
        litellm_model=litellm_model,
    )


def _config_dict(
    *,
    base_url: str | None = GATEWAY_BASE_URL,
    api_key: str | None = FAKE_KEY,
    api_key_env: str | None = None,
    provider: str = PROVIDER,
    model_id: str = MODEL_ID,
) -> dict[str, Any]:
    """A valid config with one custom (non-native) provider."""
    provider_cfg: dict[str, Any] = {}
    if base_url is not None:
        provider_cfg["base_url"] = base_url
    if api_key is not None:
        provider_cfg["api_key"] = api_key
    if api_key_env is not None:
        provider_cfg["api_key_env"] = api_key_env
    return {
        "providers": {provider: provider_cfg},
        "models": {
            model_id: {
                "categories": {"code": 0.8},
                "cost_tier": "budget",
                "provider": provider,
            },
        },
        "defaults": {
            "dispatcher": model_id,
            "default_worker": model_id,
            "default_aggregator": model_id,
        },
        "retry": {"max_attempts": 1, "base_delay_ms": 1, "max_delay_ms": 5},
        "observability": {"log_level": "warning", "trace_enabled": False},
    }


@contextmanager
def _compat_stub() -> Iterator[tuple[str, list[dict[str, Any]]]]:
    """A loopback OpenAI-compatible stub; yields ``(base_url, seen_requests)``."""
    seen: list[dict[str, Any]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            body = json.loads(raw or b"{}")
            seen.append({
                "path": self.path,
                "authorization": self.headers.get("Authorization"),
                "body": body,
            })
            payload = {
                "id": "chatcmpl-stub",
                "object": "chat.completion",
                "created": 0,
                "model": body.get("model", "unknown"),
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "STUB-OK"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 3,
                    "completion_tokens": 1,
                    "total_tokens": 4,
                },
            }
            encoded = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, *args: Any) -> None:  # noqa: ANN401
            """Silence the per-request stderr line (keeps pytest output clean)."""

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/v1", seen
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


# --------------------------------------------------------------------------- #
# resolve_litellm_model — the generic branch
# --------------------------------------------------------------------------- #


def test_custom_base_url_routes_through_the_openai_compatible_provider() -> None:
    model, extra = resolve_litellm_model(
        MODEL_ID, _entry(PROVIDER), api_key=FAKE_KEY, base_url=GATEWAY_BASE_URL,
    )
    assert model == f"openai/{BARE_MODEL}"
    assert extra["api_base"] == GATEWAY_BASE_URL
    assert extra["custom_llm_provider"] == "openai"
    assert extra["api_key"] == FAKE_KEY


@pytest.mark.parametrize(
    ("catalog_id", "provider", "expected_upstream"),
    [
        # A single-slash catalog id carrying its provider prefix: exactly one
        # prefix goes, as it always did.
        ("hermes/glm-5.3-flash", "hermes", "glm-5.3-flash"),
        ("local-serving/llama-3.1-8b", "local-serving", "llama-3.1-8b"),
        # A NAMESPACED upstream id: the endpoint's own model id is itself
        # slash-separated, so only the one leading catalog prefix is stripped
        # and the inner slashes survive (INT-PROV-ROUTER9-001).
        ("hermes/deepseek/v4-flash", "hermes", "deepseek/v4-flash"),
        # A catalog id that does NOT carry its provider prefix keeps the
        # innermost-segment behavior — the fallback for every other shape.
        ("vendor/some/model", "hermes", "model"),
    ],
)
def test_catalog_prefix_is_stripped_to_the_upstream_model_id(
    catalog_id: str, provider: str, expected_upstream: str,
) -> None:
    """The gateway (and every OpenAI-compatible endpoint) wants its own id."""
    model, extra = resolve_litellm_model(
        catalog_id, _entry(provider),
        api_key=FAKE_KEY, base_url=GATEWAY_BASE_URL,
    )
    assert model == f"openai/{expected_upstream}"
    assert extra["api_base"] == GATEWAY_BASE_URL


def test_keyless_custom_endpoint_passes_no_api_key() -> None:
    """No resolved key → no ``api_key`` kwarg (the existing keyless contract)."""
    model, extra = resolve_litellm_model(
        MODEL_ID, _entry(PROVIDER), base_url=GATEWAY_BASE_URL,
    )
    assert model == f"openai/{BARE_MODEL}"
    assert "api_key" not in extra


def test_explicit_litellm_model_still_wins_over_base_url() -> None:
    model, extra = resolve_litellm_model(
        MODEL_ID, _entry(PROVIDER, litellm_model="openrouter/some/model"),
        api_key=FAKE_KEY, base_url=GATEWAY_BASE_URL,
    )
    assert model == "openrouter/some/model"
    assert "api_base" not in extra


def test_no_base_url_keeps_the_legacy_passthrough() -> None:
    """A provider with no configured base_url is untouched (mistral-style)."""
    model, extra = resolve_litellm_model(
        "mistral/mistral-large", _entry("mistral"), api_key=FAKE_KEY,
    )
    assert model == "mistral/mistral-large"
    assert extra == {"api_key": FAKE_KEY}


@pytest.mark.parametrize(
    "provider", ["zai", "deepseek", "openrouter", "anthropic", "google", "openai"],
)
def test_native_providers_ignore_a_configured_base_url(
    provider: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """C2: routing for every natively-handled provider is byte-identical.

    Each provider is resolved twice — once with a base_url supplied, once
    without — and both results must match exactly.
    """
    monkeypatch.setenv("ZAI_API_KEY", "zai-env-key")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-env-key")
    name = {
        "zai": "zai-coding-plan/glm-5.2",
        "deepseek": "deepseek/deepseek-v4-flash",
        "openrouter": "openrouter/qwen/qwen3-coder",
        "anthropic": "anthropic/claude-sonnet-4",
        "google": "google/gemini-3-flash-preview",
        "openai": "openai/gpt-5.6",
    }[provider]

    without = resolve_litellm_model(name, _entry(provider))
    with_base_url = resolve_litellm_model(
        name, _entry(provider), base_url="http://127.0.0.1:9999/v1",
    )
    assert with_base_url == without


# --------------------------------------------------------------------------- #
# router9 — the 9router fleet gateway (namespaced upstream model ids)
# --------------------------------------------------------------------------- #


def test_router9_namespaced_id_keeps_its_inner_slash() -> None:
    """INT-PROV-ROUTER9-001: the one leading catalog prefix goes, no more.

    ``router9/ds/deepseek-v4-flash`` must reach 9router as
    ``ds/deepseek-v4-flash`` — ``deepseek-v4-flash`` (the innermost segment)
    is not a model that gateway knows.
    """
    model, extra = resolve_litellm_model(
        ROUTER9_MODEL_ID, _entry(ROUTER9_PROVIDER),
        api_key=FAKE_ROUTER9_KEY, base_url=ROUTER9_BASE_URL,
    )
    assert model == "openai/ds/deepseek-v4-flash"
    assert extra == {
        "api_key": FAKE_ROUTER9_KEY,
        "api_base": ROUTER9_BASE_URL,
        "custom_llm_provider": "openai",
    }


@pytest.mark.parametrize(
    ("catalog_id", "expected_upstream"),
    [
        ("router9/ds/deepseek-v4-flash", "ds/deepseek-v4-flash"),
        ("router9/ds/deepseek-v4-pro", "ds/deepseek-v4-pro"),
        ("router9/mmx/MiniMax-M3", "mmx/MiniMax-M3"),
        ("router9/openrouter/x-ai/grok-4.6", "openrouter/x-ai/grok-4.6"),
        ("router9/xai/grok-4", "xai/grok-4"),
    ],
)
def test_router9_catalog_ids_keep_every_namespace_segment(
    catalog_id: str, expected_upstream: str,
) -> None:
    """Every segment after the one catalog prefix survives unchanged."""
    model, extra = resolve_litellm_model(
        catalog_id, _entry(ROUTER9_PROVIDER),
        api_key=FAKE_ROUTER9_KEY, base_url=ROUTER9_BASE_URL,
    )
    assert model == f"openai/{expected_upstream}"
    assert extra["api_base"] == ROUTER9_BASE_URL
    assert extra["custom_llm_provider"] == "openai"


def test_router9_provider_prefix_match_is_case_insensitive() -> None:
    """A mixed-case catalog provider segment still matches its provider name."""
    model, extra = resolve_litellm_model(
        "Router9/ds/deepseek-v4-flash", _entry(ROUTER9_PROVIDER),
        api_key=FAKE_ROUTER9_KEY, base_url=ROUTER9_BASE_URL,
    )
    assert model == "openai/ds/deepseek-v4-flash"
    assert extra["api_base"] == ROUTER9_BASE_URL


def test_hermes_provider_id_is_unchanged_by_the_namespaced_rule() -> None:
    """Regression guard: the hermes catalog id resolves byte-identically."""
    model, extra = resolve_litellm_model(
        MODEL_ID, _entry(PROVIDER), api_key=FAKE_KEY, base_url=GATEWAY_BASE_URL,
    )
    assert model == f"openai/{BARE_MODEL}"
    assert extra == {
        "api_key": FAKE_KEY,
        "api_base": GATEWAY_BASE_URL,
        "custom_llm_provider": "openai",
    }


def test_other_provider_name_does_not_eat_a_vendor_prefix() -> None:
    """Only the SERVING provider's own name is stripped, never a vendor one."""
    model, _ = resolve_litellm_model(
        "openrouter/x-ai/grok-4.6", _entry(ROUTER9_PROVIDER),
        api_key=FAKE_ROUTER9_KEY, base_url=ROUTER9_BASE_URL,
    )
    assert model == "openai/grok-4.6"


# --------------------------------------------------------------------------- #
# LiteLLMGateway.complete — the kwargs actually handed to LiteLLM
# --------------------------------------------------------------------------- #


class _StubResult:
    """Minimal LiteLLM-shaped result so ``_build_response`` works."""

    class _Message:
        content = "KWARGS-OK"

    class _Choice:
        finish_reason = "stop"

        def __init__(self) -> None:
            self.message = _StubResult._Message()

    class _Usage:
        prompt_tokens = 5
        completion_tokens = 2

    def __init__(self) -> None:
        self.choices = [_StubResult._Choice()]
        self.usage = _StubResult._Usage()


async def test_complete_passes_base_url_and_resolved_key_to_litellm() -> None:
    """The configured base_url and the provider's key reach the LLM call."""
    config = ChimeraConfig.model_validate(_config_dict())
    gateway = LiteLLMGateway(config)
    captured: list[dict[str, Any]] = []

    async def capture(**kwargs: Any) -> Any:  # noqa: ANN401
        captured.append(kwargs)
        return _StubResult()

    with patch("litellm.acompletion", new=capture):
        resp = await gateway.complete(
            MODEL_ID, [{"role": "user", "content": "hi"}],
        )

    assert resp.text == "KWARGS-OK"
    assert len(captured) == 1
    call = captured[0]
    assert call["model"] == f"openai/{BARE_MODEL}"
    assert call["api_base"] == GATEWAY_BASE_URL
    assert call["custom_llm_provider"] == "openai"
    assert call["api_key"] == FAKE_KEY


async def test_complete_omits_api_key_for_a_keyless_custom_endpoint() -> None:
    config = ChimeraConfig.model_validate(_config_dict(api_key=None))
    gateway = LiteLLMGateway(config)
    captured: list[dict[str, Any]] = []

    async def capture(**kwargs: Any) -> Any:  # noqa: ANN401
        captured.append(kwargs)
        return _StubResult()

    with patch("litellm.acompletion", new=capture):
        await gateway.complete(MODEL_ID, [{"role": "user", "content": "hi"}])

    assert captured[0]["api_base"] == GATEWAY_BASE_URL
    assert "api_key" not in captured[0]


async def test_gateway_completion_reaches_the_configured_base_url_endpoint() -> None:
    """C1 end-to-end over a real socket: bare model id + Bearer header.

    A stdlib stub stands in for the Hermes gateway (same OpenAI-compatible
    surface).  The path, the model id in the JSON body and the Authorization
    header are asserted on the request the stub actually received.
    """
    with _compat_stub() as (base_url, seen):
        config = ChimeraConfig.model_validate(_config_dict(base_url=base_url))
        gateway = LiteLLMGateway(config)
        resp = await gateway.complete(
            MODEL_ID, [{"role": "user", "content": "ping"}],
            temperature=0, max_tokens=4,
        )

        assert resp.text == "STUB-OK"
        assert len(seen) == 1, f"expected exactly one request, saw {len(seen)}"
        request = seen[0]
        assert request["path"] == "/v1/chat/completions"
        # The endpoint sees the BARE model name — not "hermes/glm-5.3-flash".
        assert request["body"]["model"] == BARE_MODEL
        assert request["authorization"] == f"Bearer {FAKE_KEY}"


async def test_gateway_completion_sends_the_namespaced_upstream_id() -> None:
    """Real socket: 9router receives ``ds/deepseek-v4-flash``, not the tail."""
    with _compat_stub() as (base_url, seen):
        config = ChimeraConfig.model_validate(
            _config_dict(
                base_url=base_url, api_key=FAKE_ROUTER9_KEY,
                provider=ROUTER9_PROVIDER, model_id=ROUTER9_MODEL_ID,
            )
        )
        gateway = LiteLLMGateway(config)
        resp = await gateway.complete(
            ROUTER9_MODEL_ID, [{"role": "user", "content": "ping"}],
            temperature=0, max_tokens=4,
        )

        assert resp.text == "STUB-OK"
        assert len(seen) == 1, f"expected exactly one request, saw {len(seen)}"
        request = seen[0]
        assert request["path"] == "/v1/chat/completions"
        # The namespaced id survives all the way to the wire.
        assert request["body"]["model"] == "ds/deepseek-v4-flash"
        assert request["authorization"] == f"Bearer {FAKE_ROUTER9_KEY}"


# --------------------------------------------------------------------------- #
# The shipped example config + docs (C3) and the credential seam
# --------------------------------------------------------------------------- #


async def test_credential_failure_names_the_providers_own_env_var(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A hermes failure names API_SERVER_KEY, not LiteLLM's OPENAI_API_KEY."""
    import litellm

    monkeypatch.setenv("API_SERVER_KEY", FAKE_KEY)
    # No literal api_key: the seam under test is ``api_key_env``.
    config = ChimeraConfig.model_validate(
        _config_dict(api_key=None, api_key_env="API_SERVER_KEY")
    )
    gateway = LiteLLMGateway(config)
    exc = litellm.exceptions.AuthenticationError(
        message="invalid api key", model=BARE_MODEL, llm_provider="openai",
    )

    with (
        patch("litellm.acompletion", side_effect=exc),
        pytest.raises(GatewayError) as excinfo,
    ):
        await gateway.complete(MODEL_ID, [{"role": "user", "content": "hi"}])

    message = str(excinfo.value)
    assert "provider 'hermes'" in message
    assert "API_SERVER_KEY" in message
    assert is_credential_error(message)


async def test_api_key_env_resolved_key_reaches_litellm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The whole chain: ``api_key_env`` → provider entry → the LLM call."""
    monkeypatch.setenv("API_SERVER_KEY", FAKE_KEY)
    config = ChimeraConfig.model_validate(
        _config_dict(api_key=None, api_key_env="API_SERVER_KEY")
    )
    gateway = LiteLLMGateway(config)
    captured: list[dict[str, Any]] = []

    async def capture(**kwargs: Any) -> Any:  # noqa: ANN401
        captured.append(kwargs)
        return _StubResult()

    with patch("litellm.acompletion", new=capture):
        await gateway.complete(MODEL_ID, [{"role": "user", "content": "hi"}])

    assert captured[0]["api_key"] == FAKE_KEY
    assert captured[0]["api_base"] == GATEWAY_BASE_URL


def _example_config() -> dict[str, Any]:
    raw = yaml.safe_load(EXAMPLE_CONFIG.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    return raw


def test_example_config_declares_the_hermes_gateway_provider() -> None:
    raw = _example_config()
    provider = raw["providers"][PROVIDER]
    assert provider["base_url"] == GATEWAY_BASE_URL
    assert provider["api_key_env"] == "API_SERVER_KEY"
    # Never a literal key: the env var NAME is the only credential reference.
    assert "api_key" not in provider

    entry = raw["models"][MODEL_ID]
    assert entry["provider"] == PROVIDER
    assert entry["enabled"] is True
    assert entry["categories"], "the catalog model needs category scores"
    assert entry["cost_tier"] in {"budget", "standard", "premium"}


def test_example_config_declares_the_router9_gateway_provider() -> None:
    """C3: the shipped example wires the 9router fleet gateway as a provider."""
    raw = _example_config()
    provider = raw["providers"][ROUTER9_PROVIDER]
    assert provider["base_url"] == ROUTER9_BASE_URL
    assert provider["api_key_env"] == "ROUTER9_API_KEY"
    # Never a literal key: the env var NAME is the only credential reference.
    assert "api_key" not in provider

    router9_models = {
        model_id: entry
        for model_id, entry in raw["models"].items()
        if entry.get("provider") == ROUTER9_PROVIDER
    }
    assert len(router9_models) >= 3, "the example needs >= 3 router9 catalog models"
    for model_id, entry in router9_models.items():
        assert model_id.startswith(f"{ROUTER9_PROVIDER}/"), model_id
        assert entry["enabled"] is True
        assert entry["categories"], f"{model_id} needs category scores"
        assert entry["cost_tier"] in {"budget", "standard", "premium"}


def test_every_example_router9_model_resolves_to_its_upstream_id() -> None:
    """The example's own catalog ids route to 9router's namespaced ids."""
    raw = _example_config()
    base_url = raw["providers"][ROUTER9_PROVIDER]["base_url"]
    namespaced = [
        model_id
        for model_id, entry in raw["models"].items()
        if entry.get("provider") == ROUTER9_PROVIDER
        and model_id.count("/") >= 2  # "<provider>/<namespace>/<model>"
    ]
    assert namespaced, "at least one example model must use a namespaced upstream id"

    for model_id in namespaced:
        model, extra = resolve_litellm_model(
            model_id, _entry(ROUTER9_PROVIDER), base_url=base_url,
        )
        expected = model_id[len(ROUTER9_PROVIDER) + 1:]
        assert model == f"openai/{expected}"
        assert extra["api_base"] == base_url
        assert extra["custom_llm_provider"] == "openai"


def test_example_config_holds_no_literal_credentials() -> None:
    """Every tracked credential reference is a ``${VAR}`` placeholder."""
    raw = _example_config()
    for name, api_keys_value in raw.get("api_keys", {}).items():
        assert api_keys_value.startswith("${") and api_keys_value.endswith("}"), (
            f"api_keys.{name} must be a ${{VAR}} placeholder, got a literal"
        )
    for name, provider in raw["providers"].items():
        assert "api_key" not in provider, f"providers.{name} inlines a key"
    # The two custom OpenAI-compatible endpoints name their env var, nothing else.
    for name, env_var in ((PROVIDER, "API_SERVER_KEY"), (ROUTER9_PROVIDER, "ROUTER9_API_KEY")):
        assert raw["providers"][name].get("api_key_env") == env_var


def test_docs_document_the_api_key_env_seam(monkeypatch: pytest.MonkeyPatch) -> None:
    """C3: the docs name the gateway provider and its env-var seam."""
    for doc in (REPO_ROOT / "docs" / "CONFIG.md", REPO_ROOT / "README.md"):
        text = doc.read_text(encoding="utf-8")
        assert "API_SERVER_KEY" in text, f"{doc.name} does not name API_SERVER_KEY"


def test_docs_document_the_router9_provider() -> None:
    """C3: both docs describe the 9router gateway, its id map and its key seam."""
    for doc in (REPO_ROOT / "docs" / "CONFIG.md", REPO_ROOT / "README.md"):
        text = doc.read_text(encoding="utf-8")
        assert ROUTER9_PROVIDER in text, f"{doc.name} does not name the provider"
        assert "ROUTER9_API_KEY" in text, f"{doc.name} does not name ROUTER9_API_KEY"
        assert ROUTER9_BASE_URL in text, f"{doc.name} does not show the endpoint"
        assert "router9/ds/deepseek-v4-flash" in text, (
            f"{doc.name} does not show the catalog → upstream id mapping"
        )


@pytest.fixture
def _cold_dotenv(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Point HOME at a scratch dir and start the ~/.hermes/.env cache cold."""
    monkeypatch.delenv("API_SERVER_KEY", raising=False)
    monkeypatch.setattr(chimera_config, "_hermes_dotenv_cache", None)
    yield


def test_api_server_key_resolves_from_hermes_dotenv(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, _cold_dotenv: None,
) -> None:
    """``api_key_env: API_SERVER_KEY`` resolves via ~/.hermes/.env — no literal."""
    hermes_dir = tmp_path / ".hermes"
    hermes_dir.mkdir()
    (hermes_dir / ".env").write_text(
        f"API_SERVER_KEY={FAKE_KEY}\n", encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(tmp_path))

    config = ChimeraConfig.model_validate(_example_config())

    assert config.providers[PROVIDER].api_key_env == "API_SERVER_KEY"
    assert config.providers[PROVIDER].api_key == FAKE_KEY


def test_hermes_provider_is_unresolved_without_the_env_var(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, _cold_dotenv: None,
) -> None:
    """A box without the key resolves to ``None`` instead of a literal."""
    monkeypatch.setenv("HOME", str(tmp_path))

    config = ChimeraConfig.model_validate(_example_config())

    assert config.providers[PROVIDER].api_key is None
