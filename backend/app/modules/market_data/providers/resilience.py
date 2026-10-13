"""Retry, circuit breaker and fallback chain around a provider (P08-T02.2).

- **Retry:** a call that fails with `ProviderUnavailable` (including `RateLimited`) is tried again
  with exponential backoff, up to `max_attempts`. A `RateLimited` answer that names a wait waits
  that long (capped). Other errors are not retried: asking again returns the same answer.
- **Circuit breaker:** after `failure_threshold` calls in a row that still failed, the provider is
  left alone for `reset_timeout` (calls fail fast with `CircuitOpen`). After that one trial call
  is allowed: success closes the circuit, failure reopens it. `SymbolNotFound`,
  `UnsupportedKind` and `ProviderDataError` are about the request or the data, not the provider's
  health, so they do not count.
- **Fallback chain:** providers tried in order; the first answer wins. Failover happens on
  `ProviderUnavailable` (including an open circuit); a provider that does not serve the asset kind
  is skipped. An unknown symbol is not retried elsewhere silently, and bad data is never replaced
  by a guess.

Time and sleeping are injected so tests run without waiting."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum

from app.modules.market_data.providers.base import MarketDataProvider
from app.modules.market_data.providers.batch import fetch_fx_batch
from app.modules.market_data.providers.errors import (
    AllProvidersFailed,
    CircuitOpen,
    ProviderAuthError,
    ProviderError,
    ProviderUnavailable,
    RateLimited,
    UnsupportedKind,
)
from app.modules.market_data.providers.models import (
    AssetKind,
    FxBatch,
    FxQuote,
    PricePoint,
    PriceQuote,
)

Clock = Callable[[], datetime]
Sleep = Callable[[float], Awaitable[None]]


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay: timedelta = timedelta(milliseconds=500)
    factor: float = 2.0
    max_delay: timedelta = timedelta(seconds=10)

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.factor < 1:
            raise ValueError("factor must be at least 1")

    def delay_for(self, attempt: int, error: ProviderError) -> timedelta:
        """The wait before attempt number `attempt + 1` (`attempt` counts from 1)."""
        if isinstance(error, RateLimited) and error.retry_after is not None:
            return min(error.retry_after, self.max_delay)
        return min(self.base_delay * (self.factor ** (attempt - 1)), self.max_delay)


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = 5,
        reset_timeout: timedelta = timedelta(seconds=30),
        clock: Clock = _utc_now,
    ) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be at least 1")
        self._threshold = failure_threshold
        self._reset_timeout = reset_timeout
        self._clock = clock
        self._failures = 0
        self._opened_at: datetime | None = None
        self._trial_in_flight = False

    @property
    def state(self) -> CircuitState:
        if self._opened_at is None:
            return CircuitState.CLOSED
        if self._clock() - self._opened_at >= self._reset_timeout:
            return CircuitState.HALF_OPEN
        return CircuitState.OPEN

    def before_call(self) -> None:
        """Raise `CircuitOpen` when the call must not be made."""
        state = self.state
        if state is CircuitState.OPEN:
            raise CircuitOpen("provider circuit is open")
        if state is CircuitState.HALF_OPEN:
            if self._trial_in_flight:
                raise CircuitOpen("provider circuit is open (trial call in progress)")
            self._trial_in_flight = True

    def record_success(self) -> None:
        self._failures = 0
        self._opened_at = None
        self._trial_in_flight = False

    def record_failure(self) -> None:
        self._trial_in_flight = False
        self._failures += 1
        if self._failures >= self._threshold or self._opened_at is not None:
            self._opened_at = self._clock()

    def release(self) -> None:
        """A call ended in a way that says nothing about health: free a trial slot."""
        self._trial_in_flight = False


async def call_guarded[T](
    op: Callable[[], Awaitable[T]], retry: RetryPolicy, breaker: CircuitBreaker, sleep: Sleep
) -> T:
    """One call under the retry policy and circuit breaker described above. Shared by every
    provider family (market data here, forex quotes and candles in P13)."""
    breaker.before_call()
    attempt = 1
    while True:
        try:
            result = await op()
        except ProviderAuthError:
            # Retrying with the same credentials cannot help.
            breaker.record_failure()
            raise
        except ProviderUnavailable as error:
            if attempt >= retry.max_attempts:
                breaker.record_failure()
                raise
            await sleep(retry.delay_for(attempt, error).total_seconds())
            attempt += 1
        except ProviderError:
            # About the request or the data, not the provider's health.
            breaker.release()
            raise
        else:
            breaker.record_success()
            return result


class ResilientProvider:
    """Wraps a provider with retry and a circuit breaker. Implements `MarketDataProvider`."""

    def __init__(
        self,
        inner: MarketDataProvider,
        retry: RetryPolicy | None = None,
        breaker: CircuitBreaker | None = None,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self._inner = inner
        self._retry = retry or RetryPolicy()
        self.breaker = breaker or CircuitBreaker()
        self._sleep = sleep

    @property
    def name(self) -> str:
        return self._inner.name

    @property
    def supported_kinds(self) -> frozenset[AssetKind]:
        return self._inner.supported_kinds

    async def _call[T](self, op: Callable[[], Awaitable[T]]) -> T:
        return await call_guarded(op, self._retry, self.breaker, self._sleep)

    async def get_quote(self, symbol: str, kind: AssetKind) -> PriceQuote:
        return await self._call(lambda: self._inner.get_quote(symbol, kind))

    async def get_history(
        self, symbol: str, kind: AssetKind, start: date, end: date
    ) -> list[PricePoint]:
        return await self._call(lambda: self._inner.get_history(symbol, kind, start, end))

    async def get_fx_rate(self, base: str, quote: str) -> FxQuote:
        return await self._call(lambda: self._inner.get_fx_rate(base, quote))

    async def get_fx_history(self, base: str, quote: str, start: date, end: date) -> list[FxQuote]:
        return await self._call(lambda: self._inner.get_fx_history(base, quote, start, end))

    async def get_fx_rates(self, base: str, quotes: list[str]) -> FxBatch:
        """The inner provider's batch (or one-by-one) answer, with the same retry and breaker."""
        return await self._call(lambda: fetch_fx_batch(self._inner, base, quotes))


