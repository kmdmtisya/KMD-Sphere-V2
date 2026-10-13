"""Eligibility rules (P12-T02.3): jurisdiction, risk and liquidity at their boundaries, and that
an instrument is eligible only when every rule passes, with the reason for each."""

import pytest

from app.modules.assets.liquidity import Liquidity
from app.modules.universe.eligibility import (
    LAUNCH_JURISDICTIONS,
    MAX_RISK_LEVEL,
    Instrument,
    Investor,
    JurisdictionRules,
    Rule,
    evaluate,
    jurisdiction,
    liquidity,
    risk,
)

KE_BALANCED = Investor("KE", "balanced", 3)


def instrument(
    risk_level: int = 2,
    liq: Liquidity = Liquidity.MARKET,
    where: tuple[str, ...] = ("KE", "AE"),
    cls: str = "etf",
    active: bool = True,
) -> Instrument:
    return Instrument(cls, risk_level, liq, where, active)


def test_the_launch_jurisdictions_are_kenya_and_the_uae_and_none_is_legally_reviewed() -> None:
    assert set(LAUNCH_JURISDICTIONS) == {"KE", "AE"}
    assert not any(r.legally_reviewed for r in LAUNCH_JURISDICTIONS.values())


@pytest.mark.parametrize(
    ("country", "where", "passed", "reason"),
    [
        (None, ("KE",), False, "No country of residence is set."),
        ("GB", ("KE", "GB"), False, "GB is not a supported jurisdiction yet."),
        ("AE", ("KE",), False, "Not offered in AE."),
        ("KE", ("KE",), True, "Offered in KE."),
    ],
)
def test_jurisdiction(
    country: str | None, where: tuple[str, ...], passed: bool, reason: str
) -> None:
    outcome = jurisdiction(Investor(country, "aggressive", 10), instrument(where=where))
    assert (outcome.rule, outcome.passed, outcome.reason) == (Rule.JURISDICTION, passed, reason)
    assert outcome.legally_reviewed is False, "every jurisdiction outcome says it is unreviewed"


def test_a_class_excluded_in_a_country_fails_with_the_reason() -> None:
    rules = {"KE": JurisdictionRules("KE", frozenset({"cryptocurrency"}))}
    outcome = jurisdiction(KE_BALANCED, instrument(cls="cryptocurrency"), rules)
    assert not outcome.passed and outcome.reason == "cryptocurrency is excluded in KE."


@pytest.mark.parametrize(("tolerance", "ceiling"), sorted(MAX_RISK_LEVEL.items()))
def test_risk_level_up_to_the_tolerances_ceiling(tolerance: str, ceiling: int) -> None:
    investor = Investor("KE", tolerance, 10)
    assert risk(investor, instrument(risk_level=ceiling)).passed
    if ceiling < 5:
        above = risk(investor, instrument(risk_level=ceiling + 1))
        assert not above.passed and f"above the {ceiling}" in above.reason


def test_without_a_risk_profile_nothing_passes_the_risk_rule() -> None:
    outcome = risk(Investor("KE", None, None), instrument(risk_level=1))
    assert not outcome.passed and outcome.reason == "No risk profile is set."


@pytest.mark.parametrize(
    ("liq", "horizon", "passed"),
    [
        (Liquidity.IMMEDIATE, None, True),
        (Liquidity.MARKET, 0, True),
        (Liquidity.TERM, None, False),
        (Liquidity.TERM, 0, False),
        (Liquidity.TERM, 1, True),
        (Liquidity.ILLIQUID, 4, False),
        (Liquidity.ILLIQUID, 5, True),
        (Liquidity.UNKNOWN, 4, False),
        (Liquidity.UNKNOWN, 5, True),
    ],
)
def test_locked_money_needs_a_long_enough_horizon(
    liq: Liquidity, horizon: int | None, passed: bool
) -> None:
    outcome = liquidity(Investor("KE", "balanced", horizon), instrument(liq=liq))
    assert outcome.passed is passed
    assert outcome.reason


def test_eligible_only_when_every_rule_passes_and_every_rule_is_reported() -> None:
    ok = evaluate(KE_BALANCED, instrument())
    assert ok.eligible and ok.reasons == []
    assert [o.rule for o in ok.outcomes] == list(Rule), "every rule, in a fixed order"

    risky_and_locked = evaluate(KE_BALANCED, instrument(risk_level=5, liq=Liquidity.ILLIQUID))
    assert not risky_and_locked.eligible
    assert len(risky_and_locked.reasons) == 2, "each failing rule says why"

    gone = evaluate(KE_BALANCED, instrument(active=False))
    assert not gone.eligible and gone.reasons == ["No longer in the universe."]


def test_the_same_inputs_always_give_the_same_answer() -> None:
    a = evaluate(Investor("AE", "growth", 2), instrument(risk_level=4, where=("AE",)))
    b = evaluate(Investor("AE", "growth", 2), instrument(risk_level=4, where=("AE",)))
    assert a == b and a.eligible
