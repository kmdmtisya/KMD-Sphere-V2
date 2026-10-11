"""One portfolio's allocation from its real ledger, valuations and asset data (P06-T04)."""

import secrets
import string
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
from app.core.money import minor_units
from app.main import create_app
from app.modules.analytics.allocation import Dimension
from app.modules.portfolio.allocation_service import AllocationService, PortfolioAllocation
from tests import auth_helpers as ah
from tests.authz_harness import TwoUsers, two_users  # noqa: F401
from tests.db_fixtures import migrated_settings  # noqa: F401

pytestmark = [pytest.mark.integration, pytest.mark.security]
DAY = date.today() - timedelta(days=30)
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


def fresh_currency() -> str:
    """A code no other test uses (FX rates are shared), with 2 minor units."""
    while True:
        code = "Q" + "".join(secrets.choice(string.ascii_uppercase) for _ in range(2))
        if minor_units(code) == 2:
            return code


def m(amount: str, currency: str = "USD") -> dict[str, str]:
    return {"amount": amount, "currency": currency}


class Book:
    def __init__(self, http: httpx.AsyncClient, h: dict[str, str]) -> None:
        self.http, self.h = http, h

    async def asset(self, cls: str, currency: str, **fields: Any) -> str:
        body = {"asset_class": cls, "name": f"{cls} {uuid.uuid4().hex[:6]}", "currency": currency}
        r = await self.http.post("/api/v1/assets", headers=self.h, json=body | fields)
        assert r.status_code == 201, r.text
        return str(r.json()["id"])

    async def portfolio(self) -> str:
        body = {"name": f"A {uuid.uuid4().hex[:8]}", "base_currency": "USD"}
        r = await self.http.post("/api/v1/portfolios", headers=self.h, json=body)
        assert r.status_code == 201, r.text
        return str(r.json()["id"])

    async def post(self, pid: str, kind: str, currency: str = "USD", **fields: Any) -> None:
        body = {"transaction_type": kind, "trade_date": DAY.isoformat(), "currency": currency}
        r = await self.http.post(
            f"/api/v1/portfolios/{pid}/transactions", headers=self.h, json=body | fields
        )
        assert r.status_code == 201, r.text

    async def value(self, pid: str, asset: str, amount: str, currency: str) -> None:
        body = {
            "asset_id": asset,
            "value": m(amount, currency),
            "as_of": (NOW - timedelta(hours=2)).isoformat(),
            "source": "test",
        }
        r = await self.http.post(f"/api/v1/portfolios/{pid}/valuations", headers=self.h, json=body)
        assert r.status_code == 201, r.text


async def allocation(app: FastAPI, user: str, pid: str) -> PortfolioAllocation:
    async with app.state.db.session_factory() as session:
        return await AllocationService(session).portfolio(uuid.UUID(user), uuid.UUID(pid))


def table(a: PortfolioAllocation, d: Dimension) -> list[tuple[str | None, Decimal, Decimal | None]]:
    return [(s.key, s.value, s.weight_percent) for s in a.by[d].slices]


