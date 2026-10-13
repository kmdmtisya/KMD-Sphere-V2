"""POST /api/v1/universe/compatibility (P12-T04) on the real database: before and after measures
from the portfolio's own figures, verdicts from eligibility, the minimum investment (through a
stored FX rate) and material changes, owner-scoped access, and nothing changed in the portfolio."""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.main import create_app
from app.modules.assets.models import Asset
from app.modules.universe.ingestion import DemoUniverseSource, ingest
from tests import auth_helpers as ah
from tests.authz_harness import TwoUsers, two_users  # noqa: F401
from tests.db_fixtures import migrated_settings  # noqa: F401
from tests.test_analytics_api import Book, m

pytestmark = [pytest.mark.integration, pytest.mark.security]
FIT = "/api/v1/universe/compatibility"


@pytest.fixture(scope="module")
async def app(migrated_settings: Settings) -> AsyncIterator[FastAPI]:  # noqa: F811
    application = create_app(migrated_settings, readiness_checks={}, token_verifier=ah.verifier())
    sessions: async_sessionmaker[AsyncSession] = application.state.db.session_factory
    async with sessions() as s:
        await ingest(s, DemoUniverseSource())
        now = datetime.now(UTC) - timedelta(hours=1)
        await s.execute(
            text(
                "INSERT INTO fx_rates (base_currency, quote_currency, rate, provider, "
                "rate_timestamp, retrieved_at) VALUES ('USD', 'KES', 129, 'test', :t, :t)"
            ),
            {"t": now},
        )
        await s.commit()
        application.state.symbols = dict((await s.execute(select(Asset.symbol, Asset.id))).all())
    yield application
    await application.state.db.dispose()


@pytest.fixture
async def http(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def kenyan(http: httpx.AsyncClient, h: dict[str, str]) -> str:
    """A balanced Kenyan investor (3 years) with 9,000 in one stock and 1,000 cash."""
    await http.patch("/api/v1/me/preferences", headers=h, json={"residence_country": "KE"})
    await http.post(
        "/api/v1/risk-profiles", headers=h, json={"risk_tolerance": "balanced", "horizon_years": 3}
    )
    book = Book(http, h)
    pid = await book.portfolio()
    stock = await book.asset(country="US", metadata={"sector": "Tech"})
    await book.post(pid, "DEPOSIT", gross_amount=m("10000.00"))
    await book.post(pid, "BUY", asset_id=stock, quantity="90", unit_price=m("100"))
    await book.value(pid, stock, "9000.00")
    return pid


async def fit(
    app: FastAPI, http: httpx.AsyncClient, h: dict[str, str], pid: str, symbol: str, amount: str
) -> dict[str, Any]:
    asset = str(app.state.symbols[symbol])
    r = await http.post(
        FIT, headers=h, json={"portfolio_id": pid, "asset_id": asset, "amount": m(amount)}
    )
    assert r.status_code == 200, r.text
    return dict(r.json())


async def test_a_bond_etf_fits_and_the_measures_come_from_the_portfolio(
    app: FastAPI,
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    h = two_users.alice.headers
    pid = await kenyan(http, h)
    body = await fit(app, http, h, pid, "DEMO-GBD", "1000.00")
    assert body["verdict"] == "fits" and body["reasons"] == []
    assert body["is_trade"] is False and "not an order" in body["assumptions"][0]
    assert body["before"]["total_value"] == m("10000.00")
    assert body["after"]["total_value"] == m("11000.00")
    assert (
        body["before"]["largest_holding_percent"],
        body["after"]["largest_holding_percent"],
    ) == ("90", "81.82")
    assert body["after"]["instrument_share_percent"] == "9.09"
    changes = {c["check"]: (c["before"], c["after"]) for c in body["doctor_changes"]}
    assert changes["asset_class_concentration"] == ("high", "medium")
    assert body["is_demo"] is True and body["symbol"] == "DEMO-GBD"
    # Nothing was bought.
    holdings = await http.get(f"/api/v1/portfolios/{pid}/holdings", headers=h)
    assert len(holdings.json()) == 1


async def test_verdicts_follow_eligibility_size_and_the_minimum(
    app: FastAPI,
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    h = two_users.alice.headers
    pid = await kenyan(http, h)
    risky = await fit(app, http, h, pid, "DEMO-TEC", "500.00")  # risk 5 > balanced 3
    assert risky["verdict"] == "not_suitable"
    assert [r["code"] for r in risky["reasons"]] == ["eligibility_risk"]
    big = await fit(app, http, h, pid, "DEMO-GBD", "20000.00")
    assert big["verdict"] == "caution"
    assert "large_holding" in {r["code"] for r in big["reasons"]}
    # 100 USD at 129 = 12,900 KES, below the deposit's 100,000 KES minimum.
    small = await fit(app, http, h, pid, "DEMO-KFD", "100.00")
    assert small["verdict"] == "not_suitable"
    assert "below_minimum" in {r["code"] for r in small["reasons"]}
    enough = await fit(app, http, h, pid, "DEMO-KFD", "800.00")  # 103,200 KES
    assert "below_minimum" not in {r["code"] for r in enough["reasons"]}


async def test_bob_cannot_check_against_alices_portfolio(
    app: FastAPI,
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    pid = await kenyan(http, two_users.alice.headers)
    body = {
        "portfolio_id": pid,
        "asset_id": str(app.state.symbols["DEMO-GBD"]),
        "amount": m("100.00"),
    }
    foreign = await http.post(FIT, headers=two_users.bob.headers, json=body)
    missing = await http.post(
        FIT, headers=two_users.bob.headers, json=body | {"portfolio_id": str(uuid.uuid4())}
    )
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json()["detail"] == missing.json()["detail"]


async def test_the_request_is_validated(
    app: FastAPI,
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    h = two_users.alice.headers
    pid = await kenyan(http, h)
    asset = str(app.state.symbols["DEMO-GBD"])
    ok = {"portfolio_id": pid, "asset_id": asset, "amount": m("100.00")}
    assert (await http.post(FIT, json=ok)).status_code == 401
    cases = [
        ok | {"amount": m("100.00", "EUR")},  # not the portfolio's currency
        ok | {"amount": m("0.00")},
        ok | {"user_id": pid},  # smuggled field
    ]
    for body in cases:
        assert (await http.post(FIT, headers=h, json=body)).status_code == 422, body
    unknown = await http.post(FIT, headers=h, json=ok | {"asset_id": str(uuid.uuid4())})
    assert unknown.status_code == 404
