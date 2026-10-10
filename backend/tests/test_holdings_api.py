"""Holdings through the API (P05-T05): cache kept in step with the ledger, date-ordered checks,
currency conversion, income, and cross-user isolation."""

import uuid
from collections.abc import AsyncIterator
from datetime import date, timedelta
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
DAY = date.today() - timedelta(days=30)


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


@pytest.fixture
async def stock(db: asyncpg.Connection) -> str:
    cls = await db.fetchval("SELECT id FROM asset_classes WHERE code = 'stock'")
    return str(
        await db.fetchval(
            "INSERT INTO assets (asset_class_id, symbol, name, currency) "
            "VALUES ($1, $2, $3, 'USD') RETURNING id",
            cls,
            uuid.uuid4().hex[:6].upper(),
            f"Holding Co {uuid.uuid4().hex[:4]}",
        )
    )


async def portfolio(http: httpx.AsyncClient, h: dict[str, str], currency: str = "USD") -> str:
    r = await http.post(
        "/api/v1/portfolios",
        headers=h,
        json={"name": f"H {uuid.uuid4().hex[:8]}", "base_currency": currency},
    )
    return str(r.json()["id"])


def m(amount: str, currency: str = "USD") -> dict[str, str]:
    return {"amount": amount, "currency": currency}


def trade(kind: str, asset: str, day: int, qty: str, gross: str, **extra: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "transaction_type": kind,
        "trade_date": (DAY + timedelta(days=day)).isoformat(),
        "asset_id": asset,
        "currency": "USD",
        "quantity": qty,
        "unit_price": m(format(Decimal(gross) / Decimal(qty), "f")),
        "gross_amount": m(gross),
    }
    body.update(extra)
    return body


async def post(
    http: httpx.AsyncClient, h: dict[str, str], pid: str, body: dict[str, Any]
) -> httpx.Response:
    return await http.post(f"/api/v1/portfolios/{pid}/transactions", headers=h, json=body)


async def holdings(
    http: httpx.AsyncClient, h: dict[str, str], pid: str, closed: bool = False
) -> list[dict[str, Any]]:
    r = await http.get(
        f"/api/v1/portfolios/{pid}/holdings", headers=h, params={"include_closed": closed}
    )
    assert r.status_code == 200, r.text
    return r.json()  # type: ignore[no-any-return]


async def test_holdings_follow_the_ledger(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    stock: str,
) -> None:
    h = two_users.alice.headers
    pid = await portfolio(http, h)
    assert (
        await post(http, h, pid, trade("BUY", stock, 1, "10", "1000", fees=m("10")))
    ).status_code == 201
    assert (
        await post(http, h, pid, trade("BUY", stock, 2, "5", "600", fees=m("5")))
    ).status_code == 201
    sale = trade("SELL", stock, 3, "6", "780", fees=m("6"), taxes=m("4"))
    assert (await post(http, h, pid, sale)).status_code == 201
    [held] = await holdings(http, h, pid)
    assert held["asset"]["id"] == stock
    assert held["quantity"] == "9"
    assert held["cost_basis"] == m("969.00")
    assert held["realized_pl"] == m("124.00")
    assert held["average_cost"] == m("107.66666667")
    assert held["income"] == m("0.00") and held["expenses"] == m("0.00")


async def test_a_sold_out_position_is_listed_only_when_asked(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    stock: str,
) -> None:
    h = two_users.alice.headers
    pid = await portfolio(http, h)
    await post(http, h, pid, trade("BUY", stock, 1, "3", "30"))
    await post(http, h, pid, trade("SELL", stock, 2, "3", "36"))
    assert await holdings(http, h, pid) == []
    [closed] = await holdings(http, h, pid, closed=True)
    assert closed["quantity"] == "0"
    assert closed["average_cost"] is None
    assert closed["realized_pl"] == m("6.00")


async def test_a_backdated_sale_needs_units_on_its_own_date(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    stock: str,
) -> None:
    """Units bought later do not cover an earlier sale, even when the total would."""
    h = two_users.alice.headers
    pid = await portfolio(http, h)
    await post(http, h, pid, trade("BUY", stock, 1, "10", "100"))
    await post(http, h, pid, trade("SELL", stock, 2, "10", "120"))
    await post(http, h, pid, trade("BUY", stock, 4, "10", "100"))
    r = await post(http, h, pid, trade("SELL", stock, 3, "5", "60"))  # nothing held on day 3
    assert r.status_code == 409
    early = await post(http, h, pid, trade("SELL", stock, 0, "1", "10"))  # before any purchase
    assert early.status_code == 409
    assert (await post(http, h, pid, trade("SELL", stock, 5, "5", "60"))).status_code == 201


async def test_reversals_rebuild_the_position(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    stock: str,
) -> None:
    h = two_users.alice.headers
    pid = await portfolio(http, h)
    first = (await post(http, h, pid, trade("BUY", stock, 1, "10", "100"))).json()
    second = (await post(http, h, pid, trade("BUY", stock, 2, "10", "200"))).json()
    await post(http, h, pid, trade("SELL", stock, 3, "5", "75"))
    url = f"/api/v1/portfolios/{pid}/transactions"
    assert (
        await http.post(f"{url}/{second['id']}/reversal", headers=h, json={})
    ).status_code == 201
    [held] = await holdings(http, h, pid)
    assert (held["quantity"], held["cost_basis"], held["realized_pl"]) == (
        "5",
        m("50.00"),
        m("25.00"),
    )
    # The first purchase covers the sale: reversing it is refused.
    assert (await http.post(f"{url}/{first['id']}/reversal", headers=h, json={})).status_code == 409


