"""Provider outages end to end through retry, circuit breaker and failover, with the fake provider
(P08-T08.1). Nothing here sleeps: the clock and the sleep are injected."""

from datetime import UTC, datetime, timedelta

import pytest

from app.modules.market_data.providers.errors import (
    AllProvidersFailed,
    CircuitOpen,
    ProviderUnavailable,
    RateLimited,
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


def state_of(p: ResilientProvider) -> CircuitState:
    return p.breaker.state  # read fresh, so type narrowing does not assume it is unchanged


async def no_sleep(_: float) -> None:
    return None


def resilient(fake: FakeProvider, clock: Clock, threshold: int = 3) -> ResilientProvider:
    return ResilientProvider(
        fake,
        retry=RetryPolicy(max_attempts=2),
        breaker=CircuitBreaker(failure_threshold=threshold, clock=clock),
        sleep=no_sleep,
    )


async def test_a_primary_outage_is_answered_by_the_secondary_and_says_so() -> None:
    clock = Clock()
    primary, secondary = FakeProvider("primary", clock), FakeProvider("secondary", clock)
    primary.set_outage(True)
    chain = FallbackChain([resilient(primary, clock), resilient(secondary, clock)])
    quote = await chain.get_quote("DEMO-GEQ", AssetKind.ETF)
    assert quote.price > 0
    assert quote.provenance.provider == "secondary", "the value must not be credited to the primary"
    assert quote.provenance.retrieved_at == T0


async def test_when_every_provider_is_down_the_failure_is_explicit_not_a_value() -> None:
    clock = Clock()
    a, b = FakeProvider("a", clock), FakeProvider("b", clock)
    a.set_outage(True)
    b.set_outage(True)
    chain = FallbackChain([resilient(a, clock), resilient(b, clock)])
    with pytest.raises(AllProvidersFailed) as failed:
        await chain.get_quote("DEMO-GEQ", AssetKind.ETF)
    assert len(failed.value.errors) == 2
    assert isinstance(failed.value, ProviderUnavailable)


async def test_the_circuit_opens_then_stops_calling_a_failing_provider() -> None:
    clock = Clock()
    fake = FakeProvider("flaky", clock)
    fake.set_outage(True)
    provider = resilient(fake, clock, threshold=2)
    for _ in range(2):
        with pytest.raises(ProviderUnavailable):
            await provider.get_quote("DEMO-GEQ", AssetKind.ETF)
    assert state_of(provider) is CircuitState.OPEN
    calls = len(fake.calls)
    with pytest.raises(CircuitOpen):
        await provider.get_quote("DEMO-GEQ", AssetKind.ETF)
    assert len(fake.calls) == calls, "an open circuit must not reach the provider"


async def test_an_open_circuit_fails_over_without_touching_the_broken_provider() -> None:
    clock = Clock()
    broken, healthy = FakeProvider("broken", clock), FakeProvider("healthy", clock)
    broken.set_outage(True)
    chain = FallbackChain([resilient(broken, clock, threshold=1), resilient(healthy, clock)])
    await chain.get_quote("DEMO-GEQ", AssetKind.ETF)  # trips the circuit
    before = len(broken.calls)
    quote = await chain.get_quote("DEMO-GEQ", AssetKind.ETF)
    assert quote.provenance.provider == "healthy"
    assert len(broken.calls) == before


async def test_the_provider_is_tried_again_after_the_cool_down_and_recovers() -> None:
    clock = Clock()
    fake = FakeProvider("flaky", clock)
    provider = resilient(fake, clock, threshold=1)
    fake.set_outage(True)
    with pytest.raises(ProviderUnavailable):
        await provider.get_quote("DEMO-GEQ", AssetKind.ETF)
    assert state_of(provider) is CircuitState.OPEN
    fake.set_outage(False)
    clock.now += timedelta(seconds=31)
    assert state_of(provider) is CircuitState.HALF_OPEN
    quote = await provider.get_quote("DEMO-GEQ", AssetKind.ETF)
    assert quote.provenance.provider == "flaky"
    assert state_of(provider) is CircuitState.CLOSED


async def test_a_short_blip_is_absorbed_by_retry() -> None:
    clock = Clock()
    fake = FakeProvider("blip", clock)
    fake.fail_next(1)
    provider = resilient(fake, clock)
    quote = await provider.get_quote("DEMO-GEQ", AssetKind.ETF)
    assert quote.price > 0
    assert state_of(provider) is CircuitState.CLOSED


async def test_rate_limiting_is_retried_then_failed_over() -> None:
    clock = Clock()
    limited, other = FakeProvider("limited", clock), FakeProvider("other", clock)
    limited.rate_limit_next(10, retry_after=timedelta(seconds=1))
    chain = FallbackChain([resilient(limited, clock), resilient(other, clock)])
    quote = await chain.get_quote("DEMO-GEQ", AssetKind.ETF)
    assert quote.provenance.provider == "other"
    with pytest.raises(RateLimited):
        await resilient(limited, clock).get_quote("DEMO-GEQ", AssetKind.ETF)
