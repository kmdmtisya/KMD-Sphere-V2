"""FX conversion and rate-selection rules (pure; P05-T06).

Conversion
- `convert_exact(amount, rate)` keeps full precision: use it for intermediate sums.
- `convert(amount, rate, to_currency)` rounds ROUND_HALF_UP to the target currency's ISO 4217 minor
  units (ADR-0006): use it only where a converted amount is shown or stored as money.
- A rate means: 1 unit of the base currency = `rate` units of the quote currency.

Rate selection
- **Historical** (a posting on a trade date): the most recent rate whose timestamp is at or before
  the end of that day (UTC), and no older than `HISTORICAL_MAX_AGE` before it. Weekends and
  holidays are covered by the age window; anything older is "unavailable" rather than guessed.
- **Latest** (valuing a position now): the most recent rate at or before now; it is reported as
  `stale` when older than `LATEST_FRESH_FOR`, and unavailable beyond `HISTORICAL_MAX_AGE`.
- **Direction:** a rate for the opposite pair is used inverted (1 / rate) when the direct pair
  has none.
- **Ties:** a later rate timestamp wins, then a later retrieval, then the provider name
  (alphabetical), so the choice never depends on storage order.

The thresholds are provisional until DEC-26 (refresh cadence and staleness, P11-T01)."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal, localcontext

from app.core.money import minor_units, round_half_up

HISTORICAL_MAX_AGE = timedelta(days=7)
LATEST_FRESH_FOR = timedelta(days=1)
PRECISION = 50


@dataclass(frozen=True)
class StoredRate:
    base_currency: str
    quote_currency: str
    rate: Decimal
    provider: str
    rate_timestamp: datetime
    retrieved_at: datetime
    # The currencies a provider-derived rate went through (P11-T02); None for a direct quote.
    rate_path: tuple[str, ...] | None = None


@dataclass(frozen=True)
class Quote:
    """The rate chosen for base -> quote, with where it came from."""

    base_currency: str
    quote_currency: str
    rate: Decimal
    as_of: datetime
    provider: str
    inverted: bool
    stale: bool
    # base, [intermediate currencies,] quote when the rate was derived; None for a direct rate.
    path: tuple[str, ...] | None = None


class FxRateUnavailable(LookupError):
    pass


def convert_exact(amount: Decimal, rate: Decimal) -> Decimal:
    with localcontext() as ctx:
        ctx.prec = PRECISION
        return amount * rate


def convert(amount: Decimal, rate: Decimal, to_currency: str) -> Decimal:
    return round_half_up(convert_exact(amount, rate), minor_units(to_currency))


def end_of_day(day: date) -> datetime:
    return datetime.combine(day, time.max, tzinfo=UTC)


def select(
    base: str,
    quote: str,
    candidates: list[StoredRate],
    at: datetime,
    *,
    now: datetime,
) -> Quote:
    """Chooses the rate for base -> quote valid at `at` from rates of either direction."""
    if base == quote:
        return Quote(base, quote, Decimal(1), at, "identity", inverted=False, stale=False)
    earliest = at - HISTORICAL_MAX_AGE

    def best(direct: bool) -> StoredRate | None:
        pair = (base, quote) if direct else (quote, base)
        usable = [
            r
            for r in candidates
            if (r.base_currency, r.quote_currency) == pair
            and earliest <= r.rate_timestamp <= at
            and r.rate > 0
        ]
        if not usable:
            return None
        newest = max((r.rate_timestamp, r.retrieved_at) for r in usable)
        tied = [r for r in usable if (r.rate_timestamp, r.retrieved_at) == newest]
        return min(tied, key=lambda r: r.provider)

    chosen, inverted = best(direct=True), False
    if chosen is None:
        chosen, inverted = best(direct=False), True
    if chosen is None:
        raise FxRateUnavailable(
            f"no {base}/{quote} rate between {earliest:%Y-%m-%d} and {at:%Y-%m-%d}"
        )
    # Direction check: the stored pair is exactly (base, quote) or exactly (quote, base).
    stored_pair = (chosen.base_currency, chosen.quote_currency)
    if stored_pair != ((quote, base) if inverted else (base, quote)):  # pragma: no cover
        raise FxRateUnavailable(f"{base}/{quote}: rate direction mismatch")
    with localcontext() as ctx:
        ctx.prec = PRECISION
        rate = Decimal(1) / chosen.rate if inverted else chosen.rate
    path = chosen.rate_path
    if path is not None and inverted:
        path = tuple(reversed(path))
    return Quote(
        base,
        quote,
        rate,
        chosen.rate_timestamp,
        chosen.provider,
        inverted=inverted,
        stale=now - chosen.rate_timestamp > LATEST_FRESH_FOR,
        path=path,
    )


def select_via(
    base: str,
    quote: str,
    candidates: list[StoredRate],
    at: datetime,
    *,
    now: datetime,
    pivot: str | None,
) -> Quote:
    """`select`, and when neither direction of the pair is stored, the cross rate through
    `pivot` (P11-T04): 1 base = (base->pivot) x (pivot->quote) pivot-legs, each chosen by the same
    rules. The cross rate is as old as its older leg, stale when either leg is, and carries the
    path (for example AED->USD->KES)."""
    try:
        return select(base, quote, candidates, at, now=now)
    except FxRateUnavailable:
        if pivot is None or pivot in (base, quote):
            raise
    first = select(base, pivot, candidates, at, now=now)
    second = select(pivot, quote, candidates, at, now=now)
    with localcontext() as ctx:
        ctx.prec = PRECISION
        rate = first.rate * second.rate
    providers = dict.fromkeys([first.provider, second.provider])
    return Quote(
        base,
        quote,
        rate,
        min(first.as_of, second.as_of),
        "+".join(providers),
        inverted=False,
        stale=first.stale or second.stale,
        path=(base, pivot, quote),
    )
