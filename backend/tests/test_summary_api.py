"""Portfolio summaries through the API (P05-T08). The scenario and its hand-computed figures are
the same as in tests/test_portfolio_summary.py, entered through the real endpoints."""

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
from tests import auth_helpers as ah
from tests.authz_harness import TwoUsers, assert_hidden_from, two_users  # noqa: F401
from tests.db_fixtures import migrated_settings  # noqa: F401

pytestmark = [pytest.mark.integration, pytest.mark.security]
NOW = datetime.now(UTC).replace(microsecond=0)
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


async def listed(db: asyncpg.Connection, symbol: str, currency: str) -> str:
    cls = await db.fetchval("SELECT id FROM asset_classes WHERE code = 'stock'")
    return str(
        await db.fetchval(
            "INSERT INTO assets (asset_class_id, symbol, name, currency) "
            "VALUES ($1, $2, $2, $3) RETURNING id",
            cls,
            f"{symbol}{uuid.uuid4().hex[:4]}",
            currency,
        )
    )


async def rate(db: asyncpg.Connection, base: str, quote: str, value: str, at: datetime) -> None:
    await db.execute(
        "INSERT INTO fx_rates (base_currency, quote_currency, rate, provider, rate_timestamp, "
        "retrieved_at) VALUES ($1, $2, $3, 'test', $4, $4) ON CONFLICT DO NOTHING",
        base,
        quote,
        Decimal(value),
        at,
    )


def m(amount: str, currency: str = "USD") -> dict[str, str]:
    return {"amount": amount, "currency": currency}


def posting(kind: str, day: int, currency: str, **fields: Any) -> dict[str, Any]:
    return {
        "transaction_type": kind,
        "trade_date": (DAY + timedelta(days=day)).isoformat(),
        "currency": currency,
        **fields,
    }


async def post(http: httpx.AsyncClient, h: dict[str, str], pid: str, body: dict[str, Any]) -> None:
    r = await http.post(f"/api/v1/portfolios/{pid}/transactions", headers=h, json=body)
    assert r.status_code == 201, r.text


async def value(
    http: httpx.AsyncClient, h: dict[str, str], pid: str, asset: str, amount: str, ccy: str
) -> None:
    r = await http.post(
        f"/api/v1/portfolios/{pid}/valuations",
        headers=h,
        json={
            "asset_id": asset,
            "value": m(amount, ccy),
            "as_of": (NOW - timedelta(days=2)).isoformat(),
            "source": "test",
        },
    )
    assert r.status_code == 201, r.text


async def portfolio(http: httpx.AsyncClient, h: dict[str, str], currency: str) -> str:
    r = await http.post(
        "/api/v1/portfolios",
        headers=h,
        json={"name": f"S {uuid.uuid4().hex[:8]}", "base_currency": currency},
    )
    return str(r.json()["id"])


async def build_scenario(
    http: httpx.AsyncClient, h: dict[str, str], db: asyncpg.Connection
) -> tuple[str, dict[str, str]]:
    a, b, d = (
        await listed(db, "A", "USD"),
        await listed(db, "B", "EUR"),
        await listed(db, "D", "USD"),
    )
    house = await http.post(
        "/api/v1/assets",
        headers=h,
        json={"asset_class": "real_estate", "name": "House", "currency": "KES"},
    )
    c = house.json()["id"]
    await rate(db, "EUR", "USD", "1.08", NOW - timedelta(hours=1))
    await rate(db, "KES", "USD", "0.0077", NOW - timedelta(days=3))  # stale
    pid = await portfolio(http, h, "USD")
    for body in (
        posting("DEPOSIT", 1, "USD", gross_amount=m("10000.00")),
        posting("BUY", 2, "USD", asset_id=a, quantity="10", unit_price=m("100"), fees=m("10.00")),
        posting(
            "DEPOSIT",
            3,
            "EUR",
            gross_amount=m("1000.00", "EUR"),
            fx_rate_to_portfolio_currency="1.10",
        ),
        posting(
            "BUY",
            4,
            "EUR",
            asset_id=b,
            quantity="5",
            unit_price=m("100", "EUR"),
            fees=m("5.00", "EUR"),
            fx_rate_to_portfolio_currency="1.10",
        ),
        posting("DIVIDEND", 5, "USD", asset_id=a, gross_amount=m("20.00"), taxes=m("3.00")),
        posting("FEE", 6, "USD", gross_amount=m("2.00")),
        posting(
            "INTEREST",
            7,
            "EUR",
            gross_amount=m("4.00", "EUR"),
            fx_rate_to_portfolio_currency="1.12",
        ),
        posting("WITHDRAWAL", 8, "USD", gross_amount=m("100.00")),
        posting("SELL", 9, "USD", asset_id=a, quantity="4", unit_price=m("120"), fees=m("2.00")),
        posting("BUY", 10, "USD", asset_id=d, quantity="2", unit_price=m("25")),
    ):
        await post(http, h, pid, body)
    await value(http, h, pid, a, "900.00", "USD")
    await value(http, h, pid, b, "600.00", "EUR")
    await value(http, h, pid, c, "250000.00", "KES")
    return pid, {"A": a, "B": b, "C": c, "D": d}


