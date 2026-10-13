"""The simulated forex provider (P13-T02.6, DEC-19). The only provider wired to the app.

Every value it produces is labelled `simulated`, end to end: it is a development feed, not a
market. Prices are deterministic: a function of the pair and the second (a daily triangle wave
around a fixed reference level plus hashed noise), computed in Decimal, so the same clock always
gives the same quote and tests can predict them.

The simulated market is closed from Friday 21:00 to Sunday 21:00 UTC (a simplification; the real
session calendar is P13-T03). While closed there are heartbeats and no prices: the latest quote
is the one from the close, with its true time, and candles are absent.

For tests, `scripts` replaces the generated stream with a fixed sequence per connection, and
`down` makes every call fail as an outage would."""

import asyncio
import hashlib
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.modules.forex.instruments.registry import InstrumentSpec, Registry, load_registry
from app.modules.forex.marketdata.monitor import Clock, utc_now
from app.modules.forex.marketdata.provider import StreamEvent
from app.modules.forex.marketdata.types import (
    Candle,
    DataType,
    Heartbeat,
    PriceBasis,
    Quote,
    Timeframe,
)
from app.modules.market_data.providers.errors import (
    ProviderUnavailable,
    SymbolNotFound,
    UnsupportedKind,
)
from app.modules.market_data.providers.resilience import Sleep

NAME = "fake"
# Synthetic reference levels. Not market data: the simulated price wanders around these.
REFERENCE: dict[str, Decimal] = {
    "EUR_USD": Decimal("1.08500"),
    "GBP_USD": Decimal("1.27000"),
    "USD_JPY": Decimal("149.500"),
    "USD_CHF": Decimal("0.88000"),
    "AUD_USD": Decimal("0.66000"),
    "USD_CAD": Decimal("1.36000"),
    "NZD_USD": Decimal("0.60000"),
    "EUR_GBP": Decimal("0.85500"),
    "EUR_JPY": Decimal("162.000"),
    "GBP_JPY": Decimal("190.000"),
    "USD_ZAR": Decimal("18.20000"),
    "USD_KES": Decimal("129.000"),
}
SPREAD_PIPS = {"major": Decimal("1.2"), "minor": Decimal("2.0"), "exotic": Decimal("40")}
DAY_SWING = Decimal("0.002")  # the triangle wave moves the mid up to 0.2% from the reference
NOISE = Decimal("0.0002")
SAMPLES_PER_MINUTE = 4  # a 1m candle is built from the prices at :00, :15, :30 and :45
STEP = {
    Timeframe.M1: timedelta(minutes=1),
    Timeframe.M5: timedelta(minutes=5),
    Timeframe.M15: timedelta(minutes=15),
    Timeframe.M30: timedelta(minutes=30),
    Timeframe.H1: timedelta(hours=1),
    Timeframe.H4: timedelta(hours=4),
    Timeframe.D1: timedelta(days=1),
}
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


@dataclass(frozen=True)
class Silence:
    """Scripted: the connection stays open and sends nothing (a lost heartbeat)."""


@dataclass(frozen=True)
class Drop:
    """Scripted: the connection fails."""


ScriptItem = StreamEvent | Silence | Drop


def market_open(t: datetime) -> bool:
    t = t.astimezone(UTC)
    weekday = t.weekday()  # Monday 0
    if weekday == 5:
        return False
    if weekday == 4 and t.hour >= 21:
        return False
    return not (weekday == 6 and t.hour < 21)


def last_open_second(t: datetime) -> datetime:
    """`t` itself while open; otherwise the last second before Friday's 21:00 close."""
    t = t.astimezone(UTC).replace(microsecond=0)
    if market_open(t):
        return t
    days_back = (t.weekday() - 4) % 7
    close = (t - timedelta(days=days_back)).replace(hour=21, minute=0, second=0)
    if close > t:
        close -= timedelta(days=7)
    return close - timedelta(seconds=1)


