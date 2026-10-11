"""Net worth (P06-T07): total assets minus total liabilities in one currency, with the FX rates
used. Pure and deterministic (Decimal only). Methods: docs/design/net-worth.md."""

import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, localcontext

from app.core.money import minor_units, round_half_up
from app.modules.portfolio.summary import Rate

ZERO = Decimal(0)
PRECISION = 50


@dataclass(frozen=True)
class Debt:
    id: uuid.UUID
    name: str
    liability_type: str
    currency: str
    balance: Decimal
    balance_as_of: date


@dataclass(frozen=True)
class ConvertedDebt:
    debt: Debt
    converted: Decimal | None  # in the reporting currency, rounded; None without a rate


@dataclass(frozen=True)
class TypeTotal:
    liability_type: str
    value: Decimal
    count: int


@dataclass(frozen=True)
class NetWorth:
    currency: str
    assets: Decimal  # rounded to the currency
    liabilities: Decimal  # the sum of the rounded converted liabilities
    net_worth: Decimal  # assets - liabilities, exactly as shown
    debts: tuple[ConvertedDebt, ...]
    by_type: tuple[TypeTotal, ...]
    unconverted: frozenset[str]  # liability currencies without a rate (left out)


def compute(
    currency: str, assets: Decimal, debts: Iterable[Debt], rates: Mapping[str, Rate]
) -> NetWorth:
    """`assets` is the unrounded total value of the user's portfolios in `currency`; `rates`
    are the latest rates into `currency`."""
    places = minor_units(currency)
    converted = []
    unconverted = set()
    with localcontext() as ctx:
        ctx.prec = PRECISION
        for d in debts:
            if d.currency == currency:
                value: Decimal | None = round_half_up(d.balance, places)
            elif d.currency in rates:
                value = round_half_up(d.balance * rates[d.currency].rate, places)
            else:
                value = None
                unconverted.add(d.currency)
            converted.append(ConvertedDebt(d, value))
    totals: dict[str, tuple[Decimal, int]] = {}
    for c in converted:
        if c.converted is not None:
            value_so_far, count = totals.get(c.debt.liability_type, (ZERO, 0))
            totals[c.debt.liability_type] = (value_so_far + c.converted, count + 1)
    liabilities = sum((v for v, _ in totals.values()), round_half_up(ZERO, places))
    shown_assets = round_half_up(assets, places)
    return NetWorth(
        currency=currency,
        assets=shown_assets,
        liabilities=liabilities,
        net_worth=shown_assets - liabilities,
        debts=tuple(converted),
        by_type=tuple(
            TypeTotal(kind, value, count)
            for kind, (value, count) in sorted(totals.items(), key=lambda kv: (-kv[1][0], kv[0]))
        ),
        unconverted=frozenset(unconverted),
    )
