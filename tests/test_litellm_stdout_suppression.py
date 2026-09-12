"""Regression tests: LiteLLM must never print its debug banners to stdout.

DF-CHIMERA-0911-1. LiteLLM gates two bare ``print()`` paths on the
process-global ``litellm.suppress_debug_info`` flag (False by default):

* ``litellm_core_utils/get_llm_provider_logic.py`` prints an ANSI
  ``Provider List: https://docs.litellm.ai/docs/providers`` banner whenever a
  provider-less model string reaches it — and LiteLLM calls that helper from
  provider transformations (OpenRouter's ``get_supported_openai_params`` →
  ``utils.supports_reasoning``), so the banner fires on a perfectly SUCCESSFUL
  deliberation.
* ``litellm_core_utils/exception_mapping_utils.py`` prints a
  ``Give Feedback / Get Help`` block for every mapped provider error.

Stdout is the MCP stdio JSON-RPC wire, so one banner line corrupts a live
session (0.2.4 leaked exactly three of them on a real ``formation=speed``
call while ``formation=simple`` stayed clean). ``chimera.gateway`` owns the
only LiteLLM call sites, so it silences the switches immediately before every
completion: :func:`chimera.gateway.ensure_litellm_quiet`.

These tests are offline: the ordering tests inject a fake ``litellm`` module,
and the behavioural tests rely on LiteLLM failing provider resolution BEFORE
any network call (a provider-less model raises locally).
"""

from __future__ import annotations

import importlib
import sys
from typing import Any

import pytest

from chimera import gateway
from chimera.config import ChimeraConfig, ModelEntry
from chimera.gateway import (
    GatewayError,
    LiteLLMGateway,
    _litellm_acomplete,
    _litellm_sync_complete,
    ensure_litellm_quiet,
)
from tests.conftest import CONFIG_DICT

# The exact banner strings the flag suppresses.
PROVIDER_LIST_BANNER = "Provider List: https://docs.litellm.ai/docs/providers"
FEEDBACK_BANNER = "Give Feedback / Get Help"

#: A model id LiteLLM cannot route to any provider, so ``get_llm_provider``
#: raises locally with no HTTP request — the banner path, offline.
PROVIDERLESS_MODEL = "chimera-providerless-probe-model"


class _FakeLitellm:
    """Stand-in litellm module that records the debug-flag state per call."""

    def __init__(self, result: Any = "RESULT", exc: BaseException | None = None) -> None:
        self.suppress_debug_info = False
        self.set_verbose = True
        self.result = result
        self.exc = exc
        self.flags_at_call: list[Any] = []
        self.verbose_at_call: list[Any] = []

    def _record(self) -> Any:
        self.flags_at_call.append(self.suppress_debug_info)
        self.verbose_at_call.append(self.set_verbose)
        if self.exc is not None:
            raise self.exc
        return self.result

    async def acompletion(self, **kwargs: Any) -> Any:  # noqa: ANN401
        return self._record()

    def completion(self, **kwargs: Any) -> Any:  # noqa: ANN401
        return self._record()


class _FakeResult:
    """Minimal LiteLLM-shaped completion result."""

    class _Message:
        content = "hello"

    class _Choice:
        finish_reason = "stop"

        def __init__(self) -> None:
            self.message = _FakeResult._Message()

    class _Usage:
        prompt_tokens = 1
        completion_tokens = 2

    def __init__(self) -> None:
        self.choices = [_FakeResult._Choice()]
        self.usage = _FakeResult._Usage()


@pytest.fixture
def real_litellm():  # type: ignore[no-untyped-def]
    """The real litellm module, imported for the behavioural tests."""
    return importlib.import_module("litellm")


def _config_with_model(name: str, provider: str, **retry: int) -> ChimeraConfig:
    """A valid config plus one extra model entry (and optional retry policy)."""
    data = dict(CONFIG_DICT)
    data["models"] = dict(CONFIG_DICT["models"])
    data["models"][name] = {
        "categories": {"code": 0.5},
        "cost_tier": "budget",
        "provider": provider,
    }
    if retry:
        data["retry"] = retry
    cfg = ChimeraConfig.model_validate(data)
    assert isinstance(cfg.get_model(name), ModelEntry)
    return cfg


# --------------------------------------------------------------------------- #
# The seam itself
# --------------------------------------------------------------------------- #


def test_ensure_litellm_quiet_sets_both_debug_switches() -> None:
    """Both stdout-affecting switches are flipped, not just one."""
    fake = _FakeLitellm()
    returned = ensure_litellm_quiet(fake)
    assert returned is fake
    assert fake.suppress_debug_info is True
    assert fake.set_verbose is False


def test_ensure_litellm_quiet_is_idempotent() -> None:
    fake = _FakeLitellm()
    ensure_litellm_quiet(fake)
    ensure_litellm_quiet(fake)
    assert fake.suppress_debug_info is True
    assert fake.set_verbose is False


