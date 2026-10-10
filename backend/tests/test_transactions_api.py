"""Ledger API (P05-T04): posting, idempotency, positions, reversals, listing, audit, isolation."""

import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import date, timedelta
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
TODAY = date.today()


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
            "VALUES ($1, $2, 'Test Corp', 'USD') RETURNING id",
            cls,
            uuid.uuid4().hex[:8].upper(),
        )
    )


async def portfolio(http: httpx.AsyncClient, headers: dict[str, str], currency: str = "USD") -> str:
    r = await http.post(
        "/api/v1/portfolios",
        headers=headers,
        json={"name": f"P {uuid.uuid4().hex[:8]}", "base_currency": currency},
    )
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


def money(amount: str, currency: str = "USD") -> dict[str, str]:
    return {"amount": amount, "currency": currency}


def buy(asset: str, qty: str = "10", price: str = "25.00", **extra: Any) -> dict[str, Any]:
    return {
        "transaction_type": "BUY",
        "trade_date": TODAY.isoformat(),
        "asset_id": asset,
        "currency": "USD",
        "quantity": qty,
        "unit_price": money(price),
        **extra,
    }


def sell(asset: str, qty: str, price: str = "30.00") -> dict[str, Any]:
    return {**buy(asset, qty, price), "transaction_type": "SELL"}


def deposit(amount: str = "1000.00", **extra: Any) -> dict[str, Any]:
    return {
        "transaction_type": "DEPOSIT",
        "trade_date": TODAY.isoformat(),
        "currency": "USD",
        "gross_amount": money(amount),
        **extra,
    }


def tx_url(pid: str, tid: str | None = None) -> str:
    base = f"/api/v1/portfolios/{pid}/transactions"
    return f"{base}/{tid}" if tid else base


async def post(
    http: httpx.AsyncClient, headers: dict[str, str], pid: str, body: dict[str, Any], **kw: Any
) -> httpx.Response:
    return await http.post(tx_url(pid), headers=headers, json=body, **kw)


# --------------------------------------------------------------------------------- posting


async def test_a_buy_is_posted_with_derived_gross_and_string_money(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    stock: str,
) -> None:
    h = two_users.alice.headers
    pid = await portfolio(http, h)
    r = await post(http, h, pid, buy(stock, "3", "10.005", fees=money("1.50"), note="first lot"))
    assert r.status_code == 201, r.text
    t = r.json()
    assert t["gross_amount"] == {"amount": "30.02", "currency": "USD"}  # 30.015 rounds half up
    assert t["fees"] == {"amount": "1.50", "currency": "USD"}
    assert t["taxes"] == {"amount": "0.00", "currency": "USD"}
    assert t["quantity"] == "3"
    assert t["unit_price"] == {"amount": "10.005", "currency": "USD"}
    assert t["fx_rate_to_portfolio_currency"] == "1"
    assert t["source"] == "manual"
    assert t["reverses_transaction_id"] is None and t["reversed_by_transaction_id"] is None
    assert (await http.get(tx_url(pid, t["id"]), headers=h)).json() == t


