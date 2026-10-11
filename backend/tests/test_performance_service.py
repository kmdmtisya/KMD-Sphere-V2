"""One portfolio's performance from its real ledger and summary (P06-T03)."""

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
from app.modules.analytics.performance import Flow, XirrStatus, xirr
from app.modules.portfolio.performance_service import PerformanceService, PortfolioPerformance
from tests import auth_helpers as ah
from tests.authz_harness import TwoUsers, two_users  # noqa: F401
from tests.db_fixtures import migrated_settings  # noqa: F401

pytestmark = [pytest.mark.integration, pytest.mark.security]
TODAY = date.today()
START = TODAY - timedelta(days=400)
NOW = datetime.now(UTC).replace(microsecond=0)


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


async def portfolio(http: httpx.AsyncClient, h: dict[str, str]) -> str:
    r = await http.post(
        "/api/v1/portfolios",
        headers=h,
        json={"name": f"P {uuid.uuid4().hex[:8]}", "base_currency": "USD"},
    )
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


async def post(
    http: httpx.AsyncClient, h: dict[str, str], pid: str, kind: str, day: int, **fields: Any
) -> dict[str, Any]:
    body = {
        "transaction_type": kind,
        "trade_date": (START + timedelta(days=day)).isoformat(),
        "currency": fields.pop("currency", "USD"),
        **fields,
    }
    r = await http.post(f"/api/v1/portfolios/{pid}/transactions", headers=h, json=body)
    assert r.status_code == 201, r.text
    return dict(r.json())


async def asset(db: asyncpg.Connection) -> str:
    cls = await db.fetchval("SELECT id FROM asset_classes WHERE code = 'stock'")
    return str(
        await db.fetchval(
            "INSERT INTO assets (asset_class_id, symbol, name, currency) "
            "VALUES ($1, $2, $2, 'USD') RETURNING id",
            cls,
            f"P{uuid.uuid4().hex[:6]}",
        )
    )


async def valuation(
    http: httpx.AsyncClient, h: dict[str, str], pid: str, stock: str, amount: str
) -> None:
    body = {
        "asset_id": stock,
        "value": m(amount),
        "as_of": (NOW - timedelta(days=1)).isoformat(),
        "source": "test",
    }
    r = await http.post(f"/api/v1/portfolios/{pid}/valuations", headers=h, json=body)
    assert r.status_code == 201, r.text


async def performance(app: FastAPI, user: str, pid: str) -> PortfolioPerformance:
    async with app.state.db.session_factory() as session:
        return await PerformanceService(session).portfolio(
            uuid.UUID(user), uuid.UUID(pid), today=TODAY
        )


async def test_performance_from_the_ledger(
    app: FastAPI,
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    db: asyncpg.Connection,
) -> None:
    h = two_users.alice.headers
    pid, stock = await portfolio(http, h), await asset(db)
    await post(http, h, pid, "DEPOSIT", 0, gross_amount=m("10000.00"), fees=m("5.00"))
    await post(http, h, pid, "BUY", 1, asset_id=stock, quantity="50", unit_price=m("100"))
    await post(http, h, pid, "DEPOSIT", 30, currency="EUR", gross_amount=m("1000.00", "EUR"),
               fx_rate_to_portfolio_currency="1.10")  # fmt: skip
    await post(
        http, h, pid, "TRANSFER_IN", 60, asset_id=stock, quantity="10", gross_amount=m("1200.00")
    )
    wrong = await post(http, h, pid, "DEPOSIT", 90, gross_amount=m("999.00"))
    await http.post(
        f"/api/v1/portfolios/{pid}/transactions/{wrong['id']}/reversal", headers=h, json={}
    )
    await post(http, h, pid, "WITHDRAWAL", 200, gross_amount=m("2000.00"))
    await post(http, h, pid, "DIVIDEND", 250, asset_id=stock, gross_amount=m("80.00"))
    await valuation(http, h, pid, stock, "8400.00")

    p = await performance(app, two_users.alice.id, pid)
    # In: 10000 + 1100 (EUR at 1.10) + 1200 (transfer). Out: 2000. The reversed deposit is ignored.
    assert (p.contributions, p.withdrawals, p.net_invested) == (
        Decimal("12300.00"),
        Decimal("2000.00"),
        Decimal("10300.00"),
    )
    # Cash: 9995 - 5000 - 2000 + 80 = 3075 USD, plus 1000 EUR at the latest rate (if any).
    assert p.total_gain == p.total_value - p.net_invested
    assert p.simple_return is not None
    assert abs(p.simple_return - p.total_gain / p.contributions) < Decimal("1e-25")
    assert p.currency == "USD" and p.as_of == TODAY and p.first_flow == START
    assert p.income == Decimal("80.00")
    expected = xirr(
        [
            Flow(START, Decimal("-10000.00")),
            Flow(START + timedelta(30), Decimal("-1100.0000")),
            Flow(START + timedelta(60), Decimal("-1200.00")),
            Flow(START + timedelta(200), Decimal("2000.00")),
            Flow(TODAY, p.total_value),
        ]
    )
    assert p.money_weighted == expected
    assert p.money_weighted.status == XirrStatus.OK and p.money_weighted.unique


