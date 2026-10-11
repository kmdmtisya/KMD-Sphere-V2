"""Historical portfolio value (P06-T08): dates and a hand-computed ledger history."""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from app.modules.portfolio.history import MAX_POINTS, SeriesFrequency, Valued, build, dates
from app.modules.transactions.holdings import Entry

D = Decimal
A, H = uuid.UUID(int=1), uuid.UUID(int=2)


def test_monthly_dates_end_on_month_ends() -> None:
    assert dates(date(2025, 1, 15), date(2025, 4, 10), SeriesFrequency.MONTHLY) == [
        date(2025, 1, 15), date(2025, 1, 31), date(2025, 2, 28), date(2025, 3, 31),
        date(2025, 4, 10),
    ]  # fmt: skip
    assert dates(date(2025, 1, 31), date(2025, 2, 28), SeriesFrequency.MONTHLY) == [
        date(2025, 1, 31),
        date(2025, 2, 28),
    ]
    assert dates(date(2024, 12, 31), date(2025, 1, 1), SeriesFrequency.MONTHLY) == [
        date(2024, 12, 31),
        date(2025, 1, 1),
    ]


def test_weekly_and_daily_dates() -> None:
    assert dates(date(2025, 1, 1), date(2025, 1, 20), SeriesFrequency.WEEKLY) == [
        date(2025, 1, 1), date(2025, 1, 8), date(2025, 1, 15), date(2025, 1, 20),
    ]  # fmt: skip
    assert dates(date(2025, 1, 1), date(2025, 1, 15), SeriesFrequency.WEEKLY)[-1] == date(
        2025, 1, 15
    )
    assert dates(date(2025, 1, 1), date(2025, 1, 3), SeriesFrequency.DAILY) == [
        date(2025, 1, 1), date(2025, 1, 2), date(2025, 1, 3)]  # fmt: skip
    assert dates(date(2025, 1, 1), date(2025, 1, 1), SeriesFrequency.DAILY) == [date(2025, 1, 1)]
    assert [f.per_year for f in SeriesFrequency] == [365, 52, 12]


def test_date_limits() -> None:
    with pytest.raises(ValueError, match="before"):
        dates(date(2025, 2, 1), date(2025, 1, 1), SeriesFrequency.DAILY)
    start = date(2020, 1, 1)
    assert (
        len(dates(start, start + timedelta(days=MAX_POINTS - 1), SeriesFrequency.DAILY))
        == MAX_POINTS
    )
    with pytest.raises(ValueError, match="at most"):
        dates(start, start + timedelta(days=MAX_POINTS), SeriesFrequency.DAILY)


T0 = datetime(2025, 1, 1, tzinfo=UTC)


def entry(kind: str, day: date, gross: str, *, asset: uuid.UUID | None = None,
          qty: str | None = None, currency: str = "USD", fx: str = "1",
          reverses: uuid.UUID | None = None, eid: uuid.UUID | None = None) -> Entry:  # fmt: skip
    return Entry(eid or uuid.uuid4(), kind, day, T0 + timedelta(days=(day - T0.date()).days),
                 asset, D(qty) if qty else None, D(gross), D(0), D(0), D(fx), reverses,
                 currency)  # fmt: skip


def at(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, 12, tzinfo=UTC)


def eur_rate(currency: str, day: date) -> Decimal | None:
    if currency == "USD":
        return D(1)
    return D("1.2") if currency == "EUR" and day >= date(2025, 3, 1) else None


wrong = uuid.uuid4()
LEDGER = [
    entry("DEPOSIT", date(2025, 1, 1), "1000"),
    entry("BUY", date(2025, 1, 15), "500", asset=A, qty="10"),
    entry("DEPOSIT", date(2025, 3, 5), "100", currency="EUR", fx="1.1"),
    entry("DEPOSIT", date(2025, 3, 6), "999", eid=wrong),
    entry("DEPOSIT", date(2025, 3, 7), "999", reverses=wrong),  # both ignored
    entry("SELL", date(2025, 4, 10), "700", asset=A, qty="10"),
]
VALUATIONS = [
    Valued(A, D(600), "USD", at(date(2025, 2, 10))),
    Valued(A, D(9999), "USD", at(date(2025, 5, 1))),  # after the series
    Valued(H, D(5000), "USD", at(date(2025, 1, 20))),  # valued, never traded
]


