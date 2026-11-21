"""A retried upstream call is visible to the operator (DF-CHIMERA-V2-128).

The defect this pins: a stub upstream answered 429, 429, 200 and the served API
returned 200 in 2.1 s — but the request cost three upstream attempts and the
operator could see **nothing**: no line in the log and no counter in ``/metrics``.
F7 in ``docs/RESILIENCE.md`` promised the log line, nothing promised the metric,
and the shipped ``chimera.yaml.example`` runs at ``observability.log_level:
warning`` so an ``info`` line would have been invisible even after the field was
added.

So these tests assert the two halves of the promise at the layer that actually
serves traffic, plus the negative contract (a call that never retried must not
mint a series):

* one ``gateway_retry`` line per retried attempt, carrying the attempt number,
  the delay that was slept and the status the provider answered with — asserted
  through the REAL logging pipeline at the shipped verbosity, not a mock;
* one ``chimera_retries_total{reason=...}`` increment per retried attempt, at
  exactly ``2`` for the two-429-then-200 case, and greppable by name in the
  served ``/metrics`` body.

The stub is a real loopback HTTP server: LiteLLM, the OpenAI client and httpx are
exercised for real, so the retry ladder under test is the production one.
"""

from __future__ import annotations

import io
import json
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from chimera.api.server import create_app  # noqa: E402
from chimera.config import ChimeraConfig, Observability  # noqa: E402
from chimera.gateway import LiteLLMGateway  # noqa: E402
from chimera.metrics import (  # noqa: E402
    RETRY_REASONS,
    classify_retry,
    render_metrics,
    reset_metrics,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
PROVIDER = "stub"
MODEL = "stub/stub-model"
FAKE_KEY = "fake-key-for-retry-observability"

_OK_BODY: dict[str, Any] = {
    "id": "chatcmpl-stub",
    "object": "chat.completion",
    "created": 0,
    "model": MODEL,
    "choices": [
        {
            "index": 0,
            "message": {"role": "assistant", "content": "ok"},
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
}
_RATE_LIMIT_BODY: dict[str, Any] = {
    "error": {"message": "rate limited by the test stub", "type": "rate_limit_error"}
}
_SERVER_ERROR_BODY: dict[str, Any] = {"error": {"message": "upstream is unwell", "type": "server_error"}}


class UpstreamStub:
    """Loopback OpenAI-shaped upstream answering ``script`` in order, then 200.

    ``arrivals`` records ``(monotonic, status)`` per request, so a test can prove
    how many times Chimera actually reached the provider instead of trusting the
    latency to imply it.
    """

    def __init__(self, script: list[int]) -> None:
        self.script = list(script)
        self.arrivals: list[tuple[float, int]] = []
        stub = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_POST(self) -> None:  # noqa: N802 - stdlib handler contract
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length) if length else b""
                json.loads(raw or b"{}")  # the gateway must send real JSON
                status = stub.script.pop(0) if stub.script else 200
                stub.arrivals.append((time.monotonic(), status))
                body = {
                    429: _RATE_LIMIT_BODY,
                    500: _SERVER_ERROR_BODY,
                    503: _SERVER_ERROR_BODY,
                }.get(status, _OK_BODY)
                encoded = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def log_message(self, *args: Any) -> None:  # keep pytest output clean
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}/v1"

    @property
    def statuses(self) -> list[int]:
        return [status for _, status in self.arrivals]

    def __enter__(self) -> UpstreamStub:
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)

    @contextmanager
    def running(self) -> Iterator[UpstreamStub]:
        with self:
            yield self


class LogRecorder:
    """Stand-in for structlog's bound logger that records (level, event, fields)."""

    def __init__(self) -> None:
        self.events: list[tuple[str, str, dict[str, Any]]] = []

    def __getattr__(self, level: str) -> Any:  # noqa: ANN401 - structlog shape
        def _record(event: str = "", **fields: Any) -> None:
            self.events.append((level, event or level, fields))

        return _record

    def named(self, event: str) -> list[tuple[str, dict[str, Any]]]:
        return [(level, fields) for level, name, fields in self.events if name == event]


