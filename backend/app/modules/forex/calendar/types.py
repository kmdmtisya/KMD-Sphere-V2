"""Calendar values (P13-T04.1). Validated when built: a bad value from a source raises
`ProviderDataError` and is never stored.

Three kinds of content are kept apart, end to end:
- **confirmed**: what the source published as a fact: `actual` (once released) and `previous`;
- **expectation**: the consensus `forecast`, which is not a fact;
- **commentary**: a source's speculative text, which is never data.
Times are UTC."""

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Literal

from app.modules.market_data.providers.errors import ProviderDataError

Importance = Literal["low", "medium", "high"]
Kind = Literal["indicator", "central_bank_decision", "speech", "other"]
IMPORTANCE: tuple[Importance, ...] = ("low", "medium", "high")
KINDS: tuple[Kind, ...] = ("indicator", "central_bank_decision", "speech", "other")
_CURRENCY = re.compile(r"^[A-Z]{3}$")


def _aware(t: datetime, what: str) -> datetime:
    if t.tzinfo is None or t.utcoffset() is None:
        raise ProviderDataError(f"{what} must carry a time zone")
    return t.astimezone(UTC)


def _finite(v: Decimal | None, what: str) -> None:
    if v is not None and (not isinstance(v, Decimal) or not v.is_finite()):
        raise ProviderDataError(f"{what} must be a finite decimal")


@dataclass(frozen=True)
class EventEntry:
    source_event_id: str
    name: str
    kind: Kind
    currencies: tuple[str, ...]
    scheduled_at: datetime
    importance: Importance
    unit: str | None = None
    actual: Decimal | None = None
    forecast: Decimal | None = None
    previous: Decimal | None = None
    commentary: str | None = None
    source_url: str | None = None

    def __post_init__(self) -> None:
        if not self.source_event_id or len(self.source_event_id) > 120:
            raise ProviderDataError("event id must be 1 to 120 characters")
        if not self.name.strip() or len(self.name) > 200:
            raise ProviderDataError("event name must be 1 to 200 characters")
        if self.kind not in KINDS or self.importance not in IMPORTANCE:
            raise ProviderDataError("unknown event kind or importance")
        if not self.currencies or any(not _CURRENCY.fullmatch(c) for c in self.currencies):
            raise ProviderDataError("currencies must be ISO 4217 codes")
        for what in ("actual", "forecast", "previous"):
            _finite(getattr(self, what), what)
        if self.unit is not None and len(self.unit) > 20:
            raise ProviderDataError("unit must be at most 20 characters")
        if self.commentary is not None and len(self.commentary) > 1000:
            raise ProviderDataError("commentary must be at most 1000 characters")
        if self.source_url is not None and not self.source_url.startswith("https://"):
            raise ProviderDataError("source URL must be https")
        object.__setattr__(self, "scheduled_at", _aware(self.scheduled_at, "scheduled time"))
        object.__setattr__(self, "currencies", tuple(sorted(set(self.currencies))))


@dataclass(frozen=True)
class PolicyRateEntry:
    currency: str
    bank: str
    rate: Decimal  # percent a year
    effective_date: date
    decided_at: datetime
    source_url: str | None = None

    def __post_init__(self) -> None:
        if not _CURRENCY.fullmatch(self.currency):
            raise ProviderDataError("currency must be an ISO 4217 code")
        _finite(self.rate, "rate")
        if not Decimal(-10) <= self.rate <= Decimal(100):
            raise ProviderDataError("policy rate out of range")
        if not self.bank.strip() or len(self.bank) > 100:
            raise ProviderDataError("bank must be 1 to 100 characters")
        if self.source_url is not None and not self.source_url.startswith("https://"):
            raise ProviderDataError("source URL must be https")
        object.__setattr__(self, "decided_at", _aware(self.decided_at, "decision time"))
