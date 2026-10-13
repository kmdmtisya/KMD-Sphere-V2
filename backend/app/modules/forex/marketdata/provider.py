"""Forex provider interfaces (P13-T02.1, design section 4.1). They sit beside the P08
`MarketDataProvider` and raise the same errors (`market_data.providers.errors`), never a vendor
exception. A provider never returns a guessed or filled-in price: when it has nothing, it raises
or leaves the instrument out."""

import asyncio
from collections.abc import AsyncIterator, Sequence
from datetime import datetime
from typing import Protocol, runtime_checkable

from app.modules.forex.marketdata.types import Candle, Heartbeat, PriceBasis, Quote, Timeframe
from app.modules.market_data.providers.resilience import (
    CircuitBreaker,
    RetryPolicy,
    Sleep,
    call_guarded,
)

StreamEvent = Quote | Heartbeat


@runtime_checkable
class ForexProvider(Protocol):
    @property
    def name(self) -> str:
        """Stable identifier stored with every value (for example `fake`)."""
        ...

    async def snapshot(self, instruments: Sequence[str]) -> list[Quote]:
        """The latest quote of each instrument the provider has one for. An instrument it has
        nothing for is absent from the list."""
        ...

    def stream(self, instruments: Sequence[str]) -> AsyncIterator[StreamEvent]:
        """One connection: quotes and heartbeats until it fails (`ProviderUnavailable`) or ends.
        Reconnecting is the caller's job (`stream.StreamClient`)."""
        ...

    async def candles(
        self,
        instrument: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
        basis: PriceBasis = PriceBasis.MID,
    ) -> list[Candle]:
        """Complete and forming candles starting in [start, end), oldest first. Periods without
        trades are absent."""
        ...


class ResilientForexProvider:
    """Snapshot and candle calls under the P08 retry policy and circuit breaker (reused, not
    copied). Streams are not retried here: the streaming client reconnects with backoff."""

    def __init__(
        self,
        inner: ForexProvider,
        retry: RetryPolicy | None = None,
        breaker: CircuitBreaker | None = None,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self._inner = inner
        self._retry = retry or RetryPolicy()
        self.breaker = breaker or CircuitBreaker()
        self._sleep = sleep

    @property
    def name(self) -> str:
        return self._inner.name

    async def snapshot(self, instruments: Sequence[str]) -> list[Quote]:
        return await call_guarded(
            lambda: self._inner.snapshot(instruments), self._retry, self.breaker, self._sleep
        )

    def stream(self, instruments: Sequence[str]) -> AsyncIterator[StreamEvent]:
        return self._inner.stream(instruments)

    async def candles(
        self,
        instrument: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
        basis: PriceBasis = PriceBasis.MID,
    ) -> list[Candle]:
        return await call_guarded(
            lambda: self._inner.candles(instrument, timeframe, start, end, basis),
            self._retry,
            self.breaker,
            self._sleep,
        )
