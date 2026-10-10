"""Request and response schemas for /api/v1/portfolios/{portfolio_id}/transactions."""

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.core.money import CURRENCY_PATTERN, DecimalString, Money
from app.modules.assets.schemas import AssetSummary

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


class HoldingOut(BaseModel):
    """A position derived from the ledger (weighted average cost, ADR-0012). Money is in the
    portfolio's base currency, converted at each posting's own rate."""

    asset: AssetSummary
    quantity: DecimalString
    average_cost: Money | None = Field(
        description="Cost per unit (up to 8 decimals); null when no units are held"
    )
    cost_basis: Money
    realized_pl: Money = Field(description="Profit or loss realised by sales")
    income: Money = Field(description="Dividends, coupons, rent, distributions and interest")
    expenses: Money = Field(description="Fees and taxes charged to the asset, incl. withholding")
    last_transaction_at: datetime | None
    computed_at: datetime
    value: Money | None = Field(
        description="Current value in the portfolio currency (latest valuation at the latest FX "
        "rate; market prices from P08). Null when unpriced, unconverted or closed."
    )
    native_value: Money | None = Field(description="The same value in its own currency")
    value_as_of: datetime | None = Field(description="When that value applied")
    value_source: Literal["valuation"] | None = Field(
        description="Where the value comes from (`price` arrives with market data, P08)"
    )
