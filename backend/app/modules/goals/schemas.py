"""Request and response schemas for /api/v1/goals (P06-T06). Assumption limits are the forecast
limits (app/modules/forecasting/limits.py), shared with the mobile calculator."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.money import DecimalString, Money
from app.modules.forecasting import limits
from app.modules.forecasting.engine import Frequency
from app.modules.forecasting.schemas import (
    FeePercent,
    GrowthPercent,
    InflationPercent,
    ReturnPercent,
    check_money,
)
from app.modules.fx.schemas import ReportingOut

GoalType = Literal[
    "wealth", "retirement", "education", "house_deposit", "business_capital", "custom"
]
Status = Literal["on_track", "behind"]


def _trimmed(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        raise ValueError("must not be blank")
    return value


class GoalReturns(BaseModel):
    """The annual return of each scenario (conservative <= base <= growth). Only base is
    required; the goal's status is measured against it."""

    model_config = ConfigDict(extra="forbid")

    base: ReturnPercent
    conservative: ReturnPercent | None = None
    growth: ReturnPercent | None = None

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.conservative is not None and self.conservative > self.base:
            raise ValueError("conservative must not exceed base")
        if self.growth is not None and self.growth < self.base:
            raise ValueError("growth must not be below base")
        return self

    def as_dict(self) -> dict[str, Decimal]:
        """Scenario kind -> return, in the order conservative, base, growth."""
        values = {"conservative": self.conservative, "base": self.base, "growth": self.growth}
        return {k: v for k, v in values.items() if v is not None}


class GoalAssumptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contribution: Money = Field(
        description="Paid at the end of each contribution period in the first year, then increased "
        f"yearly by contribution_growth_percent (0 to {limits.CONTRIBUTION.maximum}; in the "
        "target's currency)"
    )
    contribution_frequency: Frequency = Frequency.MONTHLY
    contribution_growth_percent: GrowthPercent = Decimal(0)
    inflation_percent: InflationPercent = Decimal(0)
    annual_fee_percent: FeePercent = Decimal(0)
    compounding_frequency: Frequency = Frequency.MONTHLY
    returns: GoalReturns

    @model_validator(mode="after")
    def _amount(self) -> Self:
        check_money(self.contribution, limits.CONTRIBUTION, "contribution")
        return self


class GoalCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    goal_type: GoalType = "wealth"
    target: Money = Field(
        description=f"The value to reach ({limits.TARGET.minimum} to {limits.TARGET.maximum})"
    )
    target_date: date = Field(description="After today and at most 60 years ahead")
    target_in_todays_money: bool = Field(
        default=False,
        strict=True,
        description="True: the target is in today's money and grows with inflation to the date",
    )
    portfolio_id: uuid.UUID | None = Field(
        default=None, description="The portfolio that funds the goal; null for all portfolios"
    )
    assumptions: GoalAssumptions

    _name = field_validator("name")(_trimmed)

    @model_validator(mode="after")
    def _amounts(self) -> Self:
        check_money(self.target, limits.TARGET, "target")
        if self.assumptions.contribution.currency != self.target.currency:
            raise ValueError("assumptions.contribution: must be in the target's currency")
        return self


class GoalUpdate(BaseModel):
    """PATCH body: any subset. `assumptions` replaces all assumptions at once. Send
    `portfolio_id: null` to fund the goal from all portfolios."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=100)
    goal_type: GoalType | None = None
    target: Money | None = None
    target_date: date | None = None
    target_in_todays_money: bool | None = Field(default=None, strict=True)
    portfolio_id: uuid.UUID | None = None
    assumptions: GoalAssumptions | None = None

    _name = field_validator("name")(_trimmed)

    @model_validator(mode="after")
    def _amounts(self) -> Self:
        if self.target is not None:
            check_money(self.target, limits.TARGET, "target")
        return self


class GoalOut(BaseModel):
    id: uuid.UUID
    name: str
    goal_type: GoalType
    target: Money
    target_date: date
    target_in_todays_money: bool
    portfolio_id: uuid.UUID | None
    assumptions: GoalAssumptions
    created_at: datetime
    updated_at: datetime


class ScenarioOutcomeOut(BaseModel):
    kind: Literal["conservative", "base", "growth"]
    annual_return_percent: DecimalString
    projected_value: Money = Field(description="Projected value on the target date")
    projected_value_real: Money = Field(description="The same in today's money")
    reaches_target: bool


class GoalProgressOut(BaseModel):
    goal_id: uuid.UUID
    name: str
    status: Status = Field(description="Under the base scenario's assumptions; an estimate")
    reached: bool = Field(description="The current value already meets the target")
    overdue: bool = Field(description="The target date has passed without reaching the target")
    progress_percent: DecimalString = Field(description="Current value / target, 0 to 100")
    current_value: Money = Field(
        description="Value of the funding portfolios, in the target's currency"
    )
    gap: Money = Field(description="Target - current value, at least 0")
    target: Money
    target_date: date
    target_in_todays_money: bool
    months_left: int = Field(description="Whole months until the target date (negative after it)")
    scenarios: list[ScenarioOutcomeOut]
    required_contribution: Money | None = Field(
        description="Per contribution period in the first year to reach the target by the date "
        "(base scenario); null when reached, overdue, or no contribution falls before the date"
    )
    estimated_completion: date | None = Field(
        description="When the base scenario reaches the target with the current contribution; null "
        "if not within 100 years"
    )
    value_complete: bool = Field(
        description="False when assets are unpriced or currencies unconverted (value understated)"
    )
    value_as_of: datetime = Field(description="The oldest input of the current value")
    assumptions: GoalAssumptions
    as_of: datetime
    notice: str

    target_in_reporting: Money | None = Field(
        default=None, description="The target in the reporting currency (snapshot rate)"
    )
    current_value_in_reporting: Money | None = Field(
        default=None, description="The current value in the reporting currency (snapshot rate)"
    )
    reporting: ReportingOut | None = None


class GoalSummaryItem(BaseModel):
    id: uuid.UUID
    name: str
    progress_percent: DecimalString
    status: Status
    reached: bool
    target: Money
    target_date: date
    target_in_reporting: Money | None = Field(
        default=None,
        description="The target shown in the reporting currency at the snapshot rate; the goal "
        "itself stays in its own currency",
    )


class GoalsSummaryOut(BaseModel):
    on_track: int
    total: int
    items: list[GoalSummaryItem]
    as_of: datetime
    notice: str
    reporting: ReportingOut | None = None
