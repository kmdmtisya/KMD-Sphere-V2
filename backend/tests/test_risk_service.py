"""One portfolio's value history and risk from its real ledger, valuations and FX history
(P06-T08)."""

import secrets
import string
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

import asyncpg
import httpx
import pytest
from fastapi import FastAPI

from app.core.authz import ResourceNotFoundError
from app.core.config import Settings
from app.core.errors import InvalidValueError
from app.core.money import minor_units
from app.main import create_app
from app.modules.analytics.risk import RiskStatus
from app.modules.portfolio.history import SeriesFrequency
from app.modules.portfolio.risk_service import PortfolioRisk, RiskService
from tests import auth_helpers as ah
from tests.authz_harness import TwoUsers, two_users  # noqa: F401
from tests.db_fixtures import migrated_settings  # noqa: F401

pytestmark = [pytest.mark.integration, pytest.mark.security]
D = Decimal
NOW = datetime.now(UTC).replace(microsecond=0)
TODAY = NOW.date()
START = date(TODAY.year - 1, TODAY.month, 1)  # about a year of month ends


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


def fresh_currency() -> str:
    while True:
        code = "V" + "".join(secrets.choice(string.ascii_uppercase) for _ in range(2))
        if minor_units(code) == 2:
            return code


async def portfolio(http: httpx.AsyncClient, h: dict[str, str]) -> str:
    body = {"name": f"R {uuid.uuid4().hex[:8]}", "base_currency": "USD"}
    r = await http.post("/api/v1/portfolios", headers=h, json=body)
    return str(r.json()["id"])


async def post(http: httpx.AsyncClient, h: dict[str, str], pid: str, on: date, **body: Any) -> None:
    full = {"trade_date": on.isoformat(), "currency": "USD"} | body
    r = await http.post(f"/api/v1/portfolios/{pid}/transactions", headers=h, json=full)
    assert r.status_code == 201, r.text


async def value(
    http: httpx.AsyncClient, h: dict[str, str], pid: str, asset: str, on: date, amount: str
) -> None:
    body = {
        "asset_id": asset,
        "value": m(amount),
        "as_of": datetime.combine(on, time(12), tzinfo=UTC).isoformat(),
        "source": "t",
    }
    r = await http.post(f"/api/v1/portfolios/{pid}/valuations", headers=h, json=body)
    assert r.status_code == 201, r.text


async def risk(app: FastAPI, user: str, pid: str, **kw: Any) -> PortfolioRisk:
    async with app.state.db.session_factory() as session:
        return await RiskService(session).portfolio(uuid.UUID(user), uuid.UUID(pid), now=NOW, **kw)


def month_end(d: date) -> date:
    nxt = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    return nxt - timedelta(days=1)


async def test_value_history_and_risk(
    app: FastAPI,
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    db: asyncpg.Connection,
) -> None:
    h = two_users.alice.headers
    pid = await portfolio(http, h)
    house = (await http.post("/api/v1/assets", headers=h, json={
        "asset_class": "real_estate", "name": "Flat", "currency": "USD"})).json()["id"]  # fmt: skip
    await post(http, h, pid, START, transaction_type="DEPOSIT", gross_amount=m("1000.00"))
    await post(http, h, pid, START, transaction_type="BUY", asset_id=house, quantity="1",
               unit_price=m("1000"))  # fmt: skip
    # The flat's value at each month end: up 10%, down 10%, alternately.
    ends, level = [], D(1000)
    day = month_end(START)
    for i in range(8):
        level = level * (D("1.1") if i % 2 == 0 else D("0.9"))
        await value(http, h, pid, house, day, str(level.quantize(D("0.01"))))
        ends.append((day, level.quantize(D("0.01"))))
        day = month_end(day + timedelta(days=1))
    await value(http, h, pid, house, START, "1000.00")

    r = await risk(app, two_users.alice.id, pid, end=ends[-1][0])
    assert r.currency == "USD" and r.frequency == SeriesFrequency.MONTHLY and r.start == START
    assert [(p.on, p.value) for p in r.points] == [(START, D("1000.00")), *ends]
    assert all(p.complete for p in r.points)
    assert r.risk.status == RiskStatus.OK and len(r.risk.returns) == 8
    for got, expected in zip(r.risk.returns, ["0.1", "-0.1"] * 4, strict=True):
        assert abs(got - D(expected)) < D("0.0001")  # valuations are rounded to cents
    assert r.risk.volatility is not None
    assert abs(r.risk.volatility - D("0.3703")) < D("0.001")  # sample sd x sqrt(12)
    # The 1.1 peak is never regained: the fall runs to the last point, (1.1 x 0.9)^4 / 1.1 - 1.
    drawdown = r.risk.max_drawdown
    assert drawdown is not None and drawdown.recovered is None and drawdown.peak == ends[0][0]
    assert abs(drawdown.depth - (D("0.99") ** 4 / D("1.1") - 1)) < D("0.001")


