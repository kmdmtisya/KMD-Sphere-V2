"""The fake provider: the contract, and its scripted failures (P08-T02.4)."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from app.modules.market_data.providers.base import MarketDataProvider
from app.modules.market_data.providers.errors import (
    ProviderUnavailable,
    RateLimited,
    SymbolNotFound,
    UnsupportedKind,
)
from app.modules.market_data.providers.fake import FakeProvider
from app.modules.market_data.providers.models import AssetKind
from tests.market_data.provider_contract import ProviderContract

NOW = datetime(2026, 10, 12, 12, tzinfo=UTC)


class TestFakeProviderContract(ProviderContract):
    kind = AssetKind.ETF
    symbol = "DEMO-GEQ"
    history_start = date(2026, 9, 1)
    history_end = date(2026, 9, 30)
    fx_pair = ("USD", "AED")

    def make_provider(self) -> MarketDataProvider:
        return FakeProvider(kinds=frozenset({AssetKind.ETF, AssetKind.EQUITY}))


def fake() -> FakeProvider:
    return FakeProvider(clock=lambda: NOW)


async def test_outage_fails_every_call_until_cleared() -> None:
    p = fake()
    p.set_outage(True)
    with pytest.raises(ProviderUnavailable):
        await p.get_quote("DEMO-GEQ", AssetKind.ETF)
    with pytest.raises(ProviderUnavailable):
        await p.get_fx_rate("USD", "AED")
    p.set_outage(False)
    assert (await p.get_quote("DEMO-GEQ", AssetKind.ETF)).price == Decimal("104.20")


async def test_staleness_moves_as_of_back_but_keeps_retrieval_time() -> None:
    p = fake()
    p.set_stale_by(timedelta(days=3))
    q = await p.get_quote("DEMO-GEQ", AssetKind.ETF)
    assert q.provenance.retrieved_at == NOW
    assert q.provenance.as_of == NOW - timedelta(days=3)
    assert q.provenance.is_stale(NOW, timedelta(days=1))


async def test_fail_next_fails_exactly_that_many_calls() -> None:
    p = fake()
    p.fail_next(2)
    for _ in range(2):
        with pytest.raises(ProviderUnavailable):
            await p.get_quote("DEMO-GEQ", AssetKind.ETF)
    assert (await p.get_quote("DEMO-GEQ", AssetKind.ETF)).symbol == "DEMO-GEQ"


async def test_rate_limit_carries_retry_after() -> None:
    p = fake()
    p.rate_limit_next(1, retry_after=timedelta(seconds=7))
    with pytest.raises(RateLimited) as caught:
        await p.get_quote("DEMO-GEQ", AssetKind.ETF)
    assert caught.value.retry_after == timedelta(seconds=7)


async def test_calls_are_recorded() -> None:
    p = fake()
    await p.get_quote("DEMO-GEQ", AssetKind.ETF)
    await p.get_fx_rate("USD", "AED")
    assert p.calls == ["quote:DEMO-GEQ", "fx:USDAED"]


async def test_set_price_changes_the_quote() -> None:
    p = fake()
    p.set_price("DEMO-GEQ", Decimal("110"))
    assert (await p.get_quote("DEMO-GEQ", AssetKind.ETF)).price == Decimal("110")


async def test_wrong_kind_for_a_symbol_is_not_found() -> None:
    with pytest.raises(SymbolNotFound):
        await fake().get_quote("DEMO-GEQ", AssetKind.CRYPTO)


async def test_a_kind_the_provider_does_not_serve_is_unsupported() -> None:
    p = FakeProvider(kinds=frozenset({AssetKind.CRYPTO}))
    with pytest.raises(UnsupportedKind):
        await p.get_quote("DEMO-GEQ", AssetKind.ETF)


async def test_history_is_reproducible_and_skips_weekends_except_crypto() -> None:
    p = fake()
    a = await p.get_history("DEMO-GEQ", AssetKind.ETF, date(2026, 9, 28), date(2026, 10, 4))
    b = await p.get_history("DEMO-GEQ", AssetKind.ETF, date(2026, 9, 28), date(2026, 10, 4))
    assert [(x.day, x.close) for x in a] == [(x.day, x.close) for x in b]
    assert all(x.day.weekday() < 5 for x in a)
    assert len(a) == 5
    crypto = await p.get_history("DEMO-BTC", AssetKind.CRYPTO, date(2026, 9, 28), date(2026, 10, 4))
    assert len(crypto) == 7


async def test_history_never_reaches_into_the_future() -> None:
    pts = await fake().get_history("DEMO-GEQ", AssetKind.ETF, date(2026, 10, 9), date(2026, 10, 30))
    assert max(pt.day for pt in pts) <= NOW.date()


async def test_fx_opposite_direction_is_the_inverse() -> None:
    p = fake()
    direct = await p.get_fx_rate("USD", "AED")
    inverse = await p.get_fx_rate("AED", "USD")
    assert abs(direct.rate * inverse.rate - 1) < Decimal("1e-20")


async def test_unknown_fx_pair_raises() -> None:
    with pytest.raises(SymbolNotFound):
        await fake().get_fx_rate("USD", "JPY")
