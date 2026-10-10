"""Portfolio summary and consolidation (pure; P05-T08). Formulas: docs/design/portfolio-summary.md.

Every figure is exact (50-digit context); rounding happens only when the API publishes it."""

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, localcontext

from app.modules.transactions.holdings import Entry, effective

PRECISION = 50
ZERO = Decimal(0)
_INCOME = frozenset({"DIVIDEND", "INTEREST", "COUPON", "RENT", "DISTRIBUTION"})


@dataclass(frozen=True)
class HoldingInput:
    asset_id: uuid.UUID
    quantity: Decimal
    cost_basis: Decimal  # in the portfolio's base currency
    realized_pl: Decimal
    income: Decimal
    expenses: Decimal


@dataclass(frozen=True)
class ValuationInput:
    asset_id: uuid.UUID
    value: Decimal
    currency: str
    as_of: datetime


@dataclass(frozen=True)
class Rate:
    """1 unit of `currency` = `rate` units of the target currency."""

    currency: str
    rate: Decimal
    as_of: datetime
    stale: bool


@dataclass
class Summary:
    currency: str
    holdings_value: Decimal = ZERO
    cash: Decimal = ZERO
    cost_basis: Decimal = ZERO
    unrealized_pl: Decimal = ZERO
    realized_pl: Decimal = ZERO
    income: Decimal = ZERO
    expenses: Decimal = ZERO
    net_contributions: Decimal = ZERO
    # Per currency of origin: the native amount and the same amount in `currency`. The converted
    # amounts add up to `total_value`, so the breakdown always reconciles with the total.
    native: dict[str, Decimal] = field(default_factory=dict)
    converted: dict[str, Decimal] = field(default_factory=dict)
    inputs_as_of: list[datetime] = field(default_factory=list)
    stale_fx: set[str] = field(default_factory=set)
    unpriced_assets: list[uuid.UUID] = field(default_factory=list)
    unconverted_currencies: set[str] = field(default_factory=set)
    valued_positions: int = 0

    @property
    def total_value(self) -> Decimal:
        return self.holdings_value + self.cash

    @property
    def complete(self) -> bool:
        return not self.unpriced_assets and not self.unconverted_currencies

    def data_as_of(self, default: datetime) -> datetime:
        return min(self.inputs_as_of) if self.inputs_as_of else default


class _Converter:
    """Converts into the target currency, noting the rates used, stale rates and gaps."""

    def __init__(self, target: str, rates: dict[str, Rate], summary: Summary) -> None:
        self._target = target
        self._rates = rates
        self._summary = summary

    def __call__(self, amount: Decimal, currency: str) -> Decimal | None:
        if currency == self._target:
            return amount
        rate = self._rates.get(currency)
        if rate is None:
            self._summary.unconverted_currencies.add(currency)
            return None
        self._summary.inputs_as_of.append(rate.as_of)
        if rate.stale:
            self._summary.stale_fx.add(currency)
        return amount * rate.rate


def cash_effect(e: Entry) -> Decimal:
    """The entry's effect on cash, in its own currency (docs/design/portfolio-summary.md 3)."""
    kind = e.transaction_type
    if kind == "DEPOSIT":
        return e.gross_amount - e.fees - e.taxes
    if kind == "WITHDRAWAL":
        return -(e.gross_amount + e.fees + e.taxes)
    if kind == "BUY":
        return -(e.gross_amount + e.fees + e.taxes)
    if kind in _INCOME or kind == "SELL":
        return e.gross_amount - e.fees - e.taxes
    if kind in ("FEE", "TAX"):
        return -(e.gross_amount + e.fees + e.taxes)
    if kind in ("TRANSFER_IN", "TRANSFER_OUT"):
        return -(e.fees + e.taxes)
    return ZERO  # VALUATION_ADJUSTMENT


def compute_summary(
    base_currency: str,
    holdings: list[HoldingInput],
    valuations: list[ValuationInput],
    entries: list[Entry],
    rates: dict[str, Rate],
) -> Summary:
    """One portfolio's summary in its base currency. `rates` are the latest rates into it."""
    s = Summary(base_currency)
    to_base = _Converter(base_currency, rates, s)
    by_asset = {h.asset_id: h for h in holdings}
    valued = {v.asset_id: v for v in valuations}
    with localcontext() as ctx:
        ctx.prec = PRECISION
        # Positions.
        for asset_id in sorted(set(by_asset) | set(valued)):
            h, v = by_asset.get(asset_id), valued.get(asset_id)
            if h is not None and h.quantity == 0:
                continue  # closed: not valued
            if v is None:
                s.unpriced_assets.append(asset_id)
                continue
            converted = to_base(v.value, v.currency)
            if converted is None:
                continue
            s.inputs_as_of.append(v.as_of)
            _add(s, v.currency, v.value, converted)
            s.holdings_value += converted
            s.valued_positions += 1
            if h is not None:
                s.cost_basis += h.cost_basis
                s.unrealized_pl += converted - h.cost_basis
        # Results kept on the holdings (already in the base currency).
        for h in holdings:
            s.realized_pl += h.realized_pl
            s.income += h.income
            s.expenses += h.expenses
        # Cash, contributions and asset-less income and costs, from the ledger.
        cash: dict[str, Decimal] = defaultdict(lambda: ZERO)
        for e in effective(entries):
            cash[e.currency] += cash_effect(e)
            if e.transaction_type == "DEPOSIT":
                s.net_contributions += e.gross_amount * e.fx
            elif e.transaction_type == "WITHDRAWAL":
                s.net_contributions -= e.gross_amount * e.fx
            if e.asset_id is None:
                if e.transaction_type == "INTEREST":
                    s.income += e.gross_amount * e.fx
                    s.expenses += (e.fees + e.taxes) * e.fx
                elif e.transaction_type in ("FEE", "TAX"):
                    s.expenses += (e.gross_amount + e.fees + e.taxes) * e.fx
        for currency, balance in sorted(cash.items()):
            if balance == 0:
                continue
            converted = to_base(balance, currency)
            if converted is None:
                continue
            _add(s, currency, balance, converted)
            s.cash += converted
    return s


def consolidate(reporting_currency: str, parts: list[Summary], rates: dict[str, Rate]) -> Summary:
    """Adds portfolio summaries in `reporting_currency`: every figure of a portfolio is converted
    from its base currency at the latest rate (`rates`: base currency -> reporting currency), so
    the consolidated figures and breakdown reconcile exactly."""
    s = Summary(reporting_currency)
    convert = _Converter(reporting_currency, rates, s)
    names = (
        "holdings_value",
        "cash",
        "cost_basis",
        "unrealized_pl",
        "realized_pl",
        "income",
        "expenses",
        "net_contributions",
    )
    with localcontext() as ctx:
        ctx.prec = PRECISION
        for part in parts:
            s.inputs_as_of.extend(part.inputs_as_of)
            s.stale_fx |= part.stale_fx
            s.unpriced_assets.extend(part.unpriced_assets)
            s.unconverted_currencies |= part.unconverted_currencies
            factor = convert(Decimal(1), part.currency)
            if factor is None:
                continue  # this portfolio's base currency cannot be converted
            s.valued_positions += part.valued_positions
            for name in names:
                setattr(s, name, getattr(s, name) + getattr(part, name) * factor)
            for currency, amount in part.converted.items():
                _add(s, currency, part.native[currency], amount * factor)
    return s


def _add(s: Summary, currency: str, native: Decimal, converted: Decimal) -> None:
    s.native[currency] = s.native.get(currency, ZERO) + native
    s.converted[currency] = s.converted.get(currency, ZERO) + converted
