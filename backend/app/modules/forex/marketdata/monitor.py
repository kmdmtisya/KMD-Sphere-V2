"""Feed status from heartbeats (P13-T02.4, design section 4.3). The clock is injected.

Connected while messages (prices or heartbeats) keep arriving; `degraded` once nothing has
arrived for `degraded_after`; `disconnected` after `disconnected_after`, or whenever the
connection is down. The streaming client reconnects when the feed is disconnected."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.modules.forex.marketdata.types import FeedStatus

Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class HeartbeatPolicy:
    degraded_after: timedelta = timedelta(seconds=10)
    disconnected_after: timedelta = timedelta(seconds=30)

    def __post_init__(self) -> None:
        if not timedelta(0) < self.degraded_after < self.disconnected_after:
            raise ValueError("0 < degraded_after < disconnected_after is required")


def status_for(
    last_message_at: datetime | None, now: datetime, policy: HeartbeatPolicy
) -> FeedStatus:
    if last_message_at is None:
        return FeedStatus.DISCONNECTED
    silent = now - last_message_at
    # Half-open windows: silence of exactly `degraded_after` is degraded, which is when the
    # streaming client's own timer fires.
    if silent < policy.degraded_after:
        return FeedStatus.CONNECTED
    if silent < policy.disconnected_after:
        return FeedStatus.DEGRADED
    return FeedStatus.DISCONNECTED


class FeedMonitor:
    def __init__(self, policy: HeartbeatPolicy, clock: Clock = utc_now) -> None:
        self.policy = policy
        self._clock = clock
        self._connected = False
        self._last: datetime | None = None

    @property
    def last_message_at(self) -> datetime | None:
        return self._last

    def on_connect(self) -> None:
        """A connection opened: it counts as a message, so the window starts now."""
        self._connected = True
        self._last = self._clock()

    def on_message(self) -> None:
        self._last = self._clock()

    def on_disconnect(self) -> None:
        self._connected = False

    @property
    def status(self) -> FeedStatus:
        if not self._connected:
            return FeedStatus.DISCONNECTED
        return status_for(self._last, self._clock(), self.policy)
