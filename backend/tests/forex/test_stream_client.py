"""The streaming client on an injected clock (P13-T02.4, T02.5): heartbeat loss reports degraded,
then disconnected, then reconnects with backoff and jitter; duplicates are dropped; gaps are
reported for backfill; outages never produce a price; refused credentials stop the client. A
fake waiter advances the clock instead of waiting, so nothing here sleeps."""

import asyncio
import contextlib
from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from app.modules.forex.marketdata.fake import Drop, FakeForexProvider, ScriptItem, Silence
from app.modules.forex.marketdata.monitor import FeedMonitor, HeartbeatPolicy
from app.modules.forex.marketdata.provider import StreamEvent
from app.modules.forex.marketdata.stream import Backoff, StreamClient
from app.modules.forex.marketdata.types import (
    DataType,
    FeedStatus,
    Heartbeat,
    Quality,
    Quote,
    ReceivedQuote,
)
from app.modules.market_data.providers.errors import ProviderAuthError
from tests.forex.test_marketdata_core import Clock

T0 = datetime(2026, 10, 14, 10, 0, tzinfo=UTC)
POLICY = HeartbeatPolicy(timedelta(seconds=10), timedelta(seconds=30))
S = FeedStatus


def q(seconds: float, bid: str = "1.08500", ask: str = "1.08512", pair: str = "EUR_USD") -> Quote:
    return Quote(
        "fake",
        pair,
        Decimal(bid),
        Decimal(ask),
        T0 + timedelta(seconds=seconds),
        DataType.SIMULATED,
    )


class Sink:
    def __init__(self) -> None:
        self.quotes: list[ReceivedQuote] = []
        self.statuses: list[FeedStatus] = []
        self.gaps: list[tuple[str, datetime, datetime]] = []

    async def on_quote(self, quote: ReceivedQuote) -> None:
        self.quotes.append(quote)

    async def on_status(self, provider: str, status: FeedStatus) -> None:
        self.statuses.append(status)

    async def on_gap(
        self, provider: str, instrument: str, since: datetime, until: datetime
    ) -> None:
        self.gaps.append((instrument, since, until))


class FakeWaiter:
    """Lets ready work finish; if the read is still pending, moves the clock instead of waiting."""

    def __init__(self, clock: Clock) -> None:
        self.clock = clock
        self.waited: list[float] = []

    async def __call__(self, task: "asyncio.Future[Any]", seconds: float) -> bool:
        for _ in range(50):
            if task.done():
                return True
            await asyncio.sleep(0)
        self.clock.advance(seconds)
        self.waited.append(seconds)
        return task.done()


def client(
    provider: Any, clock: Clock, sink: Sink, slept: list[float] | None = None
) -> StreamClient:
    async def sleep(seconds: float) -> None:
        if slept is not None:
            slept.append(seconds)
        clock.advance(seconds)

    return StreamClient(
        provider,
        ["EUR_USD"],
        sink,
        FeedMonitor(POLICY, clock),
        backoff=Backoff(timedelta(seconds=1), 2.0, timedelta(seconds=60), jitter=0.2),
        clock=clock,
        sleep=sleep,
        waiter=FakeWaiter(clock),
        rand=lambda: 0.5,  # no jitter in the expected delays
    )


def scripted(clock: Clock, *scripts: list[ScriptItem]) -> FakeForexProvider:
    return FakeForexProvider(clock=clock, scripts=list(scripts))


async def test_heartbeat_loss_degrades_then_disconnects_then_reconnects() -> None:
    clock, sink = Clock(T0), Sink()
    provider = scripted(clock, [Heartbeat("fake", T0), q(0), Silence()], [q(45)])
    c = client(provider, clock, sink)
    await c.run(connections=2)
    assert sink.statuses == [S.CONNECTED, S.DEGRADED, S.DISCONNECTED, S.CONNECTED, S.DISCONNECTED]
    assert provider.connections == 2 and c.reconnects == 1
    assert c.delays == [1.0]  # the first connection delivered, so the backoff starts over
    assert c.monitor.status is S.DISCONNECTED
    assert [r.quote.ts_provider for r in sink.quotes] == [T0, T0 + timedelta(seconds=45)]


async def test_a_heartbeat_inside_the_window_keeps_the_feed_connected() -> None:
    clock, sink = Clock(T0), Sink()

    class Steady:
        name = "fake"
        connections = 0

        async def stream(self, instruments: Sequence[str]) -> AsyncIterator[StreamEvent]:
            for _ in range(3):
                clock.advance(9)  # just inside the 10 s degraded window
                yield Heartbeat("fake", clock())

    await client(Steady(), clock, sink).run(connections=1)
    assert sink.statuses == [S.CONNECTED, S.DISCONNECTED]  # never degraded; closed at the end