def _config(base_url: str, *, log_level: str = "warning") -> ChimeraConfig:
    """Minimal one-model catalog pointed at *base_url*.

    ``log_level`` defaults to ``warning`` because that is what the shipped
    ``chimera.yaml.example`` sets — the verbosity a stock deployment actually
    runs at, i.e. the one the retry line has to survive.
    """
    return ChimeraConfig.model_validate(
        {
            "providers": {PROVIDER: {"base_url": base_url, "api_key": FAKE_KEY}},
            "models": {
                MODEL: {
                    "categories": {"code": 100.0, "general": 100.0},
                    "cost_tier": "budget",
                    "provider": PROVIDER,
                }
            },
            "formations": {"simple": {"workers": 1, "aggregator": "default"}},
            "defaults": {
                "dispatcher": MODEL,
                "default_worker": MODEL,
                "default_aggregator": MODEL,
            },
            "retry": {
                "max_attempts": 3,
                "base_delay_ms": 10,
                "max_delay_ms": 20,
                "backoff_multiplier": 1.0,
            },
            "observability": {"log_level": log_level, "trace_enabled": False},
        }
    )


def _retry_samples(body: str) -> list[str]:
    """Sample lines of the retry counter only (skip HELP/TYPE comments)."""
    return [
        line
        for line in body.splitlines()
        if line.startswith("chimera_retries_total{") or line == "chimera_retries_total"
    ]


@pytest.fixture(autouse=True)
def _clean_registry() -> Iterator[None]:
    """The metric registry is process-global module state; start and end empty."""
    reset_metrics()
    yield
    reset_metrics()


def test_served_api_logs_every_retry_and_counts_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC1/AC2 through the served API at the shipped log level (warning)."""
    captured = io.StringIO()
    # create_app -> configure_logging(cfg.observability) binds PrintLogger to
    # whatever sys.stdout is at that moment, so patch before building the app.
    monkeypatch.setattr("sys.stdout", captured)
    try:
        with UpstreamStub([429, 429, 200]) as stub:
            app = create_app(config=_config(stub.base_url, log_level="warning"))
            client = TestClient(app)
            response = client.post("/v1/deliberate", json={"prompt": "hi", "formation": "simple"})
            assert response.status_code == 200, response.text
            # The stub really served the retry sequence, so the lines below are
            # explained by real 429s rather than by a mocked exception.
            assert stub.statuses[:3] == [429, 429, 200]
            metrics_body = client.get("/metrics").text
    finally:
        # Rebind the process-wide logging config away from the dead buffer so a
        # later test never writes into it.
        from chimera.observability import configure_logging

        configure_logging(Observability(log_level="info"), force_stderr=True)

    records = []
    for line in captured.getvalue().splitlines():
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:  # pragma: no cover - non-structlog noise
            continue
        if isinstance(payload, dict) and payload.get("event") == "gateway_retry":
            records.append(payload)

    # One line per retried attempt: two 429s => two lines, the third attempt
    # (the 200) is not a retry.
    assert len(records) == 2, captured.getvalue()
    assert [record["attempt"] for record in records] == [1, 2]
    for record in records:
        # Visible at the shipped `log_level: warning` — this is the half the row
        # was filed for; an `info` line here would have been dropped.
        assert record["level"] == "warning"
        assert record["upstream_status"] == 429
        assert record["reason"] == "rate_limit"
        assert isinstance(record["delay_ms"], int) and record["delay_ms"] > 0
        assert record["next_attempt"] == record["attempt"] + 1
        assert record["model"] == MODEL
        assert record["provider"] == PROVIDER
        assert "error" in record

    # AC2: greppable in /metrics by name, incremented exactly twice.
    assert "# TYPE chimera_retries_total counter" in metrics_body
    assert 'chimera_retries_total{reason="rate_limit"} 2' in metrics_body


async def test_exhausted_ladder_still_reports_each_retry() -> None:
    """AC1's "whether or not the retry succeeded": a dead upstream is not silent."""
    recorder = LogRecorder()
    import chimera.gateway as gateway_module

    with UpstreamStub([429, 429, 429]) as stub:
        gateway = LiteLLMGateway(_config(stub.base_url))
        with pytest.MonkeyPatch.context() as patcher:
            patcher.setattr(gateway_module, "log", recorder)
            with pytest.raises(gateway_module.GatewayError) as excinfo:
                await gateway.complete(MODEL, [{"role": "user", "content": "hi"}])
            assert "3 attempts" in str(excinfo.value)
        # Every attempt reached the provider; two of them were retries.
        assert stub.statuses == [429, 429, 429]

    retries = recorder.named("gateway_retry")
    assert [fields["attempt"] for _, fields in retries] == [1, 2]
    exhausted = recorder.named("gateway_retry_exhausted")
    assert len(exhausted) == 1
    assert exhausted[0][1]["attempts"] == 3
    assert 'chimera_retries_total{reason="rate_limit"} 2' in render_metrics()


