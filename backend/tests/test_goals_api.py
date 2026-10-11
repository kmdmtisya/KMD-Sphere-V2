"""/api/v1/goals (P06-T06): CRUD, validation, ownership and progress through the API."""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import asyncpg
import httpx
import pytest
from fastapi import FastAPI

from app.core.config import Settings
from app.main import create_app
from app.modules.goals.progress import NOTICE, add_months
from tests import auth_helpers as ah
from tests.authz_harness import TwoUsers, assert_hidden_from, make_user, two_users  # noqa: F401
from tests.db_fixtures import migrated_settings  # noqa: F401

pytestmark = [pytest.mark.integration, pytest.mark.security]
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


def usd(amount: str) -> dict[str, str]:
    return {"amount": amount, "currency": "USD"}


def goal_body(**changes: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "name": f"House {uuid.uuid4().hex[:6]}",
        "goal_type": "house_deposit",
        "target": usd("12000.00"),
        "target_date": add_months(TODAY, 12).isoformat(),
        "assumptions": {"contribution": usd("500.00"), "returns": {"base": "0"}},
    }
    return body | changes


async def create(http: httpx.AsyncClient, h: dict[str, str], **changes: Any) -> dict[str, Any]:
    r = await http.post("/api/v1/goals", headers=h, json=goal_body(**changes))
    assert r.status_code == 201, r.text
    return dict(r.json())


async def funded_portfolio(http: httpx.AsyncClient, h: dict[str, str], amount: str) -> str:
    r = await http.post(
        "/api/v1/portfolios",
        headers=h,
        json={"name": f"G {uuid.uuid4().hex[:8]}", "base_currency": "USD"},
    )
    pid = str(r.json()["id"])
    r = await http.post(
        f"/api/v1/portfolios/{pid}/transactions",
        headers=h,
        json={
            "transaction_type": "DEPOSIT",
            "trade_date": (TODAY - timedelta(days=3)).isoformat(),
            "currency": "USD",
            "gross_amount": usd(amount),
        },
    )
    assert r.status_code == 201, r.text
    return pid


# --------------------------------------------------------------------------------------- CRUD


async def test_create_read_list_update_delete(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    db: asyncpg.Connection,
) -> None:
    h = two_users.alice.headers
    g = await create(http, h, assumptions={
        "contribution": usd("500.00"), "contribution_frequency": "quarterly",
        "inflation_percent": "2.5", "returns": {"conservative": "3", "base": "5.25", "growth": "8"},
    })  # fmt: skip
    assert g["target"] == usd("12000.00") and g["portfolio_id"] is None
    assert g["target_in_todays_money"] is False and g["goal_type"] == "house_deposit"
    a = g["assumptions"]
    assert a["contribution"] == usd("500.00") and a["contribution_frequency"] == "quarterly"
    assert a["returns"] == {"base": "5.25", "conservative": "3", "growth": "8"}
    assert (a["inflation_percent"], a["annual_fee_percent"], a["compounding_frequency"]) == (
        "2.5",
        "0",
        "monthly",
    )
    assert (await http.get(f"/api/v1/goals/{g['id']}", headers=h)).json() == g
    listed = (await http.get("/api/v1/goals", headers=h)).json()
    assert g["id"] in {x["id"] for x in listed}

    r = await http.patch(f"/api/v1/goals/{g['id']}", headers=h, json={
        "name": "  Deposit  ", "target": usd("15000.00"),
        "assumptions": {"contribution": usd("600.00"), "returns": {"base": "4"}},
    })  # fmt: skip
    assert r.status_code == 200, r.text
    changed = r.json()
    assert changed["name"] == "Deposit" and changed["target"] == usd("15000.00")
    assert changed["assumptions"]["returns"] == {"base": "4", "conservative": None, "growth": None}
    assert changed["assumptions"]["contribution_frequency"] == "monthly"  # replaced as a whole

    assert (await http.delete(f"/api/v1/goals/{g['id']}", headers=h)).status_code == 204
    assert (await http.get(f"/api/v1/goals/{g['id']}", headers=h)).status_code == 404
    actions = [
        r["action"]
        for r in await db.fetch(
            "SELECT action FROM audit_events WHERE resource_type = 'goal' AND resource_id = $1 "
            "ORDER BY occurred_at",
            g["id"],
        )
    ]
    assert actions == ["goals.goal.created", "goals.goal.updated", "goals.goal.deleted"]
    assert await db.fetchval("SELECT count(*) FROM goal_scenarios WHERE goal_id = $1",
                             uuid.UUID(g["id"])) == 0  # fmt: skip


