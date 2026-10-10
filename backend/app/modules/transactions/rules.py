"""Validation and normalisation of a ledger posting, per transaction type (pure, no I/O).

| Type                               | Asset    | Quantity | Unit price | Gross amount |
|------------------------------------|----------|----------|------------|--------------|
| BUY, SELL                          | required | > 0      | required   | derived (1)  |
| TRANSFER_IN, TRANSFER_OUT          | required | > 0      | optional   | required     |
| DIVIDEND, COUPON, RENT, DISTRIBUTION | required | -      | -          | required     |
| VALUATION_ADJUSTMENT               | required | -        | -          | may be < 0   |
| INTEREST, FEE, TAX                 | optional | -        | -          | required     |
| DEPOSIT, WITHDRAWAL                | none     | -        | -          | required     |

(1) Derived as quantity x unit price when omitted; when given, it must match within one minor
unit (brokers round).

Every amount is in the posting's currency and uses at most that currency's minor units; unit
prices allow 8 decimals and quantities 12 (the column scales). A posting in a currency other than
the portfolio's needs the FX rate to the portfolio currency (1 unit of the posting currency =
`rate` units of the portfolio currency); in the portfolio currency the rate is 1."""

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from app.core.money import Money, decimals_of, minor_units, round_half_up

POSITION_SIGN: dict[str, int] = {"BUY": 1, "TRANSFER_IN": 1, "SELL": -1, "TRANSFER_OUT": -1}
TRADES = frozenset({"BUY", "SELL"})
TRANSFERS = frozenset({"TRANSFER_IN", "TRANSFER_OUT"})
ASSET_INCOME = frozenset({"DIVIDEND", "COUPON", "RENT", "DISTRIBUTION"})
ASSET_REQUIRED = TRADES | TRANSFERS | ASSET_INCOME | {"VALUATION_ADJUSTMENT"}
ASSET_FORBIDDEN = frozenset({"DEPOSIT", "WITHDRAWAL"})
QUANTITY_TYPES = TRADES | TRANSFERS
PRICE_ALLOWED = TRADES | TRANSFERS
UNIT_PRICE_DECIMALS = 8
QUANTITY_DECIMALS = 12
RATE_DECIMALS = 12


class RuleViolation(ValueError):
    def __init__(self, field: str, message: str) -> None:
        super().__init__(f"{field}: {message}")
        self.field = field


@dataclass(frozen=True)
class Draft:
    transaction_type: str
    trade_date: date
    settlement_date: date | None
    asset_id: uuid.UUID | None
    quantity: Decimal | None
    unit_price: Money | None
    gross_amount: Money | None
    fees: Money | None
    taxes: Money | None
    currency: str
    fx_rate: Decimal | None
    fx_rate_as_of: datetime | None
    fx_rate_source: str | None


@dataclass(frozen=True)
class Posting:
    """A validated posting, ready to store."""

    transaction_type: str
    trade_date: date
    settlement_date: date | None
    asset_id: uuid.UUID | None
    quantity: Decimal | None
    unit_price: Decimal | None
    gross_amount: Decimal
    fees: Decimal
    taxes: Decimal
    currency: str
    fx_rate_to_portfolio_currency: Decimal
    fx_rate_as_of: datetime | None
    fx_rate_source: str | None


