"""DF-CHIMERA-V2-126 — Chimera's retry budget is the ONLY retry budget.

The defect this file pins: the LiteLLM client keeps its own retry ladder on top
of Chimera's, and its default (unset ``num_retries`` => 2 retries) is invisible
to ``retry.max_attempts``.  One *Chimera* attempt therefore fanned out to THREE
upstream requests, so ``max_attempts`` 1/3/5 cost 3/9/15 provider requests
(dogfood run 33, 2026-11-20) — an operator could neither see that budget nor
compute a worst-case provider bill from ``chimera.yaml``.

Why the assertions below count arrivals at a SOCKET instead of mocking
``litellm.acompletion``: the extra factor of 3 happens *inside* the client, so a
patched callable can never observe it.  A loopback stub that always answers 429
and records every arrival is the only place the multiplier is visible — and it
is also what makes the test a dependency-upgrade canary: if a future LiteLLM
reintroduces an internal retry that ignores ``num_retries``, the arrival count
stops equalling ``max_attempts`` and this suite goes red.

The stub is stdlib-only and bound to 127.0.0.1: no network, no credential.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import litellm
import pytest

from chimera import gateway as gateway_module
from chimera.config import ChimeraConfig
from chimera.gateway import GatewayError, LiteLLMGateway

#: The catalog model the socket-free arms drive: ``deepseek/deepseek-chat`` is
#: in the shared ``config`` fixture catalog (a native provider, so the call
#: kwargs are the plain production shape).
FIXTURE_MODEL = "deepseek/deepseek-chat"

PROVIDER = "metered"
MODEL_ID = "metered/meter-model"
#: Obviously-fake credential — never real key material.
FAKE_KEY = "fake-metering-stub-key-for-tests"

#: A retryable 429 body that carries no budget/quota keyword: the gateway's C7
#: detector must not short-circuit the ladder these tests drive.
RATE_LIMIT_BODY: dict[str, Any] = {
    "error": {"message": "rate limited by the metering stub", "type": "rate_limit_error"}
}


def _litellm_result(text: str = "ok") -> Any:  # noqa: ANN401
    """A minimal LiteLLM-shaped completion result."""
    return SimpleNamespace(
        choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content=text))],
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
    )


class _RecordingLogger:
    """Stand-in for ``chimera.gateway.log`` that records event names + fields.

    structlog binds its writer at import time, so the gateway's log lines do not
    reach ``capsys``/``capfd`` reliably in this suite; recording the calls at
    the module attribute is both deterministic and narrower — it asserts the
    event the operator would read, not a rendered line's layout.

    structlog's call shape is ``log.<level>(event, **fields)``, so the event
    name is the positional argument and every bound logger method is dispatched
    through ``__getattr__``.
    """

    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    def __getattr__(self, name: str) -> Any:  # noqa: ANN401 - one callable per level
        def _record(event: str = "", **fields: Any) -> None:  # noqa: ANN401
            self.events.append((event or name, fields))

        return _record

    def only(self, event: str) -> list[dict[str, Any]]:
        return [fields for name, fields in self.events if name == event]


class _MeteringStub:
    """Loopback OpenAI-compatible upstream that answers 429 forever.

    Every arrival is timestamped on the SERVER's clock (``time.monotonic``), so
    an assertion about how many requests one gateway call issued never depends
    on Chimera's own logs — which is the point, because the inner ladder writes
    none.
    """

    def __init__(self) -> None:
        self.arrivals: list[float] = []
        stub = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length) if length else b""
                # Parse the body even though it is unused: the stub must consume
                # it, or a keep-alive client waits on an unread request.
                json.loads(raw or b"{}")
                stub.arrivals.append(time.monotonic())
                encoded = json.dumps(RATE_LIMIT_BODY).encode()
                self.send_response(429)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def log_message(self, *args: Any) -> None:  # noqa: ANN401
                """Silence the per-request stderr line (keeps pytest output clean)."""

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_address[1]}/v1"

    def __enter__(self) -> _MeteringStub:
        self._thread.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)


@contextmanager
def _metering_stub() -> Iterator[_MeteringStub]:
    with _MeteringStub() as stub:
        yield stub


def _config(base_url: str, max_attempts: int) -> ChimeraConfig:
    """One custom (non-native) provider pointed at the stub.

    ``retry`` is the only variable the tests vary: it is the whole budget
    Chimera claims to own.
    """
    return ChimeraConfig.model_validate(
        {
            "providers": {PROVIDER: {"base_url": base_url, "api_key": FAKE_KEY}},
            "models": {
                MODEL_ID: {
                    "categories": {"code": 50.0},
                    "cost_tier": "budget",
                    "provider": PROVIDER,
                }
            },
            "defaults": {
                "dispatcher": MODEL_ID,
                "default_worker": MODEL_ID,
                "default_aggregator": MODEL_ID,
            },
            "retry": {
                "max_attempts": max_attempts,
                "base_delay_ms": 1,
                "max_delay_ms": 2,
                "backoff_multiplier": 1.0,
            },
            "observability": {"log_level": "critical", "trace_enabled": False},
        }
    )


# --------------------------------------------------------------------------- #
# AC 1 / AC 3 — one gateway call == ``retry.max_attempts`` upstream requests
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("max_attempts", [1, 3, 5])
async def test_one_gateway_call_issues_exactly_max_attempts_upstream_requests(
    max_attempts: int,
) -> None:
    """Arrivals == ``max_attempts``, not 3x it.

    Pre-fix this asserts 1/3/5 and measured 3/9/15: the multiplication came
    from the client's own ladder, which no ``retry`` setting could reach — so
    this is also the dependency-upgrade canary (AC 3).
    """
    with _metering_stub() as stub:
        gateway = LiteLLMGateway(_config(stub.base_url, max_attempts))
        with pytest.raises(GatewayError):
            await gateway.complete(MODEL_ID, [{"role": "user", "content": "hi"}])

        assert len(stub.arrivals) == max_attempts, (
            f"one gateway call at retry.max_attempts={max_attempts} must cost exactly "
            f"{max_attempts} upstream request(s); the stub saw {len(stub.arrivals)}"
        )


async def test_probe_costs_exactly_one_upstream_request() -> None:
    """A health probe is ONE request even when the ladder would allow five.

    ``_complete_probe_once`` makes a single Chimera attempt by design
    (DF-CHIMERA-V2-16: retrying a 429 burns the shared health budget).  With
    the inner ladder active that "one attempt" was still three provider
    requests, so this arm was silently 3x over its documented cost.
    """
    with _metering_stub() as stub:
        gateway = LiteLLMGateway(_config(stub.base_url, 5))
        with pytest.raises(GatewayError):
            await gateway.complete(
                MODEL_ID,
                [{"role": "user", "content": "ping"}],
                max_tokens=1,
                probe=True,
            )

        assert len(stub.arrivals) == 1, f"a probe must cost 1 request, saw {len(stub.arrivals)}"


# --------------------------------------------------------------------------- #
# AC 2 — the directive is explicit on the production path and cannot be
#        overridden back into an invisible budget
# --------------------------------------------------------------------------- #


async def test_production_call_declares_zero_inner_retries(config: ChimeraConfig) -> None:
    """The kwargs the production path hands LiteLLM carry ``num_retries=0``.

    Socket-free companion to the arrival-count arms: it names WHICH directive
    disables the inner ladder, so a refactor that moves it is diagnosable
    without re-deriving the multiplier from timings.
    """
    gateway = LiteLLMGateway(config)
    captured: dict[str, Any] = {}

    def capture(**kwargs: Any) -> Any:  # noqa: ANN401
        captured.update(kwargs)
        return _litellm_result()

    with patch("litellm.acompletion", side_effect=capture):
        await gateway.complete(FIXTURE_MODEL, [{"role": "user", "content": "hi"}])

    # Read the module attribute rather than importing the symbol: with the fix
    # reverted (the red-proof run) the constant does not exist, and a collection
    # error would hide the arrival-count failure this row is graded on.
    assert getattr(gateway_module, "_LITELLM_INNER_RETRIES", None) == 0
    assert captured["num_retries"] == 0


async def test_caller_supplied_retry_directive_cannot_resurrect_the_ladder() -> None:
    """A caller asking for retries is IGNORED, loudly — not silently obeyed.

    ``complete(**kwargs)`` forwards caller kwargs verbatim, so without the
    explicit override a caller (or a future caller written by someone reading
    LiteLLM's docs) could reinstate a retry budget that ``retry.max_attempts``
    does not describe.  Measured through the stub, because ``max_retries`` is
    the alias such a caller is most likely to reach for.

    The warning is asserted against a recording double for the module logger
    rather than through pytest's output capture: structlog binds its writer at
    import time, so neither ``capsys`` nor ``capfd`` reliably sees these lines.
    """
    events = _RecordingLogger()
    with _metering_stub() as stub, patch("chimera.gateway.log", events):
        gateway = LiteLLMGateway(_config(stub.base_url, 2))
        with pytest.raises(GatewayError):
            await gateway.complete(
                MODEL_ID,
                [{"role": "user", "content": "hi"}],
                num_retries=7,
                max_retries=5,
            )

        assert len(stub.arrivals) == 2, (
            f"caller retry directives must not add a budget, saw {len(stub.arrivals)} arrivals"
        )

    ignored = events.only("gateway_caller_retry_ignored")
    assert len(ignored) == 1, f"the override must be reported once, got {ignored}"
    assert ignored[0]["num_retries"] == 7
    assert ignored[0]["applied"] == 0


async def test_caller_zero_inner_retries_is_not_flagged(
    config: ChimeraConfig,
) -> None:
    """An explicit ``num_retries=0`` agrees with the gateway — no warning."""
    gateway = LiteLLMGateway(config)

    def capture(**kwargs: Any) -> Any:  # noqa: ANN401
        return _litellm_result()

    events = _RecordingLogger()
    with (
        patch("litellm.acompletion", side_effect=capture),
        patch("chimera.gateway.log", events),
    ):
        await gateway.complete(
            FIXTURE_MODEL,
            [{"role": "user", "content": "hi"}],
            num_retries=0,
        )

    assert events.only("gateway_caller_retry_ignored") == []


# --------------------------------------------------------------------------- #
# Non-vacuity: the meter really does see an inner ladder when one exists
# --------------------------------------------------------------------------- #


async def test_metering_stub_detects_client_side_retries() -> None:
    """CONTROL — proves the arrival counter is live, not vacuously == 1.

    Drives ``litellm.acompletion`` DIRECTLY with no retry directive of any
    kind: this is exactly the call the gateway used to make, and it arrives
    3 times (1 attempt + 2 client retries).  If this ever stops being > 1,
    either LiteLLM changed its defaults (re-derive the fix and the docs
    arithmetic) or the stub stopped metering — either way the arrival-count arm
    above would be passing for the wrong reason.
    """
    with _metering_stub() as stub:
        with pytest.raises(Exception):  # noqa: B017 - any mapped provider error proves the point
            await litellm.acompletion(
                model="openai/meter-model",
                messages=[{"role": "user", "content": "hi"}],
                api_base=stub.base_url,
                api_key=FAKE_KEY,
                custom_llm_provider="openai",
                timeout=10,
            )

        assert len(stub.arrivals) > 1, (
            "the metering stub saw a single arrival for an undirected client call — the "
            "inner-retry multiplier is gone, so re-derive the budget story before trusting it"
        )
