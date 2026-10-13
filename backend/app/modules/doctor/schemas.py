"""Portfolio Doctor API schemas (P12-T01)."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.money import DecimalString, Money, minor_units, round_half_up
from app.modules.doctor.rules import (
    Check,
    CheckStatus,
    Diagnosis,
    Finding,
    Scenario,
    Severity,
)

NOTICE = (
    "Observations from your own data against stated thresholds. Not investment advice. "
    "Scenarios are hypothetical: nothing is bought or sold."
)
# Measures that count things; every other measure is a fraction (0.25 is 25%).
COUNT_METRICS = frozenset({"goals_overdue", "goals_behind", "unpriced_assets"})


class DoctorRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    portfolio_id: uuid.UUID = Field(description="One of the user's portfolios")


class FindingOut(BaseModel):
    check: Check
    status: CheckStatus = Field(
        description="ok: within the thresholds; flagged: a threshold is reached; not_assessed: "
        "not enough data (the message says why)"
    )
    severity: Severity = Field(description="ok < info < low < medium < high")
    message: str = Field(description="What was found, in plain words; never advice")
    metric: str | None = None
    unit: Literal["percent", "count"] | None = Field(
        default=None,
        description="percent: of the portfolio's value (of its income for income dependence)",
    )
    value: DecimalString | None = Field(
        default=None, description="The measure; percentages to 2 decimals, half-up"
    )
    threshold: DecimalString | None = Field(
        default=None, description="The threshold the measure reached, when flagged"
    )
    subject: str | None = Field(
        default=None,
        description="What the measure is about: an asset id, an asset class, a sector, a "
        "country, goal ids, or cash_interest",
    )
    assumptions: list[str]


class ShareChangeOut(BaseModel):
    subject: str
    before: DecimalString = Field(description="Share of the portfolio now (percent)")
    after: DecimalString = Field(description="Share in the scenario (percent)")


class ScenarioOut(BaseModel):
    check: Check
    description: str
    is_trade: Literal[False] = Field(
        default=False, description="Always false: a scenario is never an order"
    )
    changes: list[ShareChangeOut]
    measure: str = Field(
        description="What `before` and `after` describe: effective_positions (2 decimals) or "
        "asset_class_hhi (4 decimals)"
    )
    before: DecimalString | None
    after: DecimalString | None
    assumptions: list[str]


class SeverityCounts(BaseModel):
    high: int
    medium: int
    low: int
    info: int


class DoctorOut(BaseModel):
    portfolio_id: uuid.UUID
    as_of: datetime
    currency: str
    total_value: Money
    overall: Severity = Field(description="The highest severity among flagged findings")
    counts: SeverityCounts = Field(description="Flagged findings by severity")
    complete: bool = Field(description="False when some holdings have no value or rate")
    findings: list[FindingOut]
    scenarios: list[ScenarioOut]
    notice: str = NOTICE


def _percent(share: Decimal | None) -> Decimal | None:
    return None if share is None else round_half_up(share * 100, 2)


def finding_out(f: Finding) -> FindingOut:
    count = f.metric in COUNT_METRICS
    unit: Literal["percent", "count"] | None = None
    if f.metric is not None:
        unit = "count" if count else "percent"
    return FindingOut(
        check=f.check,
        status=f.status,
        severity=f.severity,
        message=f.message,
        metric=f.metric,
        unit=unit,
        value=f.value if count else _percent(f.value),
        threshold=_percent(f.threshold),
        subject=f.subject,
        assumptions=list(f.assumptions),
    )


def scenario_out(s: Scenario) -> ScenarioOut:
    places = 2 if s.measure == "effective_positions" else 4
    return ScenarioOut(
        check=s.check,
        description=s.description,
        changes=[
            ShareChangeOut(
                subject=c.subject,
                before=round_half_up(c.before * 100, 2),
                after=round_half_up(c.after * 100, 2),
            )
            for c in s.changes
        ],
        measure=s.measure,
        before=None if s.before is None else round_half_up(s.before, places),
        after=None if s.after is None else round_half_up(s.after, places),
        assumptions=list(s.assumptions),
    )


def doctor_out(
    portfolio_id: uuid.UUID, as_of: datetime, diagnosis: Diagnosis, complete: bool
) -> DoctorOut:
    return DoctorOut(
        portfolio_id=portfolio_id,
        as_of=as_of,
        currency=diagnosis.currency,
        total_value=Money(
            amount=round_half_up(diagnosis.total, minor_units(diagnosis.currency)),
            currency=diagnosis.currency,
        ),
        overall=diagnosis.overall,
        counts=SeverityCounts(
            high=diagnosis.count(Severity.HIGH),
            medium=diagnosis.count(Severity.MEDIUM),
            low=diagnosis.count(Severity.LOW),
            info=diagnosis.count(Severity.INFO),
        ),
        complete=complete,
        findings=[finding_out(f) for f in diagnosis.findings],
        scenarios=[scenario_out(s) for s in diagnosis.scenarios],
    )
