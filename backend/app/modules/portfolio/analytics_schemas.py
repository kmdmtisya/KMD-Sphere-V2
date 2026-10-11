"""Response schemas of the portfolio analytics API (P06-T09). Amounts are Money at the currency's
minor units; rates and shares are percentages to 2 decimals (ADR-0006). Methods:
docs/design/performance.md, allocation.md and risk.md."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.core.money import DecimalString, Money, round_half_up

PAST_NOTICE = "Past performance is not a reliable indicator of future results."


def percent(fraction: Decimal | None) -> Decimal | None:
    """A fraction (0.0825) as a percentage to 2 decimals (8.25), half-up."""
    return None if fraction is None else round_half_up(fraction * 100, 2)


class MoneyWeightedOut(BaseModel):
    status: Literal["ok", "insufficient_flows", "no_sign_change", "no_rate_in_range"]
    annual_return_percent: DecimalString | None = Field(
        description="XIRR (actual/365), annualised even for periods under a year"
    )
    unique: bool = Field(description="The flows change sign once, so no other rate solves them")


class PerformanceOut(BaseModel):
    portfolio_id: uuid.UUID
    currency: str
    as_of: date
    total_value: Money
    contributions: Money = Field(description="Deposits and transfers in")
    withdrawals: Money = Field(description="Withdrawals and transfers out")
    net_invested: Money
    profit_loss: Money = Field(description="total_value - net_invested")
    return_percent: DecimalString | None = Field(
        description="profit_loss / contributions; null when nothing was put in"
    )
    money_weighted: MoneyWeightedOut
    realized_pl: Money
    unrealized_pl: Money
    income: Money
    expenses: Money
    complete: bool = Field(description="False when assets are unpriced or currencies unconverted")
    first_flow: date | None
    notice: str


class SliceOut(BaseModel):
    key: str | None = Field(
        description="Asset class code, currency, ISO country or sector; null is unclassified"
    )
    value: Money
    weight_percent: DecimalString | None = Field(
        description="2 decimals, adding up to 100; null when not meaningful (negative parts)"
    )
    parts: int


class DimensionOut(BaseModel):
    slices: list[SliceOut]
    hhi: DecimalString | None = Field(description="Herfindahl index of the slices (0 to 1)")


class ConcentrationOut(BaseModel):
    positions: int
    hhi: DecimalString | None = Field(description="Herfindahl index of the positions (0 to 1)")
    effective_positions: DecimalString | None
    top_1_percent: DecimalString | None
    top_3_percent: DecimalString | None
    top_5_percent: DecimalString | None
    largest: str | None = Field(description="Asset id, or cash:<currency>")


class AllocationOut(BaseModel):
    portfolio_id: uuid.UUID
    currency: str
    total: Money
    asset_class: DimensionOut
    currency_exposure: DimensionOut
    country: DimensionOut
    sector: DimensionOut
    concentration: ConcentrationOut
    complete: bool
    unpriced_assets: int


class SeriesPointOut(BaseModel):
    on: date
    value: Money
    complete: bool


class DrawdownOut(BaseModel):
    depth_percent: DecimalString = Field(description="Fall from the peak, <= 0")
    peak: date
    trough: date
    recovered: date | None


class RiskOut(BaseModel):
    portfolio_id: uuid.UUID
    currency: str
    frequency: Literal["daily", "weekly", "monthly"]
    start: date
    end: date
    status: Literal["ok", "insufficient_data", "incomplete_data", "undefined_period"]
    points: list[SeriesPointOut]
    returns: int = Field(description="Number of period returns measured")
    volatility_percent: DecimalString | None = Field(description="Annualised")
    period_volatility_percent: DecimalString | None
    max_drawdown: DrawdownOut | None
    time_weighted_return_percent: DecimalString | None
    time_weighted_annualized_percent: DecimalString | None = Field(
        description="Only for ranges of at least a year"
    )
    incomplete_points: int
    as_of: datetime
    notice: str
