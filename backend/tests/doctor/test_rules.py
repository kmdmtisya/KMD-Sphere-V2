"""Portfolio Doctor rules (P12-T01): every check at its thresholds, the not-assessed paths,
scenarios that are never trades, and determinism."""

import uuid
from dataclasses import replace
from decimal import Decimal
from typing import Any

import pytest

from app.modules.assets.catalogue import INITIAL_CLASSES
from app.modules.doctor.rules import (
    LIQUIDITY_ASSUMPTION,
    LIQUIDITY_BY_CLASS,
    Check,
    CheckStatus,
    Diagnosis,
    Finding,
    GoalState,
    Holding,
    Inputs,
    Severity,
    capped,
    diagnose,
)

D = Decimal


def ids(n: int) -> list[uuid.UUID]:
    return [uuid.UUID(int=i + 1) for i in range(n)]


def h(
    i: int,
    value: str,
    cls: str = "stock",
    currency: str = "USD",
    country: str | None = "US",
    sector: str | None = "Tech",
) -> Holding:
    return Holding(uuid.UUID(int=i), D(value), cls, currency, country, sector)


def inputs(*holdings: Holding, cash: dict[str, str] | None = None, **kw: Any) -> Inputs:
    balances = {c: D(v) for c, v in (cash or {}).items()}
    total = sum((x.value for x in holdings), D(0)) + sum(balances.values(), D(0))
    base = Inputs("USD", total, list(holdings), balances, complete=True)
    return replace(base, **kw)


def finding(diagnosis: Diagnosis, check: Check) -> Finding:
    return next(f for f in diagnosis.findings if f.check is check)


def spread(n: int) -> list[Holding]:
    """n equal holdings, each in its own sector, half in Kenya and half in the US."""
    return [h(i + 1, "100", sector=f"S{i}", country="KE" if i % 2 else "US") for i in range(n)]


# ------------------------------------------------------------------------------ concentration
@pytest.mark.parametrize(
    ("largest", "severity"),
    [("9.99", Severity.OK), ("10", Severity.LOW), ("20", Severity.MEDIUM), ("35", Severity.HIGH)],
)
def test_the_largest_holding_is_graded_at_each_threshold(largest: str, severity: Severity) -> None:
    rest = D(100) - D(largest)
    # The rest in small equal holdings so only the largest can trigger the check.
    others = [h(i + 2, str(rest / 20), sector=f"S{i}") for i in range(20)]
    f = finding(diagnose(inputs(h(1, largest), *others)), Check.POSITION_CONCENTRATION)
    assert f.severity is severity
    assert f.status is (CheckStatus.OK if severity is Severity.OK else CheckStatus.FLAGGED)
    assert f.subject == str(uuid.UUID(int=1)) and f.value == D(largest) / 100


def test_one_asset_class_is_flagged_and_its_scenario_only_rescales_shares() -> None:
    d = diagnose(inputs(h(1, "900"), h(2, "50", "bond"), cash={"USD": "50"}))
    f = finding(d, Check.ASSET_CLASS_CONCENTRATION)
    assert (f.severity, f.subject, f.value, f.threshold) == (
        Severity.HIGH,
        "stock",
        D("0.9"),
        D("0.90"),
    )
    scenario = next(s for s in d.scenarios if s.check is Check.ASSET_CLASS_CONCENTRATION)
    after = {c.subject: c.after for c in scenario.changes}
    assert after == {"stock": D("0.60"), "bond": D("0.2"), "cash": D("0.2")}
    assert sum(after.values()) == 1
    assert scenario.after is not None and scenario.before is not None
    assert scenario.after < scenario.before, "the hypothetical mix is less concentrated"
    assert "not an order" in scenario.assumptions[0]


def test_a_single_holding_has_no_scenario_because_there_is_nothing_to_spread_over() -> None:
    d = diagnose(inputs(h(1, "1000")))
    assert finding(d, Check.POSITION_CONCENTRATION).severity is Severity.HIGH
    assert d.scenarios == ()


def test_capping_keeps_the_total_and_the_proportions_of_the_rest() -> None:
    shares = {"a": D("0.5"), "b": D("0.3"), "c": D("0.2")}
    after = capped(shares, "a", D("0.2"))
    assert after["a"] == D("0.2") and sum(after.values()) == 1
    assert after["b"] / after["c"] == shares["b"] / shares["c"]
    assert capped(shares, "c", D("0.25")) == shares, "already under the cap"


