"""Retry, circuit breaker and fallback chain (P08-T02.2). Time and sleeping are injected."""

from datetime import UTC, datetime, timedelta

import pytest

from app.modules.market_data.providers.errors import (
    AllProvidersFailed,
    CircuitOpen,
    ProviderDataError,
    ProviderUnavailable,
    RateLimited,
    SymbolNotFound,
    UnsupportedKind,
)
from app.modules.market_data.providers.fake import FakeProvider
from app.modules.market_data.providers.models import AssetKind
from app.modules.market_data.providers.resilience import (
    CircuitBreaker,
    CircuitState,
    FallbackChain,
    ResilientProvider,
    RetryPolicy,
)

T0 = datetime(2026, 10, 12, 12, tzinfo=UTC)


class Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now

    def advance(self, by: timedelta) -> None:
        self.now += by


class Sleeper:
    def __init__(self, clock: Clock | None = None) -> None:
        self.slept: list[float] = []
        self._clock = clock

    async def __call__(self, seconds: float) -> None:
        self.slept.append(seconds)
        if self._clock is not None:
            self._clock.advance(timedelta(seconds=seconds))


def state_of(p: ResilientProvider) -> CircuitState:
    """The breaker's state, read fresh (keeps type narrowing from assuming it is unchanged)."""
    return p.breaker.state


def make(
    *,
    attempts: int = 3,
    threshold: int = 5,
    reset: timedelta = timedelta(seconds=30),
) -> tuple[FakeProvider, ResilientProvider, Clock, Sleeper]:
    clock = Clock()
    sleeper = Sleeper(clock)
    fake = FakeProvider(clock=clock)
    wrapped = ResilientProvider(
        fake,
        RetryPolicy(max_attempts=attempts),
        CircuitBreaker(failure_threshold=threshold, reset_timeout=reset, clock=clock),
        sleep=sleeper,
    )
    return fake, wrapped, clock, sleeper


class TestRetryPolicy:
    def test_backoff_doubles_and_is_capped(self) -> None:
        p = RetryPolicy(base_delay=timedelta(seconds=1), max_delay=timedelta(seconds=5))
        err = ProviderUnavailable()
        assert [p.delay_for(n, err).total_seconds() for n in (1, 2, 3, 4)] == [1, 2, 4, 5]

    def test_rate_limit_wait_is_honoured_up_to_the_cap(self) -> None:
        p = RetryPolicy(max_delay=timedelta(seconds=5))
        assert p.delay_for(1, RateLimited(retry_after=timedelta(seconds=3))) == timedelta(seconds=3)
        assert p.delay_for(1, RateLimited(retry_after=timedelta(seconds=60))) == timedelta(
            seconds=5
        )

    def test_invalid_settings_are_refused(self) -> None:
        with pytest.raises(ValueError, match="max_attempts"):
            RetryPolicy(max_attempts=0)
        with pytest.raises(ValueError, match="factor"):
            RetryPolicy(factor=0.5)


class TestRetry:
    async def test_a_transient_failure_is_retried_then_succeeds(self) -> None:
        fake, p, _, sleeper = make()
        fake.fail_next(2)
        q = await p.get_quote("DEMO-GEQ", AssetKind.ETF)
        assert q.symbol == "DEMO-GEQ"
        assert len(fake.calls) == 3
        assert sleeper.slept == [0.5, 1.0]

    async def test_gives_up_after_the_last_attempt(self) -> None:
        fake, p, _, sleeper = make(attempts=3)
        fake.fail_next(10)
        with pytest.raises(ProviderUnavailable):
            await p.get_quote("DEMO-GEQ", AssetKind.ETF)
        assert len(fake.calls) == 3
        assert len(sleeper.slept) == 2

    async def test_a_rate_limit_waits_as_told(self) -> None:
        fake, p, _, sleeper = make()
        fake.rate_limit_next(1, retry_after=timedelta(seconds=4))
        await p.get_quote("DEMO-GEQ", AssetKind.ETF)
        assert sleeper.slept == [4.0]

    @pytest.mark.parametrize("error", [SymbolNotFound("x"), ProviderDataError("bad")])
    async def test_request_and_data_errors_are_not_retried(self, error: Exception) -> None:
        fake, p, _, sleeper = make()
        fake.fail_next(1, error)  # type: ignore[arg-type]
        with pytest.raises(type(error)):
            await p.get_quote("DEMO-GEQ", AssetKind.ETF)
        assert len(fake.calls) == 1
        assert sleeper.slept == []

    async def test_history_and_fx_are_wrapped_too(self) -> None:
        fake, p, _, _ = make()
        fake.fail_next(1)
        assert (await p.get_fx_rate("USD", "AED")).rate > 0
        fake.fail_next(1)
        from datetime import date

        pts = await p.get_history("DEMO-GEQ", AssetKind.ETF, date(2026, 10, 5), date(2026, 10, 9))
        assert len(pts) == 5

    async def test_it_reports_the_inner_name_and_kinds(self) -> None:
        fake, p, _, _ = make()
        assert p.name == fake.name
        assert p.supported_kinds == fake.supported_kinds


