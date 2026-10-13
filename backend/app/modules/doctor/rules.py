"""Portfolio Doctor rules (P12-T01): deterministic checks of one portfolio with stated thresholds.

Pure and Decimal-only: the same inputs always give the same findings. Every figure comes from the
existing analytics (allocation, risk, income, goals); this module only compares them with the
thresholds below and describes what it found. Nothing here is advice, and the scenarios are
hypothetical allocations for illustration, never orders (no trade is placed or prepared).
Methods and thresholds: docs/design/portfolio-doctor.md."""

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from app.core.money import format_decimal, round_half_up
from app.modules.analytics.allocation import Dimension, Part, allocate, cash, herfindahl
from app.modules.assets.liquidity import (
    ACCESSIBLE,
    LIQUIDITY_ASSUMPTION,
    LIQUIDITY_BY_CLASS,
    Liquidity,
)

ZERO = Decimal(0)
ONE = Decimal(1)


class Severity(StrEnum):
    """Ordered: ok < info < low < medium < high."""

    OK = "ok"
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

    @property
    def rank(self) -> int:
        return list(Severity).index(self)


class CheckStatus(StrEnum):
    OK = "ok"  # measured, within the thresholds
    FLAGGED = "flagged"  # measured, a threshold is crossed
    NOT_ASSESSED = "not_assessed"  # not enough data to measure; says why


class Check(StrEnum):
    POSITION_CONCENTRATION = "position_concentration"
    ASSET_CLASS_CONCENTRATION = "asset_class_concentration"
    SECTOR_CONCENTRATION = "sector_concentration"
    GEOGRAPHIC_CONCENTRATION = "geographic_concentration"
    CURRENCY_EXPOSURE = "currency_exposure"
    LIQUIDITY = "liquidity"
    VOLATILITY = "volatility"
    DRAWDOWN = "drawdown"
    INCOME_DEPENDENCE = "income_dependence"
    GOAL_ALIGNMENT = "goal_alignment"
    DATA_COMPLETENESS = "data_completeness"


@dataclass(frozen=True)
class Band:
    """A measure at or above `high` is high, at or above `medium` medium, and so on. A level of
    None is not used by that check."""

    low: Decimal | None
    medium: Decimal | None
    high: Decimal | None

    def severity(self, value: Decimal) -> tuple[Severity, Decimal | None]:
        """The severity of a measure, and the threshold it reached (None when ok)."""
        for level, threshold in (
            (Severity.HIGH, self.high),
            (Severity.MEDIUM, self.medium),
            (Severity.LOW, self.low),
        ):
            if threshold is not None and value >= threshold:
                return level, threshold
        return Severity.OK, None


def _d(text: str) -> Decimal:
    return Decimal(text)


@dataclass(frozen=True)
class Thresholds:
    """Shares are fractions of the portfolio's total value (0.20 is 20%)."""

    position: Band = Band(_d("0.10"), _d("0.20"), _d("0.35"))  # the largest holding
    asset_class: Band = Band(None, _d("0.70"), _d("0.90"))  # the largest asset class
    sector: Band = Band(None, _d("0.30"), _d("0.50"))  # the largest known sector
    country: Band = Band(_d("0.75"), _d("0.90"), None)  # the largest known country
    foreign_currency: Band = Band(_d("0.25"), _d("0.50"), _d("0.75"))  # not the base currency
    volatility: Band = Band(_d("0.10"), _d("0.20"), _d("0.30"))  # annualised
    drawdown: Band = Band(_d("0.10"), _d("0.20"), _d("0.35"))  # largest fall from a peak
    income_source: Band = Band(None, _d("0.50"), _d("0.75"))  # the largest payer's share
    # Liquidity is the other way round: a *small* accessible share is the concern.
    accessible_medium: Decimal = Decimal("0.25")
    accessible_high: Decimal = Decimal("0.10")
    # Sector or country unknown for at least this share of holdings: an info finding.
    unknown_info: Decimal = Decimal("0.50")
    # Scenario caps: the largest holding or class brought down to these shares.
    position_cap: Decimal = Decimal("0.20")
    asset_class_cap: Decimal = Decimal("0.60")


DEFAULT_THRESHOLDS = Thresholds()


# ------------------------------------------------------------------------------------- inputs
@dataclass(frozen=True)
class Holding:
    asset_id: uuid.UUID
    value: Decimal  # in the portfolio's base currency
    asset_class: str
    currency: str  # of the valuation
    country: str | None = None
    sector: str | None = None