async def test_received_quotes_carry_receipt_time_quality_and_feed_status() -> None:
    clock, sink = Clock(T0 + timedelta(seconds=2)), Sink()
    await client(scripted(clock, [q(0)]), clock, sink).run(connections=1)
    [received] = sink.quotes
    assert received.ts_received == T0 + timedelta(seconds=2)
    assert received.quality is Quality.OK
    assert received.feed_status is S.CONNECTED
    assert received.quote.mid == Decimal("1.08506")


async def test_duplicates_and_replays_are_dropped() -> None:
    clock, sink = Clock(T0), Sink()
    c = client(scripted(clock, [q(0), q(0), q(-1), q(1)]), clock, sink)
    await c.run(connections=1)
    assert [r.quote.ts_provider for r in sink.quotes] == [T0, T0 + timedelta(seconds=1)]
    assert c.duplicates == 2


async def test_a_replay_after_reconnecting_is_dropped_and_a_gap_is_reported() -> None:
    clock, sink = Clock(T0), Sink()
    c = client(scripted(clock, [q(0), Drop()], [q(0), q(600)]), clock, sink)
    await c.run(connections=2)
    assert [r.quote.ts_provider for r in sink.quotes] == [T0, T0 + timedelta(seconds=600)]
    assert sink.gaps == [("EUR_USD", T0, T0 + timedelta(seconds=600))]


async def test_suspect_quotes_are_passed_on_marked_and_do_not_move_the_reference() -> None:
    clock, sink = Clock(T0), Sink()
    script: list[ScriptItem] = [
        q(0),
        q(1, bid="1.08600", ask="1.08500"),  # crossed
        q(2, bid="1.30000", ask="1.30010"),  # +20%: out of band
        q(3, bid="1.08700", ask="1.08712"),  # compared with the last good mid, fine
    ]
    await client(scripted(clock, script), clock, sink).run(connections=1)
    assert [r.quality for r in sink.quotes] == [
        Quality.OK,
        Quality.SUSPECT,
        Quality.SUSPECT,
        Quality.OK,
    ]


async def test_an_outage_never_reports_connected_and_backs_off_exponentially() -> None:
    clock, sink, slept = Clock(T0), Sink(), list[float]()
    provider = FakeForexProvider(clock=clock)
    provider.down = True
    c = client(provider, clock, sink, slept)
    await c.run(connections=4)
    assert sink.quotes == []  # no price is invented while the provider is down
    assert S.CONNECTED not in sink.statuses
    assert slept == [1.0, 2.0, 4.0]  # doubling after each failure in a row


async def test_backoff_restarts_after_a_connection_that_delivered() -> None:
    clock, sink = Clock(T0), Sink()
    c = client(scripted(clock, [q(0), Drop()], [Drop()], [Drop()], [q(9)]), clock, sink)
    await c.run(connections=4)
    assert c.delays == [1.0, 2.0, 4.0]


async def test_jitter_spreads_reconnects() -> None:
    clock, sink = Clock(T0), Sink()
    c = client(scripted(clock, [Drop()], [Drop()]), clock, sink)
    c._rand = lambda: 0.0  # the low end of the jitter band
    await c.run(connections=2)
    assert c.delays == [0.8]  # the first delay, 1 s, scaled by 0.8


async def test_refused_credentials_stop_the_client() -> None:
    clock, sink, slept = Clock(T0), Sink(), list[float]()

    class Refused:
        name = "fake"

        async def stream(self, instruments: Sequence[str]) -> AsyncIterator[StreamEvent]:
            raise ProviderAuthError("credentials refused")
            yield  # pragma: no cover - makes this an async generator

    await client(Refused(), clock, sink, slept).run()
    assert slept == [] and sink.quotes == []


async def test_stop_ends_the_generated_simulated_stream() -> None:
    clock, sink = Clock(T0), Sink()
    stop = asyncio.Event()

    async def tick(seconds: float) -> None:
        clock.advance(seconds)
        if len(sink.quotes) >= 6:
            stop.set()
            raise asyncio.CancelledError  # what cancelling the feed task does

    provider = FakeForexProvider(clock=clock, sleep=tick)
    c = StreamClient(
        provider,
        ["EUR_USD", "USD_KES"],
        sink,
        FeedMonitor(POLICY, clock),
        clock=clock,
        waiter=FakeWaiter(clock),
    )
    with contextlib.suppress(asyncio.CancelledError):
        await c.run(stop)
    assert len(sink.quotes) >= 6
    assert {r.quote.data_type for r in sink.quotes} == {DataType.SIMULATED}
    assert {r.quote.instrument for r in sink.quotes} == {"EUR_USD", "USD_KES"}
