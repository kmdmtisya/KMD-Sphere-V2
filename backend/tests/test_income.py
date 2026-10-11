"""Income figures (P06-T05): a hand-computed fixture, period edges and yields.
Methods: docs/design/income.md."""

import ast
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.modules.networth.income import (
    Totals,
    by_month,
    by_year,
    income_yield,
    monthly,
    totals,
    trailing,
    year_before,
)
from app.modules.networth.income_service import measure
from app.modules.portfolio.summary import Summary
from app.modules.transactions.income_events_service import Payment

D = Decimal
TODAY = date(2026, 10, 11)
A, B, C = (uuid.UUID(int=i) for i in (1, 2, 3))


def pay(
    on: str, kind: str, asset: uuid.UUID | None, gross: str, *, fees: str = "0",
    taxes: str = "0", currency: str = "USD", fx: str = "1",
) -> Payment:  # fmt: skip
    return Payment(uuid.uuid4(), asset, kind, date.fromisoformat(on), currency, D(gross),
                   D(fees), D(taxes), D(fx))  # fmt: skip


# Base currency USD; today 2026-10-11 (hand-computed totals in the tests below).
FIXTURE = [
    pay("2024-12-31", "DISTRIBUTION", B, "80"),
    pay("2025-10-11", "DIVIDEND", A, "100", taxes="15"),  # a year ago today: not trailing
    pay("2025-10-12", "DIVIDEND", A, "100", taxes="15"),  # trailing, but not in the 12 months
    pay("2026-01-15", "DIVIDEND", A, "120", fees="1", taxes="18", currency="EUR", fx="1.1"),
    pay("2026-03-31", "INTEREST", None, "50"),  # cash interest
    pay("2026-06-30", "COUPON", B, "200", fees="2"),
    pay("2026-10-11", "RENT", C, "1000", taxes="100", currency="KES", fx="0.0077"),  # today
]


def summary() -> Summary:
    s = Summary("USD", holdings_value=D(8640), cash=D(1360))
    s.positions = {A: D(4640), B: D(4000)}  # C is not valued
    s.unpriced_assets = [C]
    return s


def test_trailing_twelve_months() -> None:
    t = totals(trailing(FIXTURE, TODAY))
    # 100 + 120 x 1.1 + 50 + 200 + 1000 x 0.0077
    assert (t.gross, t.fees, t.taxes, t.payments) == (D("489.7"), D("3.1"), D("35.57"), 5)
    assert t.net == D("451.03")


def test_the_twelve_calendar_months() -> None:
    months = by_month(FIXTURE, TODAY)
    assert [m.period for m in months][:2] == ["2025-11", "2025-12"]
    assert months[-1].period == "2026-10" and len(months) == 12
    got = {
        m.period: (m.totals.gross, m.totals.fees, m.totals.taxes)
        for m in months
        if m.totals.payments
    }
    assert got == {
        "2026-01": (D("132.0"), D("1.1"), D("19.8")),
        "2026-03": (D(50), D(0), D(0)),
        "2026-06": (D(200), D(2), D(0)),
        "2026-10": (D("7.7000"), D("0.0000"), D("0.7700")),
    }
    assert sum(m.totals.payments for m in months) == 4  # 2025-10-12 is before the first month


def test_calendar_years() -> None:
    years = {y.period: (y.totals.gross, y.totals.taxes, y.totals.net) for y in by_year(FIXTURE)}
    assert years == {
        "2024": (D(80), D(0), D(80)),
        "2025": (D(200), D(30), D(170)),
        "2026": (D("389.7"), D("20.57"), D("366.03")),
    }
    assert [y.period for y in by_year(list(reversed(FIXTURE)))] == ["2024", "2025", "2026"]