@dataclass(frozen=True)
class GoalState:
    goal_id: uuid.UUID
    name: str
    status: str  # "on_track" or "behind" (an estimate under the goal's assumptions)
    reached: bool
    overdue: bool


@dataclass(frozen=True)
class Inputs:
    currency: str  # the portfolio's base currency
    total: Decimal
    holdings: Sequence[Holding]
    cash_balances: dict[str, Decimal]  # converted to the base currency, by currency
    complete: bool
    unpriced_assets: int = 0
    # Risk (monthly series): None when it could not be measured; `risk_status` says why.
    risk_status: str = "insufficient_data"
    volatility: Decimal | None = None
    max_drawdown: Decimal | None = None  # a fall as a positive fraction (0.25 is 25%)
    # Trailing 12 months of gross income by paying asset (None: cash interest), base currency.
    income_by_asset: dict[uuid.UUID | None, Decimal] = field(default_factory=dict)
    goals: Sequence[GoalState] = ()


# ------------------------------------------------------------------------------------ results
@dataclass(frozen=True)
class Finding:
    check: Check
    status: CheckStatus
    severity: Severity
    message: str  # plain, factual, deterministic; never advice
    value: Decimal | None = None  # the measure (a fraction, unless `metric` says otherwise)
    threshold: Decimal | None = None  # the threshold reached, when flagged
    subject: str | None = None  # what the measure is about (an asset id, class, country...)
    metric: str | None = None
    assumptions: tuple[str, ...] = ()


@dataclass(frozen=True)
class ShareChange:
    subject: str
    before: Decimal
    after: Decimal


@dataclass(frozen=True)
class Scenario:
    """A hypothetical allocation: what the measures would be if a share were different. It is
    not a recommendation and not an order; no amount to buy or sell is given."""

    check: Check
    description: str
    changes: tuple[ShareChange, ...]
    measure: str  # what `before` and `after` describe
    before: Decimal | None
    after: Decimal | None
    assumptions: tuple[str, ...]


@dataclass(frozen=True)
class Diagnosis:
    currency: str
    total: Decimal
    findings: tuple[Finding, ...]
    scenarios: tuple[Scenario, ...]

    @property
    def overall(self) -> Severity:
        flagged = [f.severity for f in self.findings if f.status is CheckStatus.FLAGGED]
        return max(flagged, key=lambda s: s.rank, default=Severity.OK)

    def count(self, severity: Severity) -> int:
        return sum(
            1 for f in self.findings if f.status is CheckStatus.FLAGGED and f.severity is severity
        )


# -------------------------------------------------------------------------------------- rules
def _pct(share: Decimal) -> str:
    """A share as the API publishes it: percent, 2 decimals, half-up (ADR-0006)."""
    return f"{format_decimal(round_half_up(share * 100, 2))}%"


def _parts(inputs: Inputs) -> list[Part]:
    return [
        Part(str(h.asset_id), h.value, h.asset_class, h.currency, h.country, h.sector)
        for h in inputs.holdings
    ] + [cash(c, v) for c, v in sorted(inputs.cash_balances.items())]


def _measurable(inputs: Inputs) -> bool:
    """Shares mean something only for a positive total without negative parts."""
    values = [h.value for h in inputs.holdings] + list(inputs.cash_balances.values())
    return inputs.total > ZERO and all(v >= ZERO for v in values)


def _not_assessed(check: Check, why: str) -> Finding:
    return Finding(check, CheckStatus.NOT_ASSESSED, Severity.INFO, why)


def _graded(
    check: Check,
    band: Band,
    value: Decimal,
    subject: str | None,
    flagged: str,
    fine: str,
    metric: str = "share",
    assumptions: tuple[str, ...] = (),
) -> Finding:
    severity, threshold = band.severity(value)
    status = CheckStatus.OK if severity is Severity.OK else CheckStatus.FLAGGED
    message = fine if severity is Severity.OK else flagged
    return Finding(check, status, severity, message, value, threshold, subject, metric, assumptions)


def position_concentration(inputs: Inputs, t: Thresholds) -> Finding:
    check = Check.POSITION_CONCENTRATION
    if not inputs.holdings:
        return _not_assessed(check, "The portfolio has no valued holdings.")
    largest = max(inputs.holdings, key=lambda h: (h.value, str(h.asset_id)))
    share = largest.value / inputs.total
    return _graded(
        check,
        t.position,
        share,
        str(largest.asset_id),
        f"The largest holding is {_pct(share)} of the portfolio's value.",
        f"No single holding is more than {_pct(t.position.low or ONE)} of the portfolio.",
    )


