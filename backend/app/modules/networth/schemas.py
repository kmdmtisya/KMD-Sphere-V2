"""Request and response schemas for /api/v1/liabilities and /api/v1/net-worth (P06-T07)."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal, Self

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.money import DecimalString, Money, decimals_of
from app.modules.forecasting.limits import TARGET, Limit
from app.modules.forecasting.schemas import check_money
from app.modules.fx.schemas import ReportingOut

LiabilityType = Literal[
    "mortgage",
    "personal_loan",
    "car_loan",
    "student_loan",
    "business_loan",
    "credit_card",
    "other",
]
BALANCE = Limit(Decimal(0), TARGET.maximum)


def _rate(value: Decimal) -> Decimal:
    if decimals_of(value) > 2 or not Decimal(0) <= value <= Decimal(100):
        raise ValueError("must be between 0 and 100 with at most 2 decimals")
    return value


InterestRate = Annotated[DecimalString, AfterValidator(_rate)]


def _trimmed(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        raise ValueError("must not be blank")
    return value


class LiabilityCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    liability_type: LiabilityType
    balance: Money = Field(
        description=f"Outstanding amount (0 to {BALANCE.maximum}), in the liability's currency"
    )
    balance_as_of: date = Field(description="When the balance applied (today or earlier)")
    interest_rate_percent: InterestRate | None = Field(
        default=None, description="Annual interest rate in percent (0 to 100), for reference"
    )
    asset_id: uuid.UUID | None = Field(
        default=None, description="The asset securing it (for example a mortgaged property)"
    )

    _name = field_validator("name")(_trimmed)

    @model_validator(mode="after")
    def _amount(self) -> Self:
        check_money(self.balance, BALANCE, "balance")
        return self


class LiabilityUpdate(BaseModel):
    """PATCH body: any subset. Send `asset_id` or `interest_rate_percent` as null to clear it."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=100)
    liability_type: LiabilityType | None = None
    balance: Money | None = None
    balance_as_of: date | None = None
    interest_rate_percent: InterestRate | None = None
    asset_id: uuid.UUID | None = None

    _name = field_validator("name")(_trimmed)

    @model_validator(mode="after")
    def _amount(self) -> Self:
        if self.balance is not None:
            check_money(self.balance, BALANCE, "balance")
        return self


class LiabilityOut(BaseModel):
    id: uuid.UUID
    name: str
    liability_type: LiabilityType
    balance: Money
    balance_as_of: date
    interest_rate_percent: DecimalString | None
    asset_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class AssetClassShare(BaseModel):
    asset_class: str
    value: Money
    share_percent: DecimalString | None = Field(
        description="Share of assets (2 decimals, adding up to 100); null when not meaningful"
    )


class LiabilityTypeTotal(BaseModel):
    liability_type: LiabilityType
    value: Money
    count: int


class LiabilityLine(BaseModel):
    id: uuid.UUID
    name: str
    liability_type: LiabilityType
    balance: Money = Field(description="In the liability's own currency")
    value: Money | None = Field(
        description="In the net-worth currency at the latest rate; null without a rate"
    )
    balance_as_of: date


class FxRateUsed(BaseModel):
    currency: str = Field(description="Converted from this currency into the net-worth currency")
    rate: DecimalString
    as_of: datetime = Field(description="When the rate was valid (the provider's timestamp)")
    provider: str
    stale: bool
    inverted: bool = Field(description="Derived as 1 / rate from the opposite pair")


class NetWorthFreshness(BaseModel):
    computed_at: datetime
    data_as_of: datetime = Field(description="The oldest valuation or rate the assets use")
    complete: bool = Field(
        description="False when assets are unpriced, or amounts in a currency without a rate are "
        "left out"
    )
    unpriced_assets: int
    unconverted_currencies: list[str]
    stale_fx: list[str]
    oldest_liability_balance: date | None = Field(
        description="The oldest balance date of the liabilities (user-entered figures)"
    )


class NetWorthOut(BaseModel):
    currency: str
    assets: Money = Field(description="Total value of the user's active portfolios")
    liabilities: Money = Field(description="Sum of the converted liabilities")
    net_worth: Money = Field(description="assets - liabilities")
    assets_by_class: list[AssetClassShare]
    liabilities_by_type: list[LiabilityTypeTotal]
    liability_lines: list[LiabilityLine]
    fx_rates: list[FxRateUsed] = Field(description="Every conversion into the net-worth currency")
    freshness: NetWorthFreshness
    as_of: datetime
    reporting: ReportingOut | None = Field(
        default=None, description="The rate snapshot the figures were converted with (P11-T06)"
    )
