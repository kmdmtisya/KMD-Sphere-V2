"""Investment universe API schemas (P12-T02)."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.core.money import Money, minor_units, round_half_up
from app.modules.universe.eligibility import JURISDICTION_NOTICE, Rule
from app.modules.universe.service import UniverseItem, UserUniverse

NOTICE = (
    "Eligibility only filters what analysis may consider; an eligible instrument is not a "
    "recommendation. DEMO instruments are fictional."
)
Liquidity = Literal["immediate", "market", "term", "illiquid", "unknown"]


class RuleOutcomeOut(BaseModel):
    rule: Rule
    passed: bool
    reason: str
    legally_reviewed: bool | None = Field(
        default=None, description="Jurisdiction rules only: false until the P12-T10 review"
    )


class EligibilityOut(BaseModel):
    eligible: bool = Field(description="True only when every rule passes")
    rules: list[RuleOutcomeOut]


class InstrumentOut(BaseModel):
    asset_id: uuid.UUID
    symbol: str | None
    name: str
    asset_class: str
    currency: str
    country: str | None
    risk_level: int = Field(ge=1, le=5, description="The source's classification, 1 lowest")
    liquidity: Liquidity = Field(description="Assumed from the asset class")
    jurisdictions: list[str] = Field(description="Where the source says it is offered")
    minimum_investment: Money | None
    is_demo: bool = Field(description="Fictional instrument for demo and development")
    licence_status: Literal["demo", "unconfirmed", "licensed"]
    data_as_of: datetime
    eligibility: EligibilityOut


class InvestorOut(BaseModel):
    residence_country: str | None
    risk_tolerance: str | None
    horizon_years: int | None


class UniverseOut(BaseModel):
    investor: InvestorOut = Field(description="The facts eligibility used")
    total: int
    eligible: int
    items: list[InstrumentOut]
    jurisdiction_notice: str = JURISDICTION_NOTICE
    notice: str = NOTICE


def instrument_out(item: UniverseItem) -> InstrumentOut:
    minimum = item.minimum_investment
    return InstrumentOut(
        asset_id=item.asset_id,
        symbol=item.symbol,
        name=item.name,
        asset_class=item.asset_class,
        currency=item.currency,
        country=item.country,
        risk_level=item.risk_level,
        liquidity=item.liquidity.value,
        jurisdictions=item.jurisdictions,
        minimum_investment=None
        if minimum is None
        else Money(
            amount=round_half_up(minimum, minor_units(item.currency)), currency=item.currency
        ),
        is_demo=item.is_demo,
        licence_status=item.licence_status,
        data_as_of=item.data_as_of,
        eligibility=EligibilityOut(
            eligible=item.eligibility.eligible,
            rules=[
                RuleOutcomeOut(
                    rule=o.rule,
                    passed=o.passed,
                    reason=o.reason,
                    legally_reviewed=o.legally_reviewed,
                )
                for o in item.eligibility.outcomes
            ],
        ),
    )


def universe_out(universe: UserUniverse, eligible_only: bool) -> UniverseOut:
    items = [i for i in universe.items if i.eligibility.eligible or not eligible_only]
    return UniverseOut(
        investor=InvestorOut(
            residence_country=universe.investor.residence_country,
            risk_tolerance=universe.investor.risk_tolerance,
            horizon_years=universe.investor.horizon_years,
        ),
        total=len(universe.items),
        eligible=sum(1 for i in universe.items if i.eligibility.eligible),
        items=[instrument_out(i) for i in items],
    )