def test_value_history_from_the_ledger() -> None:
    days = dates(date(2025, 1, 1), date(2025, 4, 30), SeriesFrequency.MONTHLY)
    points = build(LEDGER, VALUATIONS, eur_rate, days)
    got = [(p.on, p.value, p.flow_next, p.complete, p.unpriced) for p in points]
    assert got == [
        # Cash 1000; the house is not valued yet, so it is not part of the portfolio.
        (date(2025, 1, 1), D(1000), D(0), True, 0),
        # Cash 500 + house 5000; the stock is held but not valued yet.
        (date(2025, 1, 31), D(5500), D(0), False, 1),
        # + stock 600; the EUR deposit (100 x 1.1 at its posting rate) is next period's flow.
        (date(2025, 2, 28), D(6100), D("110.0"), True, 0),
        # + 100 EUR at 1.2.
        (date(2025, 3, 31), D("6220.0"), D(0), True, 0),
        # Stock sold for 700: closed, so its valuation no longer counts.
        (date(2025, 4, 30), D("6320.0"), D(0), True, 0),
    ]


def test_a_currency_without_a_rate_leaves_the_point_incomplete() -> None:
    days = [date(2025, 3, 5), date(2025, 3, 31)]
    points = build(LEDGER, VALUATIONS, lambda c, d: D(1) if c == "USD" else None, days)
    assert points[0].unconverted == frozenset({"EUR"}) and not points[0].complete
    assert points[0].value == D(6100)  # the EUR is left out, never guessed


def test_nothing_recorded() -> None:
    points = build([], [], eur_rate, [date(2025, 1, 1), date(2025, 1, 2)])
    assert [(p.value, p.complete) for p in points] == [(D(0), True), (D(0), True)]


def test_a_valuation_counts_from_the_end_of_its_day() -> None:
    late = [Valued(H, D(10), "USD", datetime(2025, 1, 1, 23, 59, 59, tzinfo=UTC)),
            Valued(H, D(20), "USD", datetime(2025, 1, 2, 0, 0, tzinfo=UTC))]  # fmt: skip
    points = build([], late, eur_rate, [date(2025, 1, 1), date(2025, 1, 2)])
    assert [p.value for p in points] == [D(10), D(20)]


def test_a_flow_on_the_next_point_belongs_to_the_period_before_it() -> None:
    ledger = [entry("DEPOSIT", date(2025, 1, 1), "100"), entry("DEPOSIT", date(2025, 1, 31), "50")]
    points = build(ledger, [], eur_rate, [date(2025, 1, 1), date(2025, 1, 31)])
    assert [(p.value, p.flow_next) for p in points] == [(D(100), D(50)), (D(150), D(0))]
    assert points[0].flows == ((date(2025, 1, 31), D(50)),) and points[1].flows == ()


def test_a_valuation_in_a_currency_without_a_rate_is_left_out() -> None:
    euro_house = [Valued(H, D(1000), "EUR", at(date(2025, 2, 1)))]
    before, after = build([], euro_house, eur_rate, [date(2025, 2, 15), date(2025, 3, 15)])
    assert (before.value, before.complete, before.unconverted) == (D(0), False, frozenset({"EUR"}))
    assert (after.value, after.complete) == (D("1200.0"), True)  # 1000 EUR at 1.2


def test_an_emptied_balance_needs_no_rate() -> None:
    ledger = [entry("DEPOSIT", date(2025, 1, 2), "50", currency="EUR", fx="1.1"),
              entry("WITHDRAWAL", date(2025, 1, 3), "50", currency="EUR", fx="1.1")]  # fmt: skip
    [point] = build(ledger, [], eur_rate, [date(2025, 1, 10)])  # no EUR rate before March
    assert (point.value, point.complete, point.unconverted) == (D(0), True, frozenset())
