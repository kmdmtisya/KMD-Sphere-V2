"""Price and FX ingestion with the fake provider against a real database (P08-T05): provenance on
every row, idempotent ingestion and backfill, isolation of failures, currency safety, staleness.
Needs the migrated test database."""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.modules.assets.models import Asset, AssetClass
from app.modules.identity.models import User
from app.modules.market_data.freshness import FRESH_FOR, is_stale, kind_for_asset_class
from app.modules.market_data.ingestion import (
    backfill_fx,
    backfill_prices,
    fx_pairs_needed,
    ingest_fx,
    ingest_quote,
    ingest_quotes,
    latest_price,
    market_assets,
)
from app.modules.market_data.models import FxRate, MarketPrice
from app.modules.market_data.providers.fake import FakeProvider
from app.modules.market_data.providers.models import AssetKind
from app.modules.portfolio.models import Portfolio
from tests.db_fixtures import migrated_settings  # noqa: F401

pytestmark = pytest.mark.integration

NOW = datetime(2026, 10, 12, 12, tzinfo=UTC)


def provider(**kw: object) -> FakeProvider:
    return FakeProvider(clock=lambda: NOW, **kw)  # type: ignore[arg-type]


@pytest.fixture
async def sessions(
    migrated_settings: Settings,  # noqa: F811
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(migrated_settings.sqlalchemy_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        await s.execute(text("DELETE FROM market_prices"))
        await s.execute(text("DELETE FROM fx_rates"))
        await s.execute(text("DELETE FROM portfolios"))
        await s.execute(
            text("DELETE FROM assets WHERE symbol LIKE 'TST-%' OR symbol LIKE 'DEMO-%'")
        )
        await s.commit()
    try:
        yield factory
    finally:
        await engine.dispose()


async def make_asset(
    s: AsyncSession, symbol: str | None, class_code: str, currency: str = "USD", **kw: object
) -> Asset:
    cls = (await s.execute(select(AssetClass).where(AssetClass.code == class_code))).scalar_one()
    asset = Asset(
        asset_class_id=cls.id,
        symbol=symbol,
        name=f"Test {symbol}",
        currency=currency,
        **kw,
    )
    s.add(asset)
    await s.commit()
    return asset


async def count(s: AsyncSession, model: type) -> int:
    return (await s.execute(select(func.count()).select_from(model))).scalar_one()


class TestFreshness:
    def test_classes_map_to_provider_kinds(self) -> None:
        assert kind_for_asset_class("stock") is AssetKind.EQUITY
        assert kind_for_asset_class("etf") is AssetKind.ETF
        assert kind_for_asset_class("cryptocurrency") is AssetKind.CRYPTO
        assert kind_for_asset_class("real_estate") is None
        assert kind_for_asset_class("bond") is None, "no bond provider yet"

    def test_a_price_is_stale_only_after_its_window(self) -> None:
        window = FRESH_FOR[AssetKind.ETF]
        assert not is_stale(NOW - window, NOW, AssetKind.ETF)
        assert is_stale(NOW - window - timedelta(seconds=1), NOW, AssetKind.ETF)

    def test_crypto_goes_stale_much_sooner_than_listed_assets(self) -> None:
        assert FRESH_FOR[AssetKind.CRYPTO] < FRESH_FOR[AssetKind.ETF]
        assert is_stale(NOW - timedelta(hours=7), NOW, AssetKind.CRYPTO)
        assert not is_stale(NOW - timedelta(hours=7), NOW, AssetKind.ETF)


class TestQuotes:
    async def test_every_stored_price_has_provider_as_of_and_ingestion_timestamps(
        self, sessions: async_sessionmaker[AsyncSession]
    ) -> None:
        async with sessions() as s:
            await make_asset(s, "DEMO-GEQ", "etf")
            result = await ingest_quotes(s, {AssetKind.ETF: provider()})
            assert (result.stored, result.duplicates, result.failures) == (1, 0, [])
            row = (await s.execute(select(MarketPrice))).scalar_one()
        assert row.price == Decimal("104.200000000000")
        assert row.currency == "USD"
        assert row.price_type == "quote"
        assert row.provider == "fake"
        assert row.as_of == NOW
        assert row.retrieved_at == NOW
        assert row.ingested_at is not None

    async def test_running_it_again_does_not_duplicate(
        self, sessions: async_sessionmaker[AsyncSession]
    ) -> None:
        async with sessions() as s:
            await make_asset(s, "DEMO-GEQ", "etf")
            first = await ingest_quotes(s, {AssetKind.ETF: provider()})
            second = await ingest_quotes(s, {AssetKind.ETF: provider()})
            assert (first.stored, second.stored, second.duplicates) == (1, 0, 1)
            assert await count(s, MarketPrice) == 1

    async def test_a_new_provider_timestamp_is_a_new_row(
        self, sessions: async_sessionmaker[AsyncSession]
    ) -> None:
        later = FakeProvider(clock=lambda: NOW + timedelta(hours=1))
        async with sessions() as s:
            await make_asset(s, "DEMO-GEQ", "etf")
            await ingest_quotes(s, {AssetKind.ETF: provider()})
            await ingest_quotes(s, {AssetKind.ETF: later})
            assert await count(s, MarketPrice) == 2

    async def test_only_global_active_market_valued_assets_with_a_symbol_and_provider(
        self, sessions: async_sessionmaker[AsyncSession]
    ) -> None:
        async with sessions() as s:
            await make_asset(s, "DEMO-GEQ", "etf")
            await make_asset(s, "DEMO-TEC", "etf", is_active=False)
            await make_asset(s, "TST-CASH", "cash")  # manual valuation
            await make_asset(s, "TST-BOND", "bond")  # market-valued but no provider kind
            await make_asset(s, None, "etf")  # no symbol: nothing to ask a provider for
            found = [a.symbol for a, _ in await market_assets(s)]
        assert found == ["DEMO-GEQ"]

    async def test_a_failing_asset_does_not_stop_the_others(
        self, sessions: async_sessionmaker[AsyncSession]
    ) -> None:
        async with sessions() as s:
            await make_asset(s, "DEMO-GEQ", "etf")
            await make_asset(s, "TST-UNKNOWN", "etf")  # the provider does not know it
            await make_asset(s, "DEMO-BTC", "cryptocurrency")
            result = await ingest_quotes(s, {kind: provider() for kind in AssetKind})
            assert result.stored == 2
            assert [(f.subject, f.error_type) for f in result.failures] == [
                ("TST-UNKNOWN", "SymbolNotFound")
            ]
            assert result.attempted_all_and_failed is False

    async def test_an_outage_stores_nothing_and_says_all_failed(
        self, sessions: async_sessionmaker[AsyncSession]
    ) -> None:
        down = provider()
        down.set_outage(True)
        async with sessions() as s:
            await make_asset(s, "DEMO-GEQ", "etf")
            await make_asset(s, "DEMO-TEC", "etf")
            result = await ingest_quotes(s, {AssetKind.ETF: down})
            assert result.stored == 0
            assert len(result.failures) == 2
            assert result.attempted_all_and_failed is True
            assert await count(s, MarketPrice) == 0

    async def test_a_kind_without_a_provider_is_skipped_quietly(
        self, sessions: async_sessionmaker[AsyncSession]
    ) -> None:
        async with sessions() as s:
            await make_asset(s, "DEMO-GEQ", "etf")
            result = await ingest_quotes(s, {})
            assert (result.stored, result.failures) == (0, [])

    async def test_a_price_in_another_currency_is_refused_not_converted(
        self, sessions: async_sessionmaker[AsyncSession]
    ) -> None:
        async with sessions() as s:
            asset = await make_asset(s, "DEMO-KEN", "stock", currency="USD")  # fake prices in KES
            result = await ingest_quote(s, provider(), asset, AssetKind.EQUITY)
            assert result.stored == 0
            assert result.failures[0].error_type == "ProviderDataError"
            assert "KES" in result.failures[0].message
            assert await count(s, MarketPrice) == 0

    async def test_the_table_itself_rejects_bad_rows(
        self, sessions: async_sessionmaker[AsyncSession]
    ) -> None:
        async with sessions() as s:
            asset_id = (await make_asset(s, "DEMO-GEQ", "etf")).id
            bad: list[dict[str, object]] = [
                {"price": Decimal(0)},
                {"currency": "usd"},
                {"price_type": "bid"},
                {"retrieved_at": NOW - timedelta(days=1)},
            ]
            for override in bad:
                row = {
                    "asset_id": asset_id,
                    "price": Decimal("1"),
                    "currency": "USD",
                    "price_type": "quote",
                    "provider": "x",
                    "as_of": NOW,
                    "retrieved_at": NOW,
                    **override,
                }
                s.add(MarketPrice(**row))
                with pytest.raises(IntegrityError):
                    await s.commit()
                await s.rollback()


class TestBackfill:
    async def test_it_stores_daily_closes_with_provenance(
        self, sessions: async_sessionmaker[AsyncSession]
    ) -> None:
        async with sessions() as s:
            asset = await make_asset(s, "DEMO-GEQ", "etf")
            result = await backfill_prices(
                s, provider(), asset, AssetKind.ETF, date(2026, 10, 5), date(2026, 10, 9)
            )
            assert (result.stored, result.duplicates) == (5, 0)
            rows = (
                (await s.execute(select(MarketPrice).order_by(MarketPrice.as_of))).scalars().all()
            )
        assert {r.price_type for r in rows} == {"close"}
        assert all(r.provider == "fake" and r.retrieved_at >= r.as_of for r in rows)

    async def test_rerunning_and_overlapping_ranges_do_not_duplicate(
        self, sessions: async_sessionmaker[AsyncSession]
    ) -> None:
        async with sessions() as s:
            asset = await make_asset(s, "DEMO-GEQ", "etf")
            p = provider()
            await backfill_prices(s, p, asset, AssetKind.ETF, date(2026, 10, 5), date(2026, 10, 9))
            again = await backfill_prices(
                s, p, asset, AssetKind.ETF, date(2026, 10, 5), date(2026, 10, 9)
            )
            wider = await backfill_prices(
                s, p, asset, AssetKind.ETF, date(2026, 10, 1), date(2026, 10, 12)
            )
            assert (again.stored, again.duplicates) == (0, 5)
            # 1 and 2 October and 12 October are new; the five days already stored are not.
            assert (wider.stored, wider.duplicates) == (3, 5)
            assert await count(s, MarketPrice) == 8

    async def test_a_provider_failure_is_returned_not_raised(
        self, sessions: async_sessionmaker[AsyncSession]
    ) -> None:
        p = provider()
        p.set_outage(True)
        async with sessions() as s:
            asset = await make_asset(s, "DEMO-GEQ", "etf")
            result = await backfill_prices(
                s, p, asset, AssetKind.ETF, date(2026, 10, 5), date(2026, 10, 9)
            )
            assert result.stored == 0
            assert result.failures[0].error_type == "ProviderUnavailable"

    async def test_a_currency_mismatch_in_history_stores_nothing(
        self, sessions: async_sessionmaker[AsyncSession]
    ) -> None:
        async with sessions() as s:
            asset = await make_asset(s, "DEMO-KEN", "stock", currency="USD")
            result = await backfill_prices(
                s, provider(), asset, AssetKind.EQUITY, date(2026, 10, 5), date(2026, 10, 9)
            )
            assert result.stored == 0
            assert await count(s, MarketPrice) == 0


class TestFx:
    async def test_rates_are_stored_with_provenance_and_not_duplicated(
        self, sessions: async_sessionmaker[AsyncSession]
    ) -> None:
        async with sessions() as s:
            p = provider()
            first = await ingest_fx(s, p, [("USD", "AED"), ("EUR", "USD")])
            second = await ingest_fx(s, p, [("USD", "AED"), ("EUR", "USD")])
            assert (first.stored, second.stored, second.duplicates) == (2, 0, 2)
            row = (
                await s.execute(select(FxRate).where(FxRate.quote_currency == "AED"))
            ).scalar_one()
        assert row.rate == Decimal("3.672500000000")
        assert (row.provider, row.rate_timestamp, row.retrieved_at) == ("fake", NOW, NOW)

    async def test_an_unknown_pair_fails_alone(
        self, sessions: async_sessionmaker[AsyncSession]
    ) -> None:
        async with sessions() as s:
            result = await ingest_fx(s, provider(), [("USD", "JPY"), ("USD", "AED")])
            assert result.stored == 1
            assert [f.subject for f in result.failures] == ["USD/JPY"]

    async def test_an_outage_marks_everything_failed(
        self, sessions: async_sessionmaker[AsyncSession]
    ) -> None:
        down = provider()
        down.set_outage(True)
        async with sessions() as s:
            result = await ingest_fx(s, down, [("USD", "AED")])
            assert result.attempted_all_and_failed is True

    async def test_fx_backfill_is_idempotent(
        self, sessions: async_sessionmaker[AsyncSession]
    ) -> None:
        async with sessions() as s:
            p = provider()
            a = await backfill_fx(s, p, "USD", "AED", date(2026, 10, 5), date(2026, 10, 9))
            b = await backfill_fx(s, p, "USD", "AED", date(2026, 10, 5), date(2026, 10, 9))
            assert (a.stored, b.stored, b.duplicates) == (5, 0, 5)
            assert await count(s, FxRate) == 5

    async def test_fx_backfill_failure_is_returned(
        self, sessions: async_sessionmaker[AsyncSession]
    ) -> None:
        down = provider()
        down.set_outage(True)
        async with sessions() as s:
            result = await backfill_fx(s, down, "USD", "AED", date(2026, 10, 5), date(2026, 10, 9))
            assert result.failures[0].error_type == "ProviderUnavailable"

    async def test_the_pairs_needed_come_from_asset_and_portfolio_currencies(
        self, sessions: async_sessionmaker[AsyncSession]
    ) -> None:
        async with sessions() as s:
            await make_asset(s, "DEMO-GEQ", "etf", currency="USD")
            await make_asset(s, "DEMO-KEN", "stock", currency="KES")
            user = User(issuer="https://issuer.test", subject=str(uuid.uuid4()))
            s.add(user)
            await s.flush()
            s.add(Portfolio(user_id=user.id, name="p1", base_currency="USD"))
            s.add(Portfolio(user_id=user.id, name="p2", base_currency="EUR"))
            s.add(Portfolio(user_id=user.id, name="old", base_currency="GBP", archived_at=NOW))
            await s.commit()
            pairs = await fx_pairs_needed(s)
        assert pairs == [
            ("EUR", "USD"),
            ("KES", "EUR"),
            ("KES", "USD"),
            ("USD", "EUR"),
        ]


class TestLatestPrice:
    async def test_none_when_nothing_is_stored(
        self, sessions: async_sessionmaker[AsyncSession]
    ) -> None:
        async with sessions() as s:
            asset = await make_asset(s, "DEMO-GEQ", "etf")
            assert await latest_price(s, asset.id, AssetKind.ETF, NOW) is None

    async def test_the_newest_price_is_returned_and_flagged_by_age(
        self, sessions: async_sessionmaker[AsyncSession]
    ) -> None:
        async with sessions() as s:
            asset = await make_asset(s, "DEMO-GEQ", "etf")
            old = FakeProvider(clock=lambda: NOW - timedelta(days=10))
            old.set_price("DEMO-GEQ", Decimal("90"))
            await ingest_quote(s, old, asset, AssetKind.ETF)
            await ingest_quote(s, provider(), asset, AssetKind.ETF)

            fresh = await latest_price(s, asset.id, AssetKind.ETF, NOW)
            assert fresh is not None
            assert fresh.price == Decimal("104.2")
            assert fresh.stale is False
            assert fresh.provider == "fake"

            # Ten days later nothing newer exists: the same price, now flagged stale.
            later = await latest_price(s, asset.id, AssetKind.ETF, NOW + timedelta(days=10))
            assert later is not None
            assert later.price == Decimal("104.2")
            assert later.stale is True

    async def test_a_price_from_the_future_is_not_used(
        self, sessions: async_sessionmaker[AsyncSession]
    ) -> None:
        async with sessions() as s:
            asset = await make_asset(s, "DEMO-GEQ", "etf")
            await ingest_quote(s, provider(), asset, AssetKind.ETF)
            assert await latest_price(s, asset.id, AssetKind.ETF, NOW - timedelta(hours=1)) is None
