"""The core read tools (P10-T03): the API's own figures, structured with as-of times, and a
cross-user denial test for every tool."""

import json
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg
import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.tools.base import ToolContext, ToolOutcome
from app.ai.tools.factory import build_tool_registry
from app.ai.tools.registry import ToolRegistry
from app.core.config import Settings
from app.main import create_app
from tests import auth_helpers as ah
from tests.authz_harness import TwoUsers, two_users  # noqa: F401
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


@pytest.fixture
async def raw(migrated_settings: Settings) -> AsyncIterator[asyncpg.Connection]:  # noqa: F811
    conn = await asyncpg.connect(migrated_settings.database_dsn, timeout=5)
    yield conn
    await conn.close()


@pytest.fixture
def registry(migrated_settings: Settings) -> ToolRegistry:  # noqa: F811
    return build_tool_registry(
        migrated_settings.model_copy(update={"ai_tool_calls_per_minute": 1000})
    )


def m(amount: str) -> dict[str, str]:
    return {"amount": amount, "currency": "USD"}


class World:
    def __init__(self, http: httpx.AsyncClient, users: TwoUsers) -> None:
        self.http, self.users = http, users
        self.portfolio = ""
        self.goal = ""

    async def seed(self) -> "World":
        h = self.users.alice.headers
        self.portfolio = (
            await self.http.post(
                "/api/v1/portfolios", headers=h, json={"name": "Retirement", "base_currency": "USD"}
            )
        ).json()["id"]
        day = (TODAY - timedelta(days=40)).isoformat()
        deposit = {
            "transaction_type": "DEPOSIT",
            "trade_date": day,
            "currency": "USD",
            "gross_amount": m("5000.00"),
        }
        r = await self.http.post(
            f"/api/v1/portfolios/{self.portfolio}/transactions", headers=h, json=deposit
        )
        assert r.status_code == 201, r.text
        goal = await self.http.post(
            "/api/v1/goals",
            headers=h,
            json={
                "name": "House",
                "goal_type": "house_deposit",
                "target": m("20000.00"),
                "target_date": (TODAY + timedelta(days=700)).isoformat(),
                "portfolio_id": self.portfolio,
                "assumptions": {"contribution": m("200.00"), "returns": {"base": "5"}},
            },
        )
        assert goal.status_code == 201, goal.text
        self.goal = goal.json()["id"]
        return self


@pytest.fixture
async def world(http: httpx.AsyncClient, two_users: TwoUsers) -> World:  # noqa: F811
    return await World(http, two_users).seed()


async def call(
    app: FastAPI,
    registry: ToolRegistry,
    user_id: str,
    tool: str,
    arguments: dict[str, Any] | None = None,
) -> ToolOutcome:
    sessions: async_sessionmaker[AsyncSession] = app.state.db.session_factory
    async with sessions() as session:
        return await registry.execute(
            tool,
            arguments or {},
            ToolContext(uuid.UUID(user_id), session, "corr-test", "fake-1", "fake"),
        )


def no_floats(value: Any) -> None:
    if isinstance(value, float):
        raise AssertionError("a JSON float in a tool result")
    if isinstance(value, dict):
        for v in value.values():
            no_floats(v)
    if isinstance(value, list):
        for v in value:
            no_floats(v)


# ---------------------------------------------------------------------- the owner
async def test_summary_lists_portfolios_and_matches_the_api(
    app: FastAPI, http: httpx.AsyncClient, registry: ToolRegistry, world: World
) -> None:
    alice = world.users.alice
    outcome = await call(app, registry, alice.id, "get_portfolio_summary")
    assert outcome.ok and outcome.data is not None
    assert [p["name"] for p in outcome.data["portfolios"]] == ["Retirement"]
    api = (await http.get("/api/v1/portfolios/consolidated/summary", headers=alice.headers)).json()
    assert outcome.data["summary"]["total_value"] == api["total_value"]
    assert outcome.data["as_of"] and outcome.data["complete"] in (True, False)
    one = await call(
        app, registry, alice.id, "get_portfolio_summary", {"portfolio_id": world.portfolio}
    )
    assert one.ok and one.data is not None
    assert one.data["summary"]["total_value"] == api["total_value"]


async def test_allocation_performance_net_worth_and_goals_match_the_api(
    app: FastAPI, http: httpx.AsyncClient, registry: ToolRegistry, world: World
) -> None:
    alice = world.users.alice
    pid = world.portfolio
    allocation = await call(
        app, registry, alice.id, "get_portfolio_allocation", {"portfolio_id": pid}
    )
    api_alloc = (
        await http.get(f"/api/v1/portfolios/{pid}/allocation", headers=alice.headers)
    ).json()
    assert allocation.data is not None
    assert allocation.data["allocation"]["total"] == api_alloc["total"]
    assert allocation.data["allocation"]["asset_class"] == api_alloc["asset_class"]

    performance = await call(
        app, registry, alice.id, "get_portfolio_performance", {"portfolio_id": pid}
    )
    api_perf = (
        await http.get(f"/api/v1/portfolios/{pid}/performance", headers=alice.headers)
    ).json()
    assert performance.data is not None
    assert performance.data["performance"]["profit_loss"] == api_perf["profit_loss"]
    assert performance.data["performance"]["notice"] == api_perf["notice"]
    assert "points" not in performance.data["risk"], "the value series is not sent to the model"

    net = await call(app, registry, alice.id, "get_net_worth")
    api_net = (await http.get("/api/v1/net-worth", headers=alice.headers)).json()
    assert net.data is not None
    assert net.data["net_worth"]["net_worth"] == api_net["net_worth"]

    goals = await call(app, registry, alice.id, "get_goal_progress")
    assert goals.data is not None and goals.data["summary"]["total"] == 1
    assert goals.data["summary"]["notice"], "the estimates disclosure travels with the data"
    one = await call(app, registry, alice.id, "get_goal_progress", {"goal_id": world.goal})
    api_goal = (
        await http.get(f"/api/v1/goals/{world.goal}/progress", headers=alice.headers)
    ).json()
    assert one.data is not None
    assert one.data["progress"]["progress_percent"] == api_goal["progress_percent"]


