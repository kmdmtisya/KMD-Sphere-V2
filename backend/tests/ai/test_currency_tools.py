"""The Copilot's currency tools (P11-T08): authorised, validated, and equal to the API's answers
for the same snapshot."""

import json
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, time, timedelta
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
from tests.fx.codes import unique_code

pytestmark = [pytest.mark.integration, pytest.mark.security]
CURRENCY_TOOLS = {
    "get_current_fx_rate",
    "get_historical_fx_rate",
    "convert_currency",
    "get_portfolio_value",
    "get_fx_exposure",
}
PAST = datetime.now(UTC).date() - timedelta(days=20)


def code() -> str:
    return unique_code()


@pytest.fixture
async def raw(migrated_settings: Settings) -> AsyncIterator[asyncpg.Connection]:  # noqa: F811
    conn = await asyncpg.connect(migrated_settings.database_dsn, timeout=5)
    yield conn
    await conn.close()


async def store(raw: asyncpg.Connection, base: str, quote: str, rate: str, at: datetime) -> None:
    await raw.execute(
        "INSERT INTO fx_rates (base_currency, quote_currency, rate, provider, rate_timestamp, "
        "retrieved_at) VALUES ($1, $2, $3::numeric, 'tool-test', $4, $4)",
        base,
        quote,
        rate,
        at,
    )


@pytest.fixture
async def world(
    migrated_settings: Settings,  # noqa: F811
    raw: asyncpg.Connection,
) -> AsyncIterator[tuple[FastAPI, str]]:
    """An app whose pivot is a test currency with its own current and past rates."""
    pivot = code()
    await raw.execute(
        "INSERT INTO currencies (code, name, symbol, decimal_places) VALUES ($1, 'Pivot', 'P', 2)",
        pivot,
    )
    now = datetime.now(UTC) - timedelta(minutes=5)
    for quote, rate in (("AED", "3.6725"), ("KES", "129.15"), ("USD", "1")):
        await store(raw, pivot, quote, rate, now)
    await store(raw, pivot, "AED", "3.60", datetime.combine(PAST, time(12), tzinfo=UTC))
    settings = migrated_settings.model_copy(
        update={"fx_pivot_currency": pivot, "ai_tool_calls_per_minute": 1000}
    )
    app = create_app(settings, readiness_checks={}, token_verifier=ah.verifier())
    yield app, pivot
    await app.state.db.dispose()
    await raw.execute("DELETE FROM currencies WHERE code = $1", pivot)


@pytest.fixture
async def http(world: tuple[FastAPI, str]) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=world[0], raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def registry(world: tuple[FastAPI, str], monkeypatch: pytest.MonkeyPatch) -> ToolRegistry:
    import app.ai.tools.currency as currency
    import app.modules.portfolio.summary_service as summary_service

    settings = world[0].state.settings
    monkeypatch.setattr(currency, "get_settings", lambda: settings)
    monkeypatch.setattr(summary_service, "get_settings", lambda: settings)
    return build_tool_registry(settings)


async def call(
    world: tuple[FastAPI, str],
    registry: ToolRegistry,
    user_id: str,
    tool: str,
    arguments: dict[str, Any],
) -> ToolOutcome:
    sessions: async_sessionmaker[AsyncSession] = world[0].state.db.session_factory
    async with sessions() as session:
        return await registry.execute(
            tool, arguments, ToolContext(uuid.UUID(user_id), session, "corr", "fake-1", "fake")
        )


def no_floats(value: Any) -> None:
    assert not isinstance(value, float), "a JSON float in a tool result"
    if isinstance(value, dict):
        for v in value.values():
            no_floats(v)
    if isinstance(value, list):
        for v in value:
            no_floats(v)


async def portfolio(http: httpx.AsyncClient, h: dict[str, str], currency: str, cash: str) -> str:
    pid = str(
        (
            await http.post(
                "/api/v1/portfolios",
                headers=h,
                json={"name": f"P {uuid.uuid4().hex[:6]}", "base_currency": currency},
            )
        ).json()["id"]
    )
    r = await http.post(
        f"/api/v1/portfolios/{pid}/transactions",
        headers=h,
        json={
            "transaction_type": "DEPOSIT",
            "trade_date": (datetime.now(UTC).date() - timedelta(days=3)).isoformat(),
            "currency": currency,
            "gross_amount": {"amount": cash, "currency": currency},
        },
    )
    assert r.status_code == 201, r.text
    return pid


def test_the_currency_tools_are_registered_and_take_no_user() -> None:
    specs = {s.name: s for s in build_tool_registry(Settings()).specs()}
    assert set(specs) >= CURRENCY_TOOLS
    for name in CURRENCY_TOOLS:
        schema = json.dumps(specs[name].parameters)
        assert "user_id" not in schema and "owner" not in schema, name
        assert "guarantee" not in specs[name].description.lower(), name


