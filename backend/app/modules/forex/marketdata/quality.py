"""Quality of a received quote and freshness of a served one (P13-T02.5). Pure functions.

A crossed or out-of-band quote is `suspect`: kept for the record, never served as the latest
price. A quote that is already older than the staleness threshold when it arrives is `stale`.
When served, a quote's age is measured again: an old quote is shown as stale with its true age,
never as current. Nothing here invents, repairs or interpolates a price."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum

from app.modules.forex.marketdata.types import Quality, Quote

# A mid more than 5% from the previous good mid of the same pair is out of band. Wide enough
# for a major pair's largest intraday moves; a jump beyond it is far more likely a bad tick.
DEFAULT_BAND = Decimal("0.05")


@dataclass(frozen=True)
class QualityPolicy:
    stale_after: timedelta = timedelta(seconds=60)
    band: Decimal = DEFAULT_BAND

    def __post_init__(self) -> None:
        if self.stale_after <= timedelta(0):
            raise ValueError("stale_after must be positive")
        if not Decimal(0) < self.band < Decimal(1):
            raise ValueError("band must be between 0 and 1")


def assess(
    quote: Quote, previous_mid: Decimal | None, received: datetime, policy: QualityPolicy
) -> Quality:
    """The quality of `quote` when it arrives. `previous_mid` is the last good mid of the pair."""
    if quote.crossed:
        return Quality.SUSPECT
    if previous_mid is not None and abs(quote.mid - previous_mid) > previous_mid * policy.band:
        return Quality.SUSPECT
    if received - quote.ts_provider > policy.stale_after:
        return Quality.STALE
    return Quality.OK


class Freshness(StrEnum):
    FRESH = "fresh"
    STALE = "stale"
    UNAVAILABLE = "unavailable"  # no usable quote: nothing is shown in its place


def freshness(ts_provider: datetime | None, now: datetime, policy: QualityPolicy) -> Freshness:
    if ts_provider is None:
        return Freshness.UNAVAILABLE
    return Freshness.STALE if now - ts_provider > policy.stale_after else Freshness.FRESH


def age(ts_provider: datetime, now: datetime) -> timedelta:
    """The true age of a price; never negative (a provider clock slightly ahead reads as 0)."""
    return max(now - ts_provider, timedelta(0))