async def test_a_portfolio_summary_matches_the_hand_computed_figures(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    db: asyncpg.Connection,
) -> None:
    h = two_users.alice.headers
    pid, assets = await build_scenario(http, h, db)
    r = await http.get(f"/api/v1/portfolios/{pid}/summary", headers=h)
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["portfolio_ids"] == [pid]
    assert s["currency"] == "USD"
    expected = {
        "total_value": "13344.92",
        "holdings_value": "3473.00",
        "cash": "9871.92",
        "cost_basis": "1161.50",
        "unrealized_pl": "386.50",
        "realized_pl": "74.00",
        "income": "24.48",
        "expenses": "5.00",
        "net_contributions": "11000.00",
    }
    for field, amount in expected.items():
        assert s[field] == m(amount), field
    assert s["valued_positions"] == 3
    shares = {c["currency"]: (c["native"], c["value"], c["share_percent"]) for c in s["currencies"]}
    assert shares == {
        "EUR": (m("1099.00", "EUR"), m("1186.92"), "8.89"),
        "KES": (m("250000.00", "KES"), m("1925.00"), "14.43"),
        "USD": (m("10233.00"), m("10233.00"), "76.68"),
    }
    assert [a["id"] for a in s["unpriced_assets"]] == [assets["D"]]
    fresh = s["freshness"]
    assert fresh["stale_fx"] == ["KES"]
    assert fresh["unconverted_currencies"] == []
    assert fresh["complete"] is False
    assert datetime.fromisoformat(fresh["data_as_of"]) == NOW - timedelta(days=3)


async def test_the_consolidated_summary_adds_up_active_portfolios(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    db: asyncpg.Connection,
) -> None:
    h = two_users.bob.headers
    usd_pid, _ = await build_scenario(http, h, db)
    kes_pid = await portfolio(http, h, "KES")
    await post(http, h, kes_pid, posting("DEPOSIT", 1, "KES", gross_amount=m("5000.00", "KES")))
    archived = await portfolio(http, h, "USD")
    await post(http, h, archived, posting("DEPOSIT", 1, "USD", gross_amount=m("999.00")))
    await http.post(f"/api/v1/portfolios/{archived}/archive", headers=h)
    await rate(db, "USD", "EUR", "0.92", NOW - timedelta(hours=2))
    await rate(db, "KES", "EUR", "0.0071", NOW - timedelta(hours=2))

    r = await http.get(
        "/api/v1/portfolios/consolidated/summary", headers=h, params={"currency": "EUR"}
    )
    assert r.status_code == 200, r.text
    s = r.json()
    assert set(s["portfolio_ids"]) == {usd_pid, kes_pid}  # the archived one is left out
    assert s["currency"] == "EUR"
    # 13344.92 x 0.92 + 5000 x 0.0071 = 12277.3264 + 35.5
    assert s["total_value"] == m("12312.83", "EUR")
    assert s["net_contributions"] == m("10155.50", "EUR")  # 11000 x 0.92 + 35.5
    total = Decimal(s["total_value"]["amount"])
    parts = sum(Decimal(c["value"]["amount"]) for c in s["currencies"])
    assert abs(parts - total) <= Decimal("0.02")  # each part is rounded on its own
    assert sum(Decimal(c["share_percent"]) for c in s["currencies"]) == Decimal(100)

    default = await http.get("/api/v1/portfolios/consolidated/summary", headers=h)
    assert default.json()["currency"] == "USD"  # the user's base currency


async def test_an_empty_portfolio_has_zero_figures(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    h = two_users.alice.headers
    pid = await portfolio(http, h, "KES")
    s = (await http.get(f"/api/v1/portfolios/{pid}/summary", headers=h)).json()
    assert s["total_value"] == m("0.00", "KES")
    assert s["currencies"] == []
    assert s["freshness"]["complete"] is True


async def test_invalid_reporting_currency_is_refused(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    r = await http.get(
        "/api/v1/portfolios/consolidated/summary",
        headers=two_users.alice.headers,
        params={"currency": "eur"},
    )
    assert r.status_code == 422


async def test_bob_cannot_read_alices_summary(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    pid = await portfolio(http, two_users.alice.headers, "USD")
    await assert_hidden_from(http, two_users.bob, "GET", f"/api/v1/portfolios/{pid}/summary")
    consolidated = await http.get(
        "/api/v1/portfolios/consolidated/summary", headers=two_users.bob.headers
    )
    assert pid not in consolidated.json()["portfolio_ids"]
