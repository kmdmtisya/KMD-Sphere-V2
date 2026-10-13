"""Explainable instrument scores (P12-T03.2 and T03.3). Pure and Decimal-only.

Each feature becomes a factor sub-score from 0 to 100 through a stated transform; the score is the
weighted mean of the factors that could be measured, so it is exactly the sum of the factor
contributions. A factor that applies but could not be measured is not ignored: it is reported as
missing and lowers the **coverage** (the measured share of the applicable weight) and with it the
confidence; below the minimum coverage no score is given. A factor that does not apply (an expense
ratio for a share) is left out of the weights without any penalty.

A score describes measured characteristics (past prices, costs, liquidity, risk class). It is not
a forecast, not an expected return and not a recommendation. Methods: docs/design/scoring.md and
docs/financial-methods.md section 17."""

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from app.core.money import format_decimal, round_half_up
from app.modules.assets.liquidity import Liquidity
from app.modules.scoring.features import Feature, Features

ZERO = Decimal(0)
HUNDRED = Decimal(100)
NOTICE = (
    "Scores describe measured characteristics: past prices, costs, liquidity and risk class. "
    "They are not forecasts or expected returns, and not recommendations."
)


class Factor(StrEnum):
    STABILITY = "stability"  # low volatility
    RESILIENCE = "resilience"  # small past falls
    MOMENTUM = "momentum"  # trailing 12-month return
    COST = "cost"  # low expense ratio (funds only)
    LIQUIDITY = "liquidity"
    RISK_CLASS = "risk_class"  # low risk level


class FactorStatus(StrEnum):
    USED = "used"
    MISSING = "missing"  # applies, but could not be measured: lowers coverage and confidence
    NOT_APPLICABLE = "not_applicable"  # does not apply to this instrument: no penalty


class Confidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = "none"  # not enough data to score


FEATURE_OF: dict[Factor, Feature] = {
    Factor.STABILITY: Feature.VOLATILITY,
    Factor.RESILIENCE: Feature.MAX_DRAWDOWN,
    Factor.MOMENTUM: Feature.TRAILING_RETURN,
    Factor.COST: Feature.EXPENSE_RATIO,
    Factor.LIQUIDITY: Feature.LIQUIDITY,
    Factor.RISK_CLASS: Feature.RISK_LEVEL,
}

DEFAULT_WEIGHTS: dict[Factor, Decimal] = {
    Factor.STABILITY: Decimal("0.25"),
    Factor.RESILIENCE: Decimal("0.20"),
    Factor.MOMENTUM: Decimal("0.15"),
    Factor.COST: Decimal("0.10"),
    Factor.LIQUIDITY: Decimal("0.15"),
    Factor.RISK_CLASS: Decimal("0.15"),
}

# Transform scales: a measure at or beyond the scale gives 0 (or 100 for momentum's top).
VOLATILITY_SCALE = Decimal("0.60")  # 60% annualised volatility scores 0
DRAWDOWN_SCALE = Decimal("0.60")  # a 60% fall scores 0
MOMENTUM_SPAN = Decimal("0.50")  # -50% scores 0, 0% scores 50, +50% scores 100
EXPENSE_SCALE = Decimal("0.02")  # a 2% a year expense ratio scores 0
LIQUIDITY_POINTS: dict[Liquidity, Decimal] = {
    Liquidity.IMMEDIATE: Decimal(100),
    Liquidity.MARKET: Decimal(80),
    Liquidity.TERM: Decimal(40),
    Liquidity.ILLIQUID: Decimal(10),
}
MIN_COVERAGE = Decimal("0.50")  # below this share of the applicable weight: no score
HIGH_COVERAGE = Decimal("0.85")
MEDIUM_COVERAGE = Decimal("0.60")


def validate_weights(weights: Mapping[str, Decimal]) -> dict[Factor, Decimal]:
    """Weights for every factor, none negative, adding up to exactly 1."""
    try:
        parsed = {Factor(k): Decimal(v) for k, v in weights.items()}
    except ValueError as error:
        raise ValueError(f"unknown factor in weights: {error}") from None
    if set(parsed) != set(Factor):
        raise ValueError(f"weights must name every factor: {sorted(f.value for f in Factor)}")
    if any(w < ZERO for w in parsed.values()):
        raise ValueError("weights must not be negative")
    if sum(parsed.values(), ZERO) != 1:
        raise ValueError("weights must add up to 1")
    return parsed


def clamp(value: Decimal) -> Decimal:
    return max(ZERO, min(HUNDRED, value))


def sub_score(factor: Factor, features: Features) -> Decimal | None:
    """The factor's 0-100 points, or None when its feature is missing or does not apply."""
    if factor is Factor.STABILITY:
        v = features.volatility
        return None if v is None else clamp(HUNDRED * (1 - v / VOLATILITY_SCALE))
    if factor is Factor.RESILIENCE:
        v = features.max_drawdown
        return None if v is None else clamp(HUNDRED * (1 - v / DRAWDOWN_SCALE))
    if factor is Factor.MOMENTUM:
        v = features.trailing_return
        return None if v is None else clamp(50 + 50 * v / MOMENTUM_SPAN)
    if factor is Factor.COST:
        v = features.expense_ratio
        return None if v is None else clamp(HUNDRED * (1 - v / EXPENSE_SCALE))
    if factor is Factor.LIQUIDITY:
        return LIQUIDITY_POINTS.get(features.liquidity)
    return Decimal(5 - features.risk_level) / 4 * HUNDRED  # risk level 1 scores 100, 5 scores 0