async def test_a_deposit_is_not_a_return(
    app: FastAPI,
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    h = two_users.alice.headers
    pid = await portfolio(http, h)
    day = START
    for _ in range(8):  # 100 a month into cash: no growth at all
        await post(http, h, pid, day, transaction_type="DEPOSIT", gross_amount=m("100.00"))
        day = month_end(day) + timedelta(days=1)
    r = await risk(app, two_users.alice.id, pid, end=day - timedelta(days=1))
    assert r.risk.status == RiskStatus.OK
    assert all(x == 0 for x in r.risk.returns)
    assert r.risk.volatility == 0 and r.risk.max_drawdown is not None
    assert r.risk.max_drawdown.depth == 0


async def test_historical_fx_rates_convert_each_point(
    app: FastAPI,
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    db: asyncpg.Connection,
) -> None:
    h = two_users.alice.headers
    fx = fresh_currency()
    first, second = START + timedelta(days=2), START + timedelta(days=40)
    for on, rate in ((first, "0.5"), (second, "0.6")):
        await db.execute(
            "INSERT INTO fx_rates (base_currency, quote_currency, rate, provider, "
            "rate_timestamp, retrieved_at) VALUES ($1, 'USD', $2::numeric, 'test', $3, $3)",
            fx, rate, datetime.combine(on, time(9), tzinfo=UTC),
        )  # fmt: skip
    pid = await portfolio(http, h)
    await post(http, h, pid, first, transaction_type="DEPOSIT", currency=fx,
               gross_amount=m("1000.00", fx), fx_rate_to_portfolio_currency="0.5")  # fmt: skip
    r = await risk(app, two_users.alice.id, pid, frequency=SeriesFrequency.DAILY, start=first,
                   end=second + timedelta(days=10))  # fmt: skip
    by_day = {p.on: p for p in r.points}
    assert by_day[first].value == D("500.0")
    # The rate is stamped 09:00 on `first`; at the end of a day it may be at most 7 days old.
    assert by_day[first + timedelta(days=6)].value == D("500.0")
    assert not by_day[first + timedelta(days=7)].complete  # 7 days 15 hours old: not usable
    assert by_day[first + timedelta(days=7)].unconverted == frozenset({fx})
    assert by_day[second].value == D("600.0")
    assert r.risk.status == RiskStatus.INCOMPLETE_DATA and r.risk.incomplete_points > 0


async def test_too_little_history(
    app: FastAPI,
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    h = two_users.alice.headers
    pid = await portfolio(http, h)
    r = await risk(app, two_users.alice.id, pid)
    assert r.start == r.end == TODAY and len(r.points) == 1
    assert r.risk.status == RiskStatus.INSUFFICIENT_DATA


async def test_ranges_are_checked(
    app: FastAPI,
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    pid = await portfolio(http, two_users.alice.headers)
    daily = SeriesFrequency.DAILY
    for kw in ({"end": TODAY + timedelta(days=1)},
               {"start": TODAY, "end": TODAY - timedelta(days=1)},
               {"start": TODAY - timedelta(days=2000), "frequency": daily}):  # fmt: skip
        with pytest.raises(InvalidValueError):
            await risk(app, two_users.alice.id, pid, **kw)


async def test_another_users_portfolio_is_not_found(
    app: FastAPI,
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    pid = await portfolio(http, two_users.alice.headers)
    with pytest.raises(ResourceNotFoundError):
        await risk(app, two_users.bob.id, pid)
