"""The feed: the streaming client's sink (P13-T02.4, T02.5). Each received quote is stored and
published to the gateway; status changes go to the gateway; a gap triggers a candle backfill from
the provider. A storage or backfill failure is logged and the feed carries on: it never stops
the stream, and it never fills a gap with anything but the provider's own candles."""

import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.modules.forex.instruments.registry import load_registry, sync
from app.modules.forex.marketdata.factory import build_provider, heartbeat_policy, quality_policy
from app.modules.forex.marketdata.gateway import QuoteHub
from app.modules.forex.marketdata.metrics import ForexMetrics
from app.modules.forex.marketdata.monitor import Clock, FeedMonitor, utc_now
from app.modules.forex.marketdata.partitions import PARTITIONED, ensure_months
from app.modules.forex.marketdata.provider import ForexProvider
from app.modules.forex.marketdata.repository import store_candles, store_quotes
from app.modules.forex.marketdata.stream import StreamClient
from app.modules.forex.marketdata.types import FeedStatus, ReceivedQuote, Timeframe
from app.modules.forex.risk.specs import sync as sync_specs

logger = logging.getLogger(__name__)
MONTHS_AHEAD = 3  # partitions for this month and the next two
MAX_BACKFILL = timedelta(days=1)


class ForexFeed:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        hub: QuoteHub,
        provider: ForexProvider,
        clock: Clock = utc_now,
        max_backfill: timedelta = MAX_BACKFILL,
        metrics: ForexMetrics | None = None,
    ) -> None:
        self._metrics = metrics
        self._sessions = sessions
        self._hub = hub
        self._provider = provider
        self._clock = clock
        self._max_backfill = max_backfill
        self.stored = 0
        self.backfilled = 0
        self.failures = 0

    async def on_quote(self, quote: ReceivedQuote) -> None:
        try:
            async with self._sessions() as session:
                added = await store_quotes(session, [quote])
            self.stored += added
            if self._metrics is not None:
                self._metrics.quotes_stored.add(added)
        except Exception as error:  # storage trouble must not stop the stream
            self.failures += 1
            if self._metrics is not None:
                self._metrics.store_failures.add(1)
            logger.warning("forex quote not stored", extra={"error": type(error).__name__})
        self._hub.publish(quote)

    async def on_status(self, provider: str, status: FeedStatus) -> None:
        logger.info("forex feed status", extra={"provider": provider, "status": status.value})
        self._hub.publish_status(provider, status)

    async def on_gap(
        self, provider: str, instrument: str, since: datetime, until: datetime
    ) -> None:
        start = max(since, until - self._max_backfill)
        try:
            candles = await self._provider.candles(instrument, Timeframe.M1, start, until)
            async with self._sessions() as session:
                added = await store_candles(session, candles, self._clock())
            self.backfilled += added
            if self._metrics is not None:
                self._metrics.candles_backfilled.add(added)
        except Exception as error:  # ProviderError or storage: logged, the stream goes on
            self.failures += 1
            logger.warning(
                "forex backfill failed",
                extra={"instrument": instrument, "error": type(error).__name__},
            )


async def prepare(
    sessions: async_sessionmaker[AsyncSession], settings: Settings, today: datetime
) -> list[str]:
    """Registry and contract specifications in the database, and partitions ahead. Returns the
    active pairs."""
    async with sessions() as session:
        registry = load_registry()
        await sync(session, registry, settings.forex_universe)
        await sync_specs(session)
        for table in PARTITIONED:
            await ensure_months(session, table, today.date(), MONTHS_AHEAD)
    return [s.code for s in registry.active(settings.forex_universe)]


async def run_feed(
    settings: Settings,
    sessions: async_sessionmaker[AsyncSession],
    hub: QuoteHub,
    stop: asyncio.Event,
    provider: ForexProvider | None = None,
    clock: Clock = utc_now,
    metrics: ForexMetrics | None = None,
) -> None:
    """Runs the feed until `stop` is set (started by the app when `forex_feed_enabled`)."""
    provider = provider or build_provider(settings, clock)
    instruments = await prepare(sessions, settings, clock())
    client = StreamClient(
        provider,
        instruments,
        ForexFeed(sessions, hub, provider, clock, metrics=metrics),
        FeedMonitor(heartbeat_policy(settings), clock),
        quality_policy(settings),
        clock=clock,
    )
    await client.run(stop)