def applies(factor: Factor, features: Features) -> bool:
    return factor is not Factor.COST or features.fund


@dataclass(frozen=True)
class FactorResult:
    factor: Factor
    status: FactorStatus
    weight: Decimal  # configured weight
    effective_weight: Decimal  # share of the measured weight (0 unless used)
    measure: Decimal | None  # the feature's value
    points: Decimal | None  # 0-100
    contribution: Decimal  # effective_weight x points; the contributions add up to the score
    explanation: str


@dataclass(frozen=True)
class Score:
    score: Decimal | None  # 0-100, None when coverage is below the minimum
    coverage: Decimal  # measured share of the applicable weight, 0-1
    confidence: Confidence
    factors: tuple[FactorResult, ...]
    reasons: tuple[str, ...]  # why confidence is not high (missing features, stale prices)


def _pct(x: Decimal) -> str:
    return f"{format_decimal(round_half_up(x * HUNDRED, 2))}%"


def _num(x: Decimal) -> str:
    return format_decimal(round_half_up(x, 2))


def _measure(factor: Factor, f: Features) -> Decimal | None:
    return {
        Factor.STABILITY: f.volatility,
        Factor.RESILIENCE: f.max_drawdown,
        Factor.MOMENTUM: f.trailing_return,
        Factor.COST: f.expense_ratio,
        Factor.LIQUIDITY: None,
        Factor.RISK_CLASS: Decimal(f.risk_level),
    }[factor]


def _describe(factor: Factor, f: Features, points: Decimal) -> str:
    p = _num(points)
    if factor is Factor.STABILITY:
        return f"Volatility of {_pct(f.volatility or ZERO)} a year over the last year: {p}/100."
    if factor is Factor.RESILIENCE:
        return f"Largest fall from a peak in the last year {_pct(f.max_drawdown or ZERO)}: {p}/100."
    if factor is Factor.MOMENTUM:
        return (
            f"Price change over the last year {_pct(f.trailing_return or ZERO)} "
            f"(past, not a forecast): {p}/100."
        )
    if factor is Factor.COST:
        return f"Expense ratio {_pct(f.expense_ratio or ZERO)} a year: {p}/100."
    if factor is Factor.LIQUIDITY:
        return f"{f.liquidity.value.capitalize()} liquidity (assumed from the class): {p}/100."
    return f"Risk level {f.risk_level} of 5 (the source's classification): {p}/100."


def score(features: Features, weights: Mapping[Factor, Decimal] = DEFAULT_WEIGHTS) -> Score:
    missing_reasons = {m.feature: m.reason for m in features.missing}
    measured: dict[Factor, Decimal] = {}
    applicable = ZERO
    for factor in Factor:
        if not applies(factor, features):
            continue
        applicable += weights[factor]
        points = sub_score(factor, features)
        if points is not None:
            measured[factor] = points
    used_weight = sum((weights[f] for f in measured), ZERO)
    coverage = used_weight / applicable if applicable > ZERO else ZERO
    results = []
    for factor in Factor:
        w = weights[factor]
        if not applies(factor, features):
            results.append(
                FactorResult(
                    factor,
                    FactorStatus.NOT_APPLICABLE,
                    w,
                    ZERO,
                    None,
                    None,
                    ZERO,
                    "Does not apply to this instrument.",
                )
            )
        elif factor not in measured:
            reason = missing_reasons.get(FEATURE_OF[factor], "Not measured.")
            results.append(
                FactorResult(factor, FactorStatus.MISSING, w, ZERO, None, None, ZERO, reason)
            )
        else:
            share = w / used_weight
            points = measured[factor]
            results.append(
                FactorResult(
                    factor,
                    FactorStatus.USED,
                    w,
                    share,
                    _measure(factor, features),
                    points,
                    share * points,
                    _describe(factor, features, points),
                )
            )
    reasons = [r.explanation for r in results if r.status is FactorStatus.MISSING]
    if features.stale_prices:
        reasons.append("The latest price is older than its freshness window.")
    if coverage < MIN_COVERAGE or used_weight == ZERO:
        return Score(None, coverage, Confidence.NONE, tuple(results), tuple(reasons))
    if coverage >= HIGH_COVERAGE and not features.stale_prices:
        confidence = Confidence.HIGH
    elif coverage >= MEDIUM_COVERAGE:
        confidence = Confidence.MEDIUM
    else:
        confidence = Confidence.LOW
    total = sum((r.contribution for r in results), ZERO)
    return Score(total, coverage, confidence, tuple(results), tuple(reasons))
