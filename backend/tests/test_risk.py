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


# ------------------------------------------------------------ Modified Dietz (review decision 4)


def dated(
    start: date, end: date, value: str, nxt: str, *flows: tuple[int, str]
) -> list[Observation]:
    """Two observations; `flows` are (day of the period, amount)."""
    detail = tuple((start + timedelta(days=d), D(a)) for d, a in flows)
    total = sum((x for _, x in detail), D(0))
    return [Observation(start, D(value), total, True, detail), Observation(end, D(nxt), D(0))]


def test_a_late_deposit_counts_for_less_of_the_period() -> None:
    a, b = date(2025, 1, 31), date(2025, 3, 2)  # a 30-day period
    early = dated(a, b, "1000", "1600", (1, "500"))  # made at the start of day 1: invested 30/30
    late = dated(a, b, "1000", "1600", (30, "500"))  # made on the last day: invested 1/30
    middle = dated(a, b, "1000", "1600", (10, "500"))  # 21/30 = 0.7
    [(_, got_early)] = period_returns(early) or []
    [(_, got_middle)] = period_returns(middle) or []
    assert abs(got_early - D("100") / D("1500")) < D("1e-25")
    assert abs(got_middle - D("100") / D("1350")) < D("1e-25")
    [(_, got)] = period_returns(late) or []
    assert abs(got - D("100") / (D(1000) + D(500) / 30)) < D("1e-25")
    # Without dates the whole flow counts from the start, as for daily series.
    [(_, undated)] = (
        period_returns([Observation(a, D(1000), D(500)), Observation(b, D(1600), D(0))]) or []
    )
    assert abs(undated - D("100") / D("1500")) < D("1e-25")


def test_several_flows_and_withdrawals() -> None:
    a, b = date(2025, 1, 31), date(2025, 3, 2)
    s = dated(a, b, "1000", "1150", (5, "200"), (20, "-100"))
    # base = 1000 + 26/30 x 200 - 11/30 x 100; return = (1150 - 1000 - 100) / base
    [(_, got)] = period_returns(s) or []
    expected = D(50) / (D(1000) + D(26) / 30 * 200 - D(11) / 30 * 100)
    assert abs(got - expected) < D("1e-25")


def test_daily_series_are_unchanged_by_the_weighting() -> None:
    a = date(2025, 1, 1)
    s = dated(a, a + timedelta(days=1), "1000", "1650", (1, "500"))
    [(_, got)] = period_returns(s) or []
    assert abs(got - D("150") / D("1500")) < D("1e-25")


def test_dated_flows_chain_into_the_time_weighted_return() -> None:
    a = date(2025, 1, 31)
    at = [a + timedelta(days=30 * i) for i in range(14)]
    series = []
    for i in range(13):  # a mid-period deposit every period; the value grows by 2% net of it
        flow = D(100)
        series.append(
            Observation(at[i], D(1000) + 40 * i, flow, True, ((at[i] + timedelta(days=15), flow),))
        )
    series.append(Observation(at[13], D(1000) + 40 * 13, D(0)))
    r = measure(series, 12)
    returns = period_returns(series)
    assert r.status == RiskStatus.OK and returns is not None and len(returns) == 13
    assert r.returns == tuple(x for _, x in returns)
    growth = D(1)
    for _, x in returns:
        growth *= 1 + x
    assert r.time_weighted is not None and r.time_weighted.cumulative is not None
    assert abs(r.time_weighted.cumulative - (growth - 1)) < D("1e-25")
    assert r.time_weighted.days == 390 and r.time_weighted.annualized is not None


def test_chain_links_returns_and_annualises_full_years() -> None:
    from app.modules.analytics.risk import chain

    a = date(2025, 1, 1)
    pairs = [(a + timedelta(days=365), D("0.21"))]
    result = chain(pairs, 365)
    assert (result.cumulative, result.status) == (D("0.21"), TwrStatus.OK)
    assert result.annualized is not None and abs(result.annualized - D("0.21")) < D("1e-30")
    assert chain(pairs, 364).annualized is None
    assert chain([(a, D("-1"))], 400).annualized is None  # a total loss cannot be annualised


def test_chain_annualises_over_two_years() -> None:
    from app.modules.analytics.risk import chain

    result = chain([(date(2027, 1, 1), D("0.21"))], 730)  # 21% over two years = 10% a year
    assert result.annualized is not None and abs(result.annualized - D("0.1")) < D("1e-25")
