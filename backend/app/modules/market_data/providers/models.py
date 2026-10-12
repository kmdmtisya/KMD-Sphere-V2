"""What a provider returns: a value plus where it came from and when (provenance).

Every price and rate carries the provider, the time it was valid (`as_of`) and the time we fetched
it (`retrieved_at`). A value from a provider is validated on construction: a non-positive or
non-finite number, a naive timestamp or a malformed currency is rejected as bad provider data
instead of being stored (CLAUDE.md: timestamp prices and FX; never trust unvalidated market data).
Amounts are `Decimal`, never `float` (ADR-0003)."""

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import StrEnum

from app.modules.market_data.providers.errors import ProviderDataError

_CURRENCY = re.compile(r"^[A-Z]{3}$")
_SYMBOL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.\-_:/]{0,31}$")


class AssetKind(StrEnum):
    EQUITY = "equity"
    ETF = "etf"
    CRYPTO = "crypto"
    BOND = "bond"
    INDEX = "index"


def _aware(value: datetime, what: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ProviderDataError(f"{what} must be timezone-aware")


def _positive(value: Decimal, what: str) -> None:
    if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
        raise ProviderDataError(f"{what} must be a positive finite Decimal")


def _currency(value: str) -> None:
    if not _CURRENCY.match(value):
        raise ProviderDataError("currency must be a three-letter upper-case code")


def _symbol(value: str) -> None:
    if not _SYMBOL.match(value):
        raise ProviderDataError("symbol has an invalid format")


@dataclass(frozen=True)
class Provenance:
    """Where a value came from and when."""

    provider: str
    as_of: datetime
    retrieved_at: datetime

    def __post_init__(self) -> None:
        if not self.provider:
            raise ProviderDataError("provider name is required")
        _aware(self.as_of, "as_of")
        _aware(self.retrieved_at, "retrieved_at")
        if self.as_of > self.retrieved_at:
            raise ProviderDataError("as_of is after retrieved_at (a value from the future)")

    def age(self, now: datetime) -> timedelta:
        """How old the value is at `now` (never negative)."""
        return max(now - self.as_of, timedelta(0))

    def is_stale(self, now: datetime, max_age: timedelta) -> bool:
        return self.age(now) > max_age


@dataclass(frozen=True)
class PriceQuote:
    """The latest price of an instrument, in its own currency."""

    symbol: str
    kind: AssetKind
    price: Decimal
    currency: str
    provenance: Provenance

    def __post_init__(self) -> None:
        _symbol(self.symbol)
        _positive(self.price, "price")
        _currency(self.currency)


@dataclass(frozen=True)
class PricePoint:
    """A daily closing price."""

    symbol: str
    day: date
    close: Decimal
    currency: str
    provenance: Provenance

    def __post_init__(self) -> None:
        _symbol(self.symbol)
        _positive(self.close, "close")
        _currency(self.currency)


FX_RATE_TYPES = ("mid_market", "indicative", "delayed")


@dataclass(frozen=True)
class FxQuote:
    """1 unit of `base` = `rate` units of `quote`."""

    base: str
    quote: str
    rate: Decimal
    provenance: Provenance
    # What the provider publishes: `mid_market`, `indicative` (the default) or `delayed`.
    rate_type: str = "indicative"
    # For a rate the provider derived through other currencies, the currencies in order
    # (base first, quote last); None for a direct quote.
    path: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        _currency(self.base)
        _currency(self.quote)
        if self.base == self.quote:
            raise ProviderDataError("an FX rate needs two different currencies")
        _positive(self.rate, "rate")
        if self.rate_type not in FX_RATE_TYPES:
            raise ProviderDataError(f"unknown FX rate type {self.rate_type!r}")
        if self.path is not None and (
            not 3 <= len(self.path) <= 4 or self.path[0] != self.base or self.path[-1] != self.quote
        ):
            raise ProviderDataError("an FX rate path runs from the base to the quote")


@dataclass(frozen=True)
class FxBatch:
    """The rates of one base against several quotes from one request. `unsupported` lists the
    quotes this provider does not publish (another provider may)."""

    rates: list[FxQuote]
    unsupported: list[str]
