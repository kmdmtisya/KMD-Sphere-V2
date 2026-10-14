"""The calendar without a database (P13-T04.1, T04.2, T04.3): validated values, schedule rules,
the DEMO source in local time zones with daylight saving, the iCalendar adapter against a
synthetic fixture, and event-risk windows."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from app.modules.forex.calendar import risk
from app.modules.forex.calendar.sources import (
    DemoCalendarSource,
    IcsCalendarSource,
    occurrences,
    parse_datetime,
)
from app.modules.forex.calendar.types import EventEntry, PolicyRateEntry
from app.modules.market_data.providers.errors import ProviderDataError

D = Decimal
FIXTURE = Path(__file__).parent / "fixtures" / "release_calendar.ics"


def utc(y: int, mo: int, d: int, h: int = 0, mi: int = 0) -> datetime:
    return datetime(y, mo, d, h, mi, tzinfo=UTC)


def event(**overrides: object) -> EventEntry:
    values: dict[str, object] = {
        "source_event_id": "e1",
        "name": "Test release",
        "kind": "indicator",
        "currencies": ("USD",),
        "scheduled_at": utc(2026, 10, 7, 12, 30),
        "importance": "high",
    }
    values.update(overrides)
    return EventEntry(**values)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- values
def test_events_are_validated_and_normalised() -> None:
    e = event(currencies=("USD", "EUR", "USD"))
    assert e.currencies == ("EUR", "USD")
    from zoneinfo import ZoneInfo

    local = event(scheduled_at=datetime(2026, 10, 7, 8, 30, tzinfo=ZoneInfo("America/New_York")))
    assert local.scheduled_at == utc(2026, 10, 7, 12, 30) and local.scheduled_at.tzinfo is UTC


@pytest.mark.parametrize(
    "bad",
    [
        {"scheduled_at": datetime(2026, 10, 7, 12, 30)},
        {"currencies": ("usd",)},
        {"currencies": ()},
        {"importance": "urgent"},
        {"kind": "rumour"},
        {"name": " "},
        {"source_event_id": ""},
        {"actual": D("NaN")},
        {"forecast": 1.5},
        {"source_url": "http://insecure.example"},
        {"commentary": "x" * 1001},
    ],
)
def test_bad_events_are_refused(bad: dict[str, object]) -> None:
    with pytest.raises(ProviderDataError):
        event(**bad)


def test_policy_rates_are_validated() -> None:
    ok = PolicyRateEntry("USD", "Bank", D("4.5"), date(2026, 9, 17), utc(2026, 9, 16, 18))
    assert ok.rate == D("4.5")
    for bad in (
        {"currency": "US"},
        {"rate": D(200)},
        {"rate": D("Infinity")},
        {"decided_at": datetime(2026, 9, 16)},
        {"bank": ""},
    ):
        values: dict[str, object] = {
            "currency": "USD",
            "bank": "Bank",
            "rate": D("4.5"),
            "effective_date": date(2026, 9, 17),
            "decided_at": utc(2026, 9, 16, 18),
        }
        values.update(bad)
        with pytest.raises(ProviderDataError):
            PolicyRateEntry(**values)  # type: ignore[arg-type]


# ------------------------------------------------------------------------ schedule rules
def test_schedule_rules() -> None:
    oct_nov = (date(2026, 10, 1), date(2026, 11, 30))
    assert occurrences({"first_weekday": 4}, *oct_nov) == [date(2026, 10, 2), date(2026, 11, 6)]
    # The 12th of December 2026 is a Saturday: the release moves to Monday the 14th.
    assert occurrences({"monthly_day": 12}, date(2026, 12, 1), date(2026, 12, 31)) == [
        date(2026, 12, 14)
    ]
    # The 30th of February does not exist: the last day (Sunday 28 February 2027), then the next
    # weekday, Monday 1 March; March's own release is on Tuesday 30 March.
    feb_mar = occurrences({"monthly_day": 30}, date(2027, 2, 1), date(2027, 3, 31))
    assert feb_mar == [date(2027, 3, 1), date(2027, 3, 30)]
    weekly = occurrences({"weekly": 3}, date(2026, 10, 1), date(2026, 10, 31))
    assert weekly == [
        date(2026, 10, 1),
        date(2026, 10, 8),
        date(2026, 10, 15),
        date(2026, 10, 22),
        date(2026, 10, 29),
    ]
    with pytest.raises(ValueError):
        occurrences({"yearly": 1}, *oct_nov)


# ---------------------------------------------------------------------------- DEMO source
NOW = utc(2026, 10, 14, 12)


def demo(
    start: date = date(2026, 10, 1), end: date = date(2026, 12, 31), now: datetime = NOW
) -> dict[str, EventEntry]:
    return {e.source_event_id: e for e in DemoCalendarSource().load(start, end, now).events}


def test_local_release_times_become_utc_across_daylight_saving() -> None:
    events = demo()
    # US payrolls: first Friday, 08:30 New York. 2 October is EDT (UTC-4); clocks go back on
    # 1 November, so 6 November is EST (UTC-5).
    assert events["us_payrolls:2026-10-02"].scheduled_at == utc(2026, 10, 2, 12, 30)
    assert events["us_payrolls:2026-11-06"].scheduled_at == utc(2026, 11, 6, 13, 30)
    # Euro area at 11:00 Brussels: CEST (UTC+2) on 1 October, CET (UTC+1) on 1 December.
    assert events["ez_cpi:2026-10-01"].scheduled_at == utc(2026, 10, 1, 9, 0)
    assert events["ez_cpi:2026-12-01"].scheduled_at == utc(2026, 12, 1, 10, 0)
    # Tokyo 08:50 is the evening before in UTC: the UTC date differs from the local date.
    tokyo = demo(date(2026, 9, 30), date(2026, 10, 31))["jp_tankan:2026-10-01"]
    assert tokyo.scheduled_at == utc(2026, 9, 30, 23, 50)
    # Nairobi has no daylight saving: 14:00 EAT is always 11:00 UTC.
    assert events["ke_cpi:2026-10-30"].scheduled_at == utc(2026, 10, 30, 11, 0)


def test_a_release_on_the_range_edge_in_another_utc_date_is_not_missed() -> None:
    # The 1 October Tokyo release is on 30 September in UTC, so it belongs to a range ending then.
    sept = demo(date(2026, 9, 30), date(2026, 9, 30))
    assert "jp_tankan:2026-10-01" in sept
    assert "jp_tankan:2026-10-01" not in demo(date(2026, 10, 1), date(2026, 10, 31))


def test_actual_values_exist_only_after_the_release_and_previous_is_the_prior_actual() -> None:
    events = demo()
    past = events["us_cpi:2026-10-12"]
    future = events["us_cpi:2026-11-12"]
    assert past.scheduled_at < NOW and past.actual is not None
    assert future.scheduled_at > NOW and future.actual is None and future.forecast is not None
    assert future.previous == past.actual  # the prior month's published figure
    at_release = demo(now=past.scheduled_at)["us_cpi:2026-10-12"]
    just_before = demo(now=past.scheduled_at - timedelta(seconds=1))["us_cpi:2026-10-12"]
    assert at_release.actual is not None and just_before.actual is None


def test_the_demo_calendar_is_deterministic_labelled_and_keeps_commentary_apart() -> None:
    assert demo() == demo()
    events = demo()
    assert all(e.name.startswith("DEMO ") for e in events.values())
    fed = events["fed_decision:2026-10-07"]
    assert fed.kind == "central_bank_decision" and fed.actual == D("4.50")
    assert fed.commentary is not None and "not confirmed data" in fed.commentary
    speech = events["fed_speech:2026-10-22"]
    assert speech.actual is None and speech.forecast is None and speech.importance == "low"
    source = DemoCalendarSource()
    assert (source.is_demo, source.licence_status, source.name) == (True, "demo", "demo")


def test_policy_rates_appear_only_once_effective() -> None:
    rates = (
        DemoCalendarSource().load(date(2026, 10, 1), date(2026, 10, 31), utc(2026, 10, 7, 12)).rates
    )
    currencies = {r.currency for r in rates}
    assert "KES" in currencies and "NZD" not in currencies  # NZD takes effect on 8 October
    with pytest.raises(ValueError):
        DemoCalendarSource().load(date(2026, 10, 1), date(2026, 10, 2), datetime(2026, 10, 1))


# ------------------------------------------------------------------------------ iCalendar
def ics(text: str | None = None) -> IcsCalendarSource:
    return IcsCalendarSource(
        text if text is not None else FIXTURE.read_text(encoding="utf-8"),
        "stats_office",
        ["USD"],
        source_url="https://stats.example.test/schedule.ics",
    )


def test_the_ics_feed_gives_release_schedules_in_utc() -> None:
    source = ics()
    batch = source.load(date(2026, 11, 1), date(2026, 12, 31), NOW)
    got = [(e.source_event_id, e.scheduled_at, e.importance, e.name) for e in batch.events]
    assert got == [
        (
            "rel-001@example.test",
            utc(2026, 11, 6, 13, 30),
            "high",
            "Synthetic employment report, October",
        ),
        (
            "rel-002@example.test",
            utc(2026, 11, 12, 13, 30),
            "medium",
            "Synthetic consumer price index for October with a summary line that is folded "
            "onto a second line",
        ),
        (
            "rel-004@example.test",
            utc(2026, 12, 4, 13, 30),
            "high",
            "Synthetic employment report, November",
        ),
    ]
    assert source.all_day_skipped == 1  # a date without a time is not a release time
    assert all(
        e.actual is None and e.forecast is None and e.currencies == ("USD",) for e in batch.events
    )
    assert batch.rates == [] and source.is_demo is False and source.licence_status == "unconfirmed"


def test_ics_errors_are_data_errors() -> None:
    with pytest.raises(ProviderDataError):
        ics("not a calendar").load(date(2026, 1, 1), date(2026, 12, 31), NOW)
    wrap = "BEGIN:VCALENDAR\nBEGIN:VEVENT\n{}\nEND:VEVENT\nEND:VCALENDAR\n"
    floating = wrap.format("UID:x\nSUMMARY:y\nDTSTART:20261106T083000")
    with pytest.raises(ProviderDataError):
        ics(floating).load(date(2026, 1, 1), date(2026, 12, 31), NOW)
    missing = wrap.format("UID:x\nDTSTART:20261106T083000Z")
    with pytest.raises(ProviderDataError):
        ics(missing).load(date(2026, 1, 1), date(2026, 12, 31), NOW)
    with pytest.raises(ProviderDataError):
        parse_datetime("TZID=Mars/Olympus", "20261106T083000")
    with pytest.raises(ProviderDataError):
        parse_datetime("", "2026-11-06")
    assert parse_datetime("VALUE=DATE", "20261106") is None


# ------------------------------------------------------------------------- risk windows
def test_windows_by_importance() -> None:
    high = risk.window_for(event(importance="high"))
    assert high is not None and (high.starts, high.ends) == (
        utc(2026, 10, 7, 12, 0),
        utc(2026, 10, 7, 13, 30),
    )
    medium = risk.window_for(event(importance="medium"))
    assert medium is not None and (medium.starts, medium.ends) == (
        utc(2026, 10, 7, 12, 15),
        utc(2026, 10, 7, 13, 0),
    )
    assert risk.window_for(event(importance="low")) is None


def test_active_windows_touch_either_currency_of_the_pair_and_are_half_open() -> None:
    found = risk.windows(
        [
            event(importance="high"),
            event(source_event_id="e2", currencies=("JPY",), importance="medium"),
        ]
    )
    assert len(found) == 2
    at = utc(2026, 10, 7, 12, 30)
    assert [w.currencies for w in risk.active(found, "EUR_USD", at)] == [("USD",)]
    assert [w.currencies for w in risk.active(found, "USD_JPY", at)] == [("USD",), ("JPY",)]
    assert risk.active(found, "EUR_GBP", at) == []
    assert risk.active(found, "EUR_USD", utc(2026, 10, 7, 12, 0)) != []  # opens exactly then
    assert risk.active(found, "EUR_USD", utc(2026, 10, 7, 13, 30)) == []  # closed exactly then
    with pytest.raises(ValueError):
        risk.active(found, "EUR_USD", datetime(2026, 10, 7, 12, 30))
    with pytest.raises(ValueError):
        risk.pair_currencies("EURUSD")
