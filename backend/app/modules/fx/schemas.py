"""Response schemas for /api/v1/fx (P11-T03). Rates travel as strings (ADR-0003)."""

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.money import CURRENCY_PATTERN, DecimalString, Money

Status = Literal["current", "cached", "stale", "unavailable"]
Concept = Literal["transaction", "historical_valuation", "current_reporting"]
RateType = Literal["mid_market", "indicative", "delayed"]


class FxRateLineOut(BaseModel):
    """One currency against the pivot: 1 pivot = `rate` currency."""

    currency: str
    status: Status = Field(
        description="current: within the provider's update window; cached: older, from the last "
        "successful refresh; stale: older still, shown with its age; unavailable: no rate stored"
    )
    rate: DecimalString | None = None
    provider: str | None = None
    rate_type: RateType | None = None
    rate_timestamp: datetime | None = Field(
        default=None, description="When the provider published the rate"
    )
    retrieved_at: datetime | None = Field(default=None, description="When WealthSphere fetched it")
    path: list[str] | None = Field(
        default=None, description="The currencies a derived rate went through, in order"
    )
    age_seconds: int | None = None


class FxStatusOut(BaseModel):
    pivot_currency: str
    checked_at: datetime
    rates: list[FxRateLineOut]


class FxProviderAttemptOut(BaseModel):
    provider: str
    supplied: list[str]
    unsupported: list[str]
    failed: bool


class FxRefreshOut(BaseModel):
    refreshed: bool = Field(
        description="False when a refresh already ran in this window: the stored rates are "
        "returned and no provider is called"
    )
    window: str
    attempts: list[FxProviderAttemptOut]
    missing: list[str] = Field(description="Currencies no provider could supply")
    status: FxStatusOut


# ------------------------------------------------------------------------- P11-T04 conversion
class CurrencyOut(BaseModel):
    code: str
    name: str
    symbol: str
    decimal_places: int = Field(description="The precision converted amounts are rounded to")


class SnapshotRateOut(BaseModel):
    """1 `base` = `rate` `quote`, from the snapshot's stored rates."""

    base: str
    quote: str
    rate: DecimalString
    path: list[str] | None = Field(
        default=None, description="Currencies a derived rate went through, e.g. AED, USD, KES"
    )
    status: Status
    rate_timestamp: datetime | None = Field(
        default=None, description="When the oldest stored rate used was published"
    )
    providers: list[str]


class FxRatesOut(BaseModel):
    concept: Concept = "current_reporting"
    snapshot_id: uuid.UUID = Field(description="Every rate here comes from this snapshot")
    base: str
    rates: list[SnapshotRateOut]
    unavailable: list[str] = Field(description="Requested currencies without a rate")


class ConvertIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: Money
    to: str = Field(pattern=CURRENCY_PATTERN, description="Target currency (ISO 4217)")
    snapshot_id: uuid.UUID | None = Field(
        default=None,
        description="Convert with the rates of an earlier snapshot (for example a report's); "
        "omit for the latest rates",
    )
    on: date | None = Field(
        default=None,
        description="Convert with the historical rate of this day (P11-T05) instead of the "
        "current reporting rate; cannot be combined with snapshot_id",
    )


class ConvertOut(BaseModel):
    source: Money
    converted: Money = Field(description="Rounded once, half-up, to the target's decimal places")
    rate: DecimalString
    path: list[str] | None = None
    concept: Concept = Field(
        description="current_reporting (a snapshot) or historical_valuation (a past day)"
    )
    snapshot_id: uuid.UUID | None = Field(
        default=None, description="The snapshot used; none for a historical conversion"
    )
    on: date | None = None
    status: Status
    rate_timestamp: datetime | None = None
    providers: list[str]
    notice: str = Field(
        default="Indicative rate for information; not a quote for a transaction.",
        description="Shown with every conversion",
    )


# ------------------------------------------------------------------------- P11-T05 history
class FxHistoryPointOut(BaseModel):
    date: date
    rate: DecimalString | None = None
    rate_timestamp: datetime | None = None
    provider: str | None = None
    path: list[str] | None = None
    rate_missing: bool = Field(description="No usable rate for this day; nothing was substituted")
    from_earlier_day: bool = Field(
        description="The rate was published on an earlier day within the 7-day window "
        "(a weekend or holiday)"
    )


class FxHistoryOut(BaseModel):
    concept: Concept = "historical_valuation"
    base: str
    quote: str
    points: list[FxHistoryPointOut]
    missing_days: int
