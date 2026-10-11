"""Request and response schemas for /api/v1/forecasts (P06-T02).

Field names follow the mobile forecast DTOs (docs/contracts/dto-mapping.md). Every limit comes
from limits.py, which the mobile calculator mirrors."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    WithJsonSchema,
    model_validator,
)

from app.core.money import DECIMAL_PATTERN, DecimalString, Money, MoneyAmount, decimals_of
from app.core.money import minor_units as currency_minor_units
from app.modules.forecasting import limits
from app.modules.forecasting.engine import Frequency
from app.modules.forecasting.limits import Limit


def _within(limit: Limit) -> AfterValidator:
    def check(value: Decimal) -> Decimal:
        if decimals_of(value) > limit.decimals:
            raise ValueError(f"at most {limit.decimals} decimal places")
        if not limit.minimum <= value <= limit.maximum:
            raise ValueError(f"must be between {limit.minimum} and {limit.maximum}")
        return value

    return AfterValidator(check)


def _schema(limit: Limit, what: str) -> WithJsonSchema:
    return WithJsonSchema(
        {
            "type": "string",
            "pattern": DECIMAL_PATTERN,
            "description": f"{what}, in percent ({limit.minimum} to {limit.maximum}, at most "
            f"{limit.decimals} decimals)",
            "examples": ["8.00"],
        }
    )


ReturnPercent = Annotated[
    DecimalString,
    _within(limits.RETURN_RATE),
    _schema(limits.RETURN_RATE, "Assumed nominal annual return"),
]
GrowthPercent = Annotated[
    DecimalString,
    _within(limits.CONTRIBUTION_GROWTH),
    _schema(limits.CONTRIBUTION_GROWTH, "Yearly increase of the contribution"),
]
InflationPercent = Annotated[
    DecimalString,
    _within(limits.INFLATION),
    _schema(limits.INFLATION, "Assumed yearly inflation"),
]
FeePercent = Annotated[
    DecimalString,
    _within(limits.ANNUAL_FEE),
    _schema(limits.ANNUAL_FEE, "Yearly fee on the balance"),
]
Years = Annotated[
    int,
    Field(
        strict=True,
        ge=int(limits.YEARS.minimum),
        le=int(limits.YEARS.maximum),
        description=f"Horizon in whole years ({limits.YEARS.minimum} to {limits.YEARS.maximum})",
    ),
]


def _check_money(value: Money, limit: Limit, field: str) -> None:
    if decimals_of(value.amount) > currency_minor_units(value.currency):
        raise ValueError(
            f"{field}: {value.currency} amounts have at most "
            f"{currency_minor_units(value.currency)} decimals"
        )
    if not limit.minimum <= value.amount <= limit.maximum:
        raise ValueError(f"{field}: must be between {limit.minimum} and {limit.maximum}")


class ForecastAssumptions(BaseModel):
    """Inputs shared by every forecast."""

    model_config = ConfigDict(extra="forbid")

    initial_investment: Money = Field(
        description=f"Invested at the start (0 to {limits.INITIAL_INVESTMENT.maximum})"
    )
    annual_return_percent: ReturnPercent
    years: Years
    contribution_growth_percent: GrowthPercent = Decimal(0)
    inflation_percent: InflationPercent = Decimal(0)
    annual_fee_percent: FeePercent = Decimal(0)
    compounding_frequency: Frequency = Frequency.MONTHLY
    contribution_frequency: Frequency = Frequency.MONTHLY

    @property
    def currency(self) -> str:
        return self.initial_investment.currency

    def _check_amounts(self, amounts: dict[str, tuple[Money, Limit]]) -> None:
        for field, (money, limit) in amounts.items():
            _check_money(money, limit, field)
            if money.currency != self.currency:
                raise ValueError(f"{field}: must be in the same currency as initial_investment")


class CompoundForecastIn(ForecastAssumptions):
    contribution: Money = Field(
        description="Paid at the end of each contribution period in the first year, then "
        f"increased yearly by contribution_growth_percent (0 to {limits.CONTRIBUTION.maximum})"
    )

    @model_validator(mode="after")
    def _amounts(self) -> Self:
        self._check_amounts(
            {
                "initial_investment": (self.initial_investment, limits.INITIAL_INVESTMENT),
                "contribution": (self.contribution, limits.CONTRIBUTION),
            }
        )
        return self


class ScenarioForecastIn(CompoundForecastIn):
    """The base assumptions plus a conservative and a growth return (conservative <= base <=
    growth), each chosen by the user."""

    conservative_return_percent: ReturnPercent
    growth_return_percent: ReturnPercent

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.conservative_return_percent > self.annual_return_percent:
            raise ValueError("conservative_return_percent must not exceed annual_return_percent")
        if self.growth_return_percent < self.annual_return_percent:
            raise ValueError("growth_return_percent must not be below annual_return_percent")
        return self


class GoalForecastIn(ForecastAssumptions):
    """Find the contribution that reaches `target` after `years`."""

    target: Money = Field(
        description=f"The value to reach ({limits.TARGET.minimum} to {limits.TARGET.maximum})"
    )
    target_in_todays_money: bool = Field(
        default=False,
        strict=True,
        description="True: the target is in today's money and is grown by inflation to the "
        "horizon. False: the target is a nominal amount at the horizon.",
    )

    @model_validator(mode="after")
    def _amounts(self) -> Self:
        self._check_amounts(
            {
                "initial_investment": (self.initial_investment, limits.INITIAL_INVESTMENT),
                "target": (self.target, limits.TARGET),
            }
        )
        return self


class YearValue(BaseModel):
    year: int = Field(description="Years from now (0 is the start)")
    value: MoneyAmount = Field(description="Amount in the forecast currency")


class ForecastProjection(BaseModel):
    annual_return_percent: DecimalString = Field(description="The return this projection assumes")
    nominal: list[YearValue] = Field(description="Value at the end of each year")
    real: list[YearValue] = Field(description="The same values in today's money")
    contributions: list[YearValue] = Field(
        description="Paid in so far, including the initial investment"
    )
    final_nominal: Money
    final_real: Money = Field(description="Final value in today's money")
    total_contributions: Money = Field(description="Paid in, including the initial investment")
    total_growth: Money = Field(
        description="final_nominal - total_contributions (negative after losses)"
    )


class _Response(BaseModel):
    currency: str
    as_of: datetime = Field(description="When the forecast was computed")
    notice: str = Field(description="Shown with every forecast: projections are not guaranteed")


class CompoundForecastOut(_Response):
    projection: ForecastProjection
    assumptions: CompoundForecastIn = Field(description="The inputs, as validated")


class ForecastScenarios(BaseModel):
    conservative: ForecastProjection
    base: ForecastProjection
    growth: ForecastProjection


class ScenarioForecastOut(_Response):
    scenarios: ForecastScenarios
    assumptions: ScenarioForecastIn = Field(description="The inputs, as validated")


class GoalForecastOut(_Response):
    required_contribution: Money = Field(
        description="Per contribution period in the first year (then increased yearly by "
        "contribution_growth_percent). Rounded half-up, so the target is met to within rounding."
    )
    reached_without_contributions: bool = Field(
        description="The initial investment alone reaches the target"
    )
    projection: ForecastProjection = Field(description="The forecast with that contribution")
    assumptions: GoalForecastIn = Field(description="The inputs, as validated")