def normalise(draft: Draft, portfolio_currency: str, today: date) -> Posting:
    kind = draft.transaction_type
    currency = draft.currency
    places = minor_units(currency)

    def money(field: str, value: Money | None, *, allow_negative: bool = False) -> Decimal | None:
        if value is None:
            return None
        if value.currency != currency:
            raise RuleViolation(field, f"must be in the posting currency {currency}")
        if decimals_of(value.amount) > places:
            raise RuleViolation(field, f"{currency} amounts have at most {places} decimals")
        if value.amount < 0 and not allow_negative:
            raise RuleViolation(field, "must not be negative")
        return value.amount

    # Dates: no future trades (one day of slack for time zones); settlement not before the trade.
    if draft.trade_date > today + timedelta(days=1):
        raise RuleViolation("trade_date", "must not be in the future")
    if draft.settlement_date is not None and draft.settlement_date < draft.trade_date:
        raise RuleViolation("settlement_date", "must not be before the trade date")

    # Asset.
    if kind in ASSET_REQUIRED and draft.asset_id is None:
        raise RuleViolation("asset_id", f"is required for {kind}")
    if kind in ASSET_FORBIDDEN and draft.asset_id is not None:
        raise RuleViolation("asset_id", f"is not used for {kind}")

    # Quantity.
    quantity = draft.quantity
    if kind in QUANTITY_TYPES:
        if quantity is None or quantity <= 0:
            raise RuleViolation("quantity", f"is required for {kind} and must be above zero")
        if decimals_of(quantity) > QUANTITY_DECIMALS:
            raise RuleViolation("quantity", f"has at most {QUANTITY_DECIMALS} decimals")
    elif quantity is not None:
        raise RuleViolation("quantity", f"is not used for {kind}")

    # Unit price.
    unit_price = None
    if draft.unit_price is not None:
        if kind not in PRICE_ALLOWED:
            raise RuleViolation("unit_price", f"is not used for {kind}")
        if draft.unit_price.currency != currency:
            raise RuleViolation("unit_price", f"must be in the posting currency {currency}")
        if draft.unit_price.amount < 0:
            raise RuleViolation("unit_price", "must not be negative")
        if decimals_of(draft.unit_price.amount) > UNIT_PRICE_DECIMALS:
            raise RuleViolation("unit_price", f"has at most {UNIT_PRICE_DECIMALS} decimals")
        unit_price = draft.unit_price.amount
    elif kind in TRADES:
        raise RuleViolation("unit_price", f"is required for {kind}")

    # Gross amount.
    gross = money("gross_amount", draft.gross_amount, allow_negative=kind == "VALUATION_ADJUSTMENT")
    if kind in TRADES:
        if quantity is None or unit_price is None:  # checked above; keeps the types exact
            raise RuleViolation("quantity", f"is required for {kind}")
        derived = round_half_up(quantity * unit_price, places)
        if gross is None:
            gross = derived
        elif abs(gross - quantity * unit_price) > Decimal(1).scaleb(-places):
            raise RuleViolation(
                "gross_amount", f"does not match quantity x unit price ({derived} {currency})"
            )
    elif gross is None:
        raise RuleViolation("gross_amount", f"is required for {kind}")

    fees = money("fees", draft.fees) or Decimal(0)
    taxes = money("taxes", draft.taxes) or Decimal(0)

    # FX to the portfolio currency.
    rate = draft.fx_rate
    if currency == portfolio_currency:
        if rate is not None and rate != 1:
            raise RuleViolation(
                "fx_rate_to_portfolio_currency", "must be 1 in the portfolio currency"
            )
        rate = Decimal(1)
        as_of, source = None, None
    else:
        if rate is None or rate <= 0:
            raise RuleViolation(
                "fx_rate_to_portfolio_currency",
                f"is required (above zero) for a {currency} posting in a {portfolio_currency} "
                "portfolio",
            )
        if decimals_of(rate) > RATE_DECIMALS:
            raise RuleViolation(
                "fx_rate_to_portfolio_currency", f"has at most {RATE_DECIMALS} decimals"
            )
        as_of, source = draft.fx_rate_as_of, draft.fx_rate_source or "user"

    return Posting(
        transaction_type=kind,
        trade_date=draft.trade_date,
        settlement_date=draft.settlement_date,
        asset_id=draft.asset_id,
        quantity=quantity,
        unit_price=unit_price,
        gross_amount=gross,
        fees=fees,
        taxes=taxes,
        currency=currency,
        fx_rate_to_portfolio_currency=rate,
        fx_rate_as_of=as_of,
        fx_rate_source=source,
    )
