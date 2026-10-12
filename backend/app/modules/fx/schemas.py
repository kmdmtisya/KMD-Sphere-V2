"""Response schemas for /api/v1/fx (P11-T03). Rates travel as strings (ADR-0003)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.core.money import DecimalString

Status = Literal["current", "cached", "stale", "unavailable"]
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