class FallbackChain:
    """Tries providers in order and returns the first answer. Implements `MarketDataProvider`."""

    def __init__(self, providers: list[MarketDataProvider]) -> None:
        if not providers:
            raise ValueError("a fallback chain needs at least one provider")
        self._providers = providers

    @property
    def name(self) -> str:
        return "+".join(p.name for p in self._providers)

    @property
    def supported_kinds(self) -> frozenset[AssetKind]:
        kinds: set[AssetKind] = set()
        for p in self._providers:
            kinds |= p.supported_kinds
        return frozenset(kinds)

    async def _first[T](self, op: Callable[[MarketDataProvider], Awaitable[T]]) -> T:
        errors: list[ProviderError] = []
        unsupported: UnsupportedKind | None = None
        for provider in self._providers:
            try:
                return await op(provider)
            except ProviderUnavailable as error:
                errors.append(error)
            except UnsupportedKind as error:
                # This provider does not serve the asset: ask the next one.
                unsupported = error
        if errors:
            raise AllProvidersFailed(errors)
        assert unsupported is not None  # noqa: S101 (the chain is never empty)
        raise unsupported

    async def get_quote(self, symbol: str, kind: AssetKind) -> PriceQuote:
        return await self._first(lambda p: p.get_quote(symbol, kind))

    async def get_history(
        self, symbol: str, kind: AssetKind, start: date, end: date
    ) -> list[PricePoint]:
        return await self._first(lambda p: p.get_history(symbol, kind, start, end))

    async def get_fx_rate(self, base: str, quote: str) -> FxQuote:
        return await self._first(lambda p: p.get_fx_rate(base, quote))

    async def get_fx_history(self, base: str, quote: str, start: date, end: date) -> list[FxQuote]:
        return await self._first(lambda p: p.get_fx_history(base, quote, start, end))
