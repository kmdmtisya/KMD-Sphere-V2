"""Analytics API (P06-T09): performance, allocation, income, risk, income summary and dashboard
through the API, with the per-user cache and its invalidation."""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

import asyncpg
import httpx
import pytest
from fastapi import FastAPI

from app.core.cache import KEY_PREFIX, MemoryCacheStore
from app.core.config import Settings
from app.main import create_app
from tests import auth_helpers as ah
from tests.authz_harness import TwoUsers, assert_hidden_from, make_user, two_users  # noqa: F401
from tests.db_fixtures import migrated_settings  # noqa: F401

pytestmark = [pytest.mark.integration, pytest.mark.security]
NOW = datetime.now(UTC).replace(microsecond=0)
TODAY = NOW.date()
DAY = TODAY - timedelta(days=100)


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


class Book:
    def __init__(self, http: httpx.AsyncClient, h: dict[str, str]) -> None:
        self.http, self.h = http, h

    async def portfolio(self, currency: str = "USD") -> str:
        body = {"name": f"A {uuid.uuid4().hex[:8]}", "base_currency": currency}
        r = await self.http.post("/api/v1/portfolios", headers=self.h, json=body)
        assert r.status_code == 201, r.text
        return str(r.json()["id"])

    async def asset(self, cls: str = "stock", **fields: Any) -> str:
        body = {"asset_class": cls, "name": f"{cls} {uuid.uuid4().hex[:6]}", "currency": "USD"}
        r = await self.http.post("/api/v1/assets", headers=self.h, json=body | fields)
        assert r.status_code == 201, r.text
        return str(r.json()["id"])

    async def post(self, pid: str, kind: str, on: date = DAY, **fields: Any) -> dict[str, Any]:
        body = {"transaction_type": kind, "trade_date": on.isoformat(), "currency": "USD"}
        r = await self.http.post(f"/api/v1/portfolios/{pid}/transactions", headers=self.h,
                                 json=body | fields)  # fmt: skip
        assert r.status_code == 201, r.text
        return dict(r.json())

    async def value(
        self, pid: str, asset: str, amount: str, on: date = TODAY, hour: int = 1
    ) -> None:
        # Never in the future: shortly after midnight UTC, 01:00 today has not happened yet.
        as_of = min(datetime.combine(on, time(hour), tzinfo=UTC), NOW - timedelta(minutes=1))
        body = {"asset_id": asset, "value": m(amount), "source": "test",
                "as_of": as_of.isoformat()}  # fmt: skip
        r = await self.http.post(f"/api/v1/portfolios/{pid}/valuations", headers=self.h, json=body)
        assert r.status_code == 201, r.text

    async def get(self, path: str) -> dict[str, Any]:
        r = await self.http.get(path, headers=self.h)
        assert r.status_code == 200, r.text
        return dict(r.json())


async def standard_portfolio(book: Book) -> tuple[str, str]:
    """5000 deposited; 40 shares bought for 4004 (incl. 4 fee); 10 sold for 1200; a 30
    dividend with 4.50 tax; a 2 fee; the 30 remaining shares valued at 3300."""
    pid, stock = await book.portfolio(), await book.asset(country="US", metadata={"sector": "Tech"})
    await book.post(pid, "DEPOSIT", gross_amount=m("5000.00"))
    await book.post(pid, "BUY", asset_id=stock, quantity="40", unit_price=m("100"), fees=m("4.00"))
    await book.post(pid, "SELL", DAY + timedelta(days=10), asset_id=stock, quantity="10",
                    unit_price=m("120"))  # fmt: skip
    await book.post(pid, "DIVIDEND", DAY + timedelta(days=20), asset_id=stock,
                    gross_amount=m("30.00"), taxes=m("4.50"))  # fmt: skip
    await book.post(pid, "FEE", DAY + timedelta(days=30), gross_amount=m("2.00"))
    await book.value(pid, stock, "3300.00")
    return pid, stock


# ------------------------------------------------------------------------------------- figures


