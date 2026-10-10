"""FX rates API and automatic rates on foreign-currency postings (P05-T06)."""

import secrets
import string
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import asyncpg
import httpx
import pytest
from fastapi import FastAPI

from app.core.config import Settings
from app.main import create_app
from tests import auth_helpers as ah
from tests.authz_harness import TwoUsers, two_users  # noqa: F401
from tests.db_fixtures import migrated_settings  # noqa: F401

pytestmark = pytest.mark.integration
TODAY = datetime.now(UTC).date()


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


async def add_rate(
    db: asyncpg.Connection, base: str, quote: str, value: str, at: datetime, provider: str
) -> None:
    await db.execute(
        "INSERT INTO fx_rates (base_currency, quote_currency, rate, provider, rate_timestamp, "
        "retrieved_at) VALUES ($1, $2, $3, $4, $5, $5)",
        base,
        quote,
        Decimal(value),
        provider,
        at,
    )


_USED: set[str] = set()


def _code(prefix: str) -> str:
    while True:
        code = prefix + "".join(secrets.choice(string.ascii_uppercase) for _ in range(2))
        if code not in _USED:
            _USED.add(code)
            return code


def pair() -> tuple[str, str]:
    """A currency pair no other test in this run uses (FX rates are global data)."""
    return _code("X"), _code("Y")


async def test_latest_and_historical_rates_with_provenance(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    db: asyncpg.Connection,
) -> None:
    base, quote = pair()
    now = datetime.now(UTC)
    yesterday = datetime.combine(TODAY - timedelta(days=1), datetime.min.time(), UTC)
    await add_rate(db, base, quote, "1.25", yesterday + timedelta(hours=12), "ecb")
    await add_rate(db, base, quote, "1.30", now - timedelta(minutes=5), "ecb")
    h = two_users.alice.headers
    latest = await http.get(f"/api/v1/fx-rates/{base}/{quote}", headers=h)
    assert latest.status_code == 200, latest.text
    assert latest.json()["rate"] == "1.3"
    assert latest.json()["provider"] == "ecb"
    assert (latest.json()["rule"], latest.json()["stale"], latest.json()["inverted"]) == (
        "latest",
        False,
        False,
    )
    on = (TODAY - timedelta(days=1)).isoformat()
    historical = await http.get(f"/api/v1/fx-rates/{base}/{quote}", headers=h, params={"on": on})
    assert historical.json()["rate"] == "1.25"
    assert historical.json()["rule"] == "historical"
    inverse = await http.get(f"/api/v1/fx-rates/{quote}/{base}", headers=h)
    assert inverse.json()["inverted"] is True
    assert Decimal(inverse.json()["rate"]) == Decimal(1) / Decimal("1.30")


async def test_an_unknown_pair_is_a_clear_404(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    base, quote = pair()
    r = await http.get(f"/api/v1/fx-rates/{base}/{quote}", headers=two_users.alice.headers)
    assert r.status_code == 404
    assert r.json()["type"].endswith("/fx-rate-unavailable")
    bad = await http.get("/api/v1/fx-rates/usd/KES", headers=two_users.alice.headers)
    assert bad.status_code == 422


async def portfolio(http: httpx.AsyncClient, h: dict[str, str], currency: str) -> str:
    r = await http.post(
        "/api/v1/portfolios",
        headers=h,
        json={"name": f"F {uuid.uuid4().hex[:8]}", "base_currency": currency},
    )
    return str(r.json()["id"])


def deposit(currency: str, day: date, **extra: object) -> dict[str, object]:
    return {
        "transaction_type": "DEPOSIT",
        "trade_date": day.isoformat(),
        "currency": currency,
        "gross_amount": {"amount": "100.00", "currency": currency},
        **extra,
    }


async def test_a_foreign_posting_without_a_rate_uses_and_stores_the_historical_rate(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    db: asyncpg.Connection,
) -> None:
    posting_ccy, base_ccy = pair()
    day = TODAY - timedelta(days=3)
    on_the_day = datetime.combine(day, datetime.min.time(), UTC) + timedelta(hours=16)
    await add_rate(db, posting_ccy, base_ccy, "129.123456789012", on_the_day, "central-bank")
    await add_rate(db, posting_ccy, base_ccy, "999", on_the_day + timedelta(days=2), "later")
    h = two_users.alice.headers
    pid = await portfolio(http, h, base_ccy)
    r = await http.post(
        f"/api/v1/portfolios/{pid}/transactions", headers=h, json=deposit(posting_ccy, day)
    )
    assert r.status_code == 201, r.text
    t = r.json()
    assert t["currency"] == posting_ccy  # the original currency is kept
    assert t["gross_amount"] == {"amount": "100.00", "currency": posting_ccy}
    assert t["fx_rate_to_portfolio_currency"] == "129.123456789012"  # that day's, not the later
    assert t["fx_rate_source"] == "central-bank"
    assert datetime.fromisoformat(t["fx_rate_as_of"]) == on_the_day


async def test_an_inverted_rate_is_rounded_to_the_stored_precision(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    db: asyncpg.Connection,
) -> None:
    posting_ccy, base_ccy = pair()
    day = TODAY - timedelta(days=1)
    at = datetime.combine(day, datetime.min.time(), UTC) + timedelta(hours=9)
    await add_rate(db, base_ccy, posting_ccy, "3", at, "p")  # only the opposite direction
    h = two_users.alice.headers
    pid = await portfolio(http, h, base_ccy)
    r = await http.post(
        f"/api/v1/portfolios/{pid}/transactions", headers=h, json=deposit(posting_ccy, day)
    )
    assert r.status_code == 201, r.text
    assert r.json()["fx_rate_to_portfolio_currency"] == "0.333333333333"  # 1/3, 12 decimals


async def test_the_users_own_rate_wins_and_missing_rates_are_explained(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    db: asyncpg.Connection,
) -> None:
    posting_ccy, base_ccy = pair()
    day = TODAY - timedelta(days=1)
    h = two_users.alice.headers
    pid = await portfolio(http, h, base_ccy)
    missing = await http.post(
        f"/api/v1/portfolios/{pid}/transactions", headers=h, json=deposit(posting_ccy, day)
    )
    assert missing.status_code == 422
    assert "send the rate you used" in missing.json()["detail"]
    at = datetime.combine(day, datetime.min.time(), UTC)
    await add_rate(db, posting_ccy, base_ccy, "2", at, "p")
    own = await http.post(
        f"/api/v1/portfolios/{pid}/transactions",
        headers=h,
        json=deposit(posting_ccy, day, fx_rate_to_portfolio_currency="2.05"),
    )
    assert own.status_code == 201, own.text
    assert own.json()["fx_rate_to_portfolio_currency"] == "2.05"
    assert own.json()["fx_rate_source"] == "user"
