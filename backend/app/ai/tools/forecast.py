"""The forecast tools (P10-T04): `run_compound_forecast` and `run_goal_forecast`.

They call the deterministic forecast engine through the same service the API uses and nothing
else: no model, no market data, no randomness, no stored user data. The assumptions are the model's
arguments, which it takes from the user or states explicitly as its own; every result carries the
assumptions back and the engine's "illustrative, not guaranteed" notice.
"""

from pydantic import Field

from app.ai.tools.base import Tool, ToolArguments, ToolContext, ToolData
from app.ai.tools.registry import ToolRegistry
from app.modules.forecasting import service as forecasting
from app.modules.forecasting.schemas import (
    CompoundForecastIn,
    CompoundForecastOut,
    GoalForecastIn,
    GoalForecastOut,
)


class CompoundForecastArguments(ToolArguments):
    inputs: CompoundForecastIn = Field(
        description="The assumptions to project: starting amount, regular contribution, an "
        "assumed annual return in percent, years, and optionally inflation, fees and "
        "frequencies. Use the user's own numbers; if you must assume one, say so."
    )


class CompoundForecastResult(ToolData):
    forecast: CompoundForecastOut


async def run_compound_forecast(
    ctx: ToolContext, args: CompoundForecastArguments
) -> CompoundForecastResult:
    forecast = forecasting.compound(args.inputs)
    return CompoundForecastResult(as_of=forecast.as_of, forecast=forecast)


class GoalForecastArguments(ToolArguments):
    inputs: GoalForecastIn = Field(
        description="The target to reach, the years, the starting amount and an assumed annual "
        "return in percent (optionally inflation, fees and frequencies). The result is the "
        "regular contribution that reaches the target under those assumptions."
    )


class GoalForecastResult(ToolData):
    forecast: GoalForecastOut


async def run_goal_forecast(ctx: ToolContext, args: GoalForecastArguments) -> GoalForecastResult:
    forecast = forecasting.goal(args.inputs)
    return GoalForecastResult(as_of=forecast.as_of, forecast=forecast)


def register_forecast_tools(registry: ToolRegistry) -> None:
    registry.register(
        Tool(
            "run_compound_forecast",
            "Project how an amount could grow with regular contributions under the given "
            "assumptions (illustrative scenario, never a prediction or a guaranteed return). "
            "Computed by WealthSphere's deterministic engine.",
            CompoundForecastArguments,
            CompoundForecastResult,
            run_compound_forecast,
        )
    )
    registry.register(
        Tool(
            "run_goal_forecast",
            "Find the regular contribution that would reach a target amount by a date under "
            "the given assumptions (illustrative, not a guarantee). Computed by WealthSphere's "
            "deterministic engine.",
            GoalForecastArguments,
            GoalForecastResult,
            run_goal_forecast,
        )
    )
