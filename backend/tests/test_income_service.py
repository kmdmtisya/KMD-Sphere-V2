"""Income events follow the ledger, and one portfolio's income figures (P06-T05)."""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import asyncpg
import httpx
import pytest
from fastapi import FastAPI

from app.core.authz import ResourceNotFoundError
from app.core.config import Settings
from app.main import create_app
from app.modules.networth.income_service import IncomeService, PortfolioIncome
from tests import auth_helpers as ah
from tests.authz_harness import TwoUsers, two_users  # noqa: F401
from tests.db_fixtures import migrated_settings  # noqa: F401

pytestmark = [pytest.mark.integration, pytest.mark.security]
TODAY = date.today()
DAY = TODAY - timedelta(days=60)
NOW = datetime.now(UTC).replace(microsecond=0)
D = Decimal


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


async def setup(http: httpx.AsyncClient, h: dict[str, str]) -> tuple[str, str]:
    r = await http.post(
        "/api/v1/assets",
        headers=h,
        json={"asset_class": "stock", "name": f"S {uuid.uuid4().hex[:6]}", "currency": "USD"},
    )
    stock = str(r.json()["id"])
    r = await http.post(
        "/api/v1/portfolios",
        headers=h,
        json={"name": f"I {uuid.uuid4().hex[:8]}", "base_currency": "USD"},
    )
    return str(r.json()["id"]), stock


async def post(
    http: httpx.AsyncClient, h: dict[str, str], pid: str, kind: str, key: str | None = None,
    **fields: Any,
) -> httpx.Response:  # fmt: skip
    body = {"transaction_type": kind, "trade_date": DAY.isoformat(), "currency": "USD"} | fields
    headers = h | ({"Idempotency-Key": key} if key else {})
    r = await http.post(f"/api/v1/portfolios/{pid}/transactions", headers=headers, json=body)
    assert r.status_code in (200, 201), r.text
    return r


async def events(db: asyncpg.Connection, pid: str) -> list[asyncpg.Record]:
    return await db.fetch(
        "SELECT * FROM income_events WHERE portfolio_id = $1 ORDER BY paid_on, gross",
        uuid.UUID(pid),
    )


async def income(app: FastAPI, user: str, pid: str) -> PortfolioIncome:
    async with app.state.db.session_factory() as session:
        return await IncomeService(session).portfolio(uuid.UUID(user), uuid.UUID(pid), TODAY)


async def test_income_events_follow_the_ledger(
    app: FastAPI,
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    db: asyncpg.Connection,
) -> None:
    h = two_users.alice.headers
    pid, stock = await setup(http, h)
    await post(http, h, pid, "DEPOSIT", gross_amount=m("2000.00"))
    await post(http, h, pid, "BUY", asset_id=stock, quantity="10", unit_price=m("100"))
    dividend = (
        await post(http, h, pid, "DIVIDEND", asset_id=stock, gross_amount=m("30.00"),
                   taxes=m("4.50"))
    ).json()  # fmt: skip
    await post(http, h, pid, "INTEREST", currency="EUR", gross_amount=m("10.00", "EUR"),
               fx_rate_to_portfolio_currency="1.10")  # fmt: skip
    wrong = (await post(http, h, pid, "DIVIDEND", asset_id=stock, gross_amount=m("999.00"))).json()
    assert len(await events(db, pid)) == 3

    # A reversal removes the event of the entry it reverses, and adds none of its own.
    r = await http.post(
        f"/api/v1/portfolios/{pid}/transactions/{wrong['id']}/reversal", headers=h, json={}
    )
    assert r.status_code == 201, r.text
    rows = await events(db, pid)
    kept = next(e for e in rows if e["income_type"] == "DIVIDEND")
    assert str(kept["transaction_id"]) == dividend["id"]
    assert {e["income_type"] for e in rows} == {"DIVIDEND", "INTEREST"} and len(rows) == 2
    interest = next(e for e in rows if e["income_type"] == "INTEREST")
    assert (interest["asset_id"], interest["currency"], interest["fx_rate"]) == (
        None,
        "EUR",
        D("1.100000000000"),
    )
    assert kept["taxes"] == D("4.50")

    # An idempotent replay adds no second event.
    await post(http, h, pid, "COUPON", "coupon-1", asset_id=stock, gross_amount=m("5.00"))
    await post(http, h, pid, "COUPON", "coupon-1", asset_id=stock, gross_amount=m("5.00"))
    assert len(await events(db, pid)) == 3

    await http.post(
        f"/api/v1/portfolios/{pid}/valuations",
        headers=h,
        json={"asset_id": stock, "value": m("1100.00"), "as_of": NOW.isoformat(), "source": "t"},
    )
    i = await income(app, two_users.alice.id, pid)
    # Trailing: 30 + 11 (EUR at 1.10) + 5 = 46 gross, 4.50 taxes.
    assert (i.trailing_12m.gross, i.trailing_12m.taxes, i.trailing_12m.payments) == (
        D("46.0000"),
        D("4.50"),
        3,
    )
    assert i.yearly == D("41.5000")
    stock_row = next(a for a in i.by_asset if a.asset_id == uuid.UUID(stock))
    assert stock_row.trailing_12m.gross == D(35)
    assert stock_row.current_yield is not None and stock_row.yield_on_cost is not None
    assert abs(stock_row.current_yield - D(35) / D(1100)) < D("1e-25")
    assert stock_row.yield_on_cost == D("0.035")  # 35 / 1000
    # Measured against the published summary (EUR cash is valued only if a EUR rate exists).
    published = (await http.get(f"/api/v1/portfolios/{pid}/summary", headers=h)).json()
    assert i.complete is published["freshness"]["complete"]
    total = D(published["total_value"]["amount"])
    assert i.portfolio_yield is not None
    assert abs(i.portfolio_yield - D(46) / total) < D("1e-6")


async def test_only_this_portfolios_income_is_counted(
    app: FastAPI,
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    """Income of the user's other portfolio, and of another user, never appears."""
    alice, bob = two_users.alice.headers, two_users.bob.headers
    pid, _ = await setup(http, alice)
    other, _ = await setup(http, alice)
    bobs, _ = await setup(http, bob)
    await post(http, alice, pid, "INTEREST", gross_amount=m("1.00"))
    await post(http, alice, other, "INTEREST", gross_amount=m("20.00"))
    await post(http, bob, bobs, "INTEREST", gross_amount=m("300.00"))
    i = await income(app, two_users.alice.id, pid)
    assert (i.trailing_12m.gross, i.trailing_12m.payments) == (D("1.00"), 1)
    assert (await income(app, two_users.alice.id, other)).trailing_12m.gross == D("20.00")
    assert (await income(app, two_users.bob.id, bobs)).trailing_12m.gross == D("300.00")


async def test_another_users_portfolio_is_not_found(
    app: FastAPI,
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    pid, _ = await setup(http, two_users.alice.headers)
    with pytest.raises(ResourceNotFoundError):
        await income(app, two_users.bob.id, pid)
    with pytest.raises(ResourceNotFoundError):
        await income(app, two_users.alice.id, str(uuid.uuid4()))