def test_ensure_litellm_quiet_flags_the_real_module(real_litellm, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """The real litellm module is left with the banner paths disabled."""
    monkeypatch.setattr(real_litellm, "suppress_debug_info", False)
    monkeypatch.setattr(real_litellm, "set_verbose", True)
    ensure_litellm_quiet()
    assert real_litellm.suppress_debug_info is True
    assert real_litellm.set_verbose is False


def test_ensure_litellm_quiet_reasserts_after_external_reset(real_litellm, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """No cached 'already configured' shortcut: the flag is set every call."""
    monkeypatch.setattr(real_litellm, "suppress_debug_info", False)
    ensure_litellm_quiet()
    monkeypatch.setattr(real_litellm, "suppress_debug_info", False)
    ensure_litellm_quiet()
    assert real_litellm.suppress_debug_info is True


# --------------------------------------------------------------------------- #
# Ordering: the flag is set BEFORE the completion (and thus before any error
# mapping, which litellm runs inside completion/acompletion)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_async_completion_silences_before_calling_litellm(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    fake = _FakeLitellm(result="async-ok")
    monkeypatch.setitem(sys.modules, "litellm", fake)
    result = await _litellm_acomplete({"model": PROVIDERLESS_MODEL, "messages": []})
    assert result == "async-ok"
    assert fake.flags_at_call == [True], "flag was not True when acompletion was invoked"
    assert fake.verbose_at_call == [False]


@pytest.mark.asyncio
async def test_async_completion_silences_before_an_exception(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """The exception path is covered too: litellm maps errors INSIDE the call."""
    fake = _FakeLitellm(exc=RuntimeError("provider boom"))
    monkeypatch.setitem(sys.modules, "litellm", fake)
    with pytest.raises(RuntimeError, match="provider boom"):
        await _litellm_acomplete({"model": PROVIDERLESS_MODEL, "messages": []})
    assert fake.flags_at_call == [True]


def test_sync_completion_silences_before_calling_litellm(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    fake = _FakeLitellm(result="sync-ok")
    monkeypatch.setitem(sys.modules, "litellm", fake)
    result = _litellm_sync_complete({"model": PROVIDERLESS_MODEL, "messages": []})
    assert result == "sync-ok"
    assert fake.flags_at_call == [True]
    assert fake.verbose_at_call == [False]


def test_sync_completion_silences_before_an_exception(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    fake = _FakeLitellm(exc=RuntimeError("sync boom"))
    monkeypatch.setitem(sys.modules, "litellm", fake)
    with pytest.raises(RuntimeError, match="sync boom"):
        _litellm_sync_complete({"model": PROVIDERLESS_MODEL, "messages": []})
    assert fake.flags_at_call == [True]


@pytest.mark.asyncio
async def test_gateway_complete_silences_the_real_litellm_module(real_litellm, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """A normal (mocked) completion leaves the real module quiet."""
    monkeypatch.setattr(real_litellm, "suppress_debug_info", False)
    monkeypatch.setattr(
        real_litellm,
        "acompletion",
        lambda **kwargs: _FakeResult(),
    )
    gw = LiteLLMGateway(_config_with_model("probe/model", "openrouter"))
    resp = await gw.complete("probe/model", [{"role": "user", "content": "hi"}])
    assert resp.text == "hello"
    assert real_litellm.suppress_debug_info is True


# --------------------------------------------------------------------------- #
# Behavioural: the real banner no longer reaches stdout
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_gateway_complete_prints_no_provider_banner(real_litellm, monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    """A provider-less model must not leak the ANSI banner onto stdout.

    RED before the fix: litellm prints the banner while raising its
    BadRequestError, so the five retry attempts each polluted stdout.
    """
    monkeypatch.setattr(real_litellm, "suppress_debug_info", False)
    cfg = _config_with_model("probe/providerless", "providerless", max_attempts=1, base_delay_ms=1)
    gw = LiteLLMGateway(cfg)
    with pytest.raises(GatewayError):
        await gw.complete("probe/providerless", [{"role": "user", "content": "hi"}])
    out = capsys.readouterr().out
    assert PROVIDER_LIST_BANNER not in out
    assert FEEDBACK_BANNER not in out
    # The banner is the whole point: chimera's own structlog lines are handled
    # by the observability configuration (pinned to stderr on the MCP/CLI
    # paths, unconfigured here) — LiteLLM's bare prints are not, so only the
    # LiteLLM banner must be absent. RED before the fix: it was present.
    assert "Provider List" not in out


def test_real_litellm_provider_lookup_banner_is_suppressed(real_litellm, capsys) -> None:  # type: ignore[no-untyped-def]
    """Direct proof: the same lookup that leaked on 0.2.4 is silent now."""
    ensure_litellm_quiet()
    with pytest.raises(Exception):  # noqa: B017 - litellm raises BadRequestError
        real_litellm.get_llm_provider(model=PROVIDERLESS_MODEL)
    out = capsys.readouterr().out
    assert PROVIDER_LIST_BANNER not in out
    assert out == "", f"stdout must stay clean, got {out!r}"


def test_litellm_call_sites_are_all_guarded() -> None:
    """No bare ``import litellm`` may bypass the seam in the gateway module."""
    with open(gateway.__file__ or "", encoding="utf-8") as fh:
        source = fh.read()
    assert "ensure_litellm_quiet()" in source
    bare = [ln.strip() for ln in source.splitlines() if ln.strip() == "import litellm"]
    assert bare == [], (
        f"gateway.py must resolve litellm through ensure_litellm_quiet(), found bare imports: {bare}"
    )
