"""A deterministic provider for development and tests (P08-T02.4).

It serves fixed prices, a reproducible daily history and a fixed FX table, with no network. Tests
script its failures: an outage, stale data, rate limiting, a number of failing calls, or a bad
payload. It is wired in at composition time only; feature code sees `MarketDataProvider`."""

from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from app.modules.market_data.providers.errors import (
    ProviderError,
    ProviderUnavailable,
    RateLimited,
    SymbolNotFound,
    UnsupportedKind,
)
from app.modules.market_data.providers.models import (
    AssetKind,
    FxQuote,
    PricePoint,
    PriceQuote,
    Provenance,
)

# symbol -> (kind, currency, price)
DEFAULT_INSTRUMENTS: dict[str, tuple[AssetKind, str, Decimal]] = {
    "DEMO-GEQ": (AssetKind.ETF, "USD", Decimal("104.20")),
    "DEMO-TEC": (AssetKind.ETF, "USD", Decimal("187.40")),
    "DEMO-KEN": (AssetKind.EQUITY, "KES", Decimal("12.45")),
    "DEMO-BTC": (AssetKind.CRYPTO, "USD", Decimal("64800.00")),
    # The listed instruments of the DEMO investment universe (P12-T02).
    "DEMO-KBK": (AssetKind.EQUITY, "KES", Decimal("38.60")),
    "DEMO-KRT": (AssetKind.EQUITY, "KES", Decimal("21.15")),
    "DEMO-UAE": (AssetKind.EQUITY, "AED", Decimal("6.42")),
    "DEMO-GBD": (AssetKind.ETF, "USD", Decimal("48.90")),
    "DEMO-GLD": (AssetKind.ETF, "USD", Decimal("226.30")),
}

# 1 base = rate quote, for the pairs listed; the opposite direction is derived.
DEFAULT_FX: dict[tuple[str, str], Decimal] = {
    ("USD", "AED"): Decimal("3.6725"),
    ("USD", "KES"): Decimal("129.20"),
    ("EUR", "USD"): Decimal("1.0850"),
}


def _utc_now() -> datetime:
    return datetime.now(UTC)


class FakeProvider:
    def __init__(
        self,
        name: str = "fake",
        clock: Callable[[], datetime] = _utc_now,
        instruments: dict[str, tuple[AssetKind, str, Decimal]] | None = None,
        fx: dict[tuple[str, str], Decimal] | None = None,
        kinds: frozenset[AssetKind] | None = None,
    ) -> None:
        self._name = name
        self._clock = clock
        self._instruments = dict(DEFAULT_INSTRUMENTS if instruments is None else instruments)
        self._fx = dict(DEFAULT_FX if fx is None else fx)
        self._kinds = kinds if kinds is not None else frozenset(AssetKind)
        self._outage = False
        self._stale_by = timedelta(0)
        self._scripted: list[ProviderError] = []
        self.calls: list[str] = []

    # ---- scripting -------------------------------------------------------------------------
    def set_outage(self, down: bool) -> None:
        """While down, every call raises `ProviderUnavailable`."""
        self._outage = down

    def set_stale_by(self, age: timedelta) -> None:
        """Make every value look `age` old: `as_of` is `age` before the retrieval time."""
        self._stale_by = age

    def fail_next(self, count: int, error: ProviderError | None = None) -> None:
        """The next `count` calls raise `error` (default `ProviderUnavailable`)."""
        self._scripted.extend([error or ProviderUnavailable("scripted failure")] * count)

    def rate_limit_next(self, count: int, retry_after: timedelta | None = None) -> None:
        self.fail_next(count, RateLimited(retry_after=retry_after))

    def set_price(self, symbol: str, price: Decimal) -> None:
        kind, currency, _ = self._instruments[symbol]
        self._instruments[symbol] = (kind, currency, price)

    # ---- MarketDataProvider ----------------------------------------------------------------
    @property
    def name(self) -> str:
        return self._name

    @property
    def supported_kinds(self) -> frozenset[AssetKind]:
        return self._kinds

    def _enter(self, call: str) -> None:
        self.calls.append(call)
        if self._outage:
            raise ProviderUnavailable("scripted outage")
        if self._scripted:
            raise self._scripted.pop(0)

    def _provenance(self, as_of: datetime | None = None) -> Provenance:
        now = self._clock()
        valid_at = as_of if as_of is not None else now - self._stale_by
        return Provenance(provider=self._name, as_of=min(valid_at, now), retrieved_at=now)

    def _instrument(self, symbol: str, kind: AssetKind) -> tuple[str, Decimal]:
        if kind not in self._kinds:
            raise UnsupportedKind(f"{self._name} does not serve {kind}")
        found = self._instruments.get(symbol)
        if found is None or found[0] is not kind:
            raise SymbolNotFound(symbol)
        return found[1], found[2]

    async def get_quote(self, symbol: str, kind: AssetKind) -> PriceQuote:
        self._enter(f"quote:{symbol}")
        currency, price = self._instrument(symbol, kind)
        return PriceQuote(symbol, kind, price, currency, self._provenance())

    async def get_history(
        self, symbol: str, kind: AssetKind, start: date, end: date
    ) -> list[PricePoint]:
        self._enter(f"history:{symbol}")
        currency, price = self._instrument(symbol, kind)
        points: list[PricePoint] = []
        today = self._clock().date()
        day = start
        while day <= min(end, today):  # no closes in the future
            if day.weekday() < 5 or kind is AssetKind.CRYPTO:  # no closes on weekends
                # A reproducible wiggle around the current price: whole steps of 0.5%.
                step = Decimal((day.toordinal() % 9) - 4) * Decimal("0.005")
                close = (price * (Decimal(1) + step)).quantize(Decimal("0.0001"))
                closed_at = datetime(day.year, day.month, day.day, 21, tzinfo=UTC)
                points.append(PricePoint(symbol, day, close, currency, self._provenance(closed_at)))
            day += timedelta(days=1)
        return points

    async def get_fx_rate(self, base: str, quote: str) -> FxQuote:
        self._enter(f"fx:{base}{quote}")
        return FxQuote(base, quote, await self._rate(base, quote), self._provenance())

    async def get_fx_history(self, base: str, quote: str, start: date, end: date) -> list[FxQuote]:
        self._enter(f"fxhistory:{base}{quote}")
        current = await self._rate(base, quote)
        points: list[FxQuote] = []
        today = self._clock().date()
        day = start
        while day <= min(end, today):
            if day.weekday() < 5:
                step = Decimal((day.toordinal() % 7) - 3) * Decimal("0.001")
                closed_at = datetime(day.year, day.month, day.day, 14, 15, tzinfo=UTC)
                points.append(
                    FxQuote(
                        base,
                        quote,
                        (current * (Decimal(1) + step)).quantize(Decimal("0.00000001")),
                        self._provenance(closed_at),
                    )
                )
            day += timedelta(days=1)
        return points

    async def _rate(self, base: str, quote: str) -> Decimal:
        direct = self._fx.get((base, quote))
        if direct is not None:
            return direct
        opposite = self._fx.get((quote, base))
        if opposite is not None:
            return Decimal(1) / opposite
        raise SymbolNotFound(f"{base}/{quote}")
