"""Forex feed metrics (P13-T13.3), on the app's meter provider: they appear on the token-protected
`/metrics` endpoint in Prometheus format and are exported over OTLP when it is configured.

- `forex_quotes_stored` (counter): quotes stored by the feed;
- `forex_quote_store_failures` (counter): quotes that could not be stored (the stream goes on);
- `forex_candles_backfilled` (counter): one-minute candles stored by gap backfills;
- `forex_feed_status` (gauge, per provider): 0 connected, 1 degraded, 2 disconnected;
- `forex_stream_connections` (gauge): open WebSocket subscribers;
- `forex_last_quote_age_seconds` (gauge, per pair): age of the newest good quote.
The alert rules that read them are in `infra/docker/otel/forex-alerts.yaml`. No metric carries a
price, a user or a token."""

from collections.abc import Iterable
from datetime import datetime

from opentelemetry.metrics import CallbackOptions, MeterProvider, Observation

from app.modules.forex.marketdata.gateway import QuoteHub
from app.modules.forex.marketdata.monitor import Clock, utc_now
from app.modules.forex.marketdata.types import FeedStatus

STATUS_VALUE = {
    FeedStatus.CONNECTED: 0,
    FeedStatus.DEGRADED: 1,
    FeedStatus.DISCONNECTED: 2,
}


class ForexMetrics:
    def __init__(self, provider: MeterProvider, hub: QuoteHub, clock: Clock = utc_now) -> None:
        self._hub = hub
        self._clock = clock
        meter = provider.get_meter("wealthsphere.forex")
        self.quotes_stored = meter.create_counter(
            "forex_quotes_stored", description="Quotes stored by the forex feed"
        )
        self.store_failures = meter.create_counter(
            "forex_quote_store_failures", description="Quotes the feed could not store"
        )
        self.candles_backfilled = meter.create_counter(
            "forex_candles_backfilled", description="One-minute candles stored by gap backfills"
        )
        # Published at zero from the start, so an alert on increase() works from the first scrape.
        for counter in (self.quotes_stored, self.store_failures, self.candles_backfilled):
            counter.add(0)
        meter.create_observable_gauge(
            "forex_feed_status",
            callbacks=[self._status],
            description="Forex feed status: 0 connected, 1 degraded, 2 disconnected",
        )
        meter.create_observable_gauge(
            "forex_stream_connections",
            callbacks=[self._connections],
            description="Open forex WebSocket subscribers",
        )
        meter.create_observable_gauge(
            "forex_last_quote_age_seconds",
            callbacks=[self._ages],
            unit="s",
            description="Age of the newest good quote of each pair",
        )

    def _status(self, _: CallbackOptions) -> Iterable[Observation]:
        return [
            Observation(STATUS_VALUE[status], {"provider": provider})
            for provider, status in sorted(self._hub.feed_status.items())
        ]

    def _connections(self, _: CallbackOptions) -> Iterable[Observation]:
        return [Observation(self._hub.connections)]

    def _ages(self, _: CallbackOptions) -> Iterable[Observation]:
        now: datetime = self._clock()
        return [
            Observation(
                max((now - q.quote.ts_provider).total_seconds(), 0.0), {"instrument": instrument}
            )
            for instrument, q in sorted(self._hub.last_good.items())
        ]