async def test_names_are_unique_per_user(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    g = await create(http, two_users.alice.headers)
    again = await http.post("/api/v1/goals", headers=two_users.alice.headers,
                            json=goal_body(name=g["name"]))  # fmt: skip
    assert again.status_code == 409
    other = await http.post("/api/v1/goals", headers=two_users.bob.headers,
                            json=goal_body(name=g["name"]))  # fmt: skip
    assert other.status_code == 201
    second = await create(http, two_users.alice.headers)
    clash = await http.patch(f"/api/v1/goals/{second['id']}", headers=two_users.alice.headers,
                             json={"name": g["name"]})  # fmt: skip
    assert clash.status_code == 409


# ------------------------------------------------------------------------------------ validation

INVALID = [
    ("past date", {"target_date": (TODAY - timedelta(days=1)).isoformat()}),
    ("today", {"target_date": TODAY.isoformat()}),
    ("over 60 years", {"target_date": add_months(TODAY, 721).isoformat()}),
    ("target zero", {"target": usd("0.00")}),
    ("target too high", {"target": usd("10000000000.01")}),
    ("target decimals", {"target": usd("1.001")}),
    ("contribution in another currency",
     {"assumptions": {"contribution": {"amount": "1", "currency": "EUR"},
                      "returns": {"base": "1"}}}),
    ("contribution too high",
     {"assumptions": {"contribution": usd("10000000.01"), "returns": {"base": "1"}}}),
    ("return too high", {"assumptions": {"contribution": usd("1"), "returns": {"base": "50.01"}}}),
    ("no base return", {"assumptions": {"contribution": usd("1"), "returns": {"growth": "5"}}}),
    ("conservative above base",
     {"assumptions": {"contribution": usd("1"), "returns": {"base": "5", "conservative": "6"}}}),
    ("growth below base",
     {"assumptions": {"contribution": usd("1"), "returns": {"base": "5", "growth": "4"}}}),
    ("fee too high",
     {"assumptions": {"contribution": usd("1"), "annual_fee_percent": "5.01",
                      "returns": {"base": "1"}}}),
    ("unknown goal type", {"goal_type": "yacht"}),
    ("blank name", {"name": "   "}),
    ("unknown field", {"priority": 1}),
    ("today's money not boolean", {"target_in_todays_money": "yes"}),
    ("unknown portfolio", {"portfolio_id": str(uuid.uuid4())}),
]  # fmt: skip


@pytest.mark.parametrize(("name", "change"), INVALID, ids=[n for n, _ in INVALID])
async def test_invalid_goals_are_refused(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    name: str,
    change: dict[str, Any],
) -> None:
    r = await http.post("/api/v1/goals", headers=two_users.alice.headers, json=goal_body(**change))
    assert r.status_code == 422, (name, r.text)


async def test_invalid_changes_are_refused(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    h = two_users.alice.headers
    g = await create(http, h)
    for change in (
        {"name": None},
        {"target": None},
        {"assumptions": None},
        {"target_date": TODAY.isoformat()},
        {"target": {"amount": "100", "currency": "EUR"}},  # contribution stays in USD
        {"portfolio_id": str(uuid.uuid4())},
    ):
        r = await http.patch(f"/api/v1/goals/{g['id']}", headers=h, json=change)
        assert r.status_code == 422, (change, r.text)
    same = await http.patch(f"/api/v1/goals/{g['id']}", headers=h, json={})
    assert same.status_code == 200 and same.json()["updated_at"] == g["updated_at"]


async def test_another_users_portfolio_cannot_fund_a_goal(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    bobs = await funded_portfolio(http, two_users.bob.headers, "100.00")
    r = await http.post("/api/v1/goals", headers=two_users.alice.headers,
                        json=goal_body(portfolio_id=bobs))  # fmt: skip
    assert r.status_code == 422
    assert "no such portfolio" in r.text
    g = await create(http, two_users.alice.headers)
    r = await http.patch(f"/api/v1/goals/{g['id']}", headers=two_users.alice.headers,
                         json={"portfolio_id": bobs})  # fmt: skip
    assert r.status_code == 422


# -------------------------------------------------------------------------------------- progress


async def test_progress_from_a_funding_portfolio(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    h = two_users.alice.headers
    pid = await funded_portfolio(http, h, "6000.00")
    await funded_portfolio(http, h, "1000.00")  # another portfolio: not this goal's funding
    g = await create(http, h, portfolio_id=pid)
    r = await http.get(f"/api/v1/goals/{g['id']}/progress", headers=h)
    assert r.status_code == 200, r.text
    p = r.json()
    # 6000 now + 12 x 500 at 0% = 12000 on the date.
    assert (p["status"], p["reached"], p["overdue"]) == ("on_track", False, False)
    assert (p["progress_percent"], p["current_value"], p["gap"]) == (
        "50",
        usd("6000.00"),
        usd("6000.00"),
    )
    assert p["months_left"] == 12 and p["value_complete"] is True
    assert p["scenarios"] == [
        {
            "kind": "base",
            "annual_return_percent": "0",
            "projected_value": usd("12000.00"),
            "projected_value_real": usd("12000.00"),
            "reaches_target": True,
        }
    ]
    assert p["required_contribution"] == usd("500.00")
    assert p["estimated_completion"] == add_months(TODAY, 12).isoformat()
    assert p["notice"] == NOTICE and "not guaranteed" in p["notice"]
    assert p["assumptions"] == g["assumptions"] and p["target"] == g["target"]

    # Smaller contributions: behind, with the amount that would get there.
    await http.patch(f"/api/v1/goals/{g['id']}", headers=h, json={
        "assumptions": {"contribution": usd("400.00"), "returns": {"base": "0"}}})  # fmt: skip
    p = (await http.get(f"/api/v1/goals/{g['id']}/progress", headers=h)).json()
    assert p["status"] == "behind" and p["required_contribution"] == usd("500.00")
    assert p["estimated_completion"] == add_months(TODAY, 15).isoformat()


async def test_all_portfolios_fund_a_goal_without_a_portfolio(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    h = two_users.alice.headers
    before = await create(http, h, target=usd("10000000.00"))
    start = (await http.get(f"/api/v1/goals/{before['id']}/progress", headers=h)).json()
    await funded_portfolio(http, h, "250.00")
    after = (await http.get(f"/api/v1/goals/{before['id']}/progress", headers=h)).json()
    gained = Decimal(after["current_value"]["amount"]) - Decimal(start["current_value"]["amount"])
    assert gained == Decimal("250.00")


async def test_the_summary_counts_goals_on_track(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    h = two_users.bob.headers
    pid = await funded_portfolio(http, h, "6000.00")
    on = await create(http, h, portfolio_id=pid)
    behind = await create(http, h, portfolio_id=pid, target=usd("50000.00"))
    reached = await create(http, h, portfolio_id=pid, target=usd("5000.00"))
    s = (await http.get("/api/v1/goals/summary", headers=h)).json()
    items = {i["id"]: i for i in s["items"]}
    assert set(items) >= {on["id"], behind["id"], reached["id"]}
    assert (items[on["id"]]["status"], items[on["id"]]["progress_percent"]) == ("on_track", "50")
    assert items[behind["id"]]["status"] == "behind"
    assert items[reached["id"]]["reached"] is True
    assert items[reached["id"]]["progress_percent"] == "100"
    assert s["total"] == len(s["items"])
    assert s["on_track"] == sum(1 for i in s["items"] if i["status"] == "on_track")
    assert s["notice"] == NOTICE


async def test_no_goals(http: httpx.AsyncClient) -> None:
    h = (await make_user(http, "fresh")).headers
    s = (await http.get("/api/v1/goals/summary", headers=h)).json()
    assert (s["on_track"], s["total"], s["items"]) == (0, 0, [])
    assert (await http.get("/api/v1/goals", headers=h)).json() == []


async def test_the_goal_limit(http: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.modules.goals import service

    monkeypatch.setattr(service, "MAX_GOALS_PER_USER", 2)
    h = (await make_user(http, "limit")).headers
    await create(http, h)
    await create(http, h)
    r = await http.post("/api/v1/goals", headers=h, json=goal_body())
    assert r.status_code == 409


# ------------------------------------------------------------------------------ ownership (IDOR)


async def test_bob_cannot_read_alices_goal(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    g = await create(http, two_users.alice.headers)
    await assert_hidden_from(http, two_users.bob, "GET", f"/api/v1/goals/{g['id']}")
    bobs = (await http.get("/api/v1/goals", headers=two_users.bob.headers)).json()
    assert g["id"] not in {x["id"] for x in bobs}


async def test_bob_cannot_change_alices_goal(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    g = await create(http, two_users.alice.headers)
    await assert_hidden_from(http, two_users.bob, "PATCH", f"/api/v1/goals/{g['id']}",
                             json={"name": "Mine now"})  # fmt: skip
    assert (await http.get(f"/api/v1/goals/{g['id']}", headers=two_users.alice.headers)).json() == g


async def test_bob_cannot_delete_alices_goal(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    g = await create(http, two_users.alice.headers)
    await assert_hidden_from(http, two_users.bob, "DELETE", f"/api/v1/goals/{g['id']}")
    assert (
        await http.get(f"/api/v1/goals/{g['id']}", headers=two_users.alice.headers)
    ).status_code == 200


async def test_bob_cannot_see_alices_goal_progress(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    g = await create(http, two_users.alice.headers)
    await assert_hidden_from(http, two_users.bob, "GET", f"/api/v1/goals/{g['id']}/progress")
    summary = (await http.get("/api/v1/goals/summary", headers=two_users.bob.headers)).json()
    assert g["id"] not in {i["id"] for i in summary["items"]}


@pytest.mark.parametrize(
    ("method", "path"),
    [("GET", "/api/v1/goals"), ("POST", "/api/v1/goals"), ("GET", "/api/v1/goals/summary")],
)
async def test_a_signed_in_user_is_required(
    http: httpx.AsyncClient, method: str, path: str
) -> None:
    assert (await http.request(method, path, json=goal_body())).status_code == 401


async def test_repository_writes_are_scoped_to_the_owner(
    app: FastAPI,
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    """Defence in depth (ADR-0011): the owner is in every UPDATE and DELETE, even if a caller
    skipped the ownership check."""
    from app.modules.goals.repository import GoalRepository

    g = await create(http, two_users.alice.headers)
    bob, goal_id = uuid.UUID(two_users.bob.id), uuid.UUID(g["id"])
    async with app.state.db.session_factory() as session:
        repo = GoalRepository(session)
        await repo.update(bob, goal_id, {"name": "Taken"})
        await repo.delete(bob, goal_id)
        await session.commit()
    after = await http.get(f"/api/v1/goals/{g['id']}", headers=two_users.alice.headers)
    assert after.status_code == 200 and after.json()["name"] == g["name"]