def _largest_slice(
    inputs: Inputs, dimension: Dimension, *, known_only: bool
) -> tuple[str | None, Decimal, Decimal]:
    """(key, share of the total, unknown share of holdings) for one allocation dimension."""
    allocation = allocate(_parts(inputs), dimension)
    slices = [s for s in allocation.slices if not known_only or s.key is not None]
    unknown = sum((s.value for s in allocation.slices if s.key is None), ZERO)
    holdings_value = sum((h.value for h in inputs.holdings), ZERO)
    cash_value = sum(inputs.cash_balances.values(), ZERO)
    # Cash is unclassified for country and sector by design; only holdings count as unknown.
    unknown_holdings = unknown - cash_value if known_only else ZERO
    unknown_share = unknown_holdings / holdings_value if holdings_value > ZERO else ZERO
    if not slices:
        return None, ZERO, unknown_share
    top = slices[0]
    return top.key, top.value / inputs.total, unknown_share


def asset_class_concentration(inputs: Inputs, t: Thresholds) -> Finding:
    key, share, _ = _largest_slice(inputs, Dimension.ASSET_CLASS, known_only=False)
    return _graded(
        Check.ASSET_CLASS_CONCENTRATION,
        t.asset_class,
        share,
        key,
        f"{_pct(share)} of the portfolio is in one asset class ({key}).",
        f"No asset class is more than {_pct(t.asset_class.medium or ONE)} of the portfolio.",
    )


def _known_concentration(
    inputs: Inputs, t: Thresholds, check: Check, dimension: Dimension, band: Band, noun: str
) -> Finding:
    if not inputs.holdings:
        return _not_assessed(check, "The portfolio has no valued holdings.")
    key, share, unknown = _largest_slice(inputs, dimension, known_only=True)
    if key is None:
        return _not_assessed(check, f"No holding has a {noun} recorded.")
    finding = _graded(
        check,
        band,
        share,
        key,
        f"{_pct(share)} of the portfolio is in one {noun} ({key}).",
        f"No single {noun} is more than {_pct(band.medium or band.low or ONE)} of the portfolio.",
    )
    if unknown >= t.unknown_info and finding.status is CheckStatus.OK:
        return Finding(
            check,
            CheckStatus.FLAGGED,
            Severity.INFO,
            f"The {noun} is not recorded for {_pct(unknown)} of the holdings' value, so this "
            "check covers only part of the portfolio.",
            unknown,
            t.unknown_info,
            None,
            f"unknown_{noun}_share",
        )
    return finding


def currency_exposure(inputs: Inputs, t: Thresholds) -> Finding:
    allocation = allocate(_parts(inputs), Dimension.CURRENCY)
    foreign = sum((s.value for s in allocation.slices if s.key != inputs.currency), ZERO)
    share = foreign / inputs.total
    return _graded(
        Check.CURRENCY_EXPOSURE,
        t.foreign_currency,
        share,
        None,
        f"{_pct(share)} of the portfolio is held in currencies other than {inputs.currency}, "
        "so exchange-rate moves change its value.",
        f"Most of the portfolio is in {inputs.currency}; {_pct(share)} is in other currencies.",
        "foreign_currency_share",
    )


def liquidity(inputs: Inputs, t: Thresholds) -> Finding:
    accessible = sum(inputs.cash_balances.values(), ZERO) + sum(
        (
            h.value
            for h in inputs.holdings
            if LIQUIDITY_BY_CLASS.get(h.asset_class, Liquidity.UNKNOWN) in ACCESSIBLE
        ),
        ZERO,
    )
    share = accessible / inputs.total
    if share < t.accessible_high:
        severity, threshold = Severity.HIGH, t.accessible_high
    elif share < t.accessible_medium:
        severity, threshold = Severity.MEDIUM, t.accessible_medium
    else:
        return Finding(
            Check.LIQUIDITY,
            CheckStatus.OK,
            Severity.OK,
            f"{_pct(share)} of the portfolio is in cash or assets that can usually be sold "
            "within days.",
            share,
            None,
            None,
            "accessible_share",
            (LIQUIDITY_ASSUMPTION,),
        )
    return Finding(
        Check.LIQUIDITY,
        CheckStatus.FLAGGED,
        severity,
        f"Only {_pct(share)} of the portfolio is in cash or assets that can usually be sold "
        "within days; the rest is locked or slow to sell.",
        share,
        threshold,
        None,
        "accessible_share",
        (LIQUIDITY_ASSUMPTION,),
    )


