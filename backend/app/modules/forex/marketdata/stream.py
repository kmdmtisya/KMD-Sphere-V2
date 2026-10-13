"""The streaming client (P13-T02.4, design section 4.3): one upstream connection per provider for
the configured instruments, kept alive with heartbeats and reconnected with backoff.

- **Heartbeat:** every message (price or heartbeat) restarts the window. Silence for
  `degraded_after` reports `degraded`; silence for `disconnected_after` drops the connection.
- **Reconnect:** exponential backoff with jitter, reset once a connection delivers a message.
- **Dedupe:** a quote whose provider time is not after the last one for its pair is dropped (a
  replay after reconnecting, or a duplicate).
- **Gaps:** a jump in a pair's provider time longer than `gap_after` is reported to the sink, which
  backfills candles from the provider. Nothing is interpolated.
- **Quality:** each quote is assessed when it arrives (`quality.assess`) and stored with the
  feed's status at receipt.

Time, sleeping, waiting and randomness are injected, so tests drive heartbeat loss and
reconnects with a fake clock and never wait."""

import asyncio
import contextlib
import logging
import random
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Protocol

from app.modules.forex.marketdata.monitor import Clock, FeedMonitor, utc_now
from app.modules.forex.marketdata.provider import ForexProvider, StreamEvent
from app.modules.forex.marketdata.quality import QualityPolicy, assess
from app.modules.forex.marketdata.types import FeedStatus, Heartbeat, Quality, ReceivedQuote
from app.modules.market_data.providers.errors import ProviderAuthError, ProviderError
from app.modules.market_data.providers.resilience import Sleep

logger = logging.getLogger(__name__)

# Waits up to `seconds` for `task`; True when it finished. Never cancels it.
Waiter = Callable[["asyncio.Future[Any]", float], Awaitable[bool]]


async def wait_for_task(task: "asyncio.Future[Any]", seconds: float) -> bool:
    done, _ = await asyncio.wait({task}, timeout=seconds)
    return bool(done)


class QuoteSink(Protocol):
    async def on_quote(self, quote: ReceivedQuote) -> None: ...

    async def on_status(self, provider: str, status: FeedStatus) -> None: ...

    async def on_gap(
        self, provider: str, instrument: str, since: datetime, until: datetime
    ) -> None: ...


@dataclass(frozen=True)
class Backoff:
    initial: timedelta = timedelta(seconds=1)
    factor: float = 2.0
    maximum: timedelta = timedelta(seconds=60)
    jitter: float = 0.2  # each delay is scaled by a random factor in [1 - jitter, 1 + jitter]

    def __post_init__(self) -> None:
        if self.initial <= timedelta(0) or self.factor < 1 or not 0 <= self.jitter < 1:
            raise ValueError("invalid backoff")

    def delay(self, attempt: int, rand: float) -> float:
        """Seconds before reconnect number `attempt` (from 1); `rand` is uniform in [0, 1)."""
        base = min(
            self.initial.total_seconds() * self.factor ** (attempt - 1),
            self.maximum.total_seconds(),
        )
        return base * (1 - self.jitter + 2 * self.jitter * rand)


class HeartbeatLost(Exception):
    pass


class StreamClient:
    def __init__(
        self,
        provider: ForexProvider,
        instruments: Sequence[str],
        sink: QuoteSink,
        monitor: FeedMonitor,
        quality: QualityPolicy | None = None,
        backoff: Backoff | None = None,
        gap_after: timedelta = timedelta(minutes=2),
        clock: Clock = utc_now,
        sleep: Sleep = asyncio.sleep,
        waiter: Waiter = wait_for_task,
        rand: Callable[[], float] = random.random,
    ) -> None:
        self._provider = provider
        self._instruments = list(instruments)
        self._sink = sink
        self.monitor = monitor
        self._quality = quality or QualityPolicy()
        self._backoff = backoff or Backoff()
        self._gap_after = gap_after
        self._clock = clock
        self._sleep = sleep
        self._wait = waiter
        self._rand = rand
        self._last_ts: dict[str, datetime] = {}
        self._last_mid: dict[str, Decimal] = {}
        self._reported: FeedStatus | None = None
        self.reconnects = 0
        self.duplicates = 0
        self.delays: list[float] = []

    async def _report(self) -> None:
        status = self.monitor.status
        if status != self._reported:
            self._reported = status
            await self._sink.on_status(self._provider.name, status)

    async def _next(self, iterator: AsyncIterator[StreamEvent]) -> StreamEvent:
        task: asyncio.Future[StreamEvent] = asyncio.ensure_future(anext(iterator))
        policy = self.monitor.policy
        if not await self._wait(task, policy.degraded_after.total_seconds()):
            await self._report()  # degraded
            remaining = (policy.disconnected_after - policy.degraded_after).total_seconds()
            if not await self._wait(task, remaining):
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)  # let the read finish
                raise HeartbeatLost
        return task.result()

    async def _handle(self, event: StreamEvent) -> None:
        self.monitor.on_message()
        await self._report()
        if isinstance(event, Heartbeat):
            return
        last = self._last_ts.get(event.instrument)
        if last is not None and event.ts_provider <= last:
            self.duplicates += 1
            return
        if last is not None and event.ts_provider - last > self._gap_after:
            await self._sink.on_gap(self._provider.name, event.instrument, last, event.ts_provider)
        self._last_ts[event.instrument] = event.ts_provider
        now = self._clock()
        quality = assess(event, self._last_mid.get(event.instrument), now, self._quality)
        if quality is not Quality.SUSPECT:
            self._last_mid[event.instrument] = event.mid
        await self._sink.on_quote(ReceivedQuote(event, now, quality, self.monitor.status))

    async def _connection(self) -> bool:
        """One connection, until it fails, ends or goes silent. True if it delivered anything.
        The feed counts as connected from its first message, so an outage never flaps."""
        delivered = False
        iterator = aiter(self._provider.stream(self._instruments))
        try:
            while True:
                event = await self._next(iterator)
                if not delivered:
                    delivered = True
                    self.monitor.on_connect()
                await self._handle(event)
        except StopAsyncIteration:
            logger.info("forex stream ended", extra={"provider": self._provider.name})
        except HeartbeatLost:
            logger.warning("forex heartbeat lost", extra={"provider": self._provider.name})
        except ProviderError as error:
            logger.warning(
                "forex stream failed",
                extra={"provider": self._provider.name, "error": type(error).__name__},
            )
            if isinstance(error, ProviderAuthError):
                raise
        finally:
            close = getattr(iterator, "aclose", None)
            if close is not None:
                with contextlib.suppress(RuntimeError, ProviderError):
                    await close()
            self.monitor.on_disconnect()
            await self._report()
        return delivered

    async def run(self, stop: asyncio.Event | None = None, connections: int | None = None) -> None:
        """Connects, and reconnects with backoff, until `stop` is set (or after `connections`
        connections, for tests). Refused credentials end the run: retrying cannot help."""
        attempt = 0
        made = 0
        while stop is None or not stop.is_set():
            made += 1
            try:
                delivered = await self._connection()
            except ProviderAuthError:
                return
            if connections is not None and made >= connections:
                return
            attempt = 1 if delivered else attempt + 1
            self.reconnects += 1
            delay = self._backoff.delay(attempt, self._rand())
            self.delays.append(delay)
            await self._sleep(delay)