def test_portfolio_income_and_yields() -> None:
    costs = {A: D(4000), B: D(5000)}
    r = measure(summary(), FIXTURE, costs, TODAY)
    assert r.currency == "USD" and r.as_of == TODAY and not r.complete
    assert r.yearly == D("451.03")
    assert r.monthly_average == D("37.585833333333333333333333333333333333333333333333")
    assert r.portfolio_yield == D("0.04897")  # 489.7 / 10000
    rows = [(a.asset_id, a.trailing_12m.gross, a.all_time.gross, a.current_yield, a.yield_on_cost)
            for a in r.by_asset]  # fmt: skip
    assert rows == [
        (A, D("232.0"), D("332.0"), D("0.05"), D("0.058")),
        (B, D(200), D(280), D("0.05"), D("0.04")),
        (None, D(50), D(50), None, None),  # cash interest: no asset to measure against
        (C, D("7.7000"), D("7.7000"), None, None),  # not valued, no open cost
    ]
    types = {t.income_type: (t.trailing_12m.gross, t.all_time.gross) for t in r.by_type}
    assert types == {
        "COUPON": (D(200), D(200)),
        "DISTRIBUTION": (D(0), D(80)),
        "DIVIDEND": (D("232.0"), D("332.0")),
        "INTEREST": (D(50), D(50)),
        "RENT": (D("7.7000"), D("7.7000")),
    }
    assert [m.period for m in r.months] == [m.period for m in by_month(FIXTURE, TODAY)]
    assert [y.period for y in r.years] == ["2024", "2025", "2026"]


def test_no_income() -> None:
    r = measure(Summary("USD"), [], {}, TODAY)
    assert r.trailing_12m == Totals() and r.yearly == 0 and r.monthly_average == 0
    assert r.portfolio_yield is None  # nothing to measure against
    assert r.by_asset == [] and r.by_type == [] and r.years == []
    assert len(r.months) == 12 and all(m.totals.payments == 0 for m in r.months)


@pytest.mark.parametrize(
    ("today", "first", "last"),
    [(date(2026, 1, 5), "2025-02", "2026-01"), (date(2026, 12, 31), "2026-01", "2026-12")],
)
def test_months_cross_the_year_boundary(today: date, first: str, last: str) -> None:
    months = by_month([], today)
    assert (months[0].period, months[-1].period, len(months)) == (first, last, 12)
    assert len(by_month([], today, months=3)) == 3


def test_year_before_handles_the_leap_day() -> None:
    assert year_before(date(2024, 2, 29)) == date(2023, 2, 28)
    assert year_before(date(2026, 10, 11)) == date(2025, 10, 11)
    leap = [pay("2023-02-28", "DIVIDEND", A, "1"), pay("2023-03-01", "DIVIDEND", A, "2")]
    assert [p.gross for p in trailing(leap, date(2024, 2, 29))] == [D(2)]


def test_future_payments_are_not_trailing() -> None:
    assert trailing([pay("2026-10-12", "DIVIDEND", A, "1")], TODAY) == []


def test_income_yield() -> None:
    assert income_yield(D(5), D(100)) == D("0.05")
    assert income_yield(D(5), D(0)) is None
    assert income_yield(D(5), D(-1)) is None
    assert income_yield(D(5), None) is None
    assert monthly(D(12)) == 1


@settings(max_examples=100, deadline=None)
@given(
    st.lists(
        st.tuples(
            st.dates(min_value=date(2020, 1, 1), max_value=date(2026, 12, 31)),
            st.decimals(min_value=0, max_value=100000, places=2),
            st.decimals(min_value=0, max_value=100, places=2),
            st.decimals(min_value="0.01", max_value=200, places=4),
        ),
        max_size=30,
    )
)
def test_periods_add_up(rows: list[tuple[date, Decimal, Decimal, Decimal]]) -> None:
    payments = [
        Payment(uuid.uuid4(), A, "DIVIDEND", d, "USD", g, D(0), t, fx) for d, g, t, fx in rows
    ]
    whole = totals(payments)
    years = by_year(payments)
    assert sum((y.totals.gross for y in years), D(0)) == whole.gross
    assert sum(y.totals.payments for y in years) == len(payments)
    months = by_month(payments, TODAY)
    in_window = [p for p in payments if (p.paid_on.year, p.paid_on.month) >= (2025, 11)
                 and p.paid_on <= date(2026, 10, 31)]  # fmt: skip
    assert sum((m.totals.net for m in months), D(0)) == totals(in_window).net


def test_no_float_or_io_in_the_maths() -> None:
    tree = ast.parse(
        (Path(__file__).parents[1] / "app/modules/networth/income.py").read_text("utf-8")
    )
    assert "float" not in {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert not [
        n for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, float)
    ]
