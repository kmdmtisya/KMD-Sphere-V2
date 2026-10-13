"""Portfolio compatibility and suitability (P12-T04). Pure and Decimal-only.

What would adding an amount of a universe instrument do to one of the user's portfolios? The
amount is treated as **new money added** (nothing is sold); the portfolio is re-measured with the
same deterministic analytics and Portfolio Doctor rules as today, before and after. This is a
hypothetical calculation for analysis, never an order.

Verdict:
- **not_suitable** when the instrument is not eligible for the user (P12-T02) or the amount is
  below the instrument's stated minimum;
- **caution** when a Doctor check gets worse and ends at medium or high, when the instrument would
  be more than the Doctor's medium holding threshold of the portfolio, or when the minimum could
  not be checked;
- **fits** otherwise."""

import uuid
from dataclasses import dataclass, replace
from decimal import Decimal
from enum import StrEnum

from app.core.money import format_decimal, round_half_up
from app.modules.analytics.allocation import Dimension, allocate, concentration
from app.modules.assets.liquidity import ACCESSIBLE, LIQUIDITY_BY_CLASS, Liquidity
from app.modules.doctor.rules import (
    DEFAULT_THRESHOLDS,
    Check,
    CheckStatus,
    Holding,
    Inputs,
    Severity,
    Thresholds,
    diagnose,
    parts,
)
from app.modules.universe.eligibility import Eligibility

ZERO = Decimal(0)
ASSUMPTION = (
    "Hypothetical: the amount is added as new money and nothing is sold. Prices, fees and taxes "
    "are ignored. Not a recommendation and not an order."
)


class Verdict(StrEnum):
    FITS = "fits"
    CAUTION = "caution"
    NOT_SUITABLE = "not_suitable"


@dataclass(frozen=True)
class Candidate:
    asset_id: uuid.UUID
    asset_class: str
    currency: str
    country: str | None = None
    sector: str | None = None


@dataclass(frozen=True)
class Measures:
    """Shares are fractions of the portfolio's total value."""

    total: Decimal
    candidate_share: Decimal
    largest_holding: Decimal | None
    effective_positions: Decimal | None
    class_share: Decimal  # the candidate's asset class
    foreign_currency: Decimal
    accessible: Decimal


@dataclass(frozen=True)
class CheckChange:
    check: Check
    before: Severity
    after: Severity

    @property
    def worse(self) -> bool:
        return self.after.rank > self.before.rank


@dataclass(frozen=True)
class Reason:
    code: str
    message: str


@dataclass(frozen=True)
class Assessment:
    verdict: Verdict
    reasons: tuple[Reason, ...]
    before: Measures
    after: Measures
    changes: tuple[CheckChange, ...]  # Doctor checks whose severity changes


def add(inputs: Inputs, candidate: Candidate, amount: Decimal) -> Inputs:
    """The portfolio with `amount` (base currency) more of the candidate, as new money."""
    held = [h for h in inputs.holdings if h.asset_id == candidate.asset_id]
    if held:
        holdings = [
            replace(h, value=h.value + amount) if h.asset_id == candidate.asset_id else h
            for h in inputs.holdings
        ]
    else:
        holdings = [
            *inputs.holdings,
            Holding(
                candidate.asset_id,
                amount,
                candidate.asset_class,
                candidate.currency,
                candidate.country,
                candidate.sector,
            ),
        ]
    return replace(inputs, holdings=holdings, total=inputs.total + amount)


def measure(inputs: Inputs, candidate: Candidate) -> Measures:
    parts_ = parts(inputs)
    total = inputs.total
    if total <= ZERO:
        return Measures(total, ZERO, None, None, ZERO, ZERO, ZERO)
    mine = sum((h.value for h in inputs.holdings if h.asset_id == candidate.asset_id), ZERO)
    largest = max((h.value for h in inputs.holdings), default=None)
    conc = concentration(parts_)
    classes = allocate(parts_, Dimension.ASSET_CLASS)
    class_value = sum((s.value for s in classes.slices if s.key == candidate.asset_class), ZERO)
    currencies = allocate(parts_, Dimension.CURRENCY)
    foreign = sum((s.value for s in currencies.slices if s.key != inputs.currency), ZERO)
    accessible = sum(inputs.cash_balances.values(), ZERO) + sum(
        (
            h.value
            for h in inputs.holdings
            if LIQUIDITY_BY_CLASS.get(h.asset_class, Liquidity.UNKNOWN) in ACCESSIBLE
        ),
        ZERO,
    )
    return Measures(
        total=total,
        candidate_share=mine / total,
        largest_holding=None if largest is None else largest / total,
        effective_positions=conc.effective_positions,
        class_share=class_value / total,
        foreign_currency=foreign / total,
        accessible=accessible / total,
    )


def _severities(inputs: Inputs, t: Thresholds) -> dict[Check, Severity]:
    return {
        f.check: f.severity if f.status is CheckStatus.FLAGGED else Severity.OK
        for f in diagnose(inputs, t).findings
    }


def assess(
    inputs: Inputs,
    candidate: Candidate,
    amount: Decimal,
    eligibility: Eligibility,
    *,
    minimum: Decimal | None,
    amount_in_instrument_currency: Decimal | None,
    t: Thresholds = DEFAULT_THRESHOLDS,
) -> Assessment:
    """`amount` is in the portfolio's base currency; `minimum` and
    `amount_in_instrument_currency` in the instrument's (None when no rate converts it)."""
    after_inputs = add(inputs, candidate, amount)
    before, after = measure(inputs, candidate), measure(after_inputs, candidate)
    sev_before, sev_after = _severities(inputs, t), _severities(after_inputs, t)
    changes = tuple(
        CheckChange(check, sev_before[check], sev_after[check])
        for check in Check
        if sev_before[check] is not sev_after[check]
    )
    blocking: list[Reason] = [
        Reason(f"eligibility_{o.rule.value}", o.reason)
        for o in eligibility.outcomes
        if not o.passed
    ]
    caution: list[Reason] = []
    if minimum is not None:
        if amount_in_instrument_currency is None:
            caution.append(
                Reason(
                    "minimum_unchecked",
                    "The minimum investment could not be checked: no exchange rate to its "
                    "currency.",
                )
            )
        elif amount_in_instrument_currency < minimum:
            blocking.append(
                Reason(
                    "below_minimum",
                    f"The amount is below the stated minimum investment of {minimum} "
                    f"{candidate.currency}.",
                )
            )
    for c in changes:
        if c.worse and c.after.rank >= Severity.MEDIUM.rank:
            caution.append(
                Reason(
                    f"worsens_{c.check.value}",
                    f"The Portfolio Doctor's {c.check.value.replace('_', ' ')} check would go "
                    f"from {c.before.value} to {c.after.value}.",
                )
            )
    medium = t.position.medium
    if medium is not None and after.candidate_share > medium:
        caution.append(
            Reason(
                "large_holding",
                f"It would be {_pct(after.candidate_share)} of the portfolio, above the "
                f"{_pct(medium)} holding threshold.",
            )
        )
    verdict = Verdict.NOT_SUITABLE if blocking else Verdict.CAUTION if caution else Verdict.FITS
    return Assessment(verdict, tuple(blocking + caution), before, after, changes)


def _pct(share: Decimal) -> str:
    return f"{format_decimal(round_half_up(share * 100, 2))}%"
