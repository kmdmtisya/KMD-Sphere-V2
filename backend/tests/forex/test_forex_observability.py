"""Forex observability and the outage-drill fix (P13-T13.2, T13.3).

- The quote board shows the last prices as **stale** while the feed in this process reports itself
  disconnected, however recent they are (the P13-T13 outage drill found them shown as fresh for up
  to a minute). A process with no feed judges prices by age alone.
- The feed metrics are exposed in Prometheus format, and every metric the alert rules read exists.
"""

import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.sdk.metrics import MeterProvider
from prometheus_client import CollectorRegistry, generate_latest

from app.core.config import Settings
from app.main import create_app
from app.modules.forex.marketdata.gateway import QuoteHub
from app.modules.forex.marketdata.metrics import STATUS_VALUE, ForexMetrics
from app.modules.forex.marketdata.quality import QualityPolicy
from app.modules.forex.marketdata.repository import StoredQuote
from app.modules.forex.marketdata.service import quote_out
from app.modules.forex.marketdata.types import (
    DataType,
    FeedStatus,
    Quality,
    Quote,
    ReceivedQuote,
)
from tests.conftest import make_settings

ROOT = Path(__file__).resolve().parents[3]
ALERTS = ROOT / "infra" / "docker" / "otel" / "forex-alerts.yaml"
NOW = datetime(2026, 10, 14, 12, tzinfo=UTC)
POLICY = QualityPolicy(stale_after=timedelta(seconds=60))


def stored(age: int) -> StoredQuote:
    at = NOW - timedelta(seconds=age)
    return StoredQuote(
        "fake",
        "EUR_USD",
        Decimal("1.1"),
        Decimal("1.1002"),
        Decimal("1.1001"),
        at,
        at,
        "simulated",
        "ok",
        "connected",
    )


def test_a_recent_price_is_stale_during_an_explicit_outage() -> None:
    connected = quote_out("EUR_USD", stored(5), NOW, POLICY, FeedStatus.CONNECTED)
    assert connected.freshness == "fresh"
    outage = quote_out("EUR_USD", stored(5), NOW, POLICY, FeedStatus.DISCONNECTED, outage=True)
    assert outage.freshness == "stale" and outage.quality == "stale"
    assert outage.mid == Decimal("1.1001")  # the last price is still shown, labelled stale
    # Without an explicit outage (no feed in this process), the age alone decides.
    assert (
        quote_out("EUR_USD", stored(5), NOW, POLICY, FeedStatus.DISCONNECTED).freshness == "fresh"
    )
    assert quote_out("EUR_USD", stored(90), NOW, POLICY, FeedStatus.CONNECTED).freshness == "stale"


def _quote(age: int) -> ReceivedQuote:
    at = NOW - timedelta(seconds=age)
    return ReceivedQuote(
        Quote("fake", "EUR_USD", Decimal("1.1"), Decimal("1.1002"), at, DataType.SIMULATED),
        at,
        Quality.OK,
        FeedStatus.CONNECTED,
    )


def render(hub: QuoteHub, *, stored_count: int = 0) -> str:
    registry = CollectorRegistry()
    provider = MeterProvider(metric_readers=[PrometheusMetricReader(registry=registry)])
    metrics = ForexMetrics(provider, hub, clock=lambda: NOW)
    metrics.quotes_stored.add(stored_count)
    return generate_latest(registry).decode()


def value(text: str, name: str, label: str = "") -> float:
    """The sample of metric [name] whose labels contain [label] (scope labels are ignored)."""
    for line in text.splitlines():
        if line.startswith("#"):
            continue
        head, _, number = line.rpartition(" ")
        if head.split("{")[0] == name and label in head:
            return float(number)
    raise AssertionError(f"no sample {name} {label}")


def test_the_metrics_report_status_connections_age_and_counts() -> None:
    hub = QuoteHub()
    hub.publish(_quote(42))
    hub.publish_status("fake", FeedStatus.DISCONNECTED)
    hub.open("someone")
    text = render(hub, stored_count=7)
    assert value(text, "forex_feed_status", 'provider="fake"') == 2
    assert value(text, "forex_stream_connections") == 1
    assert value(text, "forex_last_quote_age_seconds", 'instrument="EUR_USD"') == 42
    assert value(text, "forex_quotes_stored_total") == 7
    assert value(text, "forex_quote_store_failures_total") == 0  # published at zero
    assert value(text, "forex_candles_backfilled_total") == 0
    assert STATUS_VALUE == {
        FeedStatus.CONNECTED: 0,
        FeedStatus.DEGRADED: 1,
        FeedStatus.DISCONNECTED: 2,
    }
    for line in text.splitlines():
        assert "token" not in line.lower() and "user" not in line.lower()


def test_every_metric_the_alert_rules_read_is_exposed() -> None:
    hub = QuoteHub()
    hub.publish(_quote(1))
    hub.publish_status("fake", FeedStatus.CONNECTED)
    exposed = {
        line.split("{")[0].split(" ")[0]
        for line in render(hub).splitlines()
        if line and not line.startswith("#")
    }
    text = ALERTS.read_text(encoding="utf-8")
    alerts = re.findall(r"^\s*- alert: (\w+)$", text, re.M)
    exprs = re.findall(r"^\s*expr: (.+)$", text, re.M)
    assert alerts == [
        "ForexFeedDisconnected",
        "ForexFeedDegraded",
        "ForexQuotesStale",
        "ForexQuoteStoreFailures",
    ]
    assert len(exprs) == len(alerts)
    used = {m for e in exprs for m in re.findall(r"\bforex_[a-z_]+", e)}
    assert used and used <= exposed, used - exposed


async def test_the_app_exposes_the_forex_metrics_on_the_protected_endpoint() -> None:
    settings: Settings = make_settings(forex_enabled=True, metrics_token="metrics-secret")
    app = create_app(settings, readiness_checks={})
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        refused = await client.get("/metrics")
        assert refused.status_code in (401, 403, 404)
        ok = await client.get("/metrics", headers={"Authorization": "Bearer metrics-secret"})
    assert ok.status_code == 200
    assert "forex_quotes_stored_total" in ok.text and "forex_stream_connections" in ok.text


@pytest.mark.parametrize("status", list(FeedStatus))
def test_every_status_has_a_gauge_value(status: FeedStatus) -> None:
    assert status in STATUS_VALUE
