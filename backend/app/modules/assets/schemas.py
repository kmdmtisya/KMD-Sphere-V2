"""Request and response schemas for /api/v1/assets and /api/v1/asset-classes."""

import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ValuationMode = Literal["market", "manual"]
MetadataValue = str | int | bool


class MetadataField(BaseModel):
    type: Literal["string", "decimal", "date", "integer", "boolean"]
    required: bool


class AssetClassOut(BaseModel):
    code: str = Field(description="Stable identifier, e.g. `stock`, `real_estate`")
    name: str
    valuation_mode: ValuationMode = Field(
        description="`market`: valued from prices. `manual`: valued from user-entered valuations."
    )
    metadata_fields: dict[str, MetadataField] = Field(
        description="Facts an asset of this class may carry. Decimals are sent as strings."
    )


class AssetSummary(BaseModel):
    id: uuid.UUID
    asset_class: str = Field(description="Asset class code")
    symbol: str | None
    name: str
    subtype: str | None
    currency: str = Field(description="ISO 4217 code the asset is priced or valued in")
    country: str | None = Field(description="ISO 3166-1 alpha-2")
    is_custom: bool = Field(description="True for an asset the caller defined (only they see it)")


class AssetOut(AssetSummary):
    asset_class_name: str
    valuation_mode: ValuationMode
    metadata: dict[str, MetadataValue] = Field(
        description="Type-specific facts. Decimals are strings, dates are YYYY-MM-DD."
    )


class AssetSearchResult(BaseModel):
    items: list[AssetSummary]


class AssetCreate(BaseModel):
    """A user-defined asset (a property, a private business, a SACCO share). Only its creator sees
    it. Listed instruments come from market data providers, not from this endpoint."""

    model_config = ConfigDict(extra="forbid")

    asset_class: str = Field(min_length=2, max_length=40, pattern=r"^[a-z][a-z0-9_]{1,39}$")
    name: str = Field(min_length=1, max_length=200)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    symbol: str | None = Field(default=None, min_length=1, max_length=32)
    subtype: str | None = Field(default=None, min_length=1, max_length=64)
    country: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    metadata: dict[str, Any] = Field(default_factory=dict, max_length=30)
