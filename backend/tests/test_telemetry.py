import json
import logging
from collections.abc import Callable

import httpx
import pytest
from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.core.logging import JsonFormatter
from app.main import create_app
from tests.conftest import make_settings


def _app(exporter: InMemorySpanExporter, **settings: object) -> FastAPI:
    app = create_app(
        make_settings(**settings),
        readiness_checks={},
        span_processors=[SimpleSpanProcessor(exporter)],
    )

    @app.get("/_probe/{item}")
    async def probe(item: str) -> dict[str, str]:
        logging.getLogger("probe").warning("inside request")
        return {"item": item}

    return app


async def test_request_produces_a_span_with_route_and_service_name(
    client_for: Callable[[FastAPI], httpx.AsyncClient],
) -> None:
    exporter = InMemorySpanExporter()
    async with client_for(_app(exporter)) as c:
        response = await c.get("/_probe/abc")
    assert response.status_code == 200
    spans = [s for s in exporter.get_finished_spans() if s.attributes]
    server = next(s for s in spans if s.attributes and s.attributes.get("http.route"))
    assert server.attributes is not None
    assert server.attributes["http.route"] == "/_probe/{item}"
    assert server.resource.attributes["service.name"] == "wealthsphere-api"
    assert server.resource.attributes["deployment.environment.name"] == "test"


async def test_health_and_metrics_are_not_traced(
    client_for: Callable[[FastAPI], httpx.AsyncClient],
) -> None:
    exporter = InMemorySpanExporter()
    async with client_for(_app(exporter, metrics_token="t")) as c:
        await c.get("/health/live")
        await c.get("/metrics", headers={"Authorization": "Bearer t"})
    assert exporter.get_finished_spans() == ()


async def test_log_records_carry_trace_ids_matching_the_span(
    client_for: Callable[[FastAPI], httpx.AsyncClient], caplog: pytest.LogCaptureFixture
) -> None:
    exporter = InMemorySpanExporter()
    formatted: list[dict[str, object]] = []

    class Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            formatted.append(json.loads(JsonFormatter().format(record)))

    handler = Capture()
    probe_logger = logging.getLogger("probe")
    probe_logger.addHandler(handler)
    try:
        async with client_for(_app(exporter)) as c:
            await c.get("/_probe/x")
    finally:
        probe_logger.removeHandler(handler)

    server = next(
        s for s in exporter.get_finished_spans() if s.attributes and s.attributes.get("http.route")
    )
    line = next(rec for rec in formatted if rec["message"] == "inside request")
    assert line["trace_id"] == format(server.context.trace_id, "032x")
    assert "span_id" in line


def test_no_trace_ids_outside_a_span() -> None:
    record = logging.LogRecord("x", logging.INFO, __file__, 1, "plain", (), None)
    payload = json.loads(JsonFormatter().format(record))
    assert "trace_id" not in payload
    assert not trace.get_current_span().get_span_context().is_valid


async def test_metrics_endpoint_is_disabled_without_a_token(
    client_for: Callable[[FastAPI], httpx.AsyncClient],
) -> None:
    async with client_for(_app(InMemorySpanExporter())) as c:
        response = await c.get("/metrics")
    assert response.status_code == 404


@pytest.mark.parametrize("header", [None, "Bearer wrong", "Basic secret-token", "secret-token"])
async def test_metrics_endpoint_rejects_missing_or_wrong_credentials(
    client_for: Callable[[FastAPI], httpx.AsyncClient], header: str | None
) -> None:
    headers = {"Authorization": header} if header else {}
    async with client_for(_app(InMemorySpanExporter(), metrics_token="secret-token")) as c:
        response = await c.get("/metrics", headers=headers)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert "secret-token" not in response.text


async def test_metrics_endpoint_serves_prometheus_text_with_request_metrics(
    client_for: Callable[[FastAPI], httpx.AsyncClient],
) -> None:
    async with client_for(_app(InMemorySpanExporter(), metrics_token="secret-token")) as c:
        await c.get("/_probe/one")
        await c.get("/_probe/two")
        response = await c.get("/metrics", headers={"Authorization": "Bearer secret-token"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    body = response.text
    assert "target_info" in body
    assert 'service_name="wealthsphere-api"' in body
    assert "http_server" in body  # request duration / active requests series
    assert "/_probe/{item}" in body


async def test_metrics_are_isolated_between_app_instances(
    client_for: Callable[[FastAPI], httpx.AsyncClient],
) -> None:
    a = _app(InMemorySpanExporter(), metrics_token="t")
    b = _app(InMemorySpanExporter(), metrics_token="t")
    async with client_for(a) as ca, client_for(b) as cb:
        await ca.get("/_probe/only-a")
        text_b = (await cb.get("/metrics", headers={"Authorization": "Bearer t"})).text
    assert "only-a" not in text_b


async def test_metrics_endpoint_is_not_in_the_openapi_contract() -> None:
    app = create_app(make_settings(), readiness_checks={})
    assert "/metrics" not in app.openapi()["paths"]
