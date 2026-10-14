"""The P13 hard rules that apply from P13-T02 (docs/design/forex-reconciliation.md section 3):

1. No order-placement path: no route, WebSocket message or vendor endpoint for orders, trades or
   positions exists in the forex module (paper trading, P13-T10, will live under `/paper/` and
   touch no broker).
4. Prices are never invented or shown as live: the only provider that can be configured is the
   simulated one, and it labels every price `simulated`.
And the switches decided in P13-T01: off by default (DEC-23), refused outside local and test
environments (DEC-20), fixture-only provider (DEC-19)."""

import re
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.main import create_app
from app.modules.forex import api as forex_api
from app.modules.forex import stream_api
from app.modules.forex.analysis import api as analysis_api
from app.modules.forex.backtest import api as backtest_api
from app.modules.forex.calendar import api as calendar_api
from app.modules.forex.forecast import api as forecast_api
from app.modules.forex.marketdata.factory import build_provider
from app.modules.forex.marketdata.types import DataType
from app.modules.forex.paper import api as paper_api
from app.modules.forex.risk import api as risk_api
from app.modules.forex.signals import api as signals_api
from tests.conftest import make_settings

FOREX = Path(__file__).resolve().parents[2] / "app" / "modules" / "forex"
ORDER_WORDS = re.compile(r"(^|[/_-])(orders?|trades?|execut\w*|positions?|brokers?)([/_-]|$)")
VENDOR_ORDER_ENDPOINT = re.compile(r"/v3/accounts/[^\"']*/(orders|trades|positions)")
ORDER_CALL = re.compile(r"\b(place|submit|send|execute|close)_(order|trade|position)s?\b")


def test_no_forex_route_places_orders() -> None:
    app = create_app(make_settings(forex_enabled=True), readiness_checks={})
    documented = [p for p in app.openapi()["paths"] if p.startswith("/api/v1/forex")]
    routers = (
        forex_api.router,
        analysis_api.router,
        backtest_api.router,
        calendar_api.router,
        forecast_api.router,
        paper_api.router,
        risk_api.router,
        signals_api.router,
        stream_api.router,
    )
    declared = [getattr(r, "path", "") for router in routers for r in router.routes]
    forex_paths = sorted({*documented, *declared})
    assert set(documented) <= set(declared)
    assert "/api/v1/forex/stream" in forex_paths and "/api/v1/forex/quotes" in forex_paths
    for path in forex_paths:
        if path.startswith("/api/v1/forex/paper/"):
            continue
        for segment in path.split("/"):
            assert not ORDER_WORDS.search(segment), path


def test_no_forex_source_names_an_order_endpoint_or_call() -> None:
    sources = [p for p in FOREX.rglob("*.py") if "paper" not in p.parts]
    assert sources
    for path in sources:
        body = path.read_text(encoding="utf-8")
        assert not VENDOR_ORDER_ENDPOINT.search(body), path
        assert not ORDER_CALL.search(body), path


def test_the_only_configurable_provider_is_simulated() -> None:
    with pytest.raises(ValidationError):
        make_settings(forex_provider="oanda")


async def test_the_built_provider_labels_every_price_simulated() -> None:
    at = datetime(2026, 10, 14, 10, tzinfo=UTC)
    provider = build_provider(make_settings(), clock=lambda: at)
    quotes = await provider.snapshot(["EUR_USD", "USD_KES", "USD_ZAR"])
    assert len(quotes) == 3
    assert {q.data_type for q in quotes} == {DataType.SIMULATED}


def test_forex_is_off_by_default() -> None:
    settings = make_settings()
    assert settings.forex_enabled is False and settings.forex_feed_enabled is False


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_forex_cannot_be_switched_on_outside_development(environment: str) -> None:
    with pytest.raises(ValidationError, match="DEC-20"):
        make_settings(environment=environment, forex_enabled=True)


@pytest.mark.parametrize("environment", ["local", "test"])
def test_forex_can_be_switched_on_in_development(environment: str) -> None:
    assert make_settings(environment=environment, forex_enabled=True).forex_enabled


def test_heartbeat_windows_must_be_ordered() -> None:
    with pytest.raises(ValidationError):
        make_settings(forex_heartbeat_degraded_seconds=30, forex_heartbeat_disconnected_seconds=10)