def test_sector_and_country_count_only_known_values_and_say_when_most_are_unknown() -> None:
    known = [h(1, "60", sector="Banks", country="KE"), h(2, "40", sector="Tech", country="US")]
    d = diagnose(inputs(*known))
    assert finding(d, Check.SECTOR_CONCENTRATION).severity is Severity.HIGH  # 60% Banks
    assert finding(d, Check.SECTOR_CONCENTRATION).subject == "Banks"
    assert finding(d, Check.GEOGRAPHIC_CONCENTRATION).severity is Severity.OK  # 60% KE

    unknown = [h(1, "20", sector="Banks"), h(2, "40", sector=None), h(3, "40", sector=None)]
    f = finding(diagnose(inputs(*unknown)), Check.SECTOR_CONCENTRATION)
    assert (f.status, f.severity, f.metric) == (
        CheckStatus.FLAGGED,
        Severity.INFO,
        "unknown_sector_share",
    )
    assert f.value == D("0.8")

    nothing = diagnose(inputs(h(1, "100", sector=None)))
    assert finding(nothing, Check.SECTOR_CONCENTRATION).status is CheckStatus.NOT_ASSESSED


def test_cash_is_not_counted_as_an_unknown_country() -> None:
    d = diagnose(inputs(h(1, "40", country="KE"), h(2, "10", country="US"), cash={"KES": "50"}))
    f = finding(d, Check.GEOGRAPHIC_CONCENTRATION)
    assert f.metric == "share" and f.value == D("0.4")


# ------------------------------------------------------------------------- currency, liquidity
@pytest.mark.parametrize(
    ("foreign", "severity"),
    [("24", Severity.OK), ("25", Severity.LOW), ("50", Severity.MEDIUM), ("75", Severity.HIGH)],
)
def test_foreign_currency_exposure(foreign: str, severity: Severity) -> None:
    base = str(D(100) - D(foreign))
    d = diagnose(inputs(h(1, foreign, currency="EUR"), cash={"USD": base}))
    f = finding(d, Check.CURRENCY_EXPOSURE)
    assert f.severity is severity and f.value == D(foreign) / 100


@pytest.mark.parametrize(
    ("accessible", "severity"),
    [
        ("9.99", Severity.HIGH),
        ("10", Severity.MEDIUM),
        ("24.99", Severity.MEDIUM),
        ("25", Severity.OK),
    ],
)
def test_liquidity_flags_a_small_accessible_share(accessible: str, severity: Severity) -> None:
    locked = str(D(100) - D(accessible))
    d = diagnose(inputs(h(1, locked, "real_estate"), cash={"USD": accessible}))
    f = finding(d, Check.LIQUIDITY)
    assert f.severity is severity and f.value == D(accessible) / 100
    assert f.assumptions == (LIQUIDITY_ASSUMPTION,), "the class-based liquidity is stated"


def test_every_asset_class_has_a_stated_liquidity() -> None:
    assert {c.code for c in INITIAL_CLASSES} == set(LIQUIDITY_BY_CLASS)


# --------------------------------------------------------------------------------------- risk
def test_volatility_and_drawdown_are_graded_or_not_assessed_with_the_reason() -> None:
    d = diagnose(
        inputs(*spread(10), volatility=D("0.22"), max_drawdown=D("0.36"), risk_status="ok")
    )
    assert finding(d, Check.VOLATILITY).severity is Severity.MEDIUM
    assert finding(d, Check.DRAWDOWN).severity is Severity.HIGH
    assert "not a forecast" in finding(d, Check.VOLATILITY).assumptions[0]

    young = diagnose(inputs(*spread(10), risk_status="insufficient_data"))
    for check in (Check.VOLATILITY, Check.DRAWDOWN):
        f = finding(young, check)
        assert f.status is CheckStatus.NOT_ASSESSED and "a year of monthly history" in f.message


# --------------------------------------------------------------------------- income and goals
def test_income_from_one_source_is_high_and_no_income_is_not_assessed() -> None:
    a, b = ids(2)
    one = diagnose(inputs(*spread(10), income_by_asset={a: D("100")}))
    assert finding(one, Check.INCOME_DEPENDENCE).severity is Severity.HIGH
    split = diagnose(inputs(*spread(10), income_by_asset={a: D("55"), b: D("45")}))
    f = finding(split, Check.INCOME_DEPENDENCE)
    assert (f.severity, f.subject) == (Severity.MEDIUM, str(a))
    interest = diagnose(inputs(*spread(10), income_by_asset={None: D("10"), a: D("30")}))
    assert finding(interest, Check.INCOME_DEPENDENCE).subject == str(a)
    none = diagnose(inputs(*spread(10)))
    assert finding(none, Check.INCOME_DEPENDENCE).status is CheckStatus.NOT_ASSESSED