async def test_performance(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    book = Book(http, two_users.alice.headers)
    pid, _ = await standard_portfolio(book)
    p = await book.get(f"/api/v1/portfolios/{pid}/performance")
    # Value 3300 + cash (5000 - 4004 + 1200 + 25.50 - 2 = 2219.50) = 5519.50.
    assert p["total_value"] == m("5519.50")
    assert (p["contributions"], p["withdrawals"], p["net_invested"]) == (
        m("5000.00"), m("0.00"), m("5000.00"))  # fmt: skip
    assert p["profit_loss"] == m("519.50") and p["return_percent"] == "10.39"
    assert p["realized_pl"] == m("199.00")  # 1200 - 10 x 100.10
    assert p["unrealized_pl"] == m("297.00")  # 3300 - 30 x 100.10
    assert (p["income"], p["expenses"]) == (m("30.00"), m("6.50"))
    mw = p["money_weighted"]
    assert mw["status"] == "ok" and mw["unique"] is True
    assert float(mw["annual_return_percent"]) > 10  # 10.39% in 100 days, annualised
    assert p["complete"] is True and p["first_flow"] == DAY.isoformat()
    assert "not a reliable indicator" in p["notice"]


async def test_allocation(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    book = Book(http, two_users.alice.headers)
    pid, stock = await standard_portfolio(book)
    a = await book.get(f"/api/v1/portfolios/{pid}/allocation")
    assert a["total"] == m("5519.50")
    assert a["asset_class"]["slices"] == [
        {"key": "stock", "value": m("3300.00"), "weight_percent": "59.79", "parts": 1},
        {"key": "cash", "value": m("2219.50"), "weight_percent": "40.21", "parts": 1},
    ]
    assert [s["key"] for s in a["sector"]["slices"]] == ["Tech", None]
    assert [s["key"] for s in a["country"]["slices"]] == ["US", None]
    assert a["currency_exposure"]["slices"][0]["key"] == "USD"
    c = a["concentration"]
    assert c["positions"] == 2 and c["largest"] == stock
    assert (c["top_1_percent"], c["top_3_percent"]) == ("59.79", "100")
    assert c["hhi"] == "0.5192"  # 0.597880^2 + 0.402120^2 = 0.519161
    assert c["effective_positions"] == "1.93"
    assert a["complete"] is True and a["unpriced_assets"] == 0


async def test_income(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    book = Book(http, two_users.alice.headers)
    pid, stock = await standard_portfolio(book)
    i = await book.get(f"/api/v1/portfolios/{pid}/income")
    assert i["trailing_12m"] == {"gross": m("30.00"), "fees": m("0.00"), "taxes": m("4.50"),
                                 "net": m("25.50"), "payments": 1}  # fmt: skip
    assert (i["yearly"], i["monthly"]) == (m("25.50"), m("2.13"))
    assert i["portfolio_yield_percent"] == "0.54"  # 30 / 5519.50
    assert len(i["months"]) == 12 and i["years"][-1]["totals"]["gross"] == m("30.00")
    [row] = i["by_asset"]
    assert row["asset_id"] == stock
    assert (row["current_yield_percent"], row["yield_on_cost_percent"]) == ("0.91", "1")
    assert [t["income_type"] for t in i["by_type"]] == ["DIVIDEND"]


async def test_risk(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    book = Book(http, two_users.alice.headers)
    pid, _ = await standard_portfolio(book)
    r = await book.get(f"/api/v1/portfolios/{pid}/risk?frequency=weekly")
    assert r["frequency"] == "weekly" and r["start"] == DAY.isoformat()
    assert r["end"] == TODAY.isoformat() and r["points"][0]["on"] == DAY.isoformat()
    # The stock has a value only from today: the earlier points are incomplete.
    assert r["status"] == "incomplete_data" and r["incomplete_points"] > 0
    assert r["volatility_percent"] is None and r["max_drawdown"] is None
    assert r["points"][-1] == {"on": TODAY.isoformat(), "value": m("5519.50"), "complete": True}
    bad = await http.get(f"/api/v1/portfolios/{pid}/risk?end={TODAY + timedelta(days=1)}",
                         headers=book.h)  # fmt: skip
    assert bad.status_code == 422
    too_many = await http.get(
        f"/api/v1/portfolios/{pid}/risk?frequency=daily&start={TODAY - timedelta(days=2000)}",
        headers=book.h,
    )
    assert too_many.status_code == 422


async def test_income_summary_and_dashboard(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    book = Book(http, two_users.alice.headers)
    pid, _ = await standard_portfolio(book)
    other = await book.portfolio()
    await book.post(other, "DEPOSIT", gross_amount=m("1000.00"))
    await book.post(other, "INTEREST", gross_amount=m("12.00"))
    s = await book.get("/api/v1/income/summary")
    assert (s["yearly"], s["yearly_gross"], s["monthly"]) == (m("37.50"), m("42.00"), m("3.13"))
    assert {line["portfolio_id"] for line in s["portfolios"]} == {pid, other}
    assert s["complete"] is True and s["unconverted_currencies"] == []

    goal = {"name": "House", "target": m("1000000.00"),
            "target_date": (TODAY + timedelta(days=3650)).isoformat(),
            "assumptions": {"contribution": m("100.00"), "returns": {"base": "0"}}}  # fmt: skip
    assert (await http.post("/api/v1/goals", headers=book.h, json=goal)).status_code == 201
    loan = {"name": "Car", "liability_type": "car_loan", "balance": m("500.00"),
            "balance_as_of": TODAY.isoformat()}  # fmt: skip
    assert (await http.post("/api/v1/liabilities", headers=book.h, json=loan)).status_code == 201
    d = await book.get("/api/v1/dashboard")
    assert d["currency"] == "USD"
    # Assets 5519.50 + 1012.00; minus the 500 car loan.
    assert d["net_worth"] == {"assets": m("6531.50"), "liabilities": m("500.00"),
                              "net_worth": m("6031.50")}  # fmt: skip
    assert d["income"] == {"monthly": m("3.13"), "yearly": m("37.50")}
    assert d["goals"] == {"on_track": 0, "total": 1} and d["complete"] is True


# --------------------------------------------------------------------------------------- cache


def cache_keys(app: FastAPI) -> list[str]:
    store = app.state.response_cache._store
    assert isinstance(store, MemoryCacheStore)
    return store.keys()


async def test_answers_are_cached_per_user(
    app: FastAPI,
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    db: asyncpg.Connection,
) -> None:
    book = Book(http, two_users.alice.headers)
    pid, stock = await standard_portfolio(book)
    first = await book.get(f"/api/v1/portfolios/{pid}/performance")
    assert await book.get("/api/v1/dashboard") == await book.get("/api/v1/dashboard")
    # A change made behind the API's back (no write request) is not seen until invalidation:
    # the answer comes from the cache.
    await db.execute("UPDATE valuations SET value = 99999 WHERE asset_id = $1", uuid.UUID(stock))
    assert await book.get(f"/api/v1/portfolios/{pid}/performance") == first
    mine = [k for k in cache_keys(app) if k.startswith(f"{KEY_PREFIX}{two_users.alice.id}:")]
    assert any(":performance:" in k for k in mine)


@pytest.mark.parametrize(
    "write",
    ["transaction", "reversal", "valuation", "liability", "goal", "portfolio"],
)
async def test_any_write_by_the_user_invalidates(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    db: asyncpg.Connection,
    write: str,
) -> None:
    book = Book(http, two_users.alice.headers)
    pid, stock = await standard_portfolio(book)
    before = await book.get("/api/v1/dashboard")
    if write == "transaction":
        await book.post(pid, "DEPOSIT", gross_amount=m("100.00"))
    elif write == "reversal":
        deposit = await book.post(pid, "DEPOSIT", gross_amount=m("100.00"))
        before = await book.get("/api/v1/dashboard")
        r = await http.post(f"/api/v1/portfolios/{pid}/transactions/{deposit['id']}/reversal",
                            headers=book.h, json={})  # fmt: skip
        assert r.status_code == 201
    elif write == "valuation":
        await book.value(pid, stock, "3400.00", TODAY, hour=0)
    elif write == "liability":
        loan = {"name": "L", "liability_type": "other", "balance": m("100.00"),
                "balance_as_of": TODAY.isoformat()}  # fmt: skip
        assert (
            await http.post("/api/v1/liabilities", headers=book.h, json=loan)
        ).status_code == 201
    elif write == "goal":
        goal = {"name": "G", "target": m("10.00"),
                "target_date": (TODAY + timedelta(days=400)).isoformat(),
                "assumptions": {"contribution": m("0.00"), "returns": {"base": "0"}}}  # fmt: skip
        assert (await http.post("/api/v1/goals", headers=book.h, json=goal)).status_code == 201
    else:
        r = await http.post(f"/api/v1/portfolios/{pid}/archive", headers=book.h)
        assert r.status_code == 200
    after = await book.get("/api/v1/dashboard")
    # Recomputed, not served from the cache (a cached answer keeps its as_of).
    assert after["as_of"] != before["as_of"]
    assert await book.get("/api/v1/dashboard") == after  # and cached again


async def test_a_failed_write_does_not_invalidate(
    app: FastAPI,
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    db: asyncpg.Connection,
) -> None:
    book = Book(http, two_users.alice.headers)
    pid, stock = await standard_portfolio(book)
    first = await book.get(f"/api/v1/portfolios/{pid}/performance")
    await db.execute("UPDATE valuations SET value = 1 WHERE asset_id = $1", uuid.UUID(stock))
    bad = await http.post(f"/api/v1/portfolios/{pid}/transactions", headers=book.h,
                          json={"transaction_type": "DEPOSIT"})  # fmt: skip
    assert bad.status_code == 422
    forecast = await http.post("/api/v1/forecasts/compound", headers=book.h, json={
        "initial_investment": m("1.00"), "contribution": m("0.00"),
        "annual_return_percent": "1", "years": 1})  # fmt: skip
    assert forecast.status_code == 200
    assert await book.get(f"/api/v1/portfolios/{pid}/performance") == first


async def test_another_users_write_does_not_invalidate_mine(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    db: asyncpg.Connection,
) -> None:
    alice, bob = Book(http, two_users.alice.headers), Book(http, two_users.bob.headers)
    pid, stock = await standard_portfolio(alice)
    first = await alice.get(f"/api/v1/portfolios/{pid}/performance")
    await db.execute("UPDATE valuations SET value = 1 WHERE asset_id = $1", uuid.UUID(stock))
    await bob.post(await bob.portfolio(), "DEPOSIT", gross_amount=m("1.00"))
    assert await alice.get(f"/api/v1/portfolios/{pid}/performance") == first


async def test_the_cache_never_answers_for_another_user(
    app: FastAPI,
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    alice = Book(http, two_users.alice.headers)
    pid, _ = await standard_portfolio(alice)
    for kind in ("performance", "allocation", "income", "risk"):
        assert (
            await http.get(f"/api/v1/portfolios/{pid}/{kind}", headers=alice.h)
        ).status_code == 200
        bob = await http.get(f"/api/v1/portfolios/{pid}/{kind}", headers=two_users.bob.headers)
        assert bob.status_code == 404, kind
    assert not [k for k in cache_keys(app) if k.startswith(f"{KEY_PREFIX}{two_users.bob.id}:")]
    # Bob's own dashboard is his, even with Alice's figures cached.
    d = await Book(http, two_users.bob.headers).get("/api/v1/dashboard")
    assert d["net_worth"]["assets"] == m("0.00")


# ------------------------------------------------------------------------------ ownership (IDOR)


async def _hidden(http: httpx.AsyncClient, users: TwoUsers, kind: str) -> None:
    pid, _ = await standard_portfolio(Book(http, users.alice.headers))
    await assert_hidden_from(http, users.bob, "GET", f"/api/v1/portfolios/{pid}/{kind}")


async def test_bob_cannot_read_alices_performance(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    await _hidden(http, two_users, "performance")


async def test_bob_cannot_read_alices_allocation(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    await _hidden(http, two_users, "allocation")


async def test_bob_cannot_read_alices_income(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    await _hidden(http, two_users, "income")


async def test_bob_cannot_read_alices_risk(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    await _hidden(http, two_users, "risk")


@pytest.mark.parametrize("path", ["/api/v1/income/summary", "/api/v1/dashboard"])
async def test_a_signed_in_user_is_required(http: httpx.AsyncClient, path: str) -> None:
    assert (await http.get(path)).status_code == 401


async def test_empty_user(http: httpx.AsyncClient) -> None:
    h = (await make_user(http, "empty")).headers
    d = (await http.get("/api/v1/dashboard", headers=h)).json()
    assert d["net_worth"]["net_worth"] == m("0.00") and d["goals"] == {"on_track": 0, "total": 0}
    s = (await http.get("/api/v1/income/summary", headers=h)).json()
    assert (s["yearly"], s["portfolios"]) == (m("0.00"), [])


def fresh_currency() -> str:
    import secrets
    import string

    from app.core.money import minor_units

    while True:
        code = "U" + "".join(secrets.choice(string.ascii_uppercase) for _ in range(2))
        # Never USD: the tests pair this code with USD, and a rate needs two different currencies.
        if code != "USD" and minor_units(code) == 2:
            return code


async def test_each_portfolio_has_its_own_cached_allocation(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    book = Book(http, two_users.alice.headers)
    first, second = await book.portfolio(), await book.portfolio()
    await book.post(first, "DEPOSIT", gross_amount=m("100.00"))
    await book.post(second, "DEPOSIT", gross_amount=m("200.00"))
    assert (await book.get(f"/api/v1/portfolios/{first}/allocation"))["total"] == m("100.00")
    assert (await book.get(f"/api/v1/portfolios/{second}/allocation"))["total"] == m("200.00")


async def test_income_summary_conversion_gaps_and_archived_portfolios(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    db: asyncpg.Connection,
) -> None:
    book = Book(http, two_users.alice.headers)
    other, lost = fresh_currency(), fresh_currency()
    await db.execute(
        "INSERT INTO fx_rates (base_currency, quote_currency, rate, provider, rate_timestamp, "
        "retrieved_at) VALUES ('USD', $1, 2, 'test', $2, $2)",
        other,
        NOW - timedelta(minutes=5),
    )
    usd = await book.portfolio()
    await book.post(usd, "INTEREST", gross_amount=m("12.00"))
    no_rate = await book.portfolio(lost)  # no rate between this currency and USD
    r = await http.post(f"/api/v1/portfolios/{no_rate}/transactions", headers=book.h, json={
        "transaction_type": "INTEREST", "trade_date": DAY.isoformat(), "currency": lost,
        "gross_amount": m("50.00", lost)})  # fmt: skip
    assert r.status_code == 201, r.text
    archived = await book.portfolio()
    await book.post(archived, "INTEREST", gross_amount=m("1000.00"))
    assert (
        await http.post(f"/api/v1/portfolios/{archived}/archive", headers=book.h)
    ).status_code == 200

    s = await book.get("/api/v1/income/summary")
    assert s["yearly"] == m("12.00")  # the unconverted and archived portfolios are left out
    assert s["unconverted_currencies"] == [lost] and s["complete"] is False
    lines = {line["portfolio_id"]: line for line in s["portfolios"]}
    assert set(lines) == {usd, no_rate}
    assert lines[no_rate]["yearly"] == m("50.00", lost) and lines[no_rate]["value"] is None
    in_other = await book.get(f"/api/v1/income/summary?currency={other}")
    assert in_other["yearly"] == m("24.00", other)  # 12 USD at 2
    assert in_other["currency"] == other
    d = await book.get("/api/v1/dashboard")
    assert d["complete"] is False


async def test_a_portfolio_in_a_currency_without_a_rate_makes_everything_incomplete(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    """Even emptied, a portfolio whose currency cannot be converted is reported, never counted
    as zero: net worth, passive income and the dashboard all say incomplete."""
    book = Book(http, two_users.alice.headers)
    lost = fresh_currency()
    pid = await book.portfolio(lost)
    for kind in ("INTEREST", "WITHDRAWAL"):
        r = await http.post(f"/api/v1/portfolios/{pid}/transactions", headers=book.h, json={
            "transaction_type": kind, "trade_date": DAY.isoformat(), "currency": lost,
            "gross_amount": m("50.00", lost)})  # fmt: skip
        assert r.status_code == 201, r.text
    nw = await book.get("/api/v1/net-worth")
    assert (
        nw["freshness"]["complete"] is False and lost in nw["freshness"]["unconverted_currencies"]
    )
    assert (await book.get("/api/v1/income/summary"))["complete"] is False
    assert (await book.get("/api/v1/dashboard"))["complete"] is False


async def test_assumed_deposits_are_reported_in_performance_and_risk(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    """Review decision 1: a purchase without a recorded deposit counts as a deposit, so the
    return exists, and the response says it is assumed."""
    book = Book(http, two_users.alice.headers)
    pid, stock = await book.portfolio(), await book.asset()
    await book.post(pid, "BUY", asset_id=stock, quantity="1", unit_price=m("100"))
    await book.value(pid, stock, "130.00")
    p = await book.get(f"/api/v1/portfolios/{pid}/performance")
    assert (p["assumed_deposits"], p["assumed_deposit_count"]) == (m("100.00"), 1)
    assert p["contributions"] == m("100.00") and p["total_value"] == m("130.00")
    assert p["profit_loss"] == m("30.00") and p["return_percent"] == "30"
    assert p["money_weighted"]["status"] == "ok"
    r = await book.get(f"/api/v1/portfolios/{pid}/risk")
    assert r["assumed_deposit_count"] == 1

    # A portfolio with its deposit recorded assumes nothing.
    other = await book.portfolio()
    await book.post(other, "DEPOSIT", gross_amount=m("100.00"))
    await book.post(other, "BUY", asset_id=stock, quantity="1", unit_price=m("100"))
    q = await book.get(f"/api/v1/portfolios/{other}/performance")
    assert (q["assumed_deposits"], q["assumed_deposit_count"]) == (m("0.00"), 0)
    # The summary does not assume anything: it shows the negative cash as it is.
    s = await book.get(f"/api/v1/portfolios/{pid}/summary")
    assert s["cash"] == m("-100.00")
    # Nor do allocation or net worth: the assumption is for performance and risk only.
    a = await book.get(f"/api/v1/portfolios/{pid}/allocation")
    assert a["total"] == m("30.00")  # 130 of stock less the 100 of negative cash
    assert (await book.get("/api/v1/net-worth"))["assets"] == m("30.00")
