"""Valuing positions from market prices with fallback to manual valuations (P08-T06): the rules,
then the summary and holdings API (docs/design/valuation-sources.md)."""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import asyncpg
import httpx
import pytest
from fastapi import FastAPI

from app.core.config import Settings
from app.main import create_app
from app.modules.market_data.freshness import FRESH_FOR
from app.modules.market_data.providers.models import AssetKind
from app.modules.market_data.valuation import (
    ManualCandidate,
    PriceCandidate,
    choose_value,
)
from tests import auth_helpers as ah
from tests.authz_harness import TwoUsers, two_users  # noqa: F401
from tests.db_fixtures import migrated_settings  # noqa: F401

NOW = datetime.now(UTC).replace(microsecond=0)
ASSET = uuid.UUID(int=1)


def price(
    value: str = "10", age: timedelta = timedelta(hours=1), provider: str = "fake"
) -> PriceCandidate:
    return PriceCandidate(Decimal(value), "USD", NOW - age, provider)


def manual(value: str = "1000", age: timedelta = timedelta(days=2)) -> ManualCandidate:
    return ManualCandidate(Decimal(value), "USD", NOW - age)


class TestChooseValue:
    def test_a_price_values_the_position_as_quantity_times_price(self) -> None:
        v = choose_value(ASSET, Decimal("7"), AssetKind.ETF, price("10.25"), None, NOW)
        assert v is not None
        assert (v.value, v.source, v.provider, v.stale) == (
            Decimal("71.75"),
            "price",
            "fake",
            False,
        )
        assert v.as_of == NOW - timedelta(hours=1)

    def test_the_arithmetic_is_exact(self) -> None:
        v = choose_value(
            ASSET, Decimal("0.1"), AssetKind.CRYPTO, price("0.2", timedelta(minutes=1)), None, NOW
        )
        assert v is not None
        assert v.value == Decimal("0.02")

    def test_without_a_price_the_manual_valuation_is_the_fallback(self) -> None:
        v = choose_value(ASSET, Decimal("7"), AssetKind.ETF, None, manual("1234"), NOW)
        assert v is not None
        assert (v.value, v.source, v.provider, v.stale) == (
            Decimal("1234"),
            "valuation",
            None,
            False,
        )

    def test_a_newer_manual_valuation_beats_an_older_price(self) -> None:
        v = choose_value(
            ASSET,
            Decimal("7"),
            AssetKind.ETF,
            price(age=timedelta(days=3)),
            manual(age=timedelta(days=1)),
            NOW,
        )
        assert v is not None
        assert v.source == "valuation"

    def test_a_newer_price_beats_an_older_manual_valuation(self) -> None:
        v = choose_value(
            ASSET,
            Decimal("7"),
            AssetKind.ETF,
            price(age=timedelta(hours=1)),
            manual(age=timedelta(days=1)),
            NOW,
        )
        assert v is not None
        assert v.source == "price"

    def test_on_a_tie_the_market_price_wins(self) -> None:
        age = timedelta(hours=5)
        v = choose_value(ASSET, Decimal("7"), AssetKind.ETF, price(age=age), manual(age=age), NOW)
        assert v is not None
        assert v.source == "price"

    def test_a_manually_valued_asset_ignores_any_price(self) -> None:
        v = choose_value(ASSET, Decimal("1"), None, price(), manual(), NOW)
        assert v is not None
        assert v.source == "valuation"

    def test_nothing_known_means_unpriced(self) -> None:
        assert choose_value(ASSET, Decimal("7"), AssetKind.ETF, None, None, NOW) is None
        assert choose_value(ASSET, Decimal("7"), None, None, None, NOW) is None

    def test_a_stale_price_is_still_used_and_flagged(self) -> None:
        old = FRESH_FOR[AssetKind.ETF] + timedelta(hours=1)
        v = choose_value(ASSET, Decimal("2"), AssetKind.ETF, price("5", old), None, NOW)
        assert v is not None
        assert v.stale is True
        assert v.value == Decimal("10")
        assert v.as_of == NOW - old, "the flag never hides how old the price is"

    def test_crypto_goes_stale_sooner_than_an_etf(self) -> None:
        age = timedelta(hours=8)
        crypto = choose_value(ASSET, Decimal("1"), AssetKind.CRYPTO, price(age=age), None, NOW)
        etf = choose_value(ASSET, Decimal("1"), AssetKind.ETF, price(age=age), None, NOW)
        assert crypto is not None
        assert etf is not None
        assert (crypto.stale, etf.stale) == (True, False)

    def test_a_manual_valuation_is_never_flagged_stale(self) -> None:
        v = choose_value(
            ASSET, Decimal("1"), AssetKind.ETF, None, manual(age=timedelta(days=900)), NOW
        )
        assert v is not None
        assert v.stale is False


