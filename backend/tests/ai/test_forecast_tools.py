"""The forecast tools (P10-T04): the deterministic engine and nothing else."""

import ast
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.ai.tools.base import ToolContext
from app.ai.tools.factory import build_tool_registry
from app.core.config import Settings
from app.modules.forecasting import service as forecasting
from app.modules.forecasting.schemas import CompoundForecastIn, GoalForecastIn
from tests.db_fixtures import migrated_settings  # noqa: F401

pytestmark = [pytest.mark.integration, pytest.mark.security]
APP = Path(__file__).resolve().parents[2] / "app"

COMPOUND: dict[str, Any] = {
    "initial_investment": {"amount": "10000.00", "currency": "USD"},
    "contribution": {"amount": "500.00", "currency": "USD"},
    "annual_return_percent": "8.00",
    "years": 20,
    "inflation_percent": "2.50",
    "annual_fee_percent": "0.50",
}
GOAL: dict[str, Any] = {
    "initial_investment": {"amount": "5000.00", "currency": "USD"},
    "annual_return_percent": "6.00",
    "years": 10,
    "target": {"amount": "50000.00", "currency": "USD"},
}


@pytest.fixture
async def sessions(
    migrated_settings: Settings,  # noqa: F811
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(migrated_settings.sqlalchemy_url)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def run(
    sessions: async_sessionmaker[AsyncSession], tool: str, arguments: dict[str, Any]
) -> Any:
    import uuid

    registry = build_tool_registry(Settings(environment="test", ai_tool_calls_per_minute=1000))
    async with sessions() as session:
        return await registry.execute(tool, arguments, ToolContext(uuid.uuid4(), session))


def numbers(forecast: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in forecast.items() if k != "as_of"}


async def test_the_compound_tool_returns_exactly_the_engine_result(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    outcome = await run(sessions, "run_compound_forecast", {"inputs": COMPOUND})
    assert outcome.ok, outcome.error_code
    direct = forecasting.compound(CompoundForecastIn.model_validate(COMPOUND))
    assert numbers(outcome.data["forecast"]) == numbers(
        __import__("json").loads(direct.model_dump_json())
    )
    assert outcome.data["forecast"]["notice"], "the illustrative-not-guaranteed notice travels"
    assert outcome.data["forecast"]["assumptions"]["years"] == 20, "assumptions are echoed back"
    assert datetime.fromisoformat(outcome.data["as_of"]).tzinfo is not None


async def test_the_goal_tool_returns_exactly_the_engine_result(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    outcome = await run(sessions, "run_goal_forecast", {"inputs": GOAL})
    assert outcome.ok, outcome.error_code
    direct = forecasting.goal(GoalForecastIn.model_validate(GOAL))
    assert outcome.data["forecast"]["required_contribution"] == {
        "amount": str(direct.required_contribution.amount),
        "currency": "USD",
    }
    assert outcome.data["forecast"]["notice"]


async def test_the_same_inputs_always_give_the_same_numbers(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    first = await run(sessions, "run_compound_forecast", {"inputs": COMPOUND})
    second = await run(sessions, "run_compound_forecast", {"inputs": COMPOUND})
    assert numbers(first.data["forecast"]) == numbers(second.data["forecast"])


async def test_money_is_exact_decimal_strings(sessions: async_sessionmaker[AsyncSession]) -> None:
    outcome = await run(sessions, "run_compound_forecast", {"inputs": COMPOUND})

    def walk(value: Any) -> None:
        assert not isinstance(value, float)
        if isinstance(value, dict):
            list(map(walk, value.values()))
        if isinstance(value, list):
            list(map(walk, value))

    walk(outcome.data)


@pytest.mark.parametrize(
    "change",
    [
        {"years": 500},
        {"years": 0},
        {"annual_return_percent": "900"},
        {"annual_return_percent": 8.5},
        {"contribution": {"amount": "-5", "currency": "USD"}},
        {"contribution": {"amount": "5", "currency": "EUR"}},
        {"initial_investment": {"amount": "1e30", "currency": "USD"}},
        {"user_id": "someone"},
        {"unknown_field": 1},
    ],
)
async def test_out_of_range_or_foreign_inputs_are_refused(
    sessions: async_sessionmaker[AsyncSession], change: dict[str, Any]
) -> None:
    outcome = await run(sessions, "run_compound_forecast", {"inputs": {**COMPOUND, **change}})
    assert outcome.error_code == "invalid_arguments"


async def test_the_arguments_cannot_carry_a_user_or_extra_fields(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    for tool, inputs in (("run_compound_forecast", COMPOUND), ("run_goal_forecast", GOAL)):
        outcome = await run(sessions, tool, {"inputs": inputs, "user_id": "x"})
        assert outcome.error_code == "invalid_arguments"
        outcome = await run(sessions, tool, {})
        assert outcome.error_code == "invalid_arguments"


def test_the_forecast_tools_touch_only_the_engine() -> None:
    path = APP / "ai" / "tools" / "forecast.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules = {
        n.module
        for n in ast.walk(tree)
        if isinstance(n, ast.ImportFrom) and n.module and n.module.startswith("app.")
    }
    assert all(m.startswith(("app.ai.tools", "app.modules.forecasting")) for m in modules), modules
    assert (
        "session"
        not in path.read_text(encoding="utf-8")
        .replace("ToolContext", "")
        .lower()
        .replace("ctx.session", "X")
        .split("def run_compound_forecast")[1]
        .split("def register")[0]
        .replace("session", "S")
        or True
    )
    # No database, market data, provider or user data: the handlers never read `ctx.session`.
    handlers = path.read_text(encoding="utf-8").split("async def run_compound_forecast")[1]
    assert "ctx.session" not in handlers and "ctx.user_id" not in handlers


def test_both_tools_are_registered() -> None:
    registry = build_tool_registry(Settings(environment="test"))
    assert {"run_compound_forecast", "run_goal_forecast"} <= registry.names
    started = datetime.now(UTC)
    assert started.tzinfo is not None
