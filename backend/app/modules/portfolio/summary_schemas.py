"""Response schemas for the portfolio summaries (docs/design/portfolio-summary.md)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.core.money import DecimalString, Money
from app.modules.assets.schemas import AssetSummary


class CurrencyShare(BaseModel):
    currency: str
    native: Money = Field(description="Valued positions and cash in this currency")
    value: Money = Field(description="The same amount in the summary currency")
    share_percent: DecimalString | None = Field(
        description="Share of total value (2 decimals, adding up to 100); null when not meaningful"
    )


class Freshness(BaseModel):
    computed_at: datetime
    data_as_of: datetime = Field(description="The oldest valuation or FX rate the figures use")
    stale_fx: list[str] = Field(description="Currencies whose FX rate is older than a day")
    unconverted_currencies: list[str] = Field(
        description="Currencies without a usable FX rate; their amounts are left out of totals"
    )
    complete: bool = Field(description="False when anything is unpriced or unconverted")


class SummaryOut(BaseModel):
    """Server-authoritative totals. Money is in `currency`, rounded to its minor units."""

    portfolio_ids: list[uuid.UUID]
    currency: str
    total_value: Money = Field(description="holdings_value + cash")
    holdings_value: Money = Field(
        description="Valued positions (latest valuations until prices arrive in P08)"
    )
    cash: Money = Field(description="Cash from the ledger; negative if deposits are not recorded")
    cost_basis: Money = Field(description="Of the valued positions with a ledger cost")
    unrealized_pl: Money
    realized_pl: Money
    income: Money
    expenses: Money
    net_contributions: Money = Field(description="Deposits minus withdrawals")
    valued_positions: int
    currencies: list[CurrencyShare]
    unpriced_assets: list[AssetSummary] = Field(
        description="Open positions without a price or valuation (not in holdings_value)"
    )
    freshness: Freshness
