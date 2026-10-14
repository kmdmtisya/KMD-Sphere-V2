"""The quote-currency to account-currency rate for a pip value (P13-T07.2, design section 9.1).

The rate always comes from the stored feed, with its provenance: the path taken, the time of the
oldest quote used, and the data types of the quotes. In order:
1. the quote currency is the account currency: exactly 1 (no quote needed);
2. a pair quoting one in the other: its mid, or 1 / its mid;
3. a cross through USD: (quote -> USD) x (USD -> account), each leg as in 2.
A rate is never assumed: with no path, `NoConversionRate` is raised and the request is refused.
A quote older than the stale threshold is still used but marked stale, and a less liquid pair's
rate counts as indicative whatever the feed says (design 4.2)."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, localcontext

from app.modules.forex.marketdata.repository import StoredQuote
from app.modules.forex.marketdata.types import DataType
from app.modules.forex.risk.engine import Conversion

PIVOT = "USD"


class NoConversionRate(LookupError):
    """No stored quote links the quote currency to the account currency."""


@dataclass(frozen=True)
class Rate:
    mid: Decimal
    as_of: datetime
    data_types: frozenset[str]


def rates_from(quotes: Mapping[str, StoredQuote], indicative: set[str]) -> dict[str, Rate]:
    """Rates from the latest quotes; `indicative` pairs (less liquid) count as indicative."""
    out = {}
    for code, q in quotes.items():
        if q.mid <= 0:
            continue
        types = {q.data_type} | ({DataType.INDICATIVE_RATE.value} if code in indicative else set())
        out[code] = Rate(q.mid, q.ts_provider, frozenset(types))
    return out


Leg = tuple[Decimal, Decimal, str, Rate]  # numerator, denominator, path, source


def _leg(rates: Mapping[str, Rate], frm: str, to: str) -> Leg | None:
    if f"{frm}_{to}" in rates:
        r = rates[f"{frm}_{to}"]
        return r.mid, Decimal(1), f"{frm}_{to} mid", r
    if f"{to}_{frm}" in rates:
        r = rates[f"{to}_{frm}"]
        return Decimal(1), r.mid, f"1 / {to}_{frm} mid", r
    return None


def resolve(
    quote: str, account: str, rates: Mapping[str, Rate], now: datetime, stale_after: timedelta
) -> Conversion:
    if quote == account:
        return Conversion(Decimal(1), "same currency", None, ())
    direct = _leg(rates, quote, account)
    if direct is not None:
        legs = [direct]
    elif PIVOT not in (quote, account):
        first, second = _leg(rates, quote, PIVOT), _leg(rates, PIVOT, account)
        if first is None or second is None:
            raise NoConversionRate(f"no stored rate converts {quote} to {account}")
        legs = [first, second]
    else:
        raise NoConversionRate(f"no stored rate converts {quote} to {account}")
    with localcontext() as ctx:
        ctx.prec = 50  # products of stored mids: exact at this precision
        numerator, denominator = Decimal(1), Decimal(1)
        for num, den, _, _ in legs:
            numerator, denominator = numerator * num, denominator * den
    as_of = min(r.as_of for _, _, _, r in legs)
    return Conversion(
        numerator=numerator,
        denominator=denominator,
        path=" x ".join(p for _, _, p, _ in legs),
        as_of=as_of,
        data_types=tuple(sorted(set().union(*(r.data_types for _, _, _, r in legs)))),
        stale=now - as_of > stale_after,
    )
