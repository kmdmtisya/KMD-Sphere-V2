"""The FX session calendar and timeframe aggregation (P13-T03, QG-14.2, QG-14.3): trading days,
weeks and months on New York rollover with daylight saving, aggregation arithmetic, and missing
candles, weekend gaps and irregular sessions left as gaps (never filled)."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from app.modules.forex.candles.aggregate import Aggregation, aggregate
from app.modules.forex.candles.sessions import (
    bucket_end,
    bucket_start,
    day_open,
    expected_candles,
    is_open,
    trading_date,
    week_close,
    week_open,
)
from app.modules.forex.marketdata.types import Candle, DataType, PriceBasis, Timeframe
from app.modules.market_data.providers.errors import ProviderDataError

D = Decimal
NY = ZoneInfo("America/New_York")
T = Timeframe


def utc(y: int, mo: int, d: int, h: int = 0, mi: int = 0, s: int = 0) -> datetime:
    return datetime(y, mo, d, h, mi, s, tzinfo=UTC)


def ny(y: int, mo: int, d: int, h: int = 0, mi: int = 0) -> datetime:
    return datetime(y, mo, d, h, mi, tzinfo=NY)


# Summer (EDT, UTC-4): Sunday 17:00 NY = 21:00 UTC. Winter (EST, UTC-5): 22:00 UTC.
def test_the_week_opens_sunday_17_new_york_and_closes_friday_17() -> None:
    assert week_open(utc(2026, 10, 14, 10)) == utc(2026, 10, 11, 21)  # EDT
    assert week_close(utc(2026, 10, 14, 10)) == utc(2026, 10, 16, 21)
    assert week_open(utc(2026, 12, 9, 10)) == utc(2026, 12, 6, 22)  # EST
    assert week_close(utc(2026, 12, 9, 10)) == utc(2026, 12, 11, 22)


@pytest.mark.parametrize(
    ("t", "expected"),
    [
        (ny(2026, 10, 9, 16, 59), True),  # Friday just before the close
        (ny(2026, 10, 9, 17, 0), False),
        (ny(2026, 10, 10, 12, 0), False),  # Saturday
        (ny(2026, 10, 11, 16, 59), False),  # Sunday before the open
        (ny(2026, 10, 11, 17, 0), True),
        (ny(2026, 10, 12, 3, 0), True),
    ],
)
def test_is_open(t: datetime, expected: bool) -> None:
    assert is_open(t) is expected


def test_the_trading_day_is_named_after_the_day_it_ends_on() -> None:
    assert trading_date(ny(2026, 10, 11, 17, 0)) == date(2026, 10, 12)  # Sunday 17:00 starts Monday
    assert trading_date(ny(2026, 10, 12, 16, 59)) == date(2026, 10, 12)
    assert trading_date(ny(2026, 10, 12, 17, 0)) == date(2026, 10, 13)
    assert day_open(ny(2026, 10, 12, 9, 0)) == utc(2026, 10, 11, 21)


def test_daylight_saving_moves_the_open_in_utc_but_not_the_day_length() -> None:
    # US clocks go back on Sunday 2026-11-01 at 02:00, while the market is closed.
    before = day_open(utc(2026, 10, 30, 12))  # Friday's day, EDT
    after = day_open(utc(2026, 11, 2, 12))  # Monday's day, started Sunday 17:00 EST
    assert before == utc(2026, 10, 29, 21)
    assert after == utc(2026, 11, 1, 22)
    assert bucket_end(after, T.D1) - after == timedelta(hours=24)
    assert week_open(utc(2026, 11, 3, 12)) == utc(2026, 11, 1, 22)
    # Spring forward: Sunday 2026-03-08.
    assert week_open(utc(2026, 3, 10, 12)) == utc(2026, 3, 8, 21)


@pytest.mark.parametrize(
    ("frame", "t", "start", "end"),
    [
        (T.M5, utc(2026, 10, 14, 10, 7, 30), utc(2026, 10, 14, 10, 5), utc(2026, 10, 14, 10, 10)),
        (T.H1, utc(2026, 10, 14, 10, 59), utc(2026, 10, 14, 10), utc(2026, 10, 14, 11)),
        # The trading day opens at 21:00 UTC, so 4-hour periods start at 21, 01, 05, 09, 13, 17.
        (T.H4, utc(2026, 10, 14, 10, 0), utc(2026, 10, 14, 9), utc(2026, 10, 14, 13)),
        (T.D1, utc(2026, 10, 14, 10), utc(2026, 10, 13, 21), utc(2026, 10, 14, 21)),
        (T.W1, utc(2026, 10, 14, 10), utc(2026, 10, 11, 21), utc(2026, 10, 16, 21)),
        (T.MN1, utc(2026, 10, 14, 10), utc(2026, 9, 30, 21), utc(2026, 10, 30, 21)),
    ],
)
def test_bucket_boundaries(frame: Timeframe, t: datetime, start: datetime, end: datetime) -> None:
    got = bucket_start(t, frame)
    assert got == start, (frame, got)
    assert bucket_end(got, frame) == end
    assert got <= t < bucket_end(got, frame)


def test_months_follow_trading_dates_so_a_weekend_month_start_belongs_to_the_next_week() -> None:
    # 1 Nov 2026 is a Sunday: the 17:00 open that evening is Monday 2 Nov's trading day, so
    # November starts then, and October's last trading day is Friday 30 Oct.
    nov = bucket_start(utc(2026, 11, 3, 12), T.MN1)
    assert nov == utc(2026, 11, 1, 22)
    assert bucket_end(bucket_start(utc(2026, 10, 30, 12), T.MN1), T.MN1) == utc(2026, 10, 30, 21)
    # December 2026 starts on a Tuesday; its open is the evening before.
    assert bucket_start(utc(2026, 12, 1, 12), T.MN1) == utc(2026, 11, 30, 22)


def test_expected_candle_counts() -> None:
    assert expected_candles(utc(2026, 10, 14, 10), T.M5) == 5
    assert expected_candles(utc(2026, 10, 13, 21), T.D1) == 1440
    assert expected_candles(utc(2026, 10, 11, 21), T.W1) == 7200
    # October 2026 has 22 weekdays (1 Oct is a Thursday): 22 x 1440, no weekends counted.
    assert expected_candles(utc(2026, 9, 30, 21), T.MN1) == 22 * 1440


# ------------------------------------------------------------------------- aggregation
def minute(ts: datetime, o: str, h: str, low: str, c: str, volume: int | None = 1) -> Candle:
    return Candle(
        "fake",
        "EUR_USD",
        T.M1,
        PriceBasis.MID,
        ts,
        D(o),
        D(h),
        D(low),
        D(c),
        volume,
        True,
        DataType.SIMULATED,
    )


AS_OF = utc(2026, 10, 20)


def run(minutes: list[Candle], frame: Timeframe, as_of: datetime = AS_OF) -> Aggregation:
    return aggregate(minutes, frame, as_of)


def test_five_minutes_are_first_open_extremes_last_close_and_summed_volume() -> None:
    t = utc(2026, 10, 14, 10, 0)
    data = [
        minute(t, "1.100", "1.105", "1.099", "1.104", 3),
        minute(t + timedelta(minutes=1), "1.104", "1.110", "1.103", "1.108", 4),
        minute(t + timedelta(minutes=2), "1.108", "1.109", "1.095", "1.096", 5),
        minute(t + timedelta(minutes=3), "1.096", "1.101", "1.094", "1.100", 6),
        minute(t + timedelta(minutes=4), "1.100", "1.103", "1.098", "1.102", 7),
    ]
    [a] = run(data, T.M5).candles
    assert (a.ts, a.end) == (t, t + timedelta(minutes=5))
    assert (a.open, a.high, a.low, a.close, a.volume) == (
        D("1.100"),
        D("1.110"),
        D("1.094"),
        D("1.102"),
        25,
    )
    assert (a.source_count, a.expected_count, a.missing, a.partial, a.forming) == (
        5,
        5,
        0,
        False,
        False,
    )


def test_missing_minutes_stay_missing_and_mark_the_period_partial() -> None:
    t = utc(2026, 10, 14, 10, 0)
    data = [
        minute(t, "1.1", "1.2", "1.0", "1.15"),
        minute(t + timedelta(minutes=4), "1.15", "1.3", "1.1", "1.2"),
    ]
    [a] = run(data, T.M5).candles
    assert (a.open, a.close, a.high, a.low) == (D("1.1"), D("1.2"), D("1.3"), D("1.0"))
    assert (a.source_count, a.missing, a.partial) == (2, 3, True)


def test_a_period_with_no_candles_is_absent_not_filled() -> None:
    t = utc(2026, 10, 14, 10, 0)
    data = [
        minute(t, "1.1", "1.2", "1.0", "1.1"),
        minute(t + timedelta(minutes=10), "1.1", "1.2", "1.0", "1.1"),
    ]
    assert [c.ts for c in run(data, T.M5).candles] == [t, t + timedelta(minutes=10)]


def test_the_weekend_gap_produces_no_candles_and_closed_minutes_are_ignored() -> None:
    friday_last = utc(2026, 10, 16, 20, 59)  # last open minute (EDT)
    sunday_first = utc(2026, 10, 18, 21, 0)
    saturday = utc(2026, 10, 17, 12, 0)  # a candle that should not exist
    data = [
        minute(friday_last, "1.1", "1.2", "1.0", "1.1"),
        minute(saturday, "9", "9", "9", "9"),
        minute(sunday_first, "1.1", "1.2", "1.0", "1.1"),
    ]
    result = run(data, T.D1)
    assert result.ignored_closed == 1
    assert [c.ts for c in result.candles] == [utc(2026, 10, 15, 21), utc(2026, 10, 18, 21)]
    assert all(c.high < 9 for c in result.candles)  # the closed-market candle never leaks in
    # Friday's candle closes its day at 17:00 New York; Sunday's belongs to Monday's trading day.
    assert result.candles[0].end == utc(2026, 10, 16, 21)
    assert result.candles[1].end == utc(2026, 10, 19, 21)


def test_a_week_spans_sunday_to_friday_and_ends_at_the_friday_close() -> None:
    mon = utc(2026, 10, 12, 8, 0)
    fri = utc(2026, 10, 16, 20, 59)
    sun = utc(2026, 10, 11, 21, 0)
    data = [
        minute(sun, "1.0", "1.1", "0.9", "1.05"),
        minute(mon, "1.05", "1.2", "1.0", "1.1"),
        minute(fri, "1.1", "1.3", "1.05", "1.25"),
    ]
    [w] = run(data, T.W1).candles
    assert (w.ts, w.end) == (utc(2026, 10, 11, 21), utc(2026, 10, 16, 21))
    assert (w.open, w.high, w.low, w.close, w.source_count, w.expected_count) == (
        D("1.0"),
        D("1.3"),
        D("0.9"),
        D("1.25"),
        3,
        7200,
    )


def test_a_month_aggregates_its_trading_days_and_counts_weekdays_only() -> None:
    data = [
        minute(utc(2026, 10, 1, 12, 0), "1.0", "1.2", "0.9", "1.1"),
        minute(utc(2026, 10, 29, 12, 0), "1.1", "1.4", "1.0", "1.3"),
    ]
    [m] = run(data, T.MN1).candles
    assert m.ts == utc(2026, 9, 30, 21) and m.expected_count == 22 * 1440
    assert (m.open, m.high, m.low, m.close) == (D("1.0"), D("1.4"), D("0.9"), D("1.3"))


def test_a_period_still_open_is_marked_forming() -> None:
    t = utc(2026, 10, 14, 10, 0)
    data = [minute(t, "1.1", "1.2", "1.0", "1.1")]
    assert run(data, T.M5, as_of=t + timedelta(minutes=3)).candles[0].forming is True
    assert run(data, T.M5, as_of=t + timedelta(minutes=5)).candles[0].forming is False


def test_forming_minutes_are_not_used_and_volume_is_none_if_any_is_missing() -> None:
    t = utc(2026, 10, 14, 10, 0)
    forming = Candle(
        "fake",
        "EUR_USD",
        T.M1,
        PriceBasis.MID,
        t + timedelta(minutes=1),
        D(1),
        D(2),
        D(1),
        D(2),
        1,
        False,
        DataType.SIMULATED,
    )
    data = [minute(t, "1.1", "1.2", "1.0", "1.1", None), forming]
    [a] = run(data, T.M5).candles
    assert a.source_count == 1 and a.volume is None and a.high == D("1.2")


def wiggly(t: datetime, count: int) -> list[Candle]:
    """Valid candles with varying open, close, high, low and volume."""
    out = []
    for k in range(count):
        o = D("1.1000") + D(k % 7) * D("0.0010")
        c = D("1.1000") + D((k + 3) % 7) * D("0.0010")
        out.append(
            minute(
                t + timedelta(minutes=k),
                str(o),
                str(max(o, c) + D(k % 5) * D("0.0001")),
                str(min(o, c) - D(k % 3) * D("0.0001")),
                str(c),
                k,
            )
        )
    return out


def test_aggregation_is_deterministic_and_input_order_does_not_matter() -> None:
    data = wiggly(utc(2026, 10, 14, 10, 0), 10)
    assert run(data, T.M5) == run(list(reversed(data)), T.M5)


def test_the_hour_equals_the_sum_of_its_five_minute_periods() -> None:
    data = wiggly(utc(2026, 10, 14, 10, 0), 60)
    [hour] = run(data, T.H1).candles
    fives = run(data, T.M5).candles
    assert len(fives) == 12
    assert hour.open == fives[0].open and hour.close == fives[-1].close
    assert hour.high == max(f.high for f in fives) and hour.low == min(f.low for f in fives)
    assert hour.volume == sum(f.volume or 0 for f in fives) and hour.source_count == 60


def test_bad_input_is_refused() -> None:
    t = utc(2026, 10, 14, 10, 0)
    with pytest.raises(ProviderDataError):
        run([minute(t, "1", "1", "1", "1"), minute(t, "1", "1", "1", "1")], T.M5)
    with pytest.raises(ProviderDataError):
        run([minute(t + timedelta(seconds=30), "1", "1", "1", "1")], T.M5)
    other = Candle(
        "fake",
        "GBP_USD",
        T.M1,
        PriceBasis.MID,
        t + timedelta(minutes=1),
        D(1),
        D(1),
        D(1),
        D(1),
        1,
        True,
        DataType.SIMULATED,
    )
    with pytest.raises(ProviderDataError):
        run([minute(t, "1", "1", "1", "1"), other], T.M5)
    with pytest.raises(ValueError):
        run([], T.M1)
    with pytest.raises(ValueError):
        aggregate([], T.M5, datetime(2026, 1, 1))
    assert run([], T.M5).candles == []
