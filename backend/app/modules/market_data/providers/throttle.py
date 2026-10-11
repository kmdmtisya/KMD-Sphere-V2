"""Client-side rate limiting (P08-T03.3): stay inside a vendor's quota instead of being refused.

A sliding window: at most `max_calls` in any `per` period. `acquire()` waits (sleeping) until a
call is allowed. Time and sleeping are injected so tests do not wait. One limiter per adapter
instance; a worker that runs several processes should size `max_calls` per process."""

import asyncio
from collections import deque
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta


def _utc_now() -> datetime:
    return datetime.now(UTC)


class RateLimiter:
    def __init__(
        self,
        max_calls: int,
        per: timedelta,
        clock: Callable[[], datetime] = _utc_now,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if max_calls < 1:
            raise ValueError("max_calls must be at least 1")
        if per <= timedelta(0):
            raise ValueError("per must be positive")
        self._max = max_calls
        self._per = per
        self._clock = clock
        self._sleep = sleep
        self._calls: deque[datetime] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            while True:
                now = self._clock()
                while self._calls and now - self._calls[0] >= self._per:
                    self._calls.popleft()
                if len(self._calls) < self._max:
                    self._calls.append(now)
                    return
                wait = self._per - (now - self._calls[0])
                await self._sleep(max(wait.total_seconds(), 0.0))