async def test_a_complete_usd_portfolio_reconciles(
    app: FastAPI,
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    db: asyncpg.Connection,
) -> None:
    """Everything in USD and valued: gain = realised + unrealised + income - expenses."""
    h = two_users.alice.headers
    pid, stock = await portfolio(http, h), await asset(db)
    await post(http, h, pid, "DEPOSIT", 0, gross_amount=m("5000.00"))
    await post(
        http, h, pid, "BUY", 1, asset_id=stock, quantity="40", unit_price=m("100"), fees=m("4.00")
    )
    await post(http, h, pid, "SELL", 100, asset_id=stock, quantity="10", unit_price=m("120"))
    await post(
        http, h, pid, "DIVIDEND", 120, asset_id=stock, gross_amount=m("30.00"), taxes=m("4.50")
    )
    await post(http, h, pid, "FEE", 130, gross_amount=m("2.00"))
    await valuation(http, h, pid, stock, "3300.00")
    p = await performance(app, two_users.alice.id, pid)
    assert p.complete
    # Cash 5000 - 4004 + 1200 + 25.50 - 2 = 2219.50; value 3300 + 2219.50 = 5519.50.
    assert p.total_value == Decimal("5519.50")
    assert p.total_gain == Decimal("519.50")
    assert p.total_gain == p.realized_pl + p.unrealized_pl + p.income - p.expenses
    assert p.simple_return == Decimal("0.1039")


async def test_purchases_without_deposits_claim_no_return(
    app: FastAPI,
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    db: asyncpg.Connection,
) -> None:
    h = two_users.alice.headers
    pid, stock = await portfolio(http, h), await asset(db)
    await post(http, h, pid, "BUY", 1, asset_id=stock, quantity="1", unit_price=m("100"))
    p = await performance(app, two_users.alice.id, pid)
    assert p.contributions == 0 and p.simple_return is None
    assert p.money_weighted.status == XirrStatus.INSUFFICIENT_FLOWS
    assert not p.complete  # the stock has no value yet


async def test_an_empty_portfolio(
    app: FastAPI,
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    pid = await portfolio(http, two_users.alice.headers)
    p = await performance(app, two_users.alice.id, pid)
    assert p.total_value == 0 and p.total_gain == 0 and p.first_flow is None
    assert p.money_weighted.status == XirrStatus.INSUFFICIENT_FLOWS


async def test_another_users_portfolio_is_not_found(
    app: FastAPI,
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    pid = await portfolio(http, two_users.alice.headers)
    await post(http, two_users.alice.headers, pid, "DEPOSIT", 0, gross_amount=m("100.00"))
    with pytest.raises(ResourceNotFoundError):
        await performance(app, two_users.bob.id, pid)
    with pytest.raises(ResourceNotFoundError):
        await performance(app, two_users.alice.id, str(uuid.uuid4()))
