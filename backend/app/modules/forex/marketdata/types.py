"""Forex market-data values (P13-T02.1, design section 4.2).

Prices are Decimal. The mid is derived from bid and ask, never taken from a provider. A value is
validated when it is built, so nothing invalid gets past the provider adapter: a bad value raises
`ProviderDataError` and is never stored or shown."""

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum

from app.modules.market_data.providers.errors import ProviderDataError

INSTRUMENT_PATTERN = r"^[A-Z]{3}_[A-Z]{3}$"
_INSTRUMENT = re.compile(INSTRUMENT_PATTERN)
TWO = Decimal(2)


class DataType(StrEnum):
    """What kind of price this is. Shown end to end; only a tradable quote is executable, and
    WealthSphere executes nothing."""

    TRADABLE_QUOTE = "tradable_quote"
    INDICATIVE_RATE = "indicative_rate"
    DELAYED = "delayed"
    SIMULATED = "simulated"


class Quality(StrEnum):
    OK = "ok"
    # Crossed (bid above ask) or out of band (too far from the previous good mid): stored for
    # the record, never served as the latest price.
    SUSPECT = "suspect"
    # Older than the staleness threshold when received, or when served.
    STALE = "stale"


class FeedStatus(StrEnum):
    CONNECTED = "connected"
    DEGRADED = "degraded"  # no message within the heartbeat window
    DISCONNECTED = "disconnected"


class Timeframe(StrEnum):
    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    M30 = "30m"
    H1 = "1H"
    H4 = "4H"
    D1 = "1D"
    W1 = "1W"
    MN1 = "1M"


class PriceBasis(StrEnum):
    MID = "mid"
    BID = "bid"
    ASK = "ask"


def check_instrument(code: str) -> str:
    if not _INSTRUMENT.fullmatch(code):
        raise ProviderDataError("instrument must look like EUR_USD")
    return code


def _price(value: Decimal, what: str) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
        raise ProviderDataError(f"{what} must be a positive decimal")
    return value


def _utc(value: datetime, what: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ProviderDataError(f"{what} must carry a time zone")
    return value.astimezone(UTC)


@dataclass(frozen=True)
class Quote:
    """A price as the provider sent it: bid and ask at the provider's time."""

    provider: str
    instrument: str
    bid: Decimal
    ask: Decimal
    ts_provider: datetime
    data_type: DataType

    def __post_init__(self) -> None:
        check_instrument(self.instrument)
        _price(self.bid, "bid")
        _price(self.ask, "ask")
        object.__setattr__(self, "ts_provider", _utc(self.ts_provider, "quote time"))

    @property
    def mid(self) -> Decimal:
        """Derived, never supplied: (bid + ask) / 2, exact."""
        return (self.bid + self.ask) / TWO

    @property
    def crossed(self) -> bool:
        return self.bid > self.ask


@dataclass(frozen=True)
class Heartbeat:
    """The provider's keep-alive: proves the connection is up when prices do not move."""

    provider: str
    ts: datetime


@dataclass(frozen=True)
class ReceivedQuote:
    """A quote as stored: with receipt time (UTC), quality and the feed's status at receipt."""

    quote: Quote
    ts_received: datetime
    quality: Quality
    feed_status: FeedStatus

    def __post_init__(self) -> None:
        object.__setattr__(self, "ts_received", _utc(self.ts_received, "receipt time"))


@dataclass(frozen=True)
class Candle:
    """One period's open, high, low and close. `ts` is the period's start (UTC). Periods without
    trades are absent, never filled."""

    provider: str
    instrument: str
    timeframe: Timeframe
    price_basis: PriceBasis
    ts: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int | None
    complete: bool
    data_type: DataType

    def __post_init__(self) -> None:
        check_instrument(self.instrument)
        for what in ("open", "high", "low", "close"):
            _price(getattr(self, what), what)
        if self.high < max(self.open, self.close, self.low) or self.low > min(
            self.open, self.close
        ):
            raise ProviderDataError("candle high and low must bound open and close")
        if self.volume is not None and self.volume < 0:
            raise ProviderDataError("volume must not be negative")
        object.__setattr__(self, "ts", _utc(self.ts, "candle time"))