async def test_results_are_structured_with_as_of_and_exact_money(
    app: FastAPI, registry: ToolRegistry, world: World
) -> None:
    alice, pid = world.users.alice, world.portfolio
    for tool, args in (
        ("get_portfolio_summary", {}),
        ("get_portfolio_allocation", {"portfolio_id": pid}),
        ("get_portfolio_performance", {"portfolio_id": pid}),
        ("get_net_worth", {}),
        ("get_goal_progress", {}),
    ):
        outcome = await call(app, registry, alice.id, tool, args)
        assert outcome.ok and outcome.data is not None, tool
        stamp = datetime.fromisoformat(outcome.data["as_of"])
        assert stamp.tzinfo is not None, f"{tool}: as_of must carry a time zone"
        assert isinstance(outcome.data["complete"], bool)
        no_floats(outcome.data)
        json.dumps(outcome.for_model())  # serialisable as it is sent to the model


# -------------------------------------------------------------------- cross-user denial
@pytest.mark.parametrize(
    ("tool", "argument"),
    [
        ("get_portfolio_summary", "portfolio_id"),
        ("get_portfolio_allocation", "portfolio_id"),
        ("get_portfolio_performance", "portfolio_id"),
        ("get_goal_progress", "goal_id"),
    ],
)
async def test_bob_cannot_read_alices_data_through_any_tool(
    app: FastAPI,
    registry: ToolRegistry,
    raw: asyncpg.Connection,
    world: World,
    tool: str,
    argument: str,
) -> None:
    bob = world.users.bob
    victim = world.goal if argument == "goal_id" else world.portfolio
    outcome = await call(app, registry, bob.id, tool, {argument: victim})
    assert not outcome.ok and outcome.error_code == "not_found"
    assert outcome.for_model()["error"]["message"] == "Not found."
    assert victim not in json.dumps(outcome.for_model()), "the id is not echoed back"
    rows = await raw.fetch(
        "SELECT outcome, actor_type FROM audit_events WHERE actor_user_id = $1 AND action = "
        "'ai.tool.call' AND details->>'tool' = $2",
        uuid.UUID(bob.id),
        tool,
    )
    assert [(r["outcome"], r["actor_type"]) for r in rows] == [("denied", "ai")]


async def test_a_foreign_id_looks_exactly_like_an_unknown_one(
    app: FastAPI, registry: ToolRegistry, world: World
) -> None:
    bob = world.users.bob
    foreign = await call(
        app, registry, bob.id, "get_portfolio_allocation", {"portfolio_id": world.portfolio}
    )
    unknown = await call(
        app, registry, bob.id, "get_portfolio_allocation", {"portfolio_id": str(uuid.uuid4())}
    )
    assert foreign.for_model()["error"] == unknown.for_model()["error"]


async def test_bobs_combined_views_hold_nothing_of_alices(
    app: FastAPI, registry: ToolRegistry, world: World
) -> None:
    bob = world.users.bob
    summary = await call(app, registry, bob.id, "get_portfolio_summary")
    goals = await call(app, registry, bob.id, "get_goal_progress")
    net = await call(app, registry, bob.id, "get_net_worth")
    assert summary.data is not None and goals.data is not None and net.data is not None
    assert summary.data["portfolios"] == []
    assert goals.data["summary"]["items"] == []
    assert net.data["net_worth"]["assets"]["amount"] == "0.00"
    for outcome in (summary, goals, net):
        assert world.portfolio not in json.dumps(outcome.data)
        assert world.goal not in json.dumps(outcome.data)


async def test_the_model_cannot_name_another_user(
    app: FastAPI, registry: ToolRegistry, world: World
) -> None:
    bob, alice = world.users.bob, world.users.alice
    for tool in ("get_portfolio_summary", "get_net_worth", "get_goal_progress"):
        for field in ("user_id", "owner_id", "email"):
            outcome = await call(app, registry, bob.id, tool, {field: alice.id})
            assert outcome.error_code == "invalid_arguments", (tool, field)


@pytest.mark.parametrize(
    ("tool", "arguments"),
    [
        ("get_portfolio_allocation", {}),
        ("get_portfolio_allocation", {"portfolio_id": "not-a-uuid"}),
        ("get_portfolio_performance", {"portfolio_id": 5}),
        ("get_net_worth", {"currency": "usd"}),
        ("get_net_worth", {"currency": "US"}),
        ("get_portfolio_summary", {"currency": "DROP TABLE"}),
        ("get_goal_progress", {"goal_id": "x"}),
    ],
)
async def test_bad_arguments_are_refused(
    app: FastAPI,
    registry: ToolRegistry,
    world: World,
    tool: str,
    arguments: dict[str, Any],
) -> None:
    outcome = await call(app, registry, world.users.alice.id, tool, arguments)
    assert outcome.error_code == "invalid_arguments"


def test_the_five_tools_are_registered_and_none_takes_a_user() -> None:
    from app.core.config import Settings

    registry = build_tool_registry(Settings(environment="test"))
    assert registry.names >= {
        "get_portfolio_summary",
        "get_portfolio_allocation",
        "get_portfolio_performance",
        "get_net_worth",
        "get_goal_progress",
    }
    for spec in registry.specs():
        assert not any("user" in name.lower() for name in spec.parameters.get("properties", {}))
        assert "guarantee" not in spec.description.lower().replace("not guarantees", "")
