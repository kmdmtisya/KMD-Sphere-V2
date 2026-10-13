"""Portfolio Doctor service (P12-T01): gathers one portfolio's existing analytics and applies the
rules. It computes nothing new: values and allocation come from the summary and asset
classifications, risk from the monthly value history, income from the trailing 12 months, and
goal status from the goal service. Ownership is enforced by those services (another user's
portfolio is not found)."""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import InvalidValueError
from app.modules.analytics.risk import RiskStatus
from app.modules.assets.service import AssetService
from app.modules.doctor.rules import (
    DEFAULT_THRESHOLDS,
    Diagnosis,
    GoalState,
    Holding,
    Inputs,
    Thresholds,
    diagnose,
)
from app.modules.goals.service import GoalService
from app.modules.networth.income_service import IncomeService
from app.modules.portfolio.history import SeriesFrequency
from app.modules.portfolio.risk_service import RiskService
from app.modules.portfolio.summary_service import SummaryService


@dataclass(frozen=True)
class PortfolioDiagnosis:
    portfolio_id: uuid.UUID
    as_of: datetime
    diagnosis: Diagnosis
    inputs: Inputs


class DoctorService:
    def __init__(self, session: AsyncSession, thresholds: Thresholds = DEFAULT_THRESHOLDS) -> None:
        self._summaries = SummaryService(session)
        self._assets = AssetService(session)
        self._risk = RiskService(session)
        self._income = IncomeService(session)
        self._goals = GoalService(session)
        self._thresholds = thresholds

    async def portfolio(
        self, user_id: uuid.UUID, portfolio_id: uuid.UUID, now: datetime
    ) -> PortfolioDiagnosis:
        """Raises ResourceNotFoundError (404) unless the portfolio is the user's."""
        inputs = await self.inputs(user_id, portfolio_id, now)
        return PortfolioDiagnosis(portfolio_id, now, diagnose(inputs, self._thresholds), inputs)

    async def inputs(self, user_id: uuid.UUID, portfolio_id: uuid.UUID, now: datetime) -> Inputs:
        summary = await self._summaries.figures(user_id, portfolio_id)  # the ownership check
        classes = await self._assets.classifications(sorted(summary.positions))
        holdings = [
            Holding(
                asset_id,
                value,
                classes[asset_id].asset_class,
                summary.position_currencies[asset_id],
                classes[asset_id].country,
                classes[asset_id].sector,
            )
            for asset_id, value in sorted(summary.positions.items())
        ]
        try:
            risk = (
                await self._risk.portfolio(user_id, portfolio_id, SeriesFrequency.MONTHLY, now=now)
            ).risk
            risk_status = risk.status.value
            vol = risk.volatility if risk.status is RiskStatus.OK else None
            fall = (
                -risk.max_drawdown.depth
                if risk.status is RiskStatus.OK and risk.max_drawdown is not None
                else None
            )
        except InvalidValueError:
            risk_status, vol, fall = RiskStatus.INSUFFICIENT_DATA.value, None, None
        income = await self._income.portfolio(user_id, portfolio_id, now.date())
        goals = [
            await self._goals.progress(user_id, g.id, now)
            for g in await self._goals.list(user_id)
            if g.portfolio_id == portfolio_id
        ]
        return Inputs(
            currency=summary.currency,
            total=summary.total_value,
            holdings=holdings,
            cash_balances=dict(summary.cash_balances),
            complete=summary.complete,
            unpriced_assets=len(summary.unpriced_assets),
            risk_status=risk_status,
            volatility=vol,
            max_drawdown=fall,
            income_by_asset={a.asset_id: a.trailing_12m.gross for a in income.by_asset},
            goals=[GoalState(g.goal_id, g.name, g.status, g.reached, g.overdue) for g in goals],
        )
