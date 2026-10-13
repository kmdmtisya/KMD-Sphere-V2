"""Instrument score schemas (P12-T03). Points and percentages to 2 decimals, half-up (ADR-0006)."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.core.money import DecimalString, round_half_up
from app.modules.scoring.scoring import NOTICE, Confidence, Factor, FactorResult, FactorStatus
from app.modules.scoring.service import ScoredItem

HUNDRED = Decimal(100)
# How each factor's measure is published.
UNITS: dict[Factor, Literal["percent", "level", None]] = {
    Factor.STABILITY: "percent",
    Factor.RESILIENCE: "percent",
    Factor.MOMENTUM: "percent",
    Factor.COST: "percent",
    Factor.LIQUIDITY: None,
    Factor.RISK_CLASS: "level",
}


class FactorOut(BaseModel):
    factor: Factor
    status: FactorStatus = Field(
        description="used; missing (applies but could not be measured: lowers coverage and "
        "confidence); not_applicable (no penalty)"
    )
    weight_percent: DecimalString = Field(description="The configured weight")
    effective_weight_percent: DecimalString = Field(description="Share of the measured weight")
    measure: DecimalString | None = Field(
        default=None, description="The feature's value (percent, or the risk level)"
    )
    unit: Literal["percent", "level"] | None = None
    points: DecimalString | None = Field(default=None, description="0 to 100")
    contribution: DecimalString = Field(description="Points x effective weight")
    explanation: str


class ScoreOut(BaseModel):
    score: DecimalString | None = Field(
        description="0 to 100: the sum of the contributions; null when coverage is too low"
    )
    coverage_percent: DecimalString = Field(description="Measured share of the applicable weight")
    confidence: Confidence
    factors: list[FactorOut]
    reasons: list[str] = Field(description="Why confidence is not high")


class ScoredInstrumentOut(BaseModel):
    asset_id: uuid.UUID
    symbol: str | None
    name: str
    asset_class: str
    currency: str
    is_demo: bool
    eligible: bool = Field(description="Passes every eligibility rule for you (P12-T02)")
    last_close: date | None = Field(description="The newest close the price features use")
    score: ScoreOut


class ScoresOut(BaseModel):
    weights_percent: dict[Factor, DecimalString]
    items: list[ScoredInstrumentOut] = Field(description="Highest score first; unscored last")
    notice: str = NOTICE


def _r(x: Decimal) -> Decimal:
    return round_half_up(x, 2)


def factor_out(r: FactorResult) -> FactorOut:
    unit = UNITS[r.factor]
    measure = None
    if r.measure is not None and unit is not None:
        measure = _r(r.measure * HUNDRED) if unit == "percent" else r.measure
    return FactorOut(
        factor=r.factor,
        status=r.status,
        weight_percent=_r(r.weight * HUNDRED),
        effective_weight_percent=_r(r.effective_weight * HUNDRED),
        measure=measure,
        unit=unit if measure is not None else None,
        points=None if r.points is None else _r(r.points),
        contribution=_r(r.contribution),
        explanation=r.explanation,
    )


def scored_out(s: ScoredItem) -> ScoredInstrumentOut:
    return ScoredInstrumentOut(
        asset_id=s.item.asset_id,
        symbol=s.item.symbol,
        name=s.item.name,
        asset_class=s.item.asset_class,
        currency=s.item.currency,
        is_demo=s.item.is_demo,
        eligible=s.item.eligibility.eligible,
        last_close=s.features.last_close,
        score=ScoreOut(
            score=None if s.score.score is None else _r(s.score.score),
            coverage_percent=_r(s.score.coverage * HUNDRED),
            confidence=s.score.confidence,
            factors=[factor_out(r) for r in s.score.factors],
            reasons=list(s.score.reasons),
        ),
    )


def scores_out(
    items: list[ScoredItem], weights: dict[Factor, Decimal], eligible_only: bool
) -> ScoresOut:
    return ScoresOut(
        weights_percent={f: _r(w * HUNDRED) for f, w in weights.items()},
        items=[scored_out(s) for s in items if s.item.eligibility.eligible or not eligible_only],
    )
