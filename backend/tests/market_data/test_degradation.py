"""Outages, stale data and caching against a real database and the API (P08-T08): an outage or a
stale provider never produces an error or a silently wrong figure. Prices stay as they were,
flagged stale once past their window; the response cache bounds how long a figure can lag a new
price. The fake provider scripts every failure."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import asyncpg
import httpx
import pytest
from fastapi import FastAPI
from redis.exceptions import RedisError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.cache import MemoryCacheStore
from app.modules.market_data.ingestion import ingest_quotes, latest_price
from app.modules.market_data.models import MarketPrice
from app.modules.market_data.providers.fake import FakeProvider
from app.modules.market_data.providers.models import AssetKind
from tests.authz_harness import TwoUsers, two_users  # noqa: F401
from tests.db_fixtures import migrated_settings  # noqa: F401
from tests.market_data.test_ingestion import make_asset, sessions  # noqa: F401
from tests.test_valuation_sources import (  # noqa: F401
    app,
    db,
    holding,
    http,
    listed,
    m,
    position,
    put_price,
    summary,
)

NOW = datetime(2026, 10, 12, 12, tzinfo=UTC)
REAL_NOW = datetime.now(UTC).replace(microsecond=0)


def fake(at: datetime = NOW, stale_by: timedelta = timedelta(0)) -> FakeProvider:
    provider = FakeProvider(clock=lambda: at)
    provider.set_stale_by(stale_by)
    return provider


async def rows(s: AsyncSession) -> int:
    return int((await s.execute(select(func.count()).select_from(MarketPrice))).scalar_one())


# ------------------------------------------------------------------------- outage (T08.1)
@pytest.mark.integration
class TestOutageKeepsWhatWeHave:
    async def test_an_outage_stores_nothing_and_leaves_the_last_price_flagged_by_age(
        self,
        sessions: async_sessionmaker[AsyncSession],  # noqa: F811
    ) -> None:
        async with sessions() as s:
            asset = await make_asset(s, "DEMO-GEQ", "etf")
            await ingest_quotes(s, {AssetKind.ETF: fake()})
            down = fake(NOW + timedelta(hours=1))
            down.set_outage(True)
            result = await ingest_quotes(s, {AssetKind.ETF: down})
            assert result.attempted_all_and_failed
            assert result.stored == 0
            assert await rows(s) == 1, "an outage must not create or change prices"
            fresh = await latest_price(s, asset.id, AssetKind.ETF, NOW + timedelta(hours=2))
            old = await latest_price(s, asset.id, AssetKind.ETF, NOW + timedelta(days=10))
        assert fresh is not None and old is not None
        assert fresh.price == old.price == Decimal("104.2")
        assert (fresh.stale, old.stale) == (False, True)

    async def test_the_failure_names_the_kind_of_error_not_the_payload(
        self,
        sessions: async_sessionmaker[AsyncSession],  # noqa: F811
    ) -> None:
        async with sessions() as s:
            await make_asset(s, "DEMO-GEQ", "etf")
            down = fake()
            down.set_outage(True)
            result = await ingest_quotes(s, {AssetKind.ETF: down})
        (failure,) = result.failures
        assert failure.error_type == "ProviderUnavailable"

    async def test_one_failing_instrument_does_not_stop_the_others(
        self,
        sessions: async_sessionmaker[AsyncSession],  # noqa: F811
    ) -> None:
        async with sessions() as s:
            await make_asset(s, "DEMO-GEQ", "etf")
            await make_asset(s, "DEMO-TEC", "etf")
            flaky = fake()
            flaky.fail_next(1)
            result = await ingest_quotes(s, {AssetKind.ETF: flaky})
            assert (result.stored, len(result.failures)) == (1, 1)
            assert not result.attempted_all_and_failed

    async def test_after_the_outage_the_next_run_stores_a_fresh_price(
        self,
        sessions: async_sessionmaker[AsyncSession],  # noqa: F811
    ) -> None:
        async with sessions() as s:
            asset = await make_asset(s, "DEMO-GEQ", "etf")
            await ingest_quotes(s, {AssetKind.ETF: fake()})
            down = fake(NOW + timedelta(days=5))
            down.set_outage(True)
            await ingest_quotes(s, {AssetKind.ETF: down})
            later = NOW + timedelta(days=5, hours=1)
            before = await latest_price(s, asset.id, AssetKind.ETF, later)
            await ingest_quotes(s, {AssetKind.ETF: fake(later)})
            after = await latest_price(s, asset.id, AssetKind.ETF, later)
        assert before is not None and before.stale
        assert after is not None and not after.stale and after.as_of == later


# --------------------------------------------------------------------------- stale (T08.2)
@pytest.mark.integration
class TestStaleProviderData:
    async def test_stale_data_is_stored_with_its_true_age_and_flagged(
        self,
        sessions: async_sessionmaker[AsyncSession],  # noqa: F811
    ) -> None:
        async with sessions() as s:
            asset = await make_asset(s, "DEMO-GEQ", "etf")
            await ingest_quotes(s, {AssetKind.ETF: fake(stale_by=timedelta(days=10))})
            price = await latest_price(s, asset.id, AssetKind.ETF, NOW)
            row = (await s.execute(select(MarketPrice))).scalar_one()
        assert price is not None and price.stale
        assert row.as_of == NOW - timedelta(days=10), "as_of is the provider time, not ours"
        assert row.retrieved_at == NOW

    async def test_stale_data_never_replaces_a_fresher_price(
        self,
        sessions: async_sessionmaker[AsyncSession],  # noqa: F811
    ) -> None:
        async with sessions() as s:
            asset = await make_asset(s, "DEMO-GEQ", "etf")
            fresh = fake()
            fresh.set_price("DEMO-GEQ", Decimal("120"))
            await ingest_quotes(s, {AssetKind.ETF: fresh})
            later = fake(NOW + timedelta(hours=1), timedelta(days=9))
            await ingest_quotes(s, {AssetKind.ETF: later})
            price = await latest_price(s, asset.id, AssetKind.ETF, NOW + timedelta(hours=1))
        assert price is not None
        assert price.price == Decimal("120") and not price.stale

    async def test_the_window_is_per_kind(
        self,
        sessions: async_sessionmaker[AsyncSession],  # noqa: F811
    ) -> None:
        async with sessions() as s:
            etf = await make_asset(s, "DEMO-GEQ", "etf")
            crypto = await make_asset(s, "DEMO-BTC", "cryptocurrency")
            both = fake(stale_by=timedelta(hours=7))
            await ingest_quotes(s, {AssetKind.ETF: both, AssetKind.CRYPTO: both})
            listed_price = await latest_price(s, etf.id, AssetKind.ETF, NOW)
            coin_price = await latest_price(s, crypto.id, AssetKind.CRYPTO, NOW)
        assert listed_price is not None and coin_price is not None
        assert (listed_price.stale, coin_price.stale) == (False, True)


@pytest.mark.integration
@pytest.mark.security
class TestApiDegrades:
    async def test_an_outage_leaves_the_holding_valued_at_the_last_price_flagged_stale(
        self,
        app: FastAPI,  # noqa: F811
        http: httpx.AsyncClient,  # noqa: F811
        db: asyncpg.Connection,  # noqa: F811
        two_users: TwoUsers,  # noqa: F811
    ) -> None:
        h = two_users.alice.headers
        asset = await listed(db)
        pid = await position(http, h, asset)
        await put_price(db, asset, "90", REAL_NOW - timedelta(days=9))
        down = fake(REAL_NOW)
        down.set_outage(True)
        async with app.state.db.session_factory() as s:
            result = await ingest_quotes(s, {AssetKind.ETF: down})
        assert result.stored == 0
        row = await holding(http, h, pid)  # a 200, not an error
        assert row["value"] == m("900.00")
        assert row["value_source"] == "price"
        assert row["value_stale"] is True
        s_ = await summary(http, h, pid)
        assert [a["id"] for a in s_["freshness"]["stale_prices"]] == [asset]

    async def test_no_price_at_all_is_unpriced_not_zero_or_invented(
        self,
        http: httpx.AsyncClient,  # noqa: F811
        db: asyncpg.Connection,  # noqa: F811
        two_users: TwoUsers,  # noqa: F811
    ) -> None:
        h = two_users.alice.headers
        asset = await listed(db)
        pid = await position(http, h, asset)
        row = await holding(http, h, pid)
        assert row["value"] is None and row["value_source"] is None
        s_ = await summary(http, h, pid)
        assert [a["id"] for a in s_["unpriced_assets"]] == [asset]
        assert s_["freshness"]["complete"] is False


# -------------------------------------------------------------------------- cache (T08.3)
class FailingStore(MemoryCacheStore):
    async def get(self, key: str) -> bytes | None:
        raise RedisError("down")

    async def incr(self, key: str) -> int:
        raise RedisError("down")


@pytest.mark.integration
@pytest.mark.security
class TestCacheBoundsStaleness:
    @pytest.fixture
    def clock(self, app: FastAPI) -> list[float]:  # noqa: F811
        now = [1000.0]
        app.state.response_cache._store = MemoryCacheStore(clock=lambda: now[0])
        return now

    async def assets_value(self, http: httpx.AsyncClient, h: dict[str, str]) -> Decimal:  # noqa: F811
        r = await http.get("/api/v1/dashboard", headers=h)
        assert r.status_code == 200, r.text
        return Decimal(r.json()["net_worth"]["assets"]["amount"])

    async def world(
        self,
        http: httpx.AsyncClient,  # noqa: F811
        db: asyncpg.Connection,  # noqa: F811
        h: dict[str, str],
    ) -> str:
        asset = await listed(db)
        await position(http, h, asset)
        await put_price(db, asset, "100", REAL_NOW - timedelta(hours=2))
        return asset

    async def test_a_new_price_reaches_the_dashboard_after_the_cache_expires(
        self,
        app: FastAPI,  # noqa: F811
        http: httpx.AsyncClient,  # noqa: F811
        db: asyncpg.Connection,  # noqa: F811
        two_users: TwoUsers,  # noqa: F811
        clock: list[float],
    ) -> None:
        h = two_users.alice.headers
        asset = await self.world(http, db, h)
        first = await self.assets_value(http, h)
        await put_price(db, asset, "120", REAL_NOW - timedelta(hours=1))
        assert await self.assets_value(http, h) == first, "within the TTL the cached figure holds"
        clock[0] += app.state.response_cache._ttl + 1
        assert await self.assets_value(http, h) - first == Decimal("200"), "10 units x 20"

    async def test_a_write_by_the_user_shows_the_new_price_immediately(
        self,
        http: httpx.AsyncClient,  # noqa: F811
        db: asyncpg.Connection,  # noqa: F811
        two_users: TwoUsers,  # noqa: F811
        clock: list[float],
    ) -> None:
        h = two_users.alice.headers
        asset = await self.world(http, db, h)
        first = await self.assets_value(http, h)
        await put_price(db, asset, "130", REAL_NOW - timedelta(minutes=30))
        body = {"risk_tolerance": "balanced"}
        assert (await http.post("/api/v1/risk-profiles", headers=h, json=body)).status_code == 201
        assert await self.assets_value(http, h) - first == Decimal("300")

    async def test_a_cache_outage_computes_live_instead_of_failing_or_serving_old_figures(
        self,
        app: FastAPI,  # noqa: F811
        http: httpx.AsyncClient,  # noqa: F811
        db: asyncpg.Connection,  # noqa: F811
        two_users: TwoUsers,  # noqa: F811
        clock: list[float],
    ) -> None:
        h = two_users.alice.headers
        asset = await self.world(http, db, h)
        first = await self.assets_value(http, h)
        await put_price(db, asset, "110", REAL_NOW - timedelta(minutes=20))
        app.state.response_cache._store = FailingStore()
        assert await self.assets_value(http, h) - first == Decimal("100")

    async def test_the_cache_never_serves_one_users_figures_to_another(
        self,
        http: httpx.AsyncClient,  # noqa: F811
        db: asyncpg.Connection,  # noqa: F811
        two_users: TwoUsers,  # noqa: F811
        clock: list[float],
    ) -> None:
        await self.world(http, db, two_users.alice.headers)
        alice = await self.assets_value(http, two_users.alice.headers)
        assert alice > 0
        assert await self.assets_value(http, two_users.bob.headers) == 0