async def test_allocation_from_the_ledger(
    app: FastAPI,
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    db: asyncpg.Connection,
) -> None:
    fx = fresh_currency()
    await db.execute(
        "INSERT INTO fx_rates (base_currency, quote_currency, rate, provider, rate_timestamp, "
        "retrieved_at) VALUES ($1, 'USD', 0.5, 'test', $2, $2)",
        fx,
        NOW - timedelta(minutes=5),
    )
    book = Book(http, two_users.alice.headers)
    tech = await book.asset("stock", "USD", country="US", metadata={"sector": "  Technology "})
    house = await book.asset("real_estate", fx, country="KE")
    unpriced = await book.asset("stock", "USD", country="US")
    fund = await book.asset("etf", "USD", metadata={"exchange": "LSE", "isin": "IE00B4L5Y983"})
    pid = await book.portfolio()
    await book.post(pid, "DEPOSIT", gross_amount=m("10000.00"))
    await book.post(pid, "BUY", asset_id=tech, quantity="10", unit_price=m("100"))
    await book.post(pid, "BUY", fx, asset_id=house, quantity="1", unit_price=m("14000", fx),
                    fx_rate_to_portfolio_currency="0.5")  # fmt: skip
    await book.post(pid, "DEPOSIT", fx, gross_amount=m("1100.00", fx),
                    fx_rate_to_portfolio_currency="0.5")  # fmt: skip
    await book.post(pid, "BUY", asset_id=unpriced, quantity="1", unit_price=m("50"))
    await book.post(pid, "BUY", asset_id=fund, quantity="1", unit_price=m("100"))
    await book.value(pid, fund, "100.00", "USD")
    await book.value(pid, tech, "1500.00", "USD")
    await book.value(pid, house, "16000.00", fx)

    a = await allocation(app, two_users.alice.id, pid)
    # Positions: tech 1500, house 16000 x 0.5 = 8000, fund 100. Cash: USD 10000 - 1000 - 50 - 100
    # = 8850; fx -14000 + 1100 = -12900 x 0.5 = -6450. Total 1500 + 8000 + 100 + 8850 - 6450.
    assert a.total == D(12000) and a.currency == "USD"
    assert not a.complete and a.unpriced_assets == (uuid.UUID(unpriced),)
    # The negative cash balance makes shares meaningless: values only.
    assert table(a, Dimension.ASSET_CLASS) == [
        ("real_estate", D(8000), None),
        ("cash", D(2400), None),
        ("stock", D(1500), None),
        ("etf", D(100), None),
    ]
    assert a.concentration.hhi is None

    # Pay the fx debt: shares become defined.
    await book.post(pid, "DEPOSIT", fx, gross_amount=m("12900.00", fx),
                    fx_rate_to_portfolio_currency="0.5")  # fmt: skip
    a = await allocation(app, two_users.alice.id, pid)
    assert a.total == D(18450)
    assert table(a, Dimension.ASSET_CLASS) == [
        ("cash", D(8850), D("47.97")),  # 47.9675: the largest remainder gets the 0.01
        ("real_estate", D(8000), D("43.36")),
        ("stock", D(1500), D("8.13")),
        ("etf", D(100), D("0.54")),
    ]
    assert table(a, Dimension.CURRENCY) == [
        ("USD", D(10450), D("56.64")),
        (fx, D(8000), D("43.36")),
    ]
    assert table(a, Dimension.COUNTRY) == [
        (None, D(8950), D("48.51")),  # cash 8850 and the fund without a country
        ("KE", D(8000), D("43.36")),
        ("US", D(1500), D("8.13")),
    ]
    assert table(a, Dimension.SECTOR) == [
        (None, D(16950), D("91.87")),  # the fund has metadata, but no sector
        ("Technology", D(1500), D("8.13")),  # the metadata, trimmed
    ]
    c = a.concentration
    assert c.positions == 4 and c.largest == "cash:USD"
    assert c.top[1] is not None and abs(c.top[1] - D(8850) / D(18450)) < D("1e-25")

    # The allocation reconciles with the published summary.
    summary = (await http.get(f"/api/v1/portfolios/{pid}/summary", headers=book.h)).json()
    assert summary["total_value"]["amount"] == "18450.00"
    published = {
        c["currency"]: (c["value"]["amount"], c["share_percent"]) for c in summary["currencies"]
    }
    assert published == {k: (f"{v:.2f}", str(w)) for k, v, w in table(a, Dimension.CURRENCY)}


async def test_an_empty_portfolio(
    app: FastAPI,
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    pid = await Book(http, two_users.alice.headers).portfolio()
    a = await allocation(app, two_users.alice.id, pid)
    assert a.total == 0 and a.complete
    assert all(not x.slices for x in a.by.values())
    assert a.concentration.positions == 0 and a.concentration.hhi is None


async def test_another_users_portfolio_is_not_found(
    app: FastAPI,
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    pid = await Book(http, two_users.alice.headers).portfolio()
    with pytest.raises(ResourceNotFoundError):
        await allocation(app, two_users.bob.id, pid)
    with pytest.raises(ResourceNotFoundError):
        await allocation(app, two_users.alice.id, str(uuid.uuid4()))