class TestCircuitBreaker:
    async def _trip(self, fake: FakeProvider, p: ResilientProvider, calls: int) -> None:
        fake.set_outage(True)
        for _ in range(calls):
            with pytest.raises(ProviderUnavailable):
                await p.get_quote("DEMO-GEQ", AssetKind.ETF)

    async def test_opens_after_consecutive_failed_calls_and_fails_fast(self) -> None:
        fake, p, _, _ = make(attempts=1, threshold=3)
        await self._trip(fake, p, 3)
        assert p.breaker.state is CircuitState.OPEN
        before = len(fake.calls)
        with pytest.raises(CircuitOpen):
            await p.get_quote("DEMO-GEQ", AssetKind.ETF)
        assert len(fake.calls) == before, "the provider is not called while the circuit is open"

    async def test_stays_closed_below_the_threshold(self) -> None:
        fake, p, _, _ = make(attempts=1, threshold=3)
        await self._trip(fake, p, 2)
        assert p.breaker.state is CircuitState.CLOSED

    async def test_a_success_resets_the_count(self) -> None:
        fake, p, _, _ = make(attempts=1, threshold=3)
        await self._trip(fake, p, 2)
        fake.set_outage(False)
        await p.get_quote("DEMO-GEQ", AssetKind.ETF)
        await self._trip(fake, p, 2)
        assert p.breaker.state is CircuitState.CLOSED

    async def test_half_open_trial_success_closes_it(self) -> None:
        fake, p, clock, _ = make(attempts=1, threshold=2, reset=timedelta(seconds=30))
        await self._trip(fake, p, 2)
        clock.advance(timedelta(seconds=30))
        assert p.breaker.state is CircuitState.HALF_OPEN
        fake.set_outage(False)  # the trial call will succeed
        await p.get_quote("DEMO-GEQ", AssetKind.ETF)
        assert state_of(p) is CircuitState.CLOSED

    async def test_half_open_trial_failure_reopens_it(self) -> None:
        fake, p, clock, _ = make(attempts=1, threshold=2, reset=timedelta(seconds=30))
        await self._trip(fake, p, 2)
        clock.advance(timedelta(seconds=30))
        with pytest.raises(ProviderUnavailable):
            await p.get_quote("DEMO-GEQ", AssetKind.ETF)
        assert p.breaker.state is CircuitState.OPEN
        clock.advance(timedelta(seconds=29))
        assert p.breaker.state is CircuitState.OPEN

    async def test_only_one_trial_call_runs_at_a_time(self) -> None:
        clock = Clock()
        b = CircuitBreaker(failure_threshold=1, reset_timeout=timedelta(seconds=1), clock=clock)
        b.record_failure()
        clock.advance(timedelta(seconds=1))
        b.before_call()  # the trial
        with pytest.raises(CircuitOpen):
            b.before_call()

    async def test_request_errors_do_not_count_against_health(self) -> None:
        _fake, p, _, _ = make(attempts=1, threshold=2)
        for _ in range(5):
            with pytest.raises(SymbolNotFound):
                await p.get_quote("NOPE-NOT-REAL", AssetKind.ETF)
        assert p.breaker.state is CircuitState.CLOSED

    async def test_a_trial_that_hits_a_request_error_frees_the_slot(self) -> None:
        fake, p, clock, _ = make(attempts=1, threshold=1, reset=timedelta(seconds=1))
        await self._trip(fake, p, 1)
        clock.advance(timedelta(seconds=1))
        fake.set_outage(False)
        with pytest.raises(SymbolNotFound):
            await p.get_quote("NOPE-NOT-REAL", AssetKind.ETF)
        # The slot is free: another trial may run (and now succeeds).
        assert (await p.get_quote("DEMO-GEQ", AssetKind.ETF)).symbol == "DEMO-GEQ"

    def test_invalid_threshold_is_refused(self) -> None:
        with pytest.raises(ValueError, match="failure_threshold"):
            CircuitBreaker(failure_threshold=0)


