"""Response schemas for /api/v1/fx-rates and /api/v1/assets/{id}/prices."""

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.core.money import DecimalString


class FxQuoteOut(BaseModel):
    base_currency: str
    quote_currency: str
    rate: DecimalString = Field(description="1 unit of base_currency in quote_currency units")
    as_of: datetime = Field(description="When the rate was valid (the provider's timestamp)")
    provider: str
    data_type: Literal["indicative_rate"] = Field(
        default="indicative_rate",
        description="Reference rates for reporting-currency conversion, not tradable quotes: show "
        "them as indicative and never use them for transactions (ADR-0014)",
    )
    inverted: bool = Field(description="Derived as 1 / rate from the opposite pair")
    stale: bool = Field(description="Older than one day (provisional threshold, DEC-26)")
    rule: Literal["historical", "latest"] = Field(
        description="`historical`: the rate for the given date; `latest`: the most recent rate"
    )


class UnitPriceOut(BaseModel):
    """A price per unit, unrounded (a unit price can have more decimals than the currency)."""

    price: DecimalString
    currency: str
    as_of: datetime = Field(description="When the price was valid (the provider's timestamp)")
    provider: str
    stale: bool = Field(description="Older than its freshness window; shown, and labelled")


class PricePointOut(BaseModel):
    on: date = Field(description="The trading day of the close")
    close: DecimalString
    provider: str


class AssetPricesOut(BaseModel):
    """The stored market prices of one asset. Nothing is interpolated: days without a stored close
    are missing, and an asset without a market price has `latest: null` and no points."""

    asset_id: uuid.UUID
    currency: str
    latest: UnitPriceOut | None
    points: list[PricePointOut]
    data_type: Literal["delayed"] = Field(
        default="delayed",
        description="Stored prices from a data provider, not live or executable quotes",
    )
