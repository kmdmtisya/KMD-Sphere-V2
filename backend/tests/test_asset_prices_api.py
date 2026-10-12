"""An asset's stored prices through the API (P09-T07): latest with freshness, one close per day,
nothing for manually valued assets, and only for assets the user may see."""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import asyncpg
import httpx
import pytest
from fastapi import FastAPI

from app.core.config import Settings
from app.main import create_app
from tests import auth_helpers as ah
from tests.authz_harness import TwoUsers, assert_hidden_from, two_users  # noqa: F401
from tests.db_fixtures import migrated_settings  # noqa: F401

pytestmark = [pytest.mark.integration, pytest.mark.security]
NOW = datetime.now(UTC).replace(microsecond=0)
TODAY = NOW.date()


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


async def listed(db: asyncpg.Connection, code: str = "stock") -> str:
    cls = await db.fetchval("SELECT id FROM asset_classes WHERE code = $1", code)
    return str(
        await db.fetchval(
            "INSERT INTO assets (asset_class_id, symbol, name, currency) "
            "VALUES ($1, $2, $2, 'USD') RETURNING id",
            cls,
            f"P{uuid.uuid4().hex[:6].upper()}",
        )
    )


async def put(
    db: asyncpg.Connection,
    asset: str,
    value: str,
    as_of: datetime,
    kind: str = "close",
    provider: str = "fake",
    retrieved: datetime | None = None,
) -> None:
    await db.execute(
        "INSERT INTO market_prices (asset_id, price, currency, price_type, provider, as_of, "
        "retrieved_at) VALUES ($1, $2, 'USD', $3, $4, $5, $6)",
        uuid.UUID(asset),
        Decimal(value),
        kind,
        provider,
        as_of,
        retrieved or as_of,
    )


async def prices(
    http: httpx.AsyncClient, h: dict[str, str], asset: str, **q: str
) -> dict[str, Any]:
    r = await http.get(f"/api/v1/assets/{asset}/prices", headers=h, params=q)
    assert r.status_code == 200, r.text
    return dict(r.json())


async def test_latest_price_and_daily_closes(
    http: httpx.AsyncClient,
    db: asyncpg.Connection,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    asset = await listed(db)
    d1 = datetime.combine(TODAY - timedelta(days=3), datetime.min.time(), UTC) + timedelta(hours=21)
    d2 = d1 + timedelta(days=1)
    await put(db, asset, "100.123456", d1)
    await put(db, asset, "101.5", d2)
    await put(db, asset, "102.25", NOW - timedelta(hours=1), kind="quote")
    body = await prices(http, two_users.alice.headers, asset)
    assert body["currency"] == "USD"
    assert body["data_type"] == "delayed"
    latest = body["latest"]
    assert Decimal(latest["price"]) == Decimal("102.25")
    assert latest["stale"] is False
    assert latest["provider"] == "fake"
    assert [(p["on"], Decimal(p["close"])) for p in body["points"]] == [
        (d1.date().isoformat(), Decimal("100.123456")),
        (d2.date().isoformat(), Decimal("101.5")),
    ], "unit prices keep their decimals; quotes are not closes"


async def test_an_old_price_is_flagged_stale(
    http: httpx.AsyncClient,
    db: asyncpg.Connection,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    asset = await listed(db)
    await put(db, asset, "90", NOW - timedelta(days=20))
    body = await prices(http, two_users.alice.headers, asset)
    assert body["latest"]["stale"] is True


async def test_one_close_per_day_when_providers_overlap(
    http: httpx.AsyncClient,
    db: asyncpg.Connection,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    asset = await listed(db)
    day = datetime.combine(TODAY - timedelta(days=2), datetime.min.time(), UTC) + timedelta(
        hours=20
    )
    await put(db, asset, "50", day, provider="a", retrieved=day + timedelta(hours=1))
    await put(db, asset, "51", day, provider="b", retrieved=day + timedelta(hours=2))
    points = (await prices(http, two_users.alice.headers, asset))["points"]
    assert [(p["close"], p["provider"]) for p in points] == [("51", "b")]


async def test_the_period_limits_the_points(
    http: httpx.AsyncClient,
    db: asyncpg.Connection,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    asset = await listed(db)
    for back in (40, 10, 2):
        when = datetime.combine(TODAY - timedelta(days=back), datetime.min.time(), UTC)
        await put(db, asset, str(100 + back), when + timedelta(hours=20))
    start = (TODAY - timedelta(days=15)).isoformat()
    points = (await prices(http, two_users.alice.headers, asset, start=start))["points"]
    assert len(points) == 2


async def test_no_price_yet_is_null_not_zero(
    http: httpx.AsyncClient,
    db: asyncpg.Connection,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    body = await prices(http, two_users.alice.headers, await listed(db))
    assert body["latest"] is None
    assert body["points"] == []


async def test_a_manually_valued_asset_has_no_market_prices(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    made = await http.post(
        "/api/v1/assets",
        headers=two_users.alice.headers,
        json={"asset_class": "real_estate", "name": "Flat", "currency": "USD"},
    )
    body = await prices(http, two_users.alice.headers, made.json()["id"])
    assert body["latest"] is None and body["points"] == []


async def test_bob_cannot_read_prices_of_alices_asset(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    made = await http.post(
        "/api/v1/assets",
        headers=two_users.alice.headers,
        json={"asset_class": "real_estate", "name": "Alice flat", "currency": "USD"},
    )
    await assert_hidden_from(
        http, two_users.bob, "GET", f"/api/v1/assets/{made.json()['id']}/prices"
    )


async def test_an_unknown_asset_is_not_found(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    r = await http.get(f"/api/v1/assets/{uuid.uuid4()}/prices", headers=two_users.alice.headers)
    assert r.status_code == 404


async def test_a_signed_in_user_is_required(
    http: httpx.AsyncClient, db: asyncpg.Connection
) -> None:
    asset = await listed(db)
    assert (await http.get(f"/api/v1/assets/{asset}/prices")).status_code == 401