def test_goals_overdue_behind_on_track_and_none() -> None:
    g1, g2 = ids(2)

    def goals(*states: GoalState) -> Finding:
        return finding(diagnose(inputs(*spread(10), goals=list(states))), Check.GOAL_ALIGNMENT)

    on = GoalState(g1, "House", "on_track", reached=False, overdue=False)
    behind = GoalState(g2, "School", "behind", reached=False, overdue=False)
    late = GoalState(g2, "Car", "behind", reached=False, overdue=True)
    reached_late = GoalState(g2, "Trip", "behind", reached=True, overdue=True)
    assert goals(on).status is CheckStatus.OK
    assert goals(on, reached_late).status is CheckStatus.OK, "a reached goal is not a concern"
    assert (goals(on, behind).severity, goals(on, behind).subject) == (Severity.MEDIUM, str(g2))
    assert goals(on, late).severity is Severity.HIGH
    assert "estimate" in goals(on).assumptions[0]
    assert goals().status is CheckStatus.NOT_ASSESSED


# ------------------------------------------------------------------------ data and edge cases
def test_unpriced_holdings_are_an_info_finding() -> None:
    d = diagnose(inputs(*spread(10), complete=False, unpriced_assets=2))
    f = finding(d, Check.DATA_COMPLETENESS)
    assert (f.status, f.severity, f.value) == (CheckStatus.FLAGGED, Severity.INFO, D(2))


@pytest.mark.parametrize("cash", [{}, {"USD": "-50"}])
def test_an_empty_or_negative_portfolio_is_not_assessed(cash: dict[str, str]) -> None:
    holdings = [] if not cash else [h(1, "100")]
    d = diagnose(inputs(*holdings, cash=cash))
    assessed = [f for f in d.findings if f.check is not Check.DATA_COMPLETENESS]
    assert all(f.status is CheckStatus.NOT_ASSESSED for f in assessed)
    assert d.scenarios == () and d.overall is Severity.OK


def test_a_well_spread_portfolio_has_no_flags() -> None:
    classes = ["stock", "etf", "bond", "mutual_fund", "reit"]
    holdings = [
        h(i + 1, "100", classes[i % 5], sector=f"S{i}", country="KE" if i < 5 else "US")
        for i in range(10)
    ]
    d = diagnose(
        inputs(
            *holdings,
            cash={"USD": "300"},
            risk_status="ok",
            volatility=D("0.08"),
            max_drawdown=D("0.05"),
        )
    )
    flagged = [f for f in d.findings if f.status is CheckStatus.FLAGGED]
    assert flagged == [] and d.overall is Severity.OK and d.scenarios == ()
    assert [f.check for f in d.findings] == list(Check), "every check, in a fixed order"


def test_overall_is_the_worst_flag_and_counts_add_up() -> None:
    d = diagnose(inputs(h(1, "1000"), complete=False, unpriced_assets=1))
    assert d.overall is Severity.HIGH
    flagged = [f for f in d.findings if f.status is CheckStatus.FLAGGED]
    assert sum(d.count(s) for s in Severity if s is not Severity.OK) == len(flagged)


def test_the_same_portfolio_gives_the_same_findings_whatever_the_order() -> None:
    holdings = [h(i + 1, str(50 + i * 7), sector=f"S{i % 3}") for i in range(12)]
    expected = diagnose(inputs(*holdings, cash={"USD": "40", "EUR": "60"}))
    orders = [holdings[::-1], holdings[5:] + holdings[:5], sorted(holdings, key=lambda x: -x.value)]
    for order in orders:
        assert diagnose(inputs(*order, cash={"EUR": "60", "USD": "40"})) == expected


def test_ties_resolve_the_same_way_every_time() -> None:
    d = diagnose(inputs(h(2, "500"), h(1, "500")))
    assert finding(d, Check.POSITION_CONCENTRATION).subject == str(uuid.UUID(int=2))


def test_messages_never_give_instructions() -> None:
    d = diagnose(
        inputs(
            h(1, "900", "real_estate", "EUR"), cash={"USD": "100"}, income_by_asset={None: D("5")}
        )
    )
    text = " ".join([f.message for f in d.findings] + [s.description for s in d.scenarios])
    # Descriptions only: no advice or instruction words ("slow to sell" describes, it is fine).
    for word in ("should", "must", "consider", "recommend", "guarantee", "buy", "you need"):
        assert word not in text.lower(), word
