"""Request and response schemas for /api/v1/portfolios/{portfolio_id}/transactions."""

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.core.money import CURRENCY_PATTERN, DecimalString, Money

TransactionType = Literal[
    "BUY",
    "SELL",
    "DEPOSIT",
    "WITHDRAWAL",
    "DIVIDEND",
    "INTEREST",
    "COUPON",
    "RENT",
    "DISTRIBUTION",
    "FEE",
    "TAX",
    "TRANSFER_IN",
    "TRANSFER_OUT",
    "VALUATION_ADJUSTMENT",
]


class TransactionCreate(BaseModel):
    """A ledger posting. See `app/modules/transactions/rules.py` for the rules per type. Amounts
    are Money objects in the posting `currency`; quantities and rates are strings."""

    model_config = ConfigDict(extra="forbid")

    transaction_type: TransactionType
    trade_date: date
    settlement_date: date | None = None
    asset_id: uuid.UUID | None = None
    currency: str = Field(pattern=CURRENCY_PATTERN, description="Currency of the posting")
    quantity: DecimalString | None = Field(
        default=None, description="Units, for trades and transfers"
    )
    unit_price: Money | None = None
    gross_amount: Money | None = Field(
        default=None, description="For BUY/SELL derived from quantity x unit price when omitted"
    )
    fees: Money | None = None
    taxes: Money | None = None
    fx_rate_to_portfolio_currency: DecimalString | None = Field(
        default=None,
        description="1 unit of the posting currency in portfolio currency units. "
        "Required when the posting currency differs from the portfolio's.",
    )
    fx_rate_as_of: AwareDatetime | None = Field(
        default=None, description="When the rate was valid (with a time zone)"
    )
    fx_rate_source: str | None = Field(default=None, min_length=1, max_length=32)
    note: str | None = Field(default=None, min_length=1, max_length=500)


class ReversalCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: str | None = Field(default=None, min_length=1, max_length=500)


class TransactionOut(BaseModel):
    id: uuid.UUID
    portfolio_id: uuid.UUID
    transaction_type: TransactionType
    trade_date: date
    settlement_date: date | None
    asset_id: uuid.UUID | None
    currency: str
    quantity: DecimalString | None
    unit_price: Money | None
    gross_amount: Money
    fees: Money
    taxes: Money
    fx_rate_to_portfolio_currency: DecimalString
    fx_rate_as_of: datetime | None
    fx_rate_source: str | None
    source: Literal["manual", "import", "system"]
    idempotency_key: str | None
    reverses_transaction_id: uuid.UUID | None = Field(
        description="Set on a reversal: the entry it cancels"
    )
    reversed_by_transaction_id: uuid.UUID | None = Field(
        description="Set when this entry has been cancelled by a reversal"
    )
    note: str | None
    created_at: datetime


class TransactionPage(BaseModel):
    items: list[TransactionOut]
    next_cursor: str | None = Field(
        description="Pass as `cursor` for the next page; null at the end"
    )
