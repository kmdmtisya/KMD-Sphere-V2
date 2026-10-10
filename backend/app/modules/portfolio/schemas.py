"""Request and response schemas for /api/v1/portfolios."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

PortfolioType = Literal["personal", "family", "retirement", "geographic", "strategy"]


def _trimmed(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        raise ValueError("must not be blank")
    return value


class PortfolioCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    base_currency: str = Field(
        pattern=r"^[A-Z]{3}$",
        description="ISO 4217. Fixed once the portfolio exists: postings are converted into it.",
    )
    portfolio_type: PortfolioType = "personal"
    description: str | None = Field(default=None, max_length=500)

    _name = field_validator("name")(_trimmed)
    _description = field_validator("description")(_trimmed)


class PortfolioUpdate(BaseModel):
    """PATCH body: any subset. The base currency cannot change."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=100)
    portfolio_type: PortfolioType | None = None
    description: str | None = Field(default=None, max_length=500)

    _name = field_validator("name")(_trimmed)
    _description = field_validator("description")(_trimmed)


class PortfolioOut(BaseModel):
    id: uuid.UUID
    name: str
    base_currency: str
    portfolio_type: PortfolioType
    description: str | None
    archived_at: datetime | None = Field(description="Set when archived; archived is read-only")
    created_at: datetime
    updated_at: datetime