# ------------------------------------------------------------------------------------ API
DAY = date.today() - timedelta(days=40)


@pytest.fixture(scope="module")
async def app(migrated_settings: Settings) -> AsyncIterator[FastAPI]:  # noqa: F811
    application = create_app(migrated_settings, readiness_checks={}, token_verifier=ah.verifier())
    yield application
    await application.state.db.dispose()


@pytest.fixture
async def http(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture(scope="module")
async def db(migrated_settings: Settings) -> AsyncIterator[asyncpg.Connection]:  # noqa: F811
    conn = await asyncpg.connect(migrated_settings.database_dsn, timeout=5)
    yield conn
    await conn.close()


def m(amount: str, currency: str = "USD") -> dict[str, str]:
    return {"amount": amount, "currency": currency}


async def listed(db: asyncpg.Connection, code: str = "etf") -> str:
    cls = await db.fetchval("SELECT id FROM asset_classes WHERE code = $1", code)
    return str(
        await db.fetchval(
            "INSERT INTO assets (asset_class_id, symbol, name, currency) "
            "VALUES ($1, $2, $2, 'USD') RETURNING id",
            cls,
            f"V{uuid.uuid4().hex[:6].upper()}",
        )
    )


async def put_price(
    db: asyncpg.Connection, asset: str, value: str, as_of: datetime, provider: str = "fake"
) -> None:
    await db.execute(
        "INSERT INTO market_prices (asset_id, price, currency, price_type, provider, as_of, "
        "retrieved_at) VALUES ($1, $2, 'USD', 'quote', $3, $4, $4)",
        uuid.UUID(asset),
        Decimal(value),
        provider,
        as_of,
    )


async def position(
    http: httpx.AsyncClient, h: dict[str, str], asset: str, quantity: str = "10"
) -> str:
    r = await http.post(
        "/api/v1/portfolios",
        headers=h,
        json={"name": f"V {uuid.uuid4().hex[:8]}", "base_currency": "USD"},
    )
    pid = str(r.json()["id"])
    for body in (
        {
            "transaction_type": "DEPOSIT",
            "trade_date": DAY.isoformat(),
            "currency": "USD",
            "gross_amount": m("10000.00"),
        },
        {
            "transaction_type": "BUY",
            "trade_date": (DAY + timedelta(days=1)).isoformat(),
            "currency": "USD",
            "asset_id": asset,
            "quantity": quantity,
            "unit_price": m("100"),
        },
    ):
        posted = await http.post(f"/api/v1/portfolios/{pid}/transactions", headers=h, json=body)
        assert posted.status_code == 201, posted.text
    return pid


async def holding(http: httpx.AsyncClient, h: dict[str, str], pid: str) -> dict[str, Any]:
    r = await http.get(f"/api/v1/portfolios/{pid}/holdings", headers=h)
    assert r.status_code == 200, r.text
    (row,) = r.json()["items"] if "items" in r.json() else r.json()
    return dict(row)


async def summary(http: httpx.AsyncClient, h: dict[str, str], pid: str) -> dict[str, Any]:
    r = await http.get(f"/api/v1/portfolios/{pid}/summary", headers=h)
    assert r.status_code == 200, r.text
    return dict(r.json())


@pytest.mark.integration
@pytest.mark.security
class TestApi:
    async def test_a_market_price_values_the_holding_and_the_summary(
        self,
        http: httpx.AsyncClient,
        two_users: TwoUsers,  # noqa: F811
        db: asyncpg.Connection,
    ) -> None:
        h = two_users.alice.headers
        asset = await listed(db)
        pid = await position(http, h, asset)
        as_of = NOW - timedelta(hours=2)
        await put_price(db, asset, "112.50", as_of)

        row = await holding(http, h, pid)
        assert row["value"] == m("1125.00")
        assert row["value_source"] == "price"
        assert row["value_stale"] is False
        assert row["value_provider"] == "fake"
        assert datetime.fromisoformat(row["value_as_of"]) == as_of

        s = await summary(http, h, pid)
        assert s["holdings_value"] == m("1125.00")
        assert s["valued_positions"] == 1
        assert s["freshness"]["stale_prices"] == []
        assert datetime.fromisoformat(s["freshness"]["data_as_of"]) == as_of

    async def test_a_stale_price_is_still_used_and_flagged_per_holding_and_in_the_summary(
        self,
        http: httpx.AsyncClient,
        two_users: TwoUsers,  # noqa: F811
        db: asyncpg.Connection,
    ) -> None:
        h = two_users.alice.headers
        asset = await listed(db)
        pid = await position(http, h, asset)
        as_of = NOW - timedelta(days=12)
        await put_price(db, asset, "90.00", as_of)

        row = await holding(http, h, pid)
        assert row["value"] == m("900.00"), "a stale price is still the best price known"
        assert row["value_stale"] is True
        assert datetime.fromisoformat(row["value_as_of"]) == as_of

        s = await summary(http, h, pid)
        assert [a["id"] for a in s["freshness"]["stale_prices"]] == [asset]
        assert datetime.fromisoformat(s["freshness"]["data_as_of"]) == as_of
        assert s["freshness"]["complete"] is True, "stale is flagged, not counted as missing"

    async def test_without_a_price_the_manual_valuation_is_used(
        self,
        http: httpx.AsyncClient,
        two_users: TwoUsers,  # noqa: F811
        db: asyncpg.Connection,
    ) -> None:
        h = two_users.alice.headers
        asset = await listed(db)
        pid = await position(http, h, asset)
        r = await http.post(
            f"/api/v1/portfolios/{pid}/valuations",
            headers=h,
            json={
                "asset_id": asset,
                "value": m("1300.00"),
                "as_of": (NOW - timedelta(days=1)).isoformat(),
                "source": "test",
            },
        )
        assert r.status_code == 201, r.text
        row = await holding(http, h, pid)
        assert row["value"] == m("1300.00")
        assert (row["value_source"], row["value_stale"], row["value_provider"]) == (
            "valuation",
            False,
            None,
        )

    async def test_a_newer_manual_valuation_overrides_an_older_price(
        self,
        http: httpx.AsyncClient,
        two_users: TwoUsers,  # noqa: F811
        db: asyncpg.Connection,
    ) -> None:
        h = two_users.alice.headers
        asset = await listed(db)
        pid = await position(http, h, asset)
        await put_price(db, asset, "100.00", NOW - timedelta(days=3))
        await http.post(
            f"/api/v1/portfolios/{pid}/valuations",
            headers=h,
            json={
                "asset_id": asset,
                "value": m("1500.00"),
                "as_of": (NOW - timedelta(days=1)).isoformat(),
                "source": "test",
            },
        )
        row = await holding(http, h, pid)
        assert (row["value"], row["value_source"]) == (m("1500.00"), "valuation")

    async def test_no_price_and_no_valuation_is_unpriced_not_guessed(
        self,
        http: httpx.AsyncClient,
        two_users: TwoUsers,  # noqa: F811
        db: asyncpg.Connection,
    ) -> None:
        h = two_users.alice.headers
        asset = await listed(db)
        pid = await position(http, h, asset)
        row = await holding(http, h, pid)
        assert row["value"] is None
        assert row["value_source"] is None
        assert row["value_stale"] is None
        s = await summary(http, h, pid)
        assert [a["id"] for a in s["unpriced_assets"]] == [asset]
        assert s["freshness"]["complete"] is False

    async def test_a_manually_valued_class_ignores_a_stray_price(
        self,
        http: httpx.AsyncClient,
        two_users: TwoUsers,  # noqa: F811
        db: asyncpg.Connection,
    ) -> None:
        h = two_users.alice.headers
        asset = await listed(db, "real_estate")  # valued manually
        pid = await position(http, h, asset, "1")
        await put_price(db, asset, "999999.00", NOW - timedelta(hours=1))
        row = await holding(http, h, pid)
        assert row["value"] is None, "a price is not used for a manually valued asset"

    async def test_the_latest_of_several_prices_is_used(
        self,
        http: httpx.AsyncClient,
        two_users: TwoUsers,  # noqa: F811
        db: asyncpg.Connection,
    ) -> None:
        h = two_users.alice.headers
        asset = await listed(db)
        pid = await position(http, h, asset)
        await put_price(db, asset, "50.00", NOW - timedelta(days=2))
        await put_price(db, asset, "120.00", NOW - timedelta(hours=3))
        await put_price(db, asset, "60.00", NOW - timedelta(days=1))
        row = await holding(http, h, pid)
        assert row["value"] == m("1200.00")

    async def test_the_openapi_describes_the_new_holding_fields(self, app: FastAPI) -> None:
        schema = app.openapi()["components"]["schemas"]["HoldingOut"]["properties"]
        assert {"value_source", "value_stale", "value_provider"} <= set(schema)
        freshness = app.openapi()["components"]["schemas"]["Freshness"]["properties"]
        assert "stale_prices" in freshness
