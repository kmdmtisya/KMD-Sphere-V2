"""Request and response schemas for /api/v1/portfolios/{portfolio_id}/valuations."""

import uuid
from datetime import datetime

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from app.core.money import Money


def _label(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        raise ValueError("must not be blank")
    return value


class ValuationCreate(BaseModel):
    """A user-entered value of an asset at a moment (a property, a business, a pension)."""

    model_config = ConfigDict(extra="forbid")

    asset_id: uuid.UUID
    value: Money
    as_of: AwareDatetime = Field(description="When the value applied (with a time zone)")
    source: str = Field(
        min_length=1,
        max_length=64,
        description='Where the value comes from, e.g. "owner estimate", "bank statement"',
    )
    note: str | None = Field(default=None, max_length=500)

    _source = field_validator("source")(_label)
    _note = field_validator("note")(_label)


class ValuationUpdate(BaseModel):
    """Corrects a valuation. The asset and the as-of time cannot change: post a new valuation."""

    model_config = ConfigDict(extra="forbid")

    value: Money | None = None
    source: str | None = Field(default=None, min_length=1, max_length=64)
    note: str | None = Field(default=None, max_length=500)

    _source = field_validator("source")(_label)
    _note = field_validator("note")(_label)


class ValuationOut(BaseModel):
    id: uuid.UUID
    portfolio_id: uuid.UUID
    asset_id: uuid.UUID
    value: Money
    as_of: datetime
    source: str
    note: str | None
    created_at: datetime
    updated_at: datetime


class ValuationPage(BaseModel):
    items: list[ValuationOut]
    next_cursor: str | None = Field(
        description="Pass as `cursor` for the next page; null at the end"
    )