async def test_a_foreign_currency_posting_keeps_its_currency_and_rate(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    h = two_users.alice.headers
    pid = await portfolio(http, h, "KES")
    body = deposit("100.00", fx_rate_to_portfolio_currency="129.123456789012")
    r = await post(http, h, pid, body)
    assert r.status_code == 201, r.text
    assert r.json()["currency"] == "USD"
    assert r.json()["fx_rate_to_portfolio_currency"] == "129.123456789012"
    assert r.json()["fx_rate_source"] == "user"
    missing = await post(http, h, pid, deposit("100.00"))
    assert missing.status_code == 422
    assert "fx_rate_to_portfolio_currency" in missing.json()["detail"]


@pytest.mark.parametrize(
    "change",
    [
        {"gross_amount": {"amount": 1000, "currency": "USD"}},  # a JSON number
        {"gross_amount": money("1e3")},
        {"gross_amount": money("100.001")},
        {"gross_amount": money("-5.00")},
        {"currency": "usd"},
        {"transaction_type": "GIFT"},
        {"asset_id": str(uuid.uuid4())},  # deposits carry no asset
        {"trade_date": (TODAY + timedelta(days=5)).isoformat()},
        {"fx_rate_to_portfolio_currency": 1.0},
        {"fx_rate_as_of": "2026-10-01T10:00:00"},  # no time zone
        {"user_id": str(uuid.uuid4())},
        {"source": "import"},
        {"idempotency_key": "in-the-body"},
    ],
)
async def test_invalid_postings_are_refused(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    change: dict[str, Any],
) -> None:
    pid = await portfolio(http, two_users.alice.headers)
    r = await post(http, two_users.alice.headers, pid, {**deposit(), **change})
    assert r.status_code == 422, (change, r.text)


async def test_assets_must_be_usable_by_the_owner(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    bobs = await http.post(
        "/api/v1/assets",
        headers=two_users.bob.headers,
        json={"asset_class": "private_business", "name": "Bob Ltd", "currency": "USD"},
    )
    pid = await portfolio(http, two_users.alice.headers)
    for asset in (bobs.json()["id"], str(uuid.uuid4())):
        r = await post(http, two_users.alice.headers, pid, buy(asset))
        assert r.status_code == 422
        assert r.json()["detail"] == "asset_id: no such asset"  # same answer: no existence leak


# ----------------------------------------------------------------------------- positions


async def test_sales_cannot_exceed_the_position(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    stock: str,
) -> None:
    h = two_users.alice.headers
    pid = await portfolio(http, h)
    assert (await post(http, h, pid, sell(stock, "1"))).status_code == 409
    await post(http, h, pid, buy(stock, "10"))
    assert (await post(http, h, pid, sell(stock, "4"))).status_code == 201
    assert (await post(http, h, pid, sell(stock, "6.000000000001"))).status_code == 409
    assert (await post(http, h, pid, sell(stock, "6"))).status_code == 201
    out = {**buy(stock, "1"), "transaction_type": "TRANSFER_OUT", "gross_amount": money("0")}
    del out["unit_price"]
    assert (await post(http, h, pid, out)).status_code == 409


async def test_concurrent_sales_are_applied_one_at_a_time(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    stock: str,
) -> None:
    h = two_users.alice.headers
    pid = await portfolio(http, h)
    await post(http, h, pid, buy(stock, "10"))
    results = await asyncio.gather(*[post(http, h, pid, sell(stock, "6")) for _ in range(3)])
    assert sorted(r.status_code for r in results) == [201, 409, 409]


# --------------------------------------------------------------------------- idempotency


async def test_an_idempotent_retry_returns_the_original_entry(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    db: asyncpg.Connection,
) -> None:
    h = two_users.alice.headers
    pid = await portfolio(http, h)
    key = {"Idempotency-Key": f"pay-{uuid.uuid4()}"}
    first = await post(http, {**h, **key}, pid, deposit("250.00"))
    again = await post(http, {**h, **key}, pid, deposit("250.00"))
    assert first.status_code == 201 and again.status_code == 200
    assert again.headers["Idempotent-Replayed"] == "true"
    assert again.json() == first.json()
    other = await post(http, {**h, **key}, pid, deposit("999.00"))
    assert other.status_code == 409
    count = await db.fetchval(
        "SELECT count(*) FROM transactions WHERE portfolio_id = $1", uuid.UUID(pid)
    )
    assert count == 1
    events = await db.fetchval(
        "SELECT count(*) FROM audit_events WHERE resource_id = $1", first.json()["id"]
    )
    assert events == 1  # the replay is not a second posting


async def test_concurrent_retries_with_one_key_post_once(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    h = {**two_users.alice.headers, "Idempotency-Key": f"k-{uuid.uuid4()}"}
    pid = await portfolio(http, two_users.alice.headers)
    results = await asyncio.gather(*[post(http, h, pid, deposit("10.00")) for _ in range(4)])
    assert sorted(r.status_code for r in results) == [200, 200, 200, 201]
    assert len({r.json()["id"] for r in results}) == 1


async def test_bad_idempotency_keys_are_refused(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    pid = await portfolio(http, two_users.alice.headers)
    for key in ("x" * 129, "has space"):
        r = await post(http, {**two_users.alice.headers, "Idempotency-Key": key}, pid, deposit())
        assert r.status_code == 422, key


# ----------------------------------------------------------------------------- reversals


async def test_a_reversal_cancels_an_entry_once_and_is_linked_both_ways(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    stock: str,
    db: asyncpg.Connection,
) -> None:
    h = two_users.alice.headers
    pid = await portfolio(http, h)
    original = (await post(http, h, pid, buy(stock, "5"))).json()
    rev = await http.post(
        f"{tx_url(pid, original['id'])}/reversal", headers=h, json={"note": "wrong price"}
    )
    assert rev.status_code == 201, rev.text
    r = rev.json()
    assert r["reverses_transaction_id"] == original["id"]
    for field in ("transaction_type", "trade_date", "asset_id", "quantity", "gross_amount"):
        assert r[field] == original[field]
    assert r["note"] == "wrong price"
    reread = (await http.get(tx_url(pid, original["id"]), headers=h)).json()
    assert reread["reversed_by_transaction_id"] == r["id"]
    # The position is back to zero: nothing left to sell.
    assert (await post(http, h, pid, sell(stock, "1"))).status_code == 409
    again = await http.post(f"{tx_url(pid, original['id'])}/reversal", headers=h, json={})
    assert again.status_code == 409
    of_reversal = await http.post(f"{tx_url(pid, r['id'])}/reversal", headers=h, json={})
    assert of_reversal.status_code == 409
    actions = await db.fetch(
        "SELECT action FROM audit_events WHERE resource_id = ANY($1::text[])",
        [original["id"], r["id"]],
    )
    assert sorted(a["action"] for a in actions) == [
        "transactions.transaction.posted",
        "transactions.transaction.reversed",
    ]


async def test_a_reversal_cannot_leave_a_negative_position(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    stock: str,
) -> None:
    h = two_users.alice.headers
    pid = await portfolio(http, h)
    bought = (await post(http, h, pid, buy(stock, "10"))).json()
    sold = (await post(http, h, pid, sell(stock, "4"))).json()
    blocked = await http.post(f"{tx_url(pid, bought['id'])}/reversal", headers=h, json={})
    assert blocked.status_code == 409
    assert (
        await http.post(f"{tx_url(pid, sold['id'])}/reversal", headers=h, json={})
    ).status_code == 201
    assert (
        await http.post(f"{tx_url(pid, bought['id'])}/reversal", headers=h, json={})
    ).status_code == 201


async def test_a_reversal_retry_with_its_key_is_idempotent(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    h = two_users.alice.headers
    pid = await portfolio(http, h)
    original = (await post(http, h, pid, deposit())).json()
    key = {**h, "Idempotency-Key": f"rev-{uuid.uuid4()}"}
    first = await http.post(f"{tx_url(pid, original['id'])}/reversal", headers=key, json={})
    again = await http.post(f"{tx_url(pid, original['id'])}/reversal", headers=key, json={})
    assert (first.status_code, again.status_code) == (201, 200)
    assert again.json()["id"] == first.json()["id"]


async def test_posted_entries_cannot_be_edited_or_deleted(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    h = two_users.alice.headers
    pid = await portfolio(http, h)
    tid = (await post(http, h, pid, deposit())).json()["id"]
    for method in ("PUT", "PATCH", "DELETE"):
        r = await http.request(method, tx_url(pid, tid), headers=h, json={"note": "x"})
        assert r.status_code == 405, method


async def test_an_archived_portfolio_takes_no_entries(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    h = two_users.alice.headers
    pid = await portfolio(http, h)
    tid = (await post(http, h, pid, deposit())).json()["id"]
    await http.post(f"/api/v1/portfolios/{pid}/archive", headers=h)
    assert (await post(http, h, pid, deposit())).status_code == 409
    assert (await http.post(f"{tx_url(pid, tid)}/reversal", headers=h, json={})).status_code == 409
    assert (await http.get(tx_url(pid, tid), headers=h)).status_code == 200  # still readable


# ------------------------------------------------------------------------------- listing


async def test_listing_is_newest_first_filtered_and_paginated(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    stock: str,
) -> None:
    h = two_users.alice.headers
    pid = await portfolio(http, h)
    ids = []
    for days in (5, 4, 3, 2, 1):
        when = (TODAY - timedelta(days=days)).isoformat()
        ids.append((await post(http, h, pid, deposit(trade_date=when))).json()["id"])
    await post(http, h, pid, buy(stock, "1", trade_date=(TODAY - timedelta(days=3)).isoformat()))
    seen: list[str] = []
    cursor = None
    while True:
        params: dict[str, Any] = {"limit": 2, "transaction_type": "DEPOSIT"}
        if cursor:
            params["cursor"] = cursor
        page = (await http.get(tx_url(pid), headers=h, params=params)).json()
        seen += [t["id"] for t in page["items"]]
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert seen == list(reversed(ids))
    window = await http.get(
        tx_url(pid),
        headers=h,
        params={
            "from_date": (TODAY - timedelta(days=4)).isoformat(),
            "to_date": (TODAY - timedelta(days=2)).isoformat(),
        },
    )
    assert len(window.json()["items"]) == 4  # three deposits and the buy
    by_asset = await http.get(tx_url(pid), headers=h, params={"asset_id": stock})
    assert [t["transaction_type"] for t in by_asset.json()["items"]] == ["BUY"]
    bad = await http.get(tx_url(pid), headers=h, params={"cursor": "not-a-cursor"})
    assert bad.status_code == 422


async def test_an_entry_is_only_found_under_its_own_portfolio(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    h = two_users.alice.headers
    first, second = await portfolio(http, h), await portfolio(http, h)
    tid = (await post(http, h, first, deposit())).json()["id"]
    assert (await http.get(tx_url(second, tid), headers=h)).status_code == 404
    reversal = await http.post(f"{tx_url(second, tid)}/reversal", headers=h, json={})
    assert reversal.status_code == 404


# ------------------------------------------------------------------------- others cannot


async def test_bob_cannot_list_alices_ledger(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    pid = await portfolio(http, two_users.alice.headers)
    await post(http, two_users.alice.headers, pid, deposit())
    await assert_hidden_from(http, two_users.bob, "GET", tx_url(pid))


async def test_bob_cannot_post_to_alices_portfolio(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    db: asyncpg.Connection,
) -> None:
    pid = await portfolio(http, two_users.alice.headers)
    await assert_hidden_from(http, two_users.bob, "POST", tx_url(pid), json=deposit())
    count = await db.fetchval(
        "SELECT count(*) FROM transactions WHERE portfolio_id = $1", uuid.UUID(pid)
    )
    assert count == 0


async def test_bob_cannot_read_alices_transaction(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    pid = await portfolio(http, two_users.alice.headers)
    tid = (await post(http, two_users.alice.headers, pid, deposit())).json()["id"]
    await assert_hidden_from(http, two_users.bob, "GET", tx_url(pid, tid))


async def test_bob_cannot_reverse_alices_transaction(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    db: asyncpg.Connection,
) -> None:
    pid = await portfolio(http, two_users.alice.headers)
    tid = (await post(http, two_users.alice.headers, pid, deposit())).json()["id"]
    await assert_hidden_from(http, two_users.bob, "POST", f"{tx_url(pid, tid)}/reversal", json={})
    reversed_ = await db.fetchval(
        "SELECT count(*) FROM transactions WHERE reverses_transaction_id = $1", uuid.UUID(tid)
    )
    assert reversed_ == 0


async def test_a_reversal_itself_cannot_be_reversed(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    # A deposit has no position, so only the "not a reversal" rule can refuse this.
    h = two_users.alice.headers
    pid = await portfolio(http, h)
    original = (await post(http, h, pid, deposit())).json()
    rev = (await http.post(f"{tx_url(pid, original['id'])}/reversal", headers=h, json={})).json()
    r = await http.post(f"{tx_url(pid, rev['id'])}/reversal", headers=h, json={})
    assert r.status_code == 409
    assert "cannot itself be reversed" in r.json()["detail"]
