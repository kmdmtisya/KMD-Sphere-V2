"""The FX session calendar (P13-T03, design section 4.5). Pure functions.

Convention (the common one for spot FX):
- A **trading day** runs 24 hours from 17:00 New York time to 17:00 the next day, and is named
  after the day it ends on. Sunday 17:00 starts Monday's trading day.
- The **trading week** runs from Sunday 17:00 to Friday 17:00 New York time (five trading days).
  The market is closed from Friday 17:00 to Sunday 17:00. Because the daylight-saving change
  happens at 02:00 on a Sunday, while the market is closed, every trading day is exactly 24 hours
  and the open and close move by one hour in UTC twice a year, exactly as the convention does.
- **Timeframe boundaries** follow from these: intraday periods are aligned to the start of the
  trading day, 1D is a trading day, 1W a trading week, and 1M the trading days whose name falls
  in one calendar month.

Not modelled: public holidays and early closes (liquidity is thin but quotes continue), and a
per-pair rollover time other than 17:00 New York. Both are listed as open items in
docs/design/forex-analysis.md; nothing is invented for them, because a candle exists only if the
provider published it."""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.modules.forex.marketdata.types import Timeframe

NY = ZoneInfo("America/New_York")
ROLLOVER_HOUR = 17
DAY = timedelta(hours=24)
MINUTE = timedelta(minutes=1)
STEPS: dict[Timeframe, timedelta] = {
    Timeframe.M1: timedelta(minutes=1),
    Timeframe.M5: timedelta(minutes=5),
    Timeframe.M15: timedelta(minutes=15),
    Timeframe.M30: timedelta(minutes=30),
    Timeframe.H1: timedelta(hours=1),
    Timeframe.H4: timedelta(hours=4),
}


def _utc(t: datetime) -> datetime:
    if t.tzinfo is None or t.utcoffset() is None:
        raise ValueError("time must carry a time zone")
    return t.astimezone(UTC)


def _open_of(day_end: date) -> datetime:
    """Start (UTC) of the trading day that ends on the calendar date `day_end`."""
    local = datetime(day_end.year, day_end.month, day_end.day, ROLLOVER_HOUR, tzinfo=NY) - DAY
    return local.astimezone(UTC)


def is_open(t: datetime) -> bool:
    """Whether the market is open at `t`: not between Friday and Sunday 17:00 New York time."""
    ny = _utc(t).astimezone(NY)
    weekday = ny.weekday()  # Monday is 0
    if weekday == 5:
        return False
    if weekday == 4 and ny.hour >= ROLLOVER_HOUR:
        return False
    return not (weekday == 6 and ny.hour < ROLLOVER_HOUR)


def trading_date(t: datetime) -> date:
    """The name of the trading day `t` belongs to: the calendar date at New York rollover. A time
    in the closed weekend belongs to the next Monday's trading day only from Sunday 17:00."""
    ny = _utc(t).astimezone(NY)
    return (ny + timedelta(hours=24 - ROLLOVER_HOUR)).date()


def day_open(t: datetime) -> datetime:
    """Start (UTC) of the trading day containing `t`."""
    return _open_of(trading_date(t))


def _week_monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def week_open(t: datetime) -> datetime:
    """Start (UTC) of the trading week containing `t`: Sunday 17:00 New York time."""
    return _open_of(_week_monday(trading_date(t)))


def week_close(t: datetime) -> datetime:
    """End (UTC) of the trading week containing `t`: Friday 17:00 New York time."""
    return _open_of(_week_monday(trading_date(t)) + timedelta(days=5))


def _month_days(d: date) -> tuple[date, date]:
    """First and last weekday trading dates of the month of `d`."""
    first = d.replace(day=1)
    last = (
        first.replace(year=first.year + 1, month=1)
        if first.month == 12
        else first.replace(month=first.month + 1)
    ) - timedelta(days=1)
    while first.weekday() >= 5:
        first += timedelta(days=1)
    while last.weekday() >= 5:
        last -= timedelta(days=1)
    return first, last


def bucket_start(t: datetime, timeframe: Timeframe) -> datetime:
    """Start (UTC) of the `timeframe` period containing `t` (which should be in an open session)."""
    t = _utc(t)
    if timeframe in STEPS:
        opened = day_open(t)
        return opened + ((t - opened) // STEPS[timeframe]) * STEPS[timeframe]
    if timeframe is Timeframe.D1:
        return day_open(t)
    if timeframe is Timeframe.W1:
        return week_open(t)
    first, _ = _month_days(trading_date(t))
    return _open_of(first)


def bucket_end(start: datetime, timeframe: Timeframe) -> datetime:
    """End (UTC, exclusive) of the period that starts at `start` (a value from `bucket_start`)."""
    start = _utc(start)
    if timeframe in STEPS:
        return start + STEPS[timeframe]
    if timeframe is Timeframe.D1:
        return start + DAY
    if timeframe is Timeframe.W1:
        return week_close(start)
    _, last = _month_days(trading_date(start))
    return _open_of(last) + DAY


def expected_candles(start: datetime, timeframe: Timeframe) -> int:
    """How many one-minute candles a full period holds when the market is open throughout: the
    period length in minutes, less the closed weekends inside a month."""
    start = _utc(start)
    end = bucket_end(start, timeframe)
    if timeframe is not Timeframe.MN1:
        return (end - start) // MINUTE
    first = trading_date(start)
    last = trading_date(end - MINUTE)
    days = sum(
        1 for k in range((last - first).days + 1) if (first + timedelta(days=k)).weekday() < 5
    )
    return days * (DAY // MINUTE)