async def test_a_position_whose_entries_are_all_reversed_disappears(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    stock: str,
) -> None:
    h = two_users.alice.headers
    pid = await portfolio(http, h)
    bought = (await post(http, h, pid, trade("BUY", stock, 1, "2", "20"))).json()
    await http.post(
        f"/api/v1/portfolios/{pid}/transactions/{bought['id']}/reversal", headers=h, json={}
    )
    assert await holdings(http, h, pid, closed=True) == []


async def test_cost_is_in_the_portfolio_currency_at_each_postings_rate(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    stock: str,
) -> None:
    h = two_users.alice.headers
    pid = await portfolio(http, h, "KES")
    buy = trade("BUY", stock, 1, "10", "200", fees=m("2"), fx_rate_to_portfolio_currency="130")
    sell = trade("SELL", stock, 2, "4", "100", fees=m("1"), fx_rate_to_portfolio_currency="125.5")
    assert (await post(http, h, pid, buy)).status_code == 201
    assert (await post(http, h, pid, sell)).status_code == 201
    [held] = await holdings(http, h, pid)
    # cost 202 x 130 = 26260 for 10; sell 4 removes 10504; proceeds 99 x 125.5 = 12424.5
    assert held["cost_basis"] == m("15756.00", "KES")
    assert held["realized_pl"] == m("1920.50", "KES")


async def test_income_and_withholding_are_tracked(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    stock: str,
) -> None:
    h = two_users.alice.headers
    pid = await portfolio(http, h)
    await post(http, h, pid, trade("BUY", stock, 1, "10", "100"))
    dividend = {
        "transaction_type": "DIVIDEND",
        "trade_date": (DAY + timedelta(days=2)).isoformat(),
        "asset_id": stock,
        "currency": "USD",
        "gross_amount": m("15.00"),
        "taxes": m("2.25"),
    }
    assert (await post(http, h, pid, dividend)).status_code == 201
    [held] = await holdings(http, h, pid)
    assert (held["income"], held["expenses"], held["cost_basis"]) == (
        m("15.00"),
        m("2.25"),
        m("100.00"),
    )


async def test_bob_cannot_read_alices_holdings(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    stock: str,
) -> None:
    h = two_users.alice.headers
    pid = await portfolio(http, h)
    await post(http, h, pid, trade("BUY", stock, 1, "1", "10"))
    await assert_hidden_from(http, two_users.bob, "GET", f"/api/v1/portfolios/{pid}/holdings")


async def test_holdings_carry_their_latest_valuation(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    stock: str,
    db: asyncpg.Connection,
) -> None:
    from datetime import UTC, datetime, timedelta

    h = two_users.alice.headers
    pid = await portfolio(http, h)
    await post(http, h, pid, trade("BUY", stock, 1, "10", "100"))
    unpriced = (await holdings(http, h, pid))[0]
    assert (unpriced["value"], unpriced["native_value"], unpriced["value_source"]) == (
        None,
        None,
        None,
    )

    def valuation(asset: str, amount: str, ccy: str) -> dict[str, Any]:
        return {
            "asset_id": asset,
            "value": m(amount, ccy),
            "as_of": datetime.now(UTC).replace(microsecond=0).isoformat(),
            "source": "test",
        }

    eur_rate = uuid.uuid4().hex[:2].upper()  # a currency no other test uses
    code = "Z" + "".join(c for c in eur_rate if c.isalpha()).ljust(2, "Q")[:2]
    await http.post(
        f"/api/v1/portfolios/{pid}/valuations", headers=h, json=valuation(stock, "1500.00", "USD")
    )
    [held] = await holdings(http, h, pid)
    assert held["value"] == m("1500.00")
    assert held["native_value"] == m("1500.00")
    assert held["value_source"] == "valuation"
    assert held["value_as_of"] is not None

    # A valuation in a currency without a rate: native value only.
    second = await db.fetchval(
        "INSERT INTO assets (asset_class_id, name, currency) "
        "SELECT id, 'Foreign', $1 FROM asset_classes WHERE code = 'stock' RETURNING id",
        code,
    )
    await post(http, h, pid, trade("BUY", str(second), 1, "1", "10"))
    earlier = (datetime.now(UTC).replace(microsecond=0) - timedelta(minutes=1)).isoformat()
    first = await http.post(
        f"/api/v1/portfolios/{pid}/valuations",
        headers=h,
        json=valuation(str(second), "77.00", code) | {"as_of": earlier},
    )
    assert first.status_code == 201, first.text
    foreign = next(x for x in await holdings(http, h, pid) if x["asset"]["id"] == str(second))
    assert foreign["value"] is None
    assert foreign["native_value"] == m("77.00", code)

    # With a rate it is converted at that rate (1 unit = 1.25 USD) and rounded half-up.
    await db.execute(
        "INSERT INTO fx_rates (base_currency, quote_currency, rate, provider, rate_timestamp, "
        "retrieved_at) VALUES ($1, 'USD', 1.25, 'test', now(), now())",
        code,
    )
    newer = await http.post(
        f"/api/v1/portfolios/{pid}/valuations",
        headers=h,
        json=valuation(str(second), "80.10", code),
    )
    assert newer.status_code == 201, newer.text
    foreign = next(x for x in await holdings(http, h, pid) if x["asset"]["id"] == str(second))
    assert foreign["value"] == m("100.13")  # 80.10 x 1.25 = 100.125
    assert foreign["native_value"] == m("80.10", code)

    # A closed position is not valued, even with a valuation.
    await post(http, h, pid, trade("SELL", stock, 2, "10", "120"))
    closed = next(x for x in await holdings(http, h, pid, closed=True) if x["asset"]["id"] == stock)
    assert closed["value"] is None and closed["value_source"] is None
