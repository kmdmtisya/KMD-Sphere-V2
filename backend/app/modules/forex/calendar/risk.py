"""Event-risk windows (P13-T04.3, design section 6). Pure functions.

Around a scheduled release, prices can move sharply and spreads widen. A window opens `before`
the release and closes `after` it: 30 minutes before and 60 after for a high-importance event,
15 and 30 for a medium one, none for a low one. The scanner and the risk engine use the windows
of the pair's two currencies to raise the macro-event component and to warn on trade setups. A
window is a schedule fact, not a forecast that the price will move."""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

WINDOWS: dict[str, tuple[timedelta, timedelta]] = {
    "high": (timedelta(minutes=30), timedelta(minutes=60)),
    "medium": (timedelta(minutes=15), timedelta(minutes=30)),
}


class ScheduledEvent(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def currencies(self) -> Sequence[str]: ...

    @property
    def scheduled_at(self) -> datetime: ...

    @property
    def importance(self) -> str: ...


@dataclass(frozen=True)
class RiskWindow:
    name: str
    currencies: tuple[str, ...]
    importance: str
    scheduled_at: datetime
    starts: datetime
    ends: datetime

    def contains(self, at: datetime) -> bool:
        return self.starts <= at < self.ends


def window_for(event: ScheduledEvent) -> RiskWindow | None:
    span = WINDOWS.get(event.importance)
    if span is None:
        return None
    before, after = span
    return RiskWindow(
        event.name,
        tuple(sorted(event.currencies)),
        event.importance,
        event.scheduled_at,
        event.scheduled_at - before,
        event.scheduled_at + after,
    )


def windows(events: Iterable[ScheduledEvent]) -> list[RiskWindow]:
    out = [w for e in events if (w := window_for(e)) is not None]
    return sorted(out, key=lambda w: (w.starts, w.name))


def pair_currencies(instrument: str) -> frozenset[str]:
    """EUR_USD -> {EUR, USD}."""
    base, _, quote = instrument.partition("_")
    if len(base) != 3 or len(quote) != 3:
        raise ValueError("instrument must look like EUR_USD")
    return frozenset({base, quote})


def active(found: Iterable[RiskWindow], instrument: str, at: datetime) -> list[RiskWindow]:
    """The windows open at `at` that touch either currency of the pair."""
    if at.tzinfo is None:
        raise ValueError("time must carry a time zone")
    currencies = pair_currencies(instrument)
    return [w for w in found if w.contains(at) and currencies & set(w.currencies)]
