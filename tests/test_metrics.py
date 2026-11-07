"""Tests for the Prometheus scrape surface (CHIMERA-V2-OPS-001).

The point of these tests is not that a route exists — it is that the registry
records something and stops recording at the right boundary. A metrics endpoint
that answers 200 with empty families is indistinguishable from no endpoint at
all on a dashboard, and one that counts its own scrapes reports on monitoring
traffic instead of on user traffic.
"""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from chimera.api.server import create_app  # noqa: E402
from chimera.engine import Engine  # noqa: E402
from chimera.metrics import classify_error, reset_metrics  # noqa: E402
from tests.conftest import FakeGateway  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_registry():  # type: ignore[no-untyped-def]
    """Every test starts and ends from an empty registry (module-level state)."""
    reset_metrics()
    yield
    reset_metrics()


@pytest.fixture
def client(config):  # type: ignore[no-untyped-def]
    app = create_app(config=config, engine=Engine(config, FakeGateway(lambda *a, **k: None)))
    return TestClient(app)


def test_metrics_endpoint_serves_prometheus_text(client) -> None:  # type: ignore[no-untyped-def]
    response = client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    body = response.text
    for family in (
        "chimera_requests_total",
        "chimera_request_errors_total",
        "chimera_request_duration_seconds",
    ):
        assert f"# TYPE {family}" in body


def test_served_requests_are_counted_by_route_and_class(client) -> None:  # type: ignore[no-untyped-def]
    assert client.get("/v1/formations").status_code == 200
    body = client.get("/metrics").text
    assert 'chimera_requests_total{method="GET",route="/v1/formations",status="2xx"} 1' in body
    # The histogram observed the same request: one count, and a +Inf bucket.
    assert 'chimera_request_duration_seconds_count{method="GET",route="/v1/formations"} 1' in body
    assert 'route="/v1/formations",le="+Inf"}' in body


def test_unmatched_requests_are_bounded_and_counted_as_client_errors(client) -> None:  # type: ignore[no-untyped-def]
    assert client.get("/v1/definitely-not-a-route").status_code == 404
    body = client.get("/metrics").text
    assert 'chimera_requests_total{method="GET",route="<unmatched>",status="4xx"} 1' in body
    assert 'chimera_request_errors_total{method="GET",route="<unmatched>",reason="client_error"} 1' in body


def test_the_scrape_endpoint_does_not_count_itself(client) -> None:  # type: ignore[no-untyped-def]
    for _ in range(3):
        client.get("/metrics")
    body = client.get("/metrics").text
    assert 'route="/metrics"' not in body


def test_error_classification_is_by_cause() -> None:
    assert classify_error(200) is None
    assert classify_error(302) is None
    assert classify_error(404) == "client_error"
    assert classify_error(503) == "server_error"
    # An unhandled exception outranks the status: it is a crash, not a 5xx.
    assert classify_error(500, reason="exception") == "exception"
