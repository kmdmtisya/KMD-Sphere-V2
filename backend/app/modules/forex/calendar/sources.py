"""Calendar sources (P13-T04.2). A source turns its own format into calendar values; nothing here
fetches anything from the network (DEC-19: no licensed calendar provider yet).

- `DemoCalendarSource`: a synthetic DEMO calendar (`demo_calendar.json`). Release schedules are
  written in each release's local time and time zone, so daylight saving is exercised. Values are
  deterministic and fictional; `actual` exists only once the release time has passed.
- `IcsCalendarSource`: release schedules from an iCalendar (RFC 5545) feed, the format that many
  official statistics offices and central banks use for their release calendars. A schedule feed
  carries no values; it says what is released and when. Tested against synthetic fixtures only."""

import calendar as cal
import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.modules.forex.calendar.types import EventEntry, Importance, Kind, PolicyRateEntry
from app.modules.market_data.providers.errors import ProviderDataError

DEMO_FILE = Path(__file__).with_name("demo_calendar.json")


@dataclass(frozen=True)
class CalendarBatch:
    retrieved_at: datetime
    events: list[EventEntry]
    rates: list[PolicyRateEntry]


class CalendarSource(Protocol):
    name: str
    is_demo: bool
    licence_status: str  # demo, public_domain, unconfirmed, licensed

    def load(self, start: date, end: date, now: datetime) -> CalendarBatch:
        """Events scheduled from `start` to `end` inclusive (UTC dates), as known at `now`."""
        ...


# ------------------------------------------------------------------------------------ DEMO
def _monthly_day(year: int, month: int, day: int) -> date:
    d = date(year, month, min(day, cal.monthrange(year, month)[1]))
    while d.weekday() >= 5:  # a weekend release moves to Monday
        d += timedelta(days=1)
    return d


def _first_weekday(year: int, month: int, weekday: int) -> date:
    d = date(year, month, 1)
    while d.weekday() != weekday:
        d += timedelta(days=1)
    return d


def occurrences(rule: dict[str, int], start: date, end: date) -> list[date]:
    """Dates a template's rule falls on between `start` and `end` (inclusive), local dates."""
    out: set[date] = set()
    if "weekly" in rule:
        d = start + timedelta(days=(rule["weekly"] - start.weekday()) % 7)
        while d <= end:
            out.add(d)
            d += timedelta(days=7)
        return sorted(out)
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        if "monthly_day" in rule:
            d = _monthly_day(y, m, rule["monthly_day"])
        elif "first_weekday" in rule:
            d = _first_weekday(y, m, rule["first_weekday"])
        else:
            raise ValueError("unknown schedule rule")
        if start <= d <= end:
            out.add(d)
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return sorted(out)


def _synthetic(template: dict[str, Any], day: date, salt: str) -> Decimal | None:
    if "base" not in template:
        return None
    digest = hashlib.sha256(f"{template['id']}|{day.isoformat()}|{salt}".encode()).digest()
    unit = Decimal(int.from_bytes(digest[:4], "big") % 2001 - 1000) / Decimal(1000)  # -1..1
    value = Decimal(template["base"]) + Decimal(template["spread"]) * unit
    return value.quantize(Decimal(1).scaleb(-int(template.get("places", 1))))


class DemoCalendarSource:
    name = "demo"
    is_demo = True
    licence_status = "demo"

    def __init__(self, path: Path = DEMO_FILE) -> None:
        self._data = json.loads(path.read_text(encoding="utf-8"))

    def load(self, start: date, end: date, now: datetime) -> CalendarBatch:
        if now.tzinfo is None:
            raise ValueError("now must carry a time zone")
        events: list[EventEntry] = []
        for t in self._data["events"]:
            zone = ZoneInfo(t["tz"])
            hour, minute = (int(x) for x in t["local_time"].split(":"))
            # Local dates one day either side, so a release whose UTC date differs is not missed.
            for day in occurrences(t["rule"], start - timedelta(days=1), end + timedelta(days=1)):
                at = datetime.combine(day, time(hour, minute), zone).astimezone(UTC)
                if not start <= at.date() <= end:
                    continue
                prior = occurrences(t["rule"], day - timedelta(days=45), day - timedelta(days=1))
                events.append(
                    EventEntry(
                        source_event_id=f"{t['id']}:{day.isoformat()}",
                        name=t["name"],
                        kind=t["kind"],
                        currencies=tuple(t["currencies"]),
                        scheduled_at=at,
                        importance=t["importance"],
                        unit=t.get("unit"),
                        actual=_synthetic(t, day, "actual") if at <= now else None,
                        forecast=_synthetic(t, day, "forecast"),
                        previous=_synthetic(t, prior[-1], "actual") if prior else None,
                        commentary=t.get("commentary"),
                    )
                )
        rates = [
            PolicyRateEntry(
                currency=r["currency"],
                bank=r["bank"],
                rate=Decimal(r["rate"]),
                effective_date=date.fromisoformat(r["effective_date"]),
                decided_at=datetime.fromisoformat(r["decided_at"]),
            )
            for r in self._data["policy_rates"]
            if date.fromisoformat(r["effective_date"]) <= now.date()
        ]
        return CalendarBatch(
            now, sorted(events, key=lambda e: (e.scheduled_at, e.source_event_id)), rates
        )


