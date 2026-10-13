"""POST /api/v1/ai/portfolio-doctor and the get_portfolio_diagnosis tool (P12-T01), on the real app
and database: findings from the existing analytics, scenarios that are never trades, owner-scoped
access, and the tool returning exactly the API's findings."""

import uuid
from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.tools.base import ToolContext
from app.ai.tools.factory import build_tool_registry
from app.core.config import Settings
from app.main import create_app
from tests import auth_helpers as ah
from tests.authz_harness import TwoUsers, two_users  # noqa: F401
from tests.db_fixtures import migrated_settings  # noqa: F401
from tests.test_analytics_api import DAY, TODAY, Book, m

pytestmark = [pytest.mark.integration, pytest.mark.security]
DOCTOR = "/api/v1/ai/portfolio-doctor"


@pytest.fixture(scope="module")
async def app(migrated_settings: Settings) -> AsyncIterator[FastAPI]:  # noqa: F811
    settings = migrated_settings.model_copy(update={"ai_tool_calls_per_minute": 1000})
    application = create_app(settings, readiness_checks={}, token_verifier=ah.verifier())
    yield application
    await application.state.db.dispose()


@pytest.fixture
async def http(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def concentrated(book: Book) -> tuple[str, str]:
    """10,000 deposited; one stock bought for 9,000 and valued at 9,000; 1,000 cash."""
    pid = await book.portfolio()
    stock = await book.asset(country="US", metadata={"sector": "Tech"})
    await book.post(pid, "DEPOSIT", gross_amount=m("10000.00"))
    await book.post(pid, "BUY", asset_id=stock, quantity="90", unit_price=m("100"))
    await book.value(pid, stock, "9000.00")
    return pid, stock


async def doctor(http: httpx.AsyncClient, h: dict[str, str], pid: str) -> dict[str, Any]:
    r = await http.post(DOCTOR, headers=h, json={"portfolio_id": pid})
    assert r.status_code == 200, r.text
    return dict(r.json())


def by_check(body: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {f["check"]: f for f in body["findings"]}


async def test_a_concentrated_portfolio_is_flagged_from_its_own_figures(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    book = Book(http, two_users.alice.headers)
    pid, stock = await concentrated(book)
    body = await doctor(http, two_users.alice.headers, pid)

    assert body["portfolio_id"] == pid and body["total_value"] == m("10000.00")
    assert body["overall"] == "high" and body["complete"] is True
    assert "Not investment advice" in body["notice"]
    f = by_check(body)
    assert list(f) == [
        "position_concentration", "asset_class_concentration", "sector_concentration",
        "geographic_concentration", "currency_exposure", "liquidity", "volatility", "drawdown",
        "income_dependence", "goal_alignment", "data_completeness",
    ]  # fmt: skip
    pos = f["position_concentration"]
    assert (pos["severity"], pos["subject"], pos["value"], pos["threshold"], pos["unit"]) == (
        "high", stock, "90", "35", "percent")  # fmt: skip
    assert f["asset_class_concentration"]["subject"] == "stock"
    assert f["sector_concentration"]["subject"] == "Tech"
    assert f["currency_exposure"]["status"] == "ok" and f["currency_exposure"]["value"] == "0"
    assert f["liquidity"]["status"] == "ok" and f["liquidity"]["assumptions"]
    for check in ("volatility", "drawdown"):  # 100 days of history, not a year
        assert f[check]["status"] == "not_assessed"
    assert f["income_dependence"]["status"] == "not_assessed"
    assert f["goal_alignment"]["status"] == "not_assessed"
    assert body["counts"]["high"] == sum(
        1 for x in body["findings"] if x["status"] == "flagged" and x["severity"] == "high"
    )

    # The same figures as the analytics API.
    allocation = await book.get(f"/api/v1/portfolios/{pid}/allocation")
    assert allocation["asset_class"]["slices"][0]["weight_percent"] == "90"


async def test_scenarios_are_hypothetical_shares_never_trades(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    book = Book(http, two_users.alice.headers)
    pid, stock = await concentrated(book)
    body = await doctor(http, two_users.alice.headers, pid)
    assert {s["check"] for s in body["scenarios"]} == {
        "position_concentration",
        "asset_class_concentration",
    }
    for s in body["scenarios"]:
        assert s["is_trade"] is False and "not an order" in s["assumptions"][0]
        assert all(set(c) == {"subject", "before", "after"} for c in s["changes"]), (
            "shares only: no amount to buy or sell"
        )
    position = next(s for s in body["scenarios"] if s["check"] == "position_concentration")
    assert position["changes"] == [{"subject": stock, "before": "90", "after": "20"}]
    assert position["measure"] == "effective_positions"
    assert float(position["after"]) > float(position["before"])
    # Nothing changed in the portfolio.
    holdings = await http.get(f"/api/v1/portfolios/{pid}/holdings", headers=book.h)
    assert [x["quantity"] for x in holdings.json()] == ["90"]


async def test_illiquid_holdings_and_a_goal_behind_are_reported(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    h = two_users.alice.headers
    book = Book(http, h)
    pid = await book.portfolio()
    house = await book.asset("real_estate", country="KE")
    await book.post(pid, "DEPOSIT", gross_amount=m("500.00"))
    await book.value(pid, house, "99500.00")
    goal = await http.post(
        "/api/v1/goals",
        headers=h,
        json={
            "name": f"Retire {uuid.uuid4().hex[:6]}",
            "goal_type": "retirement",
            "target": m("5000000.00"),
            "target_date": (TODAY + timedelta(days=400)).isoformat(),
            "portfolio_id": pid,
            "assumptions": {"contribution": m("0.00"), "returns": {"base": "0"}},
        },
    )
    assert goal.status_code == 201, goal.text
    f = by_check(await doctor(http, h, pid))
    assert (f["liquidity"]["severity"], f["liquidity"]["value"]) == ("high", "0.5")
    assert "assumed from the asset class" in f["liquidity"]["assumptions"][0]
    g = f["goal_alignment"]
    assert (g["severity"], g["subject"], g["unit"], g["value"]) == (
        "medium", goal.json()["id"], "count", "1")  # fmt: skip
    assert "estimate" in g["assumptions"][0]


async def test_income_from_one_payer_is_flagged(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    book = Book(http, two_users.alice.headers)
    pid, stock = await concentrated(book)
    await book.post(pid, "DIVIDEND", DAY + timedelta(days=50), asset_id=stock,
                    gross_amount=m("120.00"))  # fmt: skip
    f = by_check(await doctor(http, two_users.alice.headers, pid))["income_dependence"]
    assert (f["severity"], f["subject"], f["value"]) == ("high", stock, "100")


async def test_bob_cannot_diagnose_alices_portfolio(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    pid, _ = await concentrated(Book(http, two_users.alice.headers))
    foreign = await http.post(DOCTOR, headers=two_users.bob.headers, json={"portfolio_id": pid})
    missing = await http.post(
        DOCTOR, headers=two_users.bob.headers, json={"portfolio_id": str(uuid.uuid4())}
    )
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json()["detail"] == missing.json()["detail"], "nothing tells them apart"
    assert pid not in foreign.text


async def test_the_request_is_validated_and_needs_a_signed_in_user(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    pid = str(uuid.uuid4())
    assert (await http.post(DOCTOR, json={"portfolio_id": pid})).status_code == 401
    h = two_users.alice.headers
    bad = await http.post(DOCTOR, headers=h, json={"portfolio_id": pid, "user_id": pid})
    assert bad.status_code == 422, "no smuggled fields"
    assert (await http.post(DOCTOR, headers=h, json={"portfolio_id": "x"})).status_code == 422


# ------------------------------------------------------------------------------------ AI tool
async def call(app: FastAPI, user_id: str, arguments: dict[str, Any]) -> Any:
    registry = build_tool_registry(app.state.settings)
    sessions: async_sessionmaker[AsyncSession] = app.state.db.session_factory
    async with sessions() as session:
        return await registry.execute(
            "get_portfolio_diagnosis",
            arguments,
            ToolContext(uuid.UUID(user_id), session, "corr", "fake-1", "fake"),
        )


async def test_the_tool_returns_the_apis_findings_and_is_owner_scoped(
    app: FastAPI,
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    pid, _ = await concentrated(Book(http, two_users.alice.headers))
    api = await doctor(http, two_users.alice.headers, pid)
    outcome = await call(app, two_users.alice.id, {"portfolio_id": pid})
    assert outcome.ok, outcome
    data = outcome.data
    assert data["findings"] == api["findings"] and data["scenarios"] == api["scenarios"]
    assert data["overall"] == api["overall"] and data["notice"] == api["notice"]
    assert data["as_of"] and data["complete"] is True

    foreign = await call(app, two_users.bob.id, {"portfolio_id": pid})
    assert (foreign.ok, foreign.error_code) == (False, "not_found")
    smuggled = await call(
        app, two_users.bob.id, {"portfolio_id": pid, "user_id": two_users.alice.id}
    )
    assert (smuggled.ok, smuggled.error_code) == (False, "invalid_arguments")