class TestFallbackChain:
    def chain(self) -> tuple[FakeProvider, FakeProvider, FallbackChain]:
        a = FakeProvider(name="a")
        b = FakeProvider(name="b")
        return a, b, FallbackChain([a, b])

    async def test_the_first_provider_answers_when_it_can(self) -> None:
        _a, b, chain = self.chain()
        q = await chain.get_quote("DEMO-GEQ", AssetKind.ETF)
        assert q.provenance.provider == "a"
        assert b.calls == []

    async def test_fails_over_when_the_first_is_down(self) -> None:
        a, _b, chain = self.chain()
        a.set_outage(True)
        q = await chain.get_quote("DEMO-GEQ", AssetKind.ETF)
        assert q.provenance.provider == "b"

    async def test_fails_over_when_the_first_circuit_is_open(self) -> None:
        clock = Clock()
        a = ResilientProvider(
            FakeProvider(name="a", clock=clock),
            RetryPolicy(max_attempts=1),
            CircuitBreaker(failure_threshold=1, clock=clock),
        )
        a.breaker.record_failure()
        b = FakeProvider(name="b", clock=clock)
        q = await FallbackChain([a, b]).get_quote("DEMO-GEQ", AssetKind.ETF)
        assert q.provenance.provider == "b"

    async def test_when_all_fail_it_says_so_and_keeps_each_error(self) -> None:
        a, b, chain = self.chain()
        a.set_outage(True)
        b.set_outage(True)
        with pytest.raises(AllProvidersFailed) as caught:
            await chain.get_quote("DEMO-GEQ", AssetKind.ETF)
        assert len(caught.value.errors) == 2

    async def test_an_unknown_symbol_is_not_hidden_by_failover(self) -> None:
        _a, b, chain = self.chain()
        with pytest.raises(SymbolNotFound):
            await chain.get_quote("NOPE-NOT-REAL", AssetKind.ETF)
        assert b.calls == []

    async def test_a_provider_that_does_not_serve_the_kind_is_skipped(self) -> None:
        crypto_only = FakeProvider(name="c", kinds=frozenset({AssetKind.CRYPTO}))
        etf = FakeProvider(name="e", kinds=frozenset({AssetKind.ETF}))
        q = await FallbackChain([crypto_only, etf]).get_quote("DEMO-GEQ", AssetKind.ETF)
        assert q.provenance.provider == "e"

    async def test_unsupported_by_every_provider_is_unsupported(self) -> None:
        only = FakeProvider(kinds=frozenset({AssetKind.CRYPTO}))
        with pytest.raises(UnsupportedKind):
            await FallbackChain([only]).get_quote("DEMO-GEQ", AssetKind.ETF)

    async def test_name_and_kinds_combine_the_providers(self) -> None:
        a = FakeProvider(name="a", kinds=frozenset({AssetKind.ETF}))
        b = FakeProvider(name="b", kinds=frozenset({AssetKind.CRYPTO}))
        chain = FallbackChain([a, b])
        assert chain.name == "a+b"
        assert chain.supported_kinds == frozenset({AssetKind.ETF, AssetKind.CRYPTO})

    async def test_history_and_fx_fail_over_too(self) -> None:
        from datetime import date

        a, _b, chain = self.chain()
        a.set_outage(True)
        assert (await chain.get_fx_rate("USD", "AED")).provenance.provider == "b"
        pts = await chain.get_history(
            "DEMO-GEQ", AssetKind.ETF, date(2026, 10, 5), date(2026, 10, 9)
        )
        assert pts[0].provenance.provider == "b"

    def test_an_empty_chain_is_refused(self) -> None:
        with pytest.raises(ValueError, match="at least one"):
            FallbackChain([])