# ------------------------------------------------------------------------------- iCalendar
def _unfold(text: str) -> list[str]:
    lines: list[str] = []
    for raw in text.replace("\r\n", "\n").split("\n"):
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        elif raw:
            lines.append(raw)
    return lines


def _unescape(value: str) -> str:
    return (
        value.replace("\\n", " ")
        .replace("\\N", " ")
        .replace("\\,", ",")
        .replace("\\;", ";")
        .replace("\\\\", "\\")
    )


def parse_datetime(params: str, value: str) -> datetime | None:
    """An RFC 5545 DTSTART: UTC (`...Z`), local with `TZID=`, or floating (treated as an error,
    because its zone is unknown). All-day dates (`VALUE=DATE`) give None: no release time."""
    if "VALUE=DATE" in params.upper() and "T" not in value:
        return None
    try:
        if value.endswith("Z"):
            return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
        tzid = next(
            (p.split("=", 1)[1] for p in params.split(";") if p.upper().startswith("TZID=")), None
        )
        if tzid is None:
            raise ProviderDataError("a release time without a time zone cannot be placed")
        return (
            datetime.strptime(value, "%Y%m%dT%H%M%S")
            .replace(tzinfo=ZoneInfo(tzid.strip('"')))
            .astimezone(UTC)
        )
    except (ValueError, ZoneInfoNotFoundError):
        raise ProviderDataError("bad DTSTART in the calendar feed") from None


class IcsCalendarSource:
    """Release schedules from an iCalendar feed. Every event gets the feed's currencies and
    default importance; a `CATEGORIES` value of HIGH, MEDIUM or LOW overrides the importance."""

    is_demo = False

    def __init__(
        self,
        text: str,
        name: str,
        currencies: Sequence[str],
        importance: Importance = "medium",
        kind: Kind = "indicator",
        licence_status: str = "unconfirmed",
        source_url: str | None = None,
    ) -> None:
        self._text = text
        self.name = name
        self._currencies = tuple(currencies)
        self._importance: Importance = importance
        self._kind: Kind = kind
        self.licence_status = licence_status
        self._url = source_url
        self.all_day_skipped = 0

    def load(self, start: date, end: date, now: datetime) -> CalendarBatch:
        lines = _unfold(self._text)
        if not lines or lines[0].upper() != "BEGIN:VCALENDAR":
            raise ProviderDataError("not an iCalendar feed")
        events: list[EventEntry] = []
        current: dict[str, tuple[str, str]] | None = None
        for line in lines:
            if line.upper() == "BEGIN:VEVENT":
                current = {}
                continue
            if line.upper() == "END:VEVENT":
                if current is not None:
                    entry = self._event(current)
                    if entry is not None and start <= entry.scheduled_at.date() <= end:
                        events.append(entry)
                current = None
                continue
            if current is None or ":" not in line:
                continue
            head, value = line.split(":", 1)
            key, _, params = head.partition(";")
            current[key.upper()] = (params, value)
        return CalendarBatch(
            now, sorted(events, key=lambda e: (e.scheduled_at, e.source_event_id)), []
        )

    def _event(self, props: dict[str, tuple[str, str]]) -> EventEntry | None:
        if "UID" not in props or "SUMMARY" not in props or "DTSTART" not in props:
            raise ProviderDataError("a calendar event needs UID, SUMMARY and DTSTART")
        at = parse_datetime(*props["DTSTART"])
        if at is None:
            self.all_day_skipped += 1
            return None
        category = props.get("CATEGORIES", ("", ""))[1].strip().lower()
        levels: dict[str, Importance] = {"low": "low", "medium": "medium", "high": "high"}
        importance = levels.get(category, self._importance)
        return EventEntry(
            source_event_id=props["UID"][1][:120],
            name=_unescape(props["SUMMARY"][1])[:200],
            kind=self._kind,
            currencies=self._currencies,
            scheduled_at=at,
            importance=importance,
            source_url=self._url,
        )