def _floor(t: datetime, step: timedelta) -> datetime:
    return EPOCH + ((t - EPOCH) // step) * step


class FakeForexProvider:
    def __init__(
        self,
        registry: Registry | None = None,
        clock: Clock = utc_now,
        sleep: Sleep = asyncio.sleep,
        tick: timedelta = timedelta(seconds=1),
        heartbeat: timedelta = timedelta(seconds=5),
        scripts: list[list[ScriptItem]] | None = None,
    ) -> None:
        self._registry = registry or load_registry()
        self._clock = clock
        self._sleep = sleep
        self._tick = tick
        self._heartbeat = heartbeat
        self._scripts = list(scripts) if scripts is not None else None
        self.down = False
        self.connections = 0

    @property
    def name(self) -> str:
        return NAME

    def _spec(self, instrument: str) -> InstrumentSpec:
        spec = self._registry.by_code.get(instrument)
        if spec is None or instrument not in REFERENCE:
            raise SymbolNotFound(instrument)
        return spec

    def _check_up(self) -> None:
        if self.down:
            raise ProviderUnavailable("simulated outage")

    # ---------------------------------------------------------------------------- prices
    def mid_at(self, instrument: str, t: datetime) -> Decimal:
        spec = self._spec(instrument)
        second = int((t.astimezone(UTC) - EPOCH).total_seconds())
        position = second % 86_400
        triangle = Decimal(abs(position - 43_200) - 21_600) / Decimal(21_600)  # -1 .. 1
        digest = hashlib.sha256(f"{instrument}|{second}".encode()).digest()
        noise = Decimal(int.from_bytes(digest[:4], "big") % 2001 - 1000) / Decimal(1000)
        mid = REFERENCE[instrument] * (1 + DAY_SWING * triangle + NOISE * noise)
        return mid.quantize(Decimal(1).scaleb(-spec.display_precision))

    def quote_at(self, instrument: str, t: datetime) -> Quote:
        spec = self._spec(instrument)
        places = Decimal(1).scaleb(-spec.display_precision)
        spread = (SPREAD_PIPS[spec.liquidity_tier] * Decimal(1).scaleb(spec.pip_location)).quantize(
            places
        )
        bid = (self.mid_at(instrument, t) - spread / 2).quantize(places)
        return Quote(NAME, instrument, bid, bid + spread, t, DataType.SIMULATED)

    async def snapshot(self, instruments: Sequence[str]) -> list[Quote]:
        self._check_up()
        at = last_open_second(self._clock())
        return [self.quote_at(i, at) for i in instruments if i in self._registry.by_code]

    # ---------------------------------------------------------------------------- stream
    async def stream(self, instruments: Sequence[str]) -> AsyncIterator[StreamEvent]:
        self._check_up()
        self.connections += 1
        if self._scripts is not None:
            script = self._scripts.pop(0) if self._scripts else [Silence()]
            for item in script:
                if isinstance(item, Silence):
                    await asyncio.Event().wait()  # until the client gives up and cancels
                if isinstance(item, Drop):
                    raise ProviderUnavailable("simulated connection loss")
                if isinstance(item, (Quote, Heartbeat)):
                    yield item
            return
        for i in instruments:
            self._spec(i)
        last_heartbeat: datetime | None = None
        while True:
            self._check_up()
            now = self._clock().replace(microsecond=0)
            if market_open(now):
                for i in instruments:
                    yield self.quote_at(i, now)
            if last_heartbeat is None or now - last_heartbeat >= self._heartbeat:
                last_heartbeat = now
                yield Heartbeat(NAME, now)
            await self._sleep(self._tick.total_seconds())

    # ---------------------------------------------------------------------------- candles
    def _minute(self, instrument: str, start: datetime, basis: PriceBasis) -> Candle | None:
        samples = [start + timedelta(seconds=15 * k) for k in range(SAMPLES_PER_MINUTE)]
        now = self._clock()
        open_samples = [s for s in samples if market_open(s) and s <= now]  # never the future
        if not open_samples:
            return None
        quotes = [self.quote_at(instrument, s) for s in open_samples]
        prices = [
            q.bid if basis is PriceBasis.BID else q.ask if basis is PriceBasis.ASK else q.mid
            for q in quotes
        ]
        return Candle(
            NAME,
            instrument,
            Timeframe.M1,
            basis,
            start,
            prices[0],
            max(prices),
            min(prices),
            prices[-1],
            len(prices),
            complete=start + STEP[Timeframe.M1] <= now,
            data_type=DataType.SIMULATED,
        )

    async def candles(
        self,
        instrument: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
        basis: PriceBasis = PriceBasis.MID,
    ) -> list[Candle]:
        self._check_up()
        self._spec(instrument)
        if timeframe not in STEP:
            raise UnsupportedKind(
                "the simulated provider serves up to 1D; weeks and months are aggregated by the "
                "backend (P13-T03)"
            )
        step = STEP[timeframe]
        now = self._clock()
        out: list[Candle] = []
        period = _floor(start, step)
        if period < start:
            period += step
        while period < end and period <= now:
            minutes = [
                c
                for k in range(int(step / STEP[Timeframe.M1]))
                if (m := period + timedelta(minutes=k)) <= now
                and (c := self._minute(instrument, m, basis)) is not None
            ]
            if minutes:
                out.append(
                    Candle(
                        NAME,
                        instrument,
                        timeframe,
                        basis,
                        period,
                        minutes[0].open,
                        max(c.high for c in minutes),
                        min(c.low for c in minutes),
                        minutes[-1].close,
                        sum(c.volume or 0 for c in minutes),
                        complete=period + step <= now,
                        data_type=DataType.SIMULATED,
                    )
                )
            period += step
        return out
