"""The core read tools (P10-T03): portfolio summary, allocation and performance, net worth, goal
progress. Each wraps the same service the API route uses and returns the API's own answer, so a
figure the assistant states is the figure the app shows. Read-only; ownership is checked by the
service (a foreign or unknown id is "not found")."""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from app.ai.tools.base import Tool, ToolArguments, ToolContext, ToolData
from app.ai.tools.registry import ToolRegistry
from app.core.money import CURRENCY_PATTERN
from app.modules.goals.schemas import GoalProgressOut, GoalsSummaryOut
from app.modules.goals.service import GoalService
from app.modules.networth.schemas import NetWorthOut
from app.modules.networth.service import NetWorthService
from app.modules.portfolio.analytics_schemas import (
    AllocationOut,
    DrawdownOut,
    PerformanceOut,
)
from app.modules.portfolio.analytics_views import allocation_out, performance_out, risk_out
from app.modules.portfolio.history import SeriesFrequency
from app.modules.portfolio.service import PortfolioService
from app.modules.portfolio.summary_schemas import SummaryOut
from app.modules.portfolio.summary_service import SummaryService

Currency = Annotated[str, StringConstraints(pattern=CURRENCY_PATTERN)]


# ------------------------------------------------------------------------ summary
class PortfolioLine(BaseModel):
    id: uuid.UUID
    name: str
    base_currency: str


class SummaryArguments(ToolArguments):
    portfolio_id: uuid.UUID | None = Field(
        default=None, description="One portfolio. Omit for all portfolios combined."
    )
    currency: Currency | None = Field(
        default=None, description="Reporting currency for the combined view (ISO 4217)."
    )


class SummaryResult(ToolData):
    portfolios: list[PortfolioLine]
    summary: SummaryOut


async def get_portfolio_summary(ctx: ToolContext, args: SummaryArguments) -> SummaryResult:
    service = SummaryService(ctx.session)
    portfolios = [
        PortfolioLine(id=p.id, name=p.name, base_currency=p.base_currency)
        for p in await PortfolioService(ctx.session).list(ctx.user_id, False)
    ]
    summary = (
        await service.portfolio(ctx.user_id, args.portfolio_id)
        if args.portfolio_id is not None
        else await service.consolidated(ctx.user_id, args.currency)
    )
    return SummaryResult(
        as_of=summary.freshness.data_as_of,
        complete=summary.freshness.complete,
        portfolios=portfolios,
        summary=summary,
    )


# ---------------------------------------------------------------------- allocation
class PortfolioArguments(ToolArguments):
    portfolio_id: uuid.UUID = Field(description="One of the user's portfolios (from the summary).")


class AllocationResult(ToolData):
    allocation: AllocationOut


async def get_portfolio_allocation(ctx: ToolContext, args: PortfolioArguments) -> AllocationResult:
    allocation = await allocation_out(ctx.session, ctx.user_id, args.portfolio_id)
    return AllocationResult(as_of=ctx.now(), complete=allocation.complete, allocation=allocation)


# --------------------------------------------------------------------- performance
class RiskStats(BaseModel):
    """Volatility, drawdown and time-weighted return, without the value series."""

    status: str
    volatility_percent: str | None
    max_drawdown: DrawdownOut | None
    time_weighted_return_percent: str | None
    time_weighted_annualized_percent: str | None
    incomplete_points: int
    notice: str


class PerformanceResult(ToolData):
    performance: PerformanceOut
    risk: RiskStats


async def get_portfolio_performance(
    ctx: ToolContext, args: PortfolioArguments
) -> PerformanceResult:
    performance = await performance_out(ctx.session, ctx.user_id, args.portfolio_id)
    risk = await risk_out(
        ctx.session, ctx.user_id, args.portfolio_id, SeriesFrequency.MONTHLY, None, None
    )
    return PerformanceResult(
        as_of=performance.as_of,
        complete=performance.complete and risk.incomplete_points == 0,
        performance=performance,
        risk=RiskStats(
            status=risk.status,
            volatility_percent=None
            if risk.volatility_percent is None
            else str(risk.volatility_percent),
            max_drawdown=risk.max_drawdown,
            time_weighted_return_percent=None
            if risk.time_weighted_return_percent is None
            else str(risk.time_weighted_return_percent),
            time_weighted_annualized_percent=None
            if risk.time_weighted_annualized_percent is None
            else str(risk.time_weighted_annualized_percent),
            incomplete_points=risk.incomplete_points,
            notice=risk.notice,
        ),
    )


# --------------------------------------------------------------------- net worth
class NetWorthArguments(ToolArguments):
    currency: Currency | None = Field(
        default=None, description="Reporting currency (ISO 4217); omit for the user's base."
    )


class NetWorthResult(ToolData):
    net_worth: NetWorthOut


async def get_net_worth(ctx: ToolContext, args: NetWorthArguments) -> NetWorthResult:
    result = await NetWorthService(ctx.session).user(ctx.user_id, args.currency, ctx.now())
    return NetWorthResult(as_of=result.as_of, complete=result.freshness.complete, net_worth=result)


# ------------------------------------------------------------------------- goals
class GoalArguments(ToolArguments):
    goal_id: uuid.UUID | None = Field(
        default=None, description="One goal. Omit for the list of all goals with their status."
    )


class GoalProgressResult(ToolData):
    summary: GoalsSummaryOut | None = None
    progress: GoalProgressOut | None = None


async def get_goal_progress(ctx: ToolContext, args: GoalArguments) -> GoalProgressResult:
    service = GoalService(ctx.session)
    now = datetime.now(UTC)
    if args.goal_id is None:
        summary = await service.summary(ctx.user_id, now)
        return GoalProgressResult(as_of=summary.as_of, summary=summary)
    progress = await service.progress(ctx.user_id, args.goal_id, now)
    return GoalProgressResult(
        as_of=progress.as_of, complete=progress.value_complete, progress=progress
    )


# ---------------------------------------------------------------------- registration
def register_core_read_tools(registry: ToolRegistry) -> None:
    registry.register(
        Tool(
            "get_portfolio_summary",
            "The user's portfolios and the total value, cash, cost basis, gains, income and "
            "freshness of one portfolio or of all combined. Start here to learn the portfolio "
            "ids. Figures are computed by WealthSphere; stale or unpriced assets are flagged.",
            SummaryArguments,
            SummaryResult,
            get_portfolio_summary,
        )
    )
    registry.register(
        Tool(
            "get_portfolio_allocation",
            "How one portfolio is split by asset class, currency, country and sector, with "
            "concentration measures.",
            PortfolioArguments,
            AllocationResult,
            get_portfolio_allocation,
        )
    )
    registry.register(
        Tool(
            "get_portfolio_performance",
            "Profit, simple return and money-weighted return of one portfolio since the "
            "start, plus volatility, maximum drawdown and time-weighted return. Past "
            "performance only; not a forecast.",
            PortfolioArguments,
            PerformanceResult,
            get_portfolio_performance,
        )
    )
    registry.register(
        Tool(
            "get_net_worth",
            "Assets minus liabilities in the reporting currency, with the breakdown, the "
            "exchange rates used and whether the total is complete.",
            NetWorthArguments,
            NetWorthResult,
            get_net_worth,
        )
    )
    registry.register(
        Tool(
            "get_goal_progress",
            "The user's goals with status and progress, or one goal in detail (gap, scenarios, "
            "required contribution). Statuses are estimates under stated assumptions, not "
            "guarantees.",
            GoalArguments,
            GoalProgressResult,
            get_goal_progress,
        )
    )
