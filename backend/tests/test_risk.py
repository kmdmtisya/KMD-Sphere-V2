"""Risk metrics (P06-T08): returns, volatility, drawdown and status (docs/design/risk.md)."""

import statistics
from datetime import date, timedelta
from decimal import Decimal, localcontext

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.modules.analytics.performance import TwrStatus
from app.modules.analytics.risk import (
    MIN_RETURNS,
    Drawdown,
    Observation,
    RiskStatus,
    index,
    max_drawdown,
    measure,
    period_returns,
    volatility,
)

D = Decimal
DAY = date(2025, 1, 31)


def days(n: int) -> list[date]:
    return [DAY + timedelta(days=30 * i) for i in range(n)]


def test_period_returns_count_flows_at_the_start_of_the_period() -> None:
    a, b, c, d = days(4)
    series = [
        Observation(a, D(0), D(1000)),  # 1000 deposited during the first period
        Observation(b, D(1100), D(500)),  # +10%, then 500 more
        Observation(c, D(1760), D(-760)),  # 1600 -> 1760: +10%; then 760 out
        Observation(d, D(900), D(0)),  # 1000 -> 900: -10%
    ]
    assert period_returns(series) == [(b, D("0.1")), (c, D("0.1")), (d, D("-0.1"))]


def test_an_empty_period_has_no_return_and_value_from_nothing_is_undefined() -> None:
    a, b, c = days(3)
    assert period_returns([Observation(a, D(0), D(0)), Observation(b, D(0), D(100)),
                           Observation(c, D(110), D(0))]) == [(c, D("0.1"))]  # fmt: skip
    assert period_returns([Observation(a, D(0), D(0)), Observation(b, D(5), D(0))]) is None
    assert period_returns([Observation(a, D(10), D(-20)), Observation(b, D(1), D(0))]) is None
    assert period_returns([Observation(a, D(10), D(0)), Observation(b, D(-1), D(0))]) is None


def test_volatility_of_alternating_returns() -> None:
    period, annual = volatility([D("0.1"), D("-0.1"), D("0.1"), D("-0.1")], 12)
    # Sample variance 0.04 / 3; annualised: sqrt(0.04 / 3 x 12) = 0.4 exactly.
    assert abs(annual - D("0.4")) < D("1e-30")
    with localcontext() as ctx:
        ctx.prec = 34
        assert abs(period - (D("0.04") / 3).sqrt()) < D("1e-30")
    assert volatility([D("0.05")] * 5, 52) == (D(0), D(0))
    with pytest.raises(ValueError, match="two"):
        volatility([D("0.1")], 12)


@settings(max_examples=100, deadline=None)
@given(st.lists(st.decimals(min_value="-0.9", max_value=3, places=4), min_size=2, max_size=40))
def test_volatility_matches_the_statistics_module(returns: list[Decimal]) -> None:
    period, annual = volatility(returns, 12)
    with localcontext() as ctx:
        ctx.prec = 34
        expected = statistics.stdev(returns)
        assert abs(period - expected) < D("1e-25")
        assert abs(annual - expected * D(12).sqrt()) < D("1e-25")


def test_max_drawdown_with_recovery() -> None:
    a, b, c, d, e = days(5)
    levels = [(a, D(1)), (b, D("1.2")), (c, D("0.9")), (d, D("1.0")), (e, D("1.3"))]
    assert max_drawdown(levels) == Drawdown(D("-0.25"), b, c, e)


def test_max_drawdown_not_recovered_and_earliest_of_equal_falls() -> None:
    a, b, c, d, e = days(5)
    assert max_drawdown([(a, D(1)), (b, D("0.5")), (c, D("0.6"))]) == Drawdown(
        D("-0.5"), a, b, None
    )
    twice = [(a, D(1)), (b, D("0.8")), (c, D(1)), (d, D("0.8")), (e, D(1))]
    assert max_drawdown(twice) == Drawdown(D("-0.2"), a, b, c)


