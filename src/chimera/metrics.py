"""Prometheus text-format metrics for the Chimera HTTP API (CHIMERA-V2-OPS-001).

The ops census flags any service that exposes health but no metrics: health
answers *"is it alive"*, never *"how much is it serving, how slow is it, and how
often does it fail, by cause"*. Those three questions are what a scrape surface
is for, and without them a degradation (rising 5xx, a single endpoint getting
slower) is invisible until a user reports it.

This module is that surface, and it deliberately has **no third-party
dependency**: the project pins its dependency set on purpose, and the
Prometheus text exposition format (0.0.4) is a stable wire contract, so a
hand-rolled registry is both smaller and safer than adding a client library to
the lock file.

Scrape ``GET /metrics`` on the API's own listener — no extra port, no second
auth scheme. The endpoint is excluded from the request counter so repeated
scrapes cannot inflate the numbers they report.

Design notes worth keeping:

* **Bounded label cardinality.** The ``route`` label is the matched route
  TEMPLATE (``/v1/deliberate``), never the request path, and an unmatched
  request collapses to ``<unmatched>``. Without that, a scanner hitting
  ``/wp-admin-<random>`` a few thousand times would mint a time series per hit
  and turn the scrape surface into its own outage.
* **Streaming-safe.** The middleware is a bare ASGI wrapper, not
  ``BaseHTTPMiddleware``: it passes ``send`` straight through, so SSE bodies
  (``/web/.../stream``) are not buffered or re-framed by instrumentation.
* **Thread-safe.** Handlers may run in a threadpool, so every mutation takes the
  registry lock. A ``reset`` exists only for tests.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Awaitable, Callable, Iterable
from typing import Any

__all__ = [
    "DEFAULT_BUCKETS",
    "METRIC_PREFIX",
    "MetricsMiddleware",
    "classify_error",
    "observe_request",
    "render_metrics",
    "reset_metrics",
]

#: Every exposed metric name starts here, so a fleet monitor can select on one
#: prefix and never has to know the individual families.
METRIC_PREFIX = "chimera"

#: Latency buckets in seconds. A deliberation API mixes sub-millisecond routes
#: (health, formations, models) with multi-second ones (a full deliberation), so
#: the interesting quantiles sit above 0.5 s and the tail matters up to a
#: minute — the server's own request timeout is the practical ceiling.
DEFAULT_BUCKETS: tuple[float, ...] = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
    30.0,
    60.0,
)

#: Route label used for a request that matched no route (bounded cardinality).
UNMATCHED_ROUTE = "<unmatched>"

#: The exposition path itself — never counted, or a scrape reports on scrapes.
METRICS_PATH = "/metrics"


_ESCAPE = str.maketrans({"\\": "\\\\", '"': '\\"', "\n": "\\n"})


def _pairs(names: tuple[str, ...], values: tuple[str, ...]) -> str:
    """Render ``name="value"`` pairs (no braces), escaping what the format requires."""
    return ",".join(f'{name}="{value.translate(_ESCAPE)}"' for name, value in zip(names, values, strict=True))


def _format_labels(names: tuple[str, ...], values: tuple[str, ...]) -> str:
    """Render a full Prometheus label set, or the empty string when there are no labels."""
    return "{" + _pairs(names, values) + "}" if names else ""


def _with_le(names: tuple[str, ...], values: tuple[str, ...], bound: str) -> str:
    """Render the label set with the histogram's ``le`` bucket label appended."""
    return "{" + _pairs(names, values) + f',le="{bound}"' + "}"


class _Counter:
    """Monotonic counter: one value per label-tuple."""

    def __init__(self, name: str, help_text: str, labels: tuple[str, ...]) -> None:
        self.name = name
        self.help_text = help_text
        self.labels = labels
        self._values: dict[tuple[str, ...], float] = {}
        self._lock = threading.Lock()

    def inc(self, values: tuple[str, ...], amount: float = 1.0) -> None:
        with self._lock:
            self._values[values] = self._values.get(values, 0.0) + amount

    def render(self) -> str:
        lines = [f"# HELP {self.name} {self.help_text}", f"# TYPE {self.name} counter"]
        with self._lock:
            snapshot = sorted(self._values.items())
        for values, value in snapshot:
            lines.append(f"{self.name}{_format_labels(self.labels, values)} {_render_number(value)}")
        return "\n".join(lines) + "\n"