async def test_the_current_rate_equals_the_apis_for_the_same_snapshot(
    world: tuple[FastAPI, str],
    registry: ToolRegistry,
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    out = await call(
        world, registry, two_users.alice.id, "get_current_fx_rate", {"base": "AED", "quote": "KES"}
    )
    assert out.ok, out.error_code
    data = out.data or {}
    no_floats(data)
    api = (
        await http.get(
            f"/api/v1/fx/rates/AED/KES?snapshot_id={data['snapshot_id']}",
            headers=two_users.alice.headers,
        )
    ).json()
    assert data["rate"] == api["rate"]
    assert data["path"] == api["path"] == ["AED", world[1], "KES"]
    assert data["status"] == "current" and data["providers"] == ["tool-test"]
    assert data["as_of"] and data["rate_timestamp"] and data["notice"]


async def test_a_conversion_equals_the_apis_and_is_audited_as_an_ai_answer(
    world: tuple[FastAPI, str],
    registry: ToolRegistry,
    http: httpx.AsyncClient,
    raw: asyncpg.Connection,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    args = {"amount": {"amount": "500000.00", "currency": "AED"}, "to": "KES"}
    out = await call(world, registry, two_users.alice.id, "convert_currency", args)
    assert out.ok, out.error_code
    data = out.data or {}
    api = (
        await http.post(
            "/api/v1/fx/convert",
            headers=two_users.alice.headers,
            json={**args, "snapshot_id": data["snapshot_id"]},
        )
    ).json()
    assert data["converted"] == api["converted"]
    assert data["rate"] == api["rate"]
    audited = await raw.fetchval(
        "SELECT count(*) FROM fx_conversion_audit WHERE user_id = $1 AND conversion_type = "
        "'ai_answer'",
        uuid.UUID(two_users.alice.id),
    )
    assert audited == 1


async def test_a_historical_rate_is_that_days_and_a_missing_one_is_not_found(
    world: tuple[FastAPI, str],
    registry: ToolRegistry,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    pivot = world[1]
    past = await call(
        world, registry, two_users.alice.id, "get_historical_fx_rate",
        {"base": pivot, "quote": "AED", "on": PAST.isoformat()},
    )  # fmt: skip
    assert past.ok and (past.data or {})["rate"] == "3.6"
    assert (past.data or {})["concept"] == "historical_valuation"
    long_ago = await call(
        world, registry, two_users.alice.id, "get_historical_fx_rate",
        {"base": pivot, "quote": "AED", "on": "2001-01-01"},
    )  # fmt: skip
    assert (long_ago.ok, long_ago.error_code) == (False, "not_found")
    later = (datetime.now(UTC).date() + timedelta(days=3)).isoformat()
    future = await call(
        world, registry, two_users.alice.id, "get_historical_fx_rate",
        {"base": pivot, "quote": "AED", "on": later},
    )  # fmt: skip
    assert future.error_code == "invalid"


@pytest.mark.parametrize(
    ("tool", "arguments", "code"),
    [
        ("get_current_fx_rate", {"base": "AED", "quote": "ZZZ"}, "invalid"),
        ("get_current_fx_rate", {"base": "AED", "quote": "GBP"}, "not_found"),
        ("get_current_fx_rate", {"base": "aed", "quote": "USD"}, "invalid_arguments"),
        (
            "convert_currency",
            {"amount": {"amount": 5, "currency": "AED"}, "to": "USD"},
            "invalid_arguments",
        ),
        ("get_fx_exposure", {"portfolio_id": "x"}, "invalid_arguments"),
        ("get_portfolio_value", {"user_id": str(uuid.uuid4())}, "invalid_arguments"),
    ],
)
async def test_bad_inputs_are_refused(
    world: tuple[FastAPI, str],
    registry: ToolRegistry,
    two_users: TwoUsers,  # noqa: F811
    tool: str,
    arguments: dict[str, Any],
    code: str,
) -> None:
    out = await call(world, registry, two_users.alice.id, tool, arguments)
    assert (out.ok, out.error_code) == (False, code)


async def test_portfolio_value_and_exposure_are_the_owners_only(
    world: tuple[FastAPI, str],
    registry: ToolRegistry,
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    alice = two_users.alice
    aed = await portfolio(http, alice.headers, "AED", "3672.50")
    value = await call(
        world, registry, alice.id, "get_portfolio_value", {"portfolio_id": aed, "currency": "USD"}
    )
    assert value.ok, value.error_code
    data = value.data or {}
    no_floats(data)
    api = (
        await http.get(
            f"/api/v1/portfolios/{aed}/summary", headers=alice.headers, params={"currency": "USD"}
        )
    ).json()
    assert data["total_value"] == api["total_value"] == {"amount": "1000.00", "currency": "USD"}
    assert data["reporting"]["rates"], "the rates used are part of the result"
    exposure = await call(world, registry, alice.id, "get_fx_exposure", {"portfolio_id": aed})
    assert exposure.ok
    shares = (exposure.data or {})["exposure"]
    assert [s["currency"] for s in shares] == ["AED"] and shares[0]["weight_percent"] == "100"
    for tool, args in (
        ("get_portfolio_value", {"portfolio_id": aed}),
        ("get_portfolio_value", {"portfolio_id": aed, "currency": "USD"}),
        ("get_fx_exposure", {"portfolio_id": aed}),
    ):
        stolen = await call(world, registry, two_users.bob.id, tool, args)
        assert (stolen.ok, stolen.error_code) == (False, "not_found"), tool
        assert "3672" not in json.dumps(stolen.for_model())
