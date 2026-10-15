"""Net worth over time (P14-T11): the pure rules of app/modules/networth/history.py."""

from datetime import date, timedelta
from decimal import Decimal

from app.modules.networth.history import DebtBalance, PortfolioSeries, combine
from app.modules.portfolio.history import Point

D0 = date(2026, 1, 31)
D1 = date(2026, 2, 28)
D2 = date(2026, 3, 31)


def point(on: date, value: str, complete: bool = True) -> Point:
    return Point(on, Decimal(value), Decimal(0), complete, 0, frozenset())


def series(currency: str, values: dict[date, str], complete: bool = True) -> PortfolioSeries:
    return PortfolioSeries(currency, {d: point(d, v, complete) for d, v in values.items()})


def no_rates(currency: str, day: date) -> Decimal | None:
    return None


def test_assets_are_summed_across_portfolios_in_the_reporting_currency() -> None:
    a = series("USD", {D0: "100.00", D1: "150.00"})
    b = series("EUR", {D0: "200.00", D1: "200.00"})

    def rate(currency: str, day: date) -> Decimal | None:
        return Decimal("1.10") if day == D0 else Decimal("1.20")  # EUR -> USD, by day

    out = combine([D0, D1], "USD", [a, b], [], rate)
    assert [p.assets for p in out] == [Decimal("320.00"), Decimal("390.00")]
    assert all(p.complete for p in out)


def test_a_liability_counts_from_the_date_its_balance_was_recorded() -> None:
    s = series("USD", {D0: "1000", D1: "1000", D2: "1000"})
    debt = DebtBalance("USD", Decimal("300"), D1)
    out = combine([D0, D1, D2], "USD", [s], [debt], no_rates)
    assert [p.liabilities for p in out] == [Decimal(0), Decimal(300), Decimal(300)]
    assert [p.net_worth for p in out] == [Decimal(1000), Decimal(700), Decimal(700)]
    # Before the recording date the balance is unknown: marked, not guessed.
    assert [p.complete for p in out] == [False, True, True]


def test_a_missing_rate_or_an_incomplete_portfolio_marks_the_date_incomplete() -> None:
    foreign = series("EUR", {D0: "100", D1: "100"})
    out = combine([D0, D1], "USD", [foreign], [], no_rates)
    assert [p.assets for p in out] == [Decimal(0), Decimal(0)]
    assert [p.complete for p in out] == [False, False]

    unpriced = series("USD", {D0: "100"}, complete=False)
    assert combine([D0], "USD", [unpriced], [], no_rates)[0].complete is False


def test_a_zero_valued_portfolio_in_a_currency_without_a_rate_is_still_complete() -> None:
    empty = series("EUR", {D0: "0"})
    assert combine([D0], "USD", [empty], [], no_rates)[0].complete is True


def test_a_foreign_liability_is_converted_at_that_days_rate() -> None:
    debt = DebtBalance("EUR", Decimal("100"), D0)
    out = combine([D0, D0 + timedelta(days=1)], "USD", [], [debt],
                  lambda c, d: Decimal("2") if d == D0 else Decimal("3"))  # fmt: skip
    assert [p.liabilities for p in out] == [Decimal(200), Decimal(300)]


def test_no_portfolios_and_no_liabilities_gives_zero() -> None:
    out = combine([D0], "USD", [], [], no_rates)
    assert out[0].net_worth == Decimal(0) and out[0].complete is True
