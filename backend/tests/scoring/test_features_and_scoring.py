"""Instrument features and explainable scores (P12-T03): features from closes with every missing
one explained, each factor's transform at its boundaries, contributions adding up to the score,
and missing data lowering confidence rather than being ignored."""

from datetime import date, timedelta
from decimal import Decimal
from itertools import pairwise

import pytest

from app.core.config import Settings
from app.modules.analytics.risk import max_drawdown, volatility
from app.modules.assets.liquidity import Liquidity
from app.modules.scoring.features import Close, Feature, Features, compute, weekly
from app.modules.scoring.scoring import (
    DEFAULT_WEIGHTS,
    Confidence,
    Factor,
    FactorStatus,
    score,
    sub_score,
    validate_weights,
)

D = Decimal
TODAY = date(2026, 10, 13)  # a Tuesday
FRESH = timedelta(days=4)


def series(
    days: int, end: date = TODAY, start_price: str = "100", step: str = "0.001"
) -> list[Close]:
    """Daily closes on weekdays, alternately up and down around a rising trend."""
    out, price = [], D(start_price)
    for i in range(days, -1, -1):
        on = end - timedelta(days=i)
        if on.weekday() < 5:
            wiggle = D("1.01") if i % 2 else D("0.995")
            price = (price * (1 + D(step)) * wiggle).quantize(D("0.0001"))
            out.append(Close(on, price))
    return out


def features(closes: list[Close], **kw: object) -> Features:
    args: dict[str, object] = {
        "risk_level": 3, "liquidity": Liquidity.MARKET, "priced": True, "fund": False,
        "expense_ratio": None, "today": TODAY, "stale_after": FRESH,
    } | kw  # fmt: skip
    return compute(closes, **args)  # type: ignore[arg-type]


def full(**kw: object) -> Features:
    base: dict[str, object] = {
        "risk_level": 2, "liquidity": Liquidity.MARKET, "priced": True, "fund": True,
        "trailing_return": D("0.10"), "volatility": D("0.15"), "max_drawdown": D("0.12"),
        "expense_ratio": D("0.002"), "last_close": TODAY, "weeks": 52,
    } | kw  # fmt: skip
    return Features(**base)  # type: ignore[arg-type]


# ------------------------------------------------------------------------------------ features
def test_weekly_keeps_the_last_close_of_each_iso_week() -> None:
    closes = [Close(date(2026, 10, d), D(d)) for d in (5, 6, 9, 12, 13)]  # Mon..Fri, Mon, Tue
    assert [c.on.day for c in weekly(closes)] == [9, 13]


def test_a_years_closes_give_every_price_feature_from_the_risk_maths() -> None:
    closes = series(400)
    f = features(closes)
    window = [c for c in closes if c.on >= TODAY - timedelta(days=365)]
    weeks = weekly(window)
    returns = [b.price / a.price - 1 for a, b in pairwise(weeks)]
    assert f.volatility == volatility(returns, 52)[1]
    assert f.max_drawdown == -max_drawdown([(c.on, c.price) for c in weeks]).depth
    assert f.trailing_return == window[-1].price / window[0].price - 1
    assert f.missing == () and not f.stale_prices and f.last_close == TODAY


def test_short_histories_are_missing_with_the_reason() -> None:
    f = features(series(120))
    missing = {m.feature: m.reason for m in f.missing}
    assert missing[Feature.TRAILING_RETURN] == "Less than 10 months of prices in the last year."
    assert "Fewer than 26 weeks" in missing[Feature.VOLATILITY]
    assert Feature.MAX_DRAWDOWN in missing and f.volatility is None


@pytest.mark.parametrize(
    ("kw", "reason"),
    [
        ({"priced": False}, "Valued manually: there are no market prices."),
        ({}, "No market prices in the last year."),
    ],
)
def test_no_prices_is_explained(kw: dict[str, object], reason: str) -> None:
    f = features([Close(TODAY - timedelta(days=500), D(1))], **kw)  # outside the window
    assert [m.reason for m in f.missing] == [reason] * 3


def test_stale_closes_are_flagged() -> None:
    assert features(series(400, end=TODAY - timedelta(days=5))).stale_prices
    assert not features(series(400, end=TODAY - timedelta(days=4))).stale_prices


def test_a_fund_without_an_expense_ratio_and_unknown_liquidity_are_missing() -> None:
    f = features(series(400), fund=True, liquidity=Liquidity.UNKNOWN)
    assert {m.feature for m in f.missing} == {Feature.EXPENSE_RATIO, Feature.LIQUIDITY}
    assert features(series(400), expense_ratio=D("0.01")).expense_ratio is None, "not a fund"


