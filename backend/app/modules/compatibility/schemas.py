"""Compatibility API schemas (P12-T04). Shares in percent, 2 decimals, half-up (ADR-0006)."""

import uuid
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.money import DecimalString, Money, minor_units, round_half_up
from app.modules.compatibility.impact import ASSUMPTION, Measures, Verdict
from app.modules.compatibility.service import Compatibility
from app.modules.doctor.rules import Check, Severity

HUNDRED = Decimal(100)


class CompatibilityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    portfolio_id: uuid.UUID = Field(description="One of the user's portfolios")
    asset_id: uuid.UUID = Field(description="An instrument of the investment universe")
    amount: Money = Field(description="A hypothetical amount, in the portfolio's base currency")


class MeasuresOut(BaseModel):
    total_value: Money
    instrument_share_percent: DecimalString
    largest_holding_percent: DecimalString | None
    effective_positions: DecimalString | None
    asset_class_percent: DecimalString = Field(description="The instrument's asset class")
    foreign_currency_percent: DecimalString
    accessible_percent: DecimalString = Field(
        description="Cash and assets that can usually be sold within days"
    )


class CheckChangeOut(BaseModel):
    check: Check
    before: Severity
    after: Severity


class ReasonOut(BaseModel):
    code: str
    message: str


class CompatibilityOut(BaseModel):
    portfolio_id: uuid.UUID
    asset_id: uuid.UUID
    symbol: str | None
    name: str
    is_demo: bool
    amount: Money
    verdict: Verdict = Field(
        description="fits; caution (the reasons say what gets worse); not_suitable (not "
        "eligible, or below the minimum investment)"
    )
    reasons: list[ReasonOut]
    before: MeasuresOut
    after: MeasuresOut
    doctor_changes: list[CheckChangeOut] = Field(
        description="Portfolio Doctor checks whose severity would change"
    )
    is_trade: Literal[False] = Field(default=False, description="Always false: never an order")
    assumptions: list[str] = Field(default_factory=lambda: [ASSUMPTION])


def _p(x: Decimal | None) -> Decimal | None:
    return None if x is None else round_half_up(x * HUNDRED, 2)


def measures_out(m: Measures, currency: str) -> MeasuresOut:
    return MeasuresOut(
        total_value=Money(amount=round_half_up(m.total, minor_units(currency)), currency=currency),
        instrument_share_percent=round_half_up(m.candidate_share * HUNDRED, 2),
        largest_holding_percent=_p(m.largest_holding),
        effective_positions=None
        if m.effective_positions is None
        else round_half_up(m.effective_positions, 2),
        asset_class_percent=round_half_up(m.class_share * HUNDRED, 2),
        foreign_currency_percent=round_half_up(m.foreign_currency * HUNDRED, 2),
        accessible_percent=round_half_up(m.accessible * HUNDRED, 2),
    )


def compatibility_out(c: Compatibility) -> CompatibilityOut:
    a = c.assessment
    return CompatibilityOut(
        portfolio_id=c.portfolio_id,
        asset_id=c.item.asset_id,
        symbol=c.item.symbol,
        name=c.item.name,
        is_demo=c.item.is_demo,
        amount=Money(amount=round_half_up(c.amount, minor_units(c.currency)), currency=c.currency),
        verdict=a.verdict,
        reasons=[ReasonOut(code=r.code, message=r.message) for r in a.reasons],
        before=measures_out(a.before, c.currency),
        after=measures_out(a.after, c.currency),
        doctor_changes=[
            CheckChangeOut(check=x.check, before=x.before, after=x.after) for x in a.changes
        ],
    )