class _Histogram:
    """Cumulative histogram: per-bucket counts, plus sum and count per label-tuple."""

    def __init__(
        self,
        name: str,
        help_text: str,
        labels: tuple[str, ...],
        buckets: Iterable[float] = DEFAULT_BUCKETS,
    ) -> None:
        self.name = name
        self.help_text = help_text
        self.labels = labels
        self.buckets: tuple[float, ...] = tuple(sorted(buckets))
        #: label-tuple -> (per-bucket counts, sum, count)
        self._series: dict[tuple[str, ...], list[float]] = {}
        self._lock = threading.Lock()

    def observe(self, values: tuple[str, ...], amount: float) -> None:
        with self._lock:
            series = self._series.get(values)
            if series is None:
                # one counter per bucket, then sum, then count
                series = [0.0] * (len(self.buckets) + 2)
                self._series[values] = series
            for index, bound in enumerate(self.buckets):
                if amount <= bound:
                    series[index] += 1.0
            series[-2] += amount
            series[-1] += 1.0

    def render(self) -> str:
        lines = [f"# HELP {self.name} {self.help_text}", f"# TYPE {self.name} histogram"]
        with self._lock:
            snapshot = sorted(self._series.items())
        for values, series in snapshot:
            for index, bound in enumerate(self.buckets):
                bucket_labels = _with_le(self.labels, values, _render_number(bound))
                lines.append(f"{self.name}_bucket{bucket_labels} {_render_number(series[index])}")
            lines.append(
                f"{self.name}_bucket{_with_le(self.labels, values, '+Inf')} {_render_number(series[-1])}"
            )
            labels = _format_labels(self.labels, values)
            lines.append(f"{self.name}_sum{labels} {_render_number(series[-2])}")
            lines.append(f"{self.name}_count{labels} {_render_number(series[-1])}")
        return "\n".join(lines) + "\n"


def _render_number(value: float) -> str:
    """Render a float the way Prometheus expects (integers without a trailing .0)."""
    if value == int(value) and abs(value) < 1e15:
        return str(int(value))
    return repr(float(value))


# --------------------------------------------------------------------------- #
# The registry
# --------------------------------------------------------------------------- #

REQUESTS = _Counter(
    f"{METRIC_PREFIX}_requests_total",
    "HTTP requests served, by route template and status class.",
    ("method", "route", "status"),
)
ERRORS = _Counter(
    f"{METRIC_PREFIX}_request_errors_total",
    "Failed HTTP requests, split by cause (client_error, server_error, exception).",
    ("method", "route", "reason"),
)
DURATION = _Histogram(
    f"{METRIC_PREFIX}_request_duration_seconds",
    "HTTP request duration in seconds, by route template.",
    ("method", "route"),
)


def classify_error(status: int, reason: str | None = None) -> str | None:
    """Return the error cause label for a completed request, or None if it succeeded.

    ``reason`` overrides the status-derived class: the middleware passes
    ``"exception"`` when the ASGI app raised instead of answering, which is a
    different failure than a handler that deliberately returned a 5xx.
    """
    if reason is not None:
        return reason
    if status >= 500:
        return "server_error"
    if status >= 400:
        return "client_error"
    return None


def _status_label(status: int) -> str:
    if status >= 500:
        return "5xx"
    if status >= 400:
        return "4xx"
    if status >= 300:
        return "3xx"
    return "2xx"


def _route_label(scope: dict[str, Any]) -> str:
    """Return the matched route TEMPLATE, so label cardinality is bounded."""
    route = scope.get("route")
    template = getattr(route, "path", None)
    if isinstance(template, str):
        return template
    path = scope.get("path", "")
    if path == METRICS_PATH:
        return METRICS_PATH
    return UNMATCHED_ROUTE


def observe_request(
    scope: dict[str, Any],
    status: int,
    duration: float,
    *,
    reason: str | None = None,
) -> None:
    """Record one finished HTTP request. The scrape endpoint is excluded."""
    route = _route_label(scope)
    if route == METRICS_PATH:
        return
    method = str(scope.get("method", "GET")).upper()
    REQUESTS.inc((method, route, _status_label(status)))
    DURATION.observe((method, route), duration)
    cause = classify_error(status, reason)
    if cause is not None:
        ERRORS.inc((method, route, cause))


def render_metrics() -> str:
    """Render the whole registry in Prometheus text exposition format 0.0.4."""
    return REQUESTS.render() + ERRORS.render() + DURATION.render()


def reset_metrics() -> None:
    """Drop every recorded series. Tests only — a live server never calls this."""
    for metric in (REQUESTS, ERRORS):
        with metric._lock:  # noqa: SLF001 - the registry owns these objects
            metric._values.clear()
    with DURATION._lock:  # noqa: SLF001
        DURATION._series.clear()


# --------------------------------------------------------------------------- #
# Middleware
# --------------------------------------------------------------------------- #


class MetricsMiddleware:
    """Pure-ASGI wrapper that times every HTTP request and records its outcome.

    Pure ASGI on purpose: ``BaseHTTPMiddleware`` re-frames the response body,
    which corrupts SSE streams (the web UI's live DAG view uses them). This
    wrapper only observes ``http.response.start`` and passes every message on
    unchanged.
    """

    def __init__(self, app: Callable[..., Awaitable[Any]]) -> None:
        self.app = app

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[[], Awaitable[Any]],
        send: Callable[[Any], Awaitable[None]],
    ) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        status_holder = {"code": 500}

        async def _send(message: dict[str, Any]) -> None:
            if message.get("type") == "http.response.start":
                status_holder["code"] = int(message.get("status", 500))
            await send(message)

        try:
            await self.app(scope, receive, _send)
        except Exception:
            # The exception is re-raised untouched: this middleware observes,
            # it does not handle. Counting it separately is what makes an
            # unhandled crash distinguishable from a deliberate 5xx.
            observe_request(scope, status_holder["code"], time.perf_counter() - started, reason="exception")
            raise
        observe_request(scope, status_holder["code"], time.perf_counter() - started)
