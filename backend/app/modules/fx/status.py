"""A rate's status, from its age and its provider's publishing rhythm (P11-T03.5, DEC-26).

| Status | Meaning |
|---|---|
| `current` | within the provider's normal update window |
| `cached` | older than that, kept from the last successful refresh |
| `stale` | older still: shown with its age, not to be taken as today's rate |
| `unavailable` | no rate has ever been stored for the pair |

The status is computed when a rate is read, from the clock, and never stored: a stored status
would turn yesterday's "current" into a lie. Cached data is never labelled current. The kind of
rate (mid-market, indicative, delayed) is separate and comes from the provider."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from app.core.config import Settings


class RateStatus(StrEnum):
    CURRENT = "current"
    CACHED = "cached"
    STALE = "stale"
    UNAVAILABLE = "unavailable"


# Providers that publish once a working day; any other provider is held to the hourly windows,
# the stricter of the two.
DAILY_PROVIDERS = frozenset({"ecb"})


@dataclass(frozen=True)
class Windows:
    current: timedelta
    cached: timedelta


@dataclass(frozen=True)
class StatusPolicy:
    daily: Windows
    hourly: Windows

    @classmethod
    def from_settings(cls, settings: Settings) -> "StatusPolicy":
        return cls(
            daily=Windows(
                timedelta(hours=settings.fx_daily_current_hours),
                timedelta(hours=settings.fx_daily_cached_hours),
            ),
            hourly=Windows(
                timedelta(hours=settings.fx_hourly_current_hours),
                timedelta(hours=settings.fx_hourly_cached_hours),
            ),
        )

    def windows(self, provider: str) -> Windows:
        return self.daily if provider in DAILY_PROVIDERS else self.hourly

    def status(self, provider: str, rate_timestamp: datetime, now: datetime) -> RateStatus:
        """The status of a rate published at `rate_timestamp` by `provider`, seen at `now`."""
        age = now - rate_timestamp
        w = self.windows(provider)
        if age <= w.current:
            return RateStatus.CURRENT
        if age <= w.cached:
            return RateStatus.CACHED
        return RateStatus.STALE
