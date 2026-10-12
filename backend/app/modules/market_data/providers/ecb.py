"""ECB euro reference rates (ADR-0014): daily FX, EUR base, no key.

The ECB publishes about 30 currencies against the euro once a working day (around 14:15 CET). Any
pair is crossed through EUR: 1 base = (EUR per base)^-1 x (quote per EUR). Rates are indicative
("for information purposes only"): the app labels them so and never uses them for transactions.
The ECB does not publish every currency (for example AED and KES are missing): such a pair is
`UnsupportedKind`, so a fallback chain moves on to the next FX provider (ADR-0014, DEC-25).

Only FX is served; quotes and history for assets are `UnsupportedKind`."""

from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, localcontext
from zoneinfo import ZoneInfo

from defusedxml import DefusedXmlException, ElementTree

from app.modules.market_data.providers.errors import (
    ProviderDataError,
    UnsupportedKind,
)
from app.modules.market_data.providers.http import HttpClient, HttpxClient, check_status
from app.modules.market_data.providers.models import (
    AssetKind,
    FxBatch,
    FxQuote,
    PricePoint,
    PriceQuote,
    Provenance,
)
from app.modules.market_data.providers.throttle import RateLimiter

DAILY_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
HIST_90D_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist-90d.xml"
HIST_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.xml"
_PUBLISHED_AT = ("Europe/Berlin", 14, 15)
_PRECISION = 28


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _published(day: date) -> datetime:
    zone, hour, minute = _PUBLISHED_AT
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=ZoneInfo(zone)).astimezone(
        UTC
    )


def parse_rates(xml_text: str) -> dict[date, dict[str, Decimal]]:
    """`{day: {currency: units per EUR}}` from an ECB feed (daily or history)."""
    try:
        root = ElementTree.fromstring(xml_text)
    except (ElementTree.ParseError, DefusedXmlException):
        # Includes entity expansion and external entities, which are refused outright.
        raise ProviderDataError("ecb returned invalid or unsafe XML") from None
    rates: dict[date, dict[str, Decimal]] = {}
    for day_node in root.iter():
        if _local(day_node.tag) != "Cube" or "time" not in day_node.attrib:
            continue
        try:
            day = date.fromisoformat(day_node.attrib["time"])
        except ValueError:
            raise ProviderDataError("ecb returned an invalid date") from None
        table: dict[str, Decimal] = {}
        for node in day_node:
            if _local(node.tag) != "Cube":
                continue
            try:
                value = Decimal(node.attrib["rate"])
                currency = node.attrib["currency"]
            except (KeyError, ArithmeticError):
                raise ProviderDataError("ecb returned an invalid rate") from None
            if not value.is_finite() or value <= 0:
                raise ProviderDataError("ecb returned a non-positive rate")
            table[currency] = value
        rates[day] = table
    if not rates:
        raise ProviderDataError("ecb feed has no rates")
    return rates


def _cross(table: dict[str, Decimal], base: str, quote: str) -> Decimal | None:
    """1 base = ? quote, through EUR; None when the ECB does not publish a leg."""
    per_eur_base = Decimal(1) if base == "EUR" else table.get(base)
    per_eur_quote = Decimal(1) if quote == "EUR" else table.get(quote)
    if per_eur_base is None or per_eur_quote is None:
        return None
    with localcontext() as ctx:
        ctx.prec = _PRECISION
        return per_eur_quote / per_eur_base


class EcbProvider:
    name = "ecb"
    supported_kinds: frozenset[AssetKind] = frozenset()

    def __init__(
        self,
        client: HttpClient | None = None,
        limiter: RateLimiter | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._client = client or HttpxClient()
        self._limiter = limiter or RateLimiter(10, timedelta(minutes=1))
        self._now: Callable[[], datetime] = clock or (lambda: datetime.now(UTC))

    async def _fetch(self, url: str) -> dict[date, dict[str, Decimal]]:
        await self._limiter.acquire()
        response = await self._client.get(url)
        check_status(self.name, response)
        return parse_rates(response.text)

    def _quote(self, day: date, table: dict[str, Decimal], base: str, quote: str) -> FxQuote:
        rate = _cross(table, base, quote)
        if rate is None:
            raise UnsupportedKind(f"{base}/{quote} (not published by the ECB)")
        as_of = _published(day)
        retrieved = max(self._now(), as_of)
        path = None if "EUR" in (base, quote) else (base, "EUR", quote)
        return FxQuote(
            base, quote, rate, Provenance(self.name, as_of, retrieved), "indicative", path
        )

    async def get_fx_rates(self, base: str, quotes: list[str]) -> FxBatch:
        """Every quote against `base` from one daily file (one request for all pairs)."""
        rates = await self._fetch(DAILY_URL)
        day = max(rates)
        found: list[FxQuote] = []
        unsupported: list[str] = []
        for quote in quotes:
            if quote == base:
                continue
            try:
                found.append(self._quote(day, rates[day], base, quote))
            except UnsupportedKind:
                unsupported.append(quote)
        return FxBatch(found, unsupported)

    async def get_fx_rate(self, base: str, quote: str) -> FxQuote:
        rates = await self._fetch(DAILY_URL)
        day = max(rates)
        return self._quote(day, rates[day], base, quote)

    async def get_fx_history(self, base: str, quote: str, start: date, end: date) -> list[FxQuote]:
        # The 90-day file covers recent backfills; the full file goes back to 1999.
        recent = self._now().date() - start <= timedelta(days=80)
        rates = await self._fetch(HIST_90D_URL if recent else HIST_URL)
        points = [
            self._quote(day, table, base, quote)
            for day, table in sorted(rates.items())
            if start <= day <= end
        ]
        if not points and not any(_cross(t, base, quote) is not None for t in rates.values()):
            raise UnsupportedKind(f"{base}/{quote} (not published by the ECB)")
        return points

    async def get_quote(self, symbol: str, kind: AssetKind) -> PriceQuote:
        raise UnsupportedKind("ecb serves FX only")

    async def get_history(
        self, symbol: str, kind: AssetKind, start: date, end: date
    ) -> list[PricePoint]:
        raise UnsupportedKind("ecb serves FX only")