_RISK_REASONS = {
    "insufficient_data": "There is not yet a year of monthly history to measure it.",
    "incomplete_data": "Some past values could not be priced, so it cannot be measured.",
    "undefined_period": "A period starts at zero, so returns are undefined.",
}
_PAST = "Measured on the portfolio's own monthly history; past movements, not a forecast."


def volatility(inputs: Inputs, t: Thresholds) -> Finding:
    if inputs.volatility is None:
        why = _RISK_REASONS.get(inputs.risk_status, "It could not be measured.")
        return _not_assessed(Check.VOLATILITY, f"Volatility not assessed: {why}")
    return _graded(
        Check.VOLATILITY,
        t.volatility,
        inputs.volatility,
        None,
        f"The portfolio's value has moved by about {_pct(inputs.volatility)} a year "
        "(annualised volatility).",
        f"Annualised volatility is {_pct(inputs.volatility)}.",
        "annualised_volatility",
        (_PAST,),
    )


def drawdown(inputs: Inputs, t: Thresholds) -> Finding:
    if inputs.max_drawdown is None:
        why = _RISK_REASONS.get(inputs.risk_status, "It could not be measured.")
        return _not_assessed(Check.DRAWDOWN, f"Drawdown not assessed: {why}")
    return _graded(
        Check.DRAWDOWN,
        t.drawdown,
        inputs.max_drawdown,
        None,
        f"The portfolio has fallen {_pct(inputs.max_drawdown)} from a previous peak at its worst.",
        f"The largest fall from a previous peak was {_pct(inputs.max_drawdown)}.",
        "max_drawdown",
        (_PAST,),
    )


def income_dependence(inputs: Inputs, t: Thresholds) -> Finding:
    paying = {k: v for k, v in inputs.income_by_asset.items() if v > ZERO}
    total = sum(paying.values(), ZERO)
    if total <= ZERO:
        return _not_assessed(
            Check.INCOME_DEPENDENCE, "No income was recorded in the last 12 months."
        )
    source, amount = max(paying.items(), key=lambda kv: (kv[1], str(kv[0])))
    share = amount / total
    subject = str(source) if source is not None else "cash_interest"
    return _graded(
        Check.INCOME_DEPENDENCE,
        t.income_source,
        share,
        subject,
        f"{_pct(share)} of the last 12 months' income came from one source.",
        f"No single source paid more than {_pct(t.income_source.medium or ONE)} of the income.",
        "largest_income_share",
    )


GOAL_NOTICE = "Goal status is an estimate under each goal's own assumptions, not a certainty."


def goal_alignment(inputs: Inputs, t: Thresholds) -> Finding:
    goals = list(inputs.goals)
    if not goals:
        return _not_assessed(Check.GOAL_ALIGNMENT, "No goal is linked to this portfolio.")
    overdue = [g for g in goals if g.overdue and not g.reached]
    behind = [g for g in goals if g.status != "on_track" and not g.reached]
    if overdue:
        return Finding(
            Check.GOAL_ALIGNMENT,
            CheckStatus.FLAGGED,
            Severity.HIGH,
            f"{len(overdue)} of {len(goals)} linked goals passed their target date without "
            "reaching the target.",
            Decimal(len(overdue)),
            None,
            ",".join(str(g.goal_id) for g in overdue),
            "goals_overdue",
            (GOAL_NOTICE,),
        )
    if behind:
        return Finding(
            Check.GOAL_ALIGNMENT,
            CheckStatus.FLAGGED,
            Severity.MEDIUM,
            f"{len(behind)} of {len(goals)} linked goals are behind under their assumptions.",
            Decimal(len(behind)),
            None,
            ",".join(str(g.goal_id) for g in behind),
            "goals_behind",
            (GOAL_NOTICE,),
        )
    return Finding(
        Check.GOAL_ALIGNMENT,
        CheckStatus.OK,
        Severity.OK,
        f"All {len(goals)} linked goals are on track or reached under their assumptions.",
        Decimal(0),
        None,
        None,
        "goals_behind",
        (GOAL_NOTICE,),
    )


def data_completeness(inputs: Inputs, t: Thresholds) -> Finding:
    if inputs.complete:
        return Finding(
            Check.DATA_COMPLETENESS,
            CheckStatus.OK,
            Severity.OK,
            "Every holding is valued.",
            metric="unpriced_assets",
            value=Decimal(0),
        )
    return Finding(
        Check.DATA_COMPLETENESS,
        CheckStatus.FLAGGED,
        Severity.INFO,
        f"{inputs.unpriced_assets} holdings have no value or rate yet, so the other checks "
        "cover only the valued part of the portfolio.",
        Decimal(inputs.unpriced_assets),
        None,
        None,
        "unpriced_assets",
    )