# ---------------------------------------------------------------------------------- transforms
@pytest.mark.parametrize(
    ("factor", "field", "value", "points"),
    [
        (Factor.STABILITY, "volatility", "0", "100"),
        (Factor.STABILITY, "volatility", "0.30", "50"),
        (Factor.STABILITY, "volatility", "0.90", "0"),
        (Factor.RESILIENCE, "max_drawdown", "0.15", "75"),
        (Factor.RESILIENCE, "max_drawdown", "0.60", "0"),
        (Factor.MOMENTUM, "trailing_return", "-0.50", "0"),
        (Factor.MOMENTUM, "trailing_return", "0", "50"),
        (Factor.MOMENTUM, "trailing_return", "0.25", "75"),
        (Factor.MOMENTUM, "trailing_return", "2", "100"),
        (Factor.COST, "expense_ratio", "0", "100"),
        (Factor.COST, "expense_ratio", "0.01", "50"),
        (Factor.COST, "expense_ratio", "0.03", "0"),
    ],
)
def test_each_transform_at_its_boundaries(
    factor: Factor, field: str, value: str, points: str
) -> None:
    assert sub_score(factor, full(**{field: D(value)})) == D(points)


def test_liquidity_and_risk_class_points() -> None:
    expected = {Liquidity.IMMEDIATE: 100, Liquidity.MARKET: 80, Liquidity.TERM: 40,
                Liquidity.ILLIQUID: 10, Liquidity.UNKNOWN: None}  # fmt: skip
    for liq, pts in expected.items():
        got = sub_score(Factor.LIQUIDITY, full(liquidity=liq))
        assert got == (None if pts is None else D(pts))
    levels = [sub_score(Factor.RISK_CLASS, full(risk_level=r)) for r in range(1, 6)]
    assert levels == [D(100), D(75), D(50), D(25), D(0)]


# ------------------------------------------------------------------------------------- scores
def test_a_fully_measured_fund_decomposes_exactly_into_its_contributions() -> None:
    s = score(full())
    # stability 75, resilience 80, momentum 60, cost 90, liquidity 80, risk class 75.
    expected = (D("0.25") * 75 + D("0.20") * 80 + D("0.15") * 60 + D("0.10") * 90
                + D("0.15") * 80 + D("0.15") * 75)  # fmt: skip
    assert s.score == expected == sum(r.contribution for r in s.factors)
    assert (s.coverage, s.confidence, s.reasons) == (D(1), Confidence.HIGH, ())
    assert all(r.status is FactorStatus.USED for r in s.factors)
    assert [r.factor for r in s.factors] == list(Factor), "every factor, in a fixed order"


def test_cost_does_not_apply_to_a_share_and_costs_it_nothing() -> None:
    s = score(full(fund=False, expense_ratio=None))
    cost = next(r for r in s.factors if r.factor is Factor.COST)
    assert cost.status is FactorStatus.NOT_APPLICABLE and cost.contribution == 0
    assert s.coverage == 1 and s.confidence is Confidence.HIGH
    assert sum(r.effective_weight for r in s.factors) == 1


def test_missing_data_lowers_coverage_and_confidence_and_says_why() -> None:
    f = full(trailing_return=None, missing=())
    s = score(f)
    momentum = next(r for r in s.factors if r.factor is Factor.MOMENTUM)
    assert momentum.status is FactorStatus.MISSING and momentum.contribution == 0
    assert s.coverage == D("0.85") and s.confidence is Confidence.HIGH  # 85% is the boundary
    two = score(full(trailing_return=None, expense_ratio=None))
    assert two.coverage == D("0.75") and two.confidence is Confidence.MEDIUM
    assert len(two.reasons) == 2 and two.score == sum(r.contribution for r in two.factors)


def test_a_manually_valued_instrument_has_too_little_data_to_score() -> None:
    f = features([], priced=False, liquidity=Liquidity.MARKET, risk_level=2)
    s = score(f)
    # Liquidity and risk class: 0.30 of the 0.90 that applies to a non-fund.
    assert s.score is None and s.confidence is Confidence.NONE
    assert s.coverage == D("0.30") / D("0.90")
    assert "Valued manually" in s.reasons[0]


def test_stale_prices_keep_confidence_below_high() -> None:
    s = score(full(stale_prices=True))
    assert s.confidence is Confidence.MEDIUM
    assert s.reasons == ("The latest price is older than its freshness window.",)


def test_the_same_features_always_score_the_same() -> None:
    assert score(full()) == score(full())


# ------------------------------------------------------------------------------------ weights
@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"stability": "0.35"}, "add up to 1"),
        ({"stability": "-0.05", "resilience": "0.50"}, "negative"),
        ({"surprise": "0"}, "unknown factor"),
    ],
)
def test_weights_are_validated(change: dict[str, str], message: str) -> None:
    weights = {f.value: str(w) for f, w in DEFAULT_WEIGHTS.items()} | change
    with pytest.raises(ValueError, match=message):
        validate_weights({k: D(v) for k, v in weights.items()})
    partial = {f.value: w for f, w in DEFAULT_WEIGHTS.items() if f is not Factor.COST}
    with pytest.raises(ValueError, match="every factor"):
        validate_weights(partial)


def test_the_default_weights_add_up_and_settings_refuse_bad_ones() -> None:
    assert sum(DEFAULT_WEIGHTS.values()) == 1
    assert validate_weights(Settings().opportunity_score_weights) == DEFAULT_WEIGHTS
    with pytest.raises(ValueError, match="add up to 1"):
        Settings(opportunity_score_weights={f.value: D("0.5") for f in Factor})
