"""Request and response schemas for /api/v1/me."""

import uuid
from datetime import datetime
from typing import Literal
from zoneinfo import available_timezones

from pydantic import BaseModel, ConfigDict, Field, field_validator

DashboardSectionName = Literal["wealthSummary", "metrics", "insight", "goals"]


class DashboardLayout(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order: list[DashboardSectionName] = Field(max_length=10)
    hidden: list[DashboardSectionName] = Field(default_factory=list, max_length=10)

    @field_validator("order")
    @classmethod
    def _no_duplicates(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("sections must not repeat")
        return value


class Preferences(BaseModel):
    """UI preferences stored for the user. Unknown keys are rejected."""

    model_config = ConfigDict(extra="forbid")

    theme_mode: Literal["system", "light", "dark"] | None = None
    dashboard_layout: DashboardLayout | None = None


class PreferencesUpdate(BaseModel):
    """PATCH body: any subset of the fields below. Omitted fields keep their value; sending null
    clears a UI preference."""

    model_config = ConfigDict(extra="forbid")

    theme_mode: Literal["system", "light", "dark"] | None = None
    dashboard_layout: DashboardLayout | None = None
    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    base_currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    locale: str | None = Field(default=None, pattern=r"^[a-z]{2,3}([_-][A-Za-z0-9]{2,8})*$")
    timezone: str | None = Field(default=None, max_length=64)

    @field_validator("timezone")
    @classmethod
    def _known_timezone(cls, value: str | None) -> str | None:
        if value is not None and value not in available_timezones():
            raise ValueError("unknown IANA time zone")
        return value


class MeResponse(BaseModel):
    id: uuid.UUID
    email: str | None
    email_verified: bool
    display_name: str | None
    base_currency: str
    locale: str
    timezone: str
    preferences: Preferences
    created_at: datetime