def test_no_fall() -> None:
    a, b, c = days(3)
    assert max_drawdown([(a, D(1)), (b, D("1.1")), (c, D("1.2"))]) == Drawdown(D(0), a, a, a)


def test_index_links_returns() -> None:
    a, b, c = days(3)
    assert index(a, [(b, D("0.1")), (c, D("-0.5"))]) == [(a, D(1)), (b, D("1.1")), (c, D("0.55"))]


def series_of(returns: list[str], start: str = "1000") -> list[Observation]:
    value, out = D(start), []
    on = days(len(returns) + 1)
    out.append(Observation(on[0], value, D(0)))
    for i, r in enumerate(returns, start=1):
        value = value * (1 + D(r))
        out.append(Observation(on[i], value, D(0)))
    return out


def test_measure_ok() -> None:
    r = measure(series_of(["0.1", "-0.1"] * 6), 12)
    assert r.status == RiskStatus.OK and r.points == 13 and len(r.returns) == 12
    assert r.volatility is not None and r.period_volatility is not None
    # Index 1, 1.1, 0.99, 1.089, 0.9801, ...: the 1.1 peak is never regained, and the lowest
    # point is the last one, 0.99^6.
    on = days(13)
    assert r.max_drawdown == Drawdown(D("0.99") ** 6 / D("1.1") - 1, on[1], on[12], None)
    assert r.time_weighted is not None and r.time_weighted.status == TwrStatus.OK
    assert r.time_weighted.cumulative is not None
    assert abs(r.time_weighted.cumulative - (D("1.1") * D("0.9")) ** 6 + 1) < D("1e-30")


def test_measure_needs_enough_returns() -> None:
    assert MIN_RETURNS == 12  # the documented floor (docs/design/risk.md; P06-T10 review)
    r = measure(series_of(["0.1"] * 11), 12)
    assert r.status == RiskStatus.INSUFFICIENT_DATA and len(r.returns) == 11
    assert measure(series_of(["0.1"] * 12), 12).status == RiskStatus.OK
    assert r.volatility is None and r.max_drawdown is None and r.time_weighted is None
    assert measure([], 12).status == RiskStatus.INSUFFICIENT_DATA
    assert measure(series_of([]), 12).status == RiskStatus.INSUFFICIENT_DATA


def test_measure_refuses_incomplete_and_undefined_series() -> None:
    s = series_of(["0.1"] * 14)
    s[3] = Observation(s[3].on, s[3].value, s[3].flow_next, complete=False)
    r = measure(s, 12)
    assert (r.status, r.incomplete_points, r.returns) == (RiskStatus.INCOMPLETE_DATA, 1, ())
    a, b = days(2)
    undefined = measure([Observation(a, D(0), D(0)), Observation(b, D(5), D(0))], 12)
    assert undefined.status == RiskStatus.UNDEFINED_PERIOD


@settings(max_examples=80, deadline=None)
@given(
    st.lists(
        st.tuples(
            st.decimals(min_value="-0.5", max_value=1, places=3),
            st.decimals(min_value=-200, max_value=5000, places=2),
        ),
        min_size=MIN_RETURNS,
        max_size=24,
    )
)
def test_flows_do_not_change_the_returns(steps: list[tuple[Decimal, Decimal]]) -> None:
    """Build values from known returns with arbitrary flows: the measured returns are those."""
    on = days(len(steps) + 1)
    value, series = D(1000), []
    with localcontext() as ctx:
        ctx.prec = 34
        for i, (r, flow) in enumerate(steps):
            flow = max(flow, -value + 1)  # never empty the portfolio
            series.append(Observation(on[i], value, flow))
            value = (value + flow) * (1 + r)
        series.append(Observation(on[-1], value, D(0)))
    result = measure(series, 12)
    assert result.status == RiskStatus.OK
    for got, (expected, _) in zip(result.returns, steps, strict=True):
        assert abs(got - expected) < D("1e-25")
    assert result.max_drawdown is not None and D(-1) <= result.max_drawdown.depth <= 0
    assert result.volatility is not None and result.volatility >= 0
