"""/api/v1/net-worth/history (P14-T11) through the API."""

import secrets
import string
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg
import httpx
import pytest
from fastapi import FastAPI

from app.core.config import Settings
from app.core.money import minor_units
from app.main import create_app
from tests import auth_helpers as ah
from tests.authz_harness import TwoUsers, two_users  # noqa: F401
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


def fresh_currency() -> str:
    while True:
        code = "W" + "".join(secrets.choice(string.ascii_uppercase) for _ in range(2))
        if minor_units(code) == 2:
            return code


def m(amount: str, currency: str = "USD") -> dict[str, str]:
    return {"amount": amount, "currency": currency}


async def portfolio_with_deposit(
    http: httpx.AsyncClient, h: dict[str, str], amount: str, days_ago: int
) -> str:
    pid = (
        await http.post(
            "/api/v1/portfolios",
            headers=h,
            json={"name": f"P {uuid.uuid4().hex[:6]}", "base_currency": "USD"},
        )
    ).json()["id"]
    r = await http.post(
        f"/api/v1/portfolios/{pid}/transactions",
        headers=h,
        json={
            "transaction_type": "DEPOSIT",
            "gross_amount": m(amount),
            "trade_date": (TODAY - timedelta(days=days_ago)).isoformat(),
            "currency": "USD",
        },
    )
    assert r.status_code == 201, r.text
    return str(pid)


def iso(days_ago: int) -> str:
    return (TODAY - timedelta(days=days_ago)).isoformat()


async def history(http: httpx.AsyncClient, h: dict[str, str], **params: Any) -> dict[str, Any]:
    r = await http.get("/api/v1/net-worth/history", headers=h, params=params)
    assert r.status_code == 200, r.text
    return dict(r.json())


async def test_history_combines_portfolios_and_liabilities(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    db: asyncpg.Connection,
) -> None:
    h = two_users.alice.headers
    await portfolio_with_deposit(http, h, "1000.00", days_ago=4)
    await portfolio_with_deposit(http, h, "500.00", days_ago=2)
    foreign = fresh_currency()
    await db.execute(
        "INSERT INTO fx_rates (base_currency, quote_currency, rate, provider, rate_timestamp, "
        "retrieved_at) VALUES ($1, 'USD', 2::numeric, 'test-provider', $2, $2)",
        foreign,
        NOW - timedelta(days=4),  # within the 7-day rule of the dates below
    )
    recorded = TODAY - timedelta(days=2)
    r = await http.post(
        "/api/v1/liabilities",
        headers=h,
        json={
            "name": f"Loan {uuid.uuid4().hex[:6]}",
            "liability_type": "personal_loan",
            "balance": m("100.00", foreign),
            "balance_as_of": recorded.isoformat(),
        },
    )
    assert r.status_code == 201, r.text

    out = await history(
        http, h, currency="USD", frequency="daily", start=(TODAY - timedelta(days=4)).isoformat()
    )
    by_day = {p["on"]: p for p in out["points"]}
    assert out["currency"] == "USD" and out["frequency"] == "daily"
    assert out["portfolio_count"] == 2 and out["liability_count"] == 1
    # Before the second deposit and before the loan was recorded.
    assert by_day[iso(4)]["assets"] == m("1000.00")
    assert by_day[iso(4)]["liabilities"] == m("0.00") and by_day[iso(4)]["complete"] is False
    # Both portfolios and the loan (100 in the foreign currency = 200 USD).
    assert by_day[iso(2)]["assets"] == m("1500.00")
    assert by_day[iso(2)]["liabilities"] == m("200.00")
    assert by_day[iso(2)]["net_worth"] == m("1300.00") and by_day[iso(2)]["complete"] is True
    assert out["points"][-1]["on"] == TODAY.isoformat()
    assert out["incomplete_points"] == sum(1 for p in out["points"] if not p["complete"])
    assert out["complete"] is (out["incomplete_points"] == 0) and out["notice"]


async def test_history_with_nothing_is_empty_and_a_future_end_is_refused(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    h = two_users.bob.headers
    out = await history(http, h, currency="USD")
    assert out["points"] == [] and out["portfolio_count"] == 0 and out["complete"] is True
    tomorrow = (TODAY + timedelta(days=1)).isoformat()
    r = await http.get("/api/v1/net-worth/history", headers=h, params={"end": tomorrow})
    assert r.status_code == 422


async def test_history_is_the_users_own(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    alice, bob = two_users.alice.headers, two_users.bob.headers
    await portfolio_with_deposit(http, alice, "7777.00", days_ago=1)
    seen = await history(http, bob, currency="USD", frequency="daily")
    assert all(p["assets"]["amount"] == "0.00" for p in seen["points"])
    anonymous = await http.get("/api/v1/net-worth/history")
    assert anonymous.status_code == 401