# ---------------------------------------------------------------------------------- scenarios
SCENARIO_ASSUMPTION = (
    "Hypothetical: the share is lowered to the cap and the difference is spread over the "
    "rest of the portfolio in proportion to its current shares. Prices, fees and taxes are "
    "ignored. Not a recommendation and not an order."
)


def capped(shares: dict[str, Decimal], subject: str, cap: Decimal) -> dict[str, Decimal]:
    """Shares (fractions adding up to 1) with `subject` lowered to `cap` and the excess spread
    over the others in proportion to their shares. Unchanged when it is already at or below the
    cap or there is nothing else to spread over."""
    current = shares[subject]
    rest = ONE - current
    if current <= cap or rest <= ZERO:
        return dict(shares)
    scale = (ONE - cap) / rest
    return {k: cap if k == subject else v * scale for k, v in shares.items()}


def _scenario_for_positions(inputs: Inputs, t: Thresholds, finding: Finding) -> Scenario | None:
    if finding.status is not CheckStatus.FLAGGED or finding.subject is None:
        return None
    parts = _parts(inputs)
    shares = {p.key: p.value / inputs.total for p in parts}
    after = capped(shares, finding.subject, t.position_cap)
    if after == shares:
        return None
    return Scenario(
        Check.POSITION_CONCENTRATION,
        f"If the largest holding were {_pct(t.position_cap)} of the portfolio instead of "
        f"{_pct(shares[finding.subject])}.",
        (ShareChange(finding.subject, shares[finding.subject], after[finding.subject]),),
        "effective_positions",
        _effective(shares.values()),
        _effective(after.values()),
        (SCENARIO_ASSUMPTION,),
    )


def _scenario_for_classes(inputs: Inputs, t: Thresholds, finding: Finding) -> Scenario | None:
    if finding.status is not CheckStatus.FLAGGED or finding.subject is None:
        return None
    allocation = allocate(_parts(inputs), Dimension.ASSET_CLASS)
    shares = {str(s.key): s.value / inputs.total for s in allocation.slices}
    after = capped(shares, finding.subject, t.asset_class_cap)
    if after == shares:
        return None
    return Scenario(
        Check.ASSET_CLASS_CONCENTRATION,
        f"If {finding.subject} were {_pct(t.asset_class_cap)} of the portfolio instead of "
        f"{_pct(shares[finding.subject])}.",
        tuple(
            ShareChange(k, shares[k], after[k])
            for k in sorted(shares, key=lambda k: (-shares[k], k))
        ),
        "asset_class_hhi",
        herfindahl(list(shares.values())),
        herfindahl(list(after.values())),
        (SCENARIO_ASSUMPTION,),
    )


def _effective(shares: Iterable[Decimal]) -> Decimal | None:
    hhi = herfindahl(list(shares))
    return None if hhi is None or hhi == ZERO else ONE / hhi


# ------------------------------------------------------------------------------------ diagnose
def diagnose(inputs: Inputs, t: Thresholds = DEFAULT_THRESHOLDS) -> Diagnosis:
    """Every check, in a fixed order, and the scenarios for flagged concentrations."""
    completeness = data_completeness(inputs, t)
    if not _measurable(inputs):
        why = (
            "The portfolio has no value to analyse."
            if inputs.total <= ZERO
            else "A negative balance makes shares of the total meaningless."
        )
        findings = (
            *(_not_assessed(c, why) for c in Check if c is not Check.DATA_COMPLETENESS),
            completeness,
        )
        return Diagnosis(inputs.currency, inputs.total, findings, ())
    position = position_concentration(inputs, t)
    classes = asset_class_concentration(inputs, t)
    findings = (
        position,
        classes,
        _known_concentration(
            inputs, t, Check.SECTOR_CONCENTRATION, Dimension.SECTOR, t.sector, "sector"
        ),
        _known_concentration(
            inputs, t, Check.GEOGRAPHIC_CONCENTRATION, Dimension.COUNTRY, t.country, "country"
        ),
        currency_exposure(inputs, t),
        liquidity(inputs, t),
        volatility(inputs, t),
        drawdown(inputs, t),
        income_dependence(inputs, t),
        goal_alignment(inputs, t),
        completeness,
    )
    scenarios = tuple(
        s
        for s in (
            _scenario_for_positions(inputs, t, position),
            _scenario_for_classes(inputs, t, classes),
        )
        if s is not None
    )
    return Diagnosis(inputs.currency, inputs.total, findings, scenarios)