async def test_server_error_retry_carries_its_own_status_and_reason() -> None:
    """The status on the line is the provider's answer, not a constant."""
    recorder = LogRecorder()
    import chimera.gateway as gateway_module

    with UpstreamStub([503, 200]) as stub:
        gateway = LiteLLMGateway(_config(stub.base_url))
        with pytest.MonkeyPatch.context() as patcher:
            patcher.setattr(gateway_module, "log", recorder)
            response = await gateway.complete(MODEL, [{"role": "user", "content": "hi"}])
    assert response.text == "ok"
    retries = recorder.named("gateway_retry")
    assert len(retries) == 1
    assert retries[0][1]["upstream_status"] == 503
    assert retries[0][1]["reason"] == "server_error"
    assert 'chimera_retries_total{reason="server_error"} 1' in render_metrics()


async def test_a_call_that_never_retried_leaves_no_series() -> None:
    """Negative contract: the counter must not count healthy calls."""
    with UpstreamStub([200]) as stub:
        gateway = LiteLLMGateway(_config(stub.base_url))
        assert (await gateway.complete(MODEL, [{"role": "user", "content": "hi"}])).text == "ok"
    assert _retry_samples(render_metrics()) == []


def test_classify_retry_uses_evidence_not_prose() -> None:
    """The label comes from the status/transport class, never from error text."""
    assert classify_retry(429) == "rate_limit"
    assert classify_retry(500) == "server_error"
    assert classify_retry(503) == "server_error"
    assert classify_retry(None, timed_out=True) == "timeout"
    assert classify_retry(None, network_error=True) == "network"
    assert classify_retry(None) == "other"
    # A status outranks a transport guess: a 429 that also read slowly is still
    # a rate limit, and must not be filed as a timeout.
    assert classify_retry(429, timed_out=True) == "rate_limit"
    assert set(RETRY_REASONS) == {
        "rate_limit",
        "server_error",
        "timeout",
        "network",
        "other",
    }


def test_docs_name_the_retry_log_fields_and_metric() -> None:
    """AC3: the doc describes what the code actually emits (no aspirational prose)."""
    resilience = (REPO_ROOT / "docs" / "RESILIENCE.md").read_text(encoding="utf-8")
    f7 = resilience.split("## F7", 1)[1].split("\n## ", 1)[0]

    for token in (
        "gateway_retry",
        "gateway_retry_exhausted",
        "upstream_status",
        "delay_ms",
        "next_attempt",
        "chimera_retries_total",
        "log_level: warning",
    ):
        assert token in f7, f"docs/RESILIENCE.md F7 no longer names {token!r}"

    for reason in RETRY_REASONS:
        assert f"`{reason}`" in f7

    operations = (REPO_ROOT / "docs" / "operations.md").read_text(encoding="utf-8")
    assert "| `chimera_retries_total` | counter | `reason` |" in operations
