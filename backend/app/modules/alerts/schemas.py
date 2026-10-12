"""Request and response schemas for /api/v1/watchlist, /api/v1/alerts and /api/v1/alert-preferences
(P08-T07). Prices and percentages travel as strings (ADR-0003)."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.money import DecimalString, Money
from app.modules.assets.schemas import AssetSummary

AlertType = Literal["price_above", "price_below", "allocation_above"]
AlertStatus = Literal["active", "triggered", "paused"]


# ------------------------------------------------------------------------------- watchlist
class WatchlistAdd(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: uuid.UUID


class LatestPriceOut(BaseModel):
    price: DecimalString = Field(
        description="Per unit in the asset's own currency, unrounded (a unit price can have "
        "more decimals than the currency)"
    )
    currency: str
    as_of: datetime
    provider: str
    stale: bool = Field(description="Older than its freshness window (still shown)")


class WatchlistItemOut(BaseModel):
    asset: AssetSummary
    added_at: datetime
    latest_price: LatestPriceOut | None = Field(
        description="The latest stored market price; null when there is none (nothing is guessed)"
    )


# ---------------------------------------------------------------------------------- alerts
class AlertCreate(BaseModel):
    """A price alert needs `asset_id` and `threshold_price` (in the asset's own currency); an
    allocation alert needs `portfolio_id`, `asset_class` and `threshold_percent` (above 0, at most
    100)."""

    model_config = ConfigDict(extra="forbid")

    alert_type: AlertType
    asset_id: uuid.UUID | None = None
    threshold_price: Money | None = None
    portfolio_id: uuid.UUID | None = None
    asset_class: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]{1,39}$")
    threshold_percent: DecimalString | None = None
    note: str | None = Field(default=None, min_length=1, max_length=200)

    @field_validator("note")
    @classmethod
    def _trimmed(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if not v:
            raise ValueError("must not be blank")
        return v

    @model_validator(mode="after")
    def _shape(self) -> Self:
        if self.alert_type in ("price_above", "price_below"):
            if self.asset_id is None or self.threshold_price is None:
                raise ValueError("a price alert needs asset_id and threshold_price")
            if (
                self.portfolio_id is not None
                or self.asset_class is not None
                or self.threshold_percent is not None
            ):
                raise ValueError("a price alert takes only asset_id and threshold_price")
            if self.threshold_price.amount <= 0:
                raise ValueError("threshold_price must be above zero")
        else:
            if (
                self.portfolio_id is None
                or self.asset_class is None
                or self.threshold_percent is None
            ):
                raise ValueError(
                    "an allocation alert needs portfolio_id, asset_class and threshold_percent"
                )
            if self.asset_id is not None or self.threshold_price is not None:
                raise ValueError("an allocation alert takes no asset_id or threshold_price")
            if not Decimal(0) < self.threshold_percent <= Decimal(100):
                raise ValueError("threshold_percent must be above 0 and at most 100")
        return self


class AlertUpdate(BaseModel):
    """Pause, re-arm (`active`) or change the threshold or note. The kind of alert and what it
    watches cannot change: make a new alert."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["active", "paused"] | None = Field(
        default=None, description="`active` re-arms a triggered alert"
    )
    threshold_price: Money | None = None
    threshold_percent: DecimalString | None = None
    note: str | None = Field(default=None, min_length=1, max_length=200)

    @field_validator("note")
    @classmethod
    def _trimmed(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if not v:
            raise ValueError("must not be blank")
        return v


class AlertOut(BaseModel):
    id: uuid.UUID
    alert_type: AlertType
    status: AlertStatus
    asset: AssetSummary | None
    threshold_price: Money | None
    portfolio_id: uuid.UUID | None
    asset_class: str | None
    threshold_percent: DecimalString | None
    note: str | None
    created_at: datetime
    triggered_at: datetime | None


class AlertEventOut(BaseModel):
    id: uuid.UUID
    alert_id: uuid.UUID
    alert_type: AlertType
    observed_value: DecimalString = Field(
        description="The price that crossed the threshold, or the class's share (%)"
    )
    observed_as_of: datetime = Field(description="When the observed value applied")
    triggered_at: datetime
    seen_at: datetime | None


class AlertEventPage(BaseModel):
    items: list[AlertEventOut]


# ---------------------------------------------------------------------------- preferences
class AlertPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alerts_enabled: bool = Field(description="Master switch: off means no alert is evaluated")
    price_alerts_enabled: bool
    allocation_alerts_enabled: bool
