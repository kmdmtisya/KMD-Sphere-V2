"""Goal use cases (P06-T06): create, list, read, update, delete, progress and a summary.

Rules:
- Only the owner sees or changes a goal; anyone else gets "not found" (ADR-0011).
- A goal can be funded by one of the user's portfolios or by all their active portfolios. A
  portfolio that is missing or not the user's is refused the same way (422).
- The target date is after today and at most 60 years ahead.
- Progress uses the forecast engine under the goal's stated assumptions and is an estimate.
- Create, update and delete write audit events (no amounts in the details)."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import Actor, AuditWriter
from app.core.authz import ResourceNotFoundError, require_found
from app.core.errors import ConflictError, InvalidValueError
from app.core.money import Money, minor_units
from app.modules.forecasting import limits
from app.modules.forecasting.engine import Frequency
from app.modules.goals import progress as calc
from app.modules.goals.models import Goal
from app.modules.goals.repository import GoalRepository
from app.modules.goals.schemas import (
    GoalAssumptions,
    GoalCreate,
    GoalOut,
    GoalProgressOut,
    GoalReturns,
    GoalsSummaryOut,
    GoalSummaryItem,
    GoalUpdate,
    ScenarioOutcomeOut,
)
from app.modules.portfolio.summary import Summary
from app.modules.portfolio.summary_service import SummaryService

MAX_GOALS_PER_USER = 50
MAX_YEARS_AHEAD = int(limits.YEARS.maximum)
_NAME_TAKEN = "uq_goals_user_id_name"


class GoalService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = GoalRepository(session)
        self._summaries = SummaryService(session)
        self._audit = AuditWriter(session)

    async def create(self, user_id: uuid.UUID, body: GoalCreate, today: date) -> GoalOut:
        if await self._repo.count(user_id) >= MAX_GOALS_PER_USER:
            raise ConflictError(f"A user can have at most {MAX_GOALS_PER_USER} goals.")
        _check_date(body.target_date, today)
        await self._check_portfolio(user_id, body.portfolio_id)
        values = {
            "name": body.name,
            "goal_type": body.goal_type,
            "target_amount": body.target.amount,
            "target_currency": body.target.currency,
            "target_date": body.target_date,
            "target_in_todays_money": body.target_in_todays_money,
            "portfolio_id": body.portfolio_id,
            **_assumption_values(body.assumptions),
        }
        try:
            row = await self._repo.add(user_id, values)
        except IntegrityError as e:
            await self._session.rollback()
            raise _conflict(e) from e
        await self._repo.set_returns(row.id, body.assumptions.returns.as_dict())
        await self._audit.record(
            "goals.goal.created",
            Actor.user(user_id),
            resource_type="goal",
            resource_id=row.id,
            details={"goal_type": row.goal_type, "currency": row.target_currency},
        )
        await self._session.commit()
        return await self.get(user_id, row.id)

    async def list(self, user_id: uuid.UUID) -> list[GoalOut]:
        rows = await self._repo.list_for(user_id)
        returns = await self._repo.returns([r.id for r in rows])
        return [_out(r, returns[r.id]) for r in rows]

    async def get(self, user_id: uuid.UUID, goal_id: uuid.UUID) -> GoalOut:
        row = await self._owned(user_id, goal_id)
        return _out(row, (await self._repo.returns([row.id]))[row.id])

    async def update(
        self, user_id: uuid.UUID, goal_id: uuid.UUID, change: GoalUpdate, today: date
    ) -> GoalOut:
        current = await self.get(user_id, goal_id)  # 404 for a missing or foreign goal
        given = change.model_dump(exclude_unset=True)
        for key in ("name", "goal_type", "target", "target_date", "target_in_todays_money",
                    "assumptions"):  # fmt: skip
            if key in given and given[key] is None:
                raise InvalidValueError(f"{key} cannot be cleared")
        target = change.target or current.target
        assumptions = change.assumptions or current.assumptions
        if assumptions.contribution.currency != target.currency:
            raise InvalidValueError("assumptions.contribution: must be in the target's currency")
        if change.target_date is not None:
            _check_date(change.target_date, today)
        if "portfolio_id" in given:
            await self._check_portfolio(user_id, change.portfolio_id)
        values: dict[str, Any] = {
            k: given[k]
            for k in ("name", "goal_type", "target_date", "target_in_todays_money", "portfolio_id")
            if k in given
        }
        if change.target is not None:
            values |= {"target_amount": target.amount, "target_currency": target.currency}
        if change.assumptions is not None:
            values |= _assumption_values(change.assumptions)
        if values:
            try:
                await self._repo.update(user_id, goal_id, values)
            except IntegrityError as e:
                await self._session.rollback()
                raise _conflict(e) from e
            if change.assumptions is not None:
                await self._repo.set_returns(goal_id, change.assumptions.returns.as_dict())
            await self._audit.record(
                "goals.goal.updated",
                Actor.user(user_id),
                resource_type="goal",
                resource_id=goal_id,
                details={"changed": sorted(given)},
            )
            await self._session.commit()
        return await self.get(user_id, goal_id)

    async def delete(self, user_id: uuid.UUID, goal_id: uuid.UUID) -> None:
        await self._owned(user_id, goal_id)
        await self._repo.delete(user_id, goal_id)
        await self._audit.record(
            "goals.goal.deleted", Actor.user(user_id), resource_type="goal", resource_id=goal_id
        )
        await self._session.commit()

    async def progress(
        self, user_id: uuid.UUID, goal_id: uuid.UUID, now: datetime
    ) -> GoalProgressOut:
        goal = await self.get(user_id, goal_id)
        return await self._progress(user_id, goal, now, {})

    async def summary(self, user_id: uuid.UUID, now: datetime) -> GoalsSummaryOut:
        values: dict[tuple[str, uuid.UUID | None], Summary] = {}
        items = []
        for goal in await self.list(user_id):
            p = await self._progress(user_id, goal, now, values)
            items.append(
                GoalSummaryItem(
                    id=goal.id,
                    name=goal.name,
                    progress_percent=p.progress_percent,
                    status=p.status,
                    reached=p.reached,
                    target=goal.target,
                    target_date=goal.target_date,
                )
            )
        return GoalsSummaryOut(
            on_track=sum(1 for i in items if i.status == "on_track"),
            total=len(items),
            items=items,
            as_of=now,
            notice=calc.NOTICE,
        )

    async def _progress(
        self,
        user_id: uuid.UUID,
        goal: GoalOut,
        now: datetime,
        values: dict[tuple[str, uuid.UUID | None], Summary],
    ) -> GoalProgressOut:
        key = (goal.target.currency, goal.portfolio_id)
        if key not in values:
            values[key] = await self._summaries.figures_in(user_id, *key)
        funding = values[key]
        a = goal.assumptions
        result = calc.progress(
            calc.GoalInput(
                target=goal.target.amount,
                currency=goal.target.currency,
                target_date=goal.target_date,
                target_in_todays_money=goal.target_in_todays_money,
                assumptions=calc.Assumptions(
                    contribution=a.contribution.amount,
                    returns=a.returns.as_dict(),
                    contribution_frequency=a.contribution_frequency,
                    contribution_growth_percent=a.contribution_growth_percent,
                    inflation_percent=a.inflation_percent,
                    annual_fee_percent=a.annual_fee_percent,
                    compounding_frequency=a.compounding_frequency,
                ),
            ),
            funding.total_value,
            now.date(),
        )
        currency = goal.target.currency

        def money(amount: Decimal) -> Money:
            return Money(amount=amount, currency=currency)

        return GoalProgressOut(
            goal_id=goal.id,
            name=goal.name,
            status=result.status,
            reached=result.reached,
            overdue=result.overdue,
            progress_percent=result.progress_percent,
            current_value=money(result.current_value),
            gap=money(result.gap),
            target=goal.target,
            target_date=goal.target_date,
            target_in_todays_money=goal.target_in_todays_money,
            months_left=result.months_left,
            scenarios=[
                ScenarioOutcomeOut(
                    kind=s.kind,
                    annual_return_percent=s.annual_return_percent,
                    projected_value=money(s.nominal),
                    projected_value_real=money(s.real),
                    reaches_target=s.reaches_target,
                )
                for s in result.scenarios
            ],
            required_contribution=(
                None
                if result.required_contribution is None
                else money(result.required_contribution)
            ),
            estimated_completion=result.estimated_completion,
            value_complete=funding.complete,
            value_as_of=funding.data_as_of(now),
            assumptions=goal.assumptions,
            as_of=now,
            notice=calc.NOTICE,
        )

    async def _owned(self, user_id: uuid.UUID, goal_id: uuid.UUID) -> Goal:
        return require_found(await self._repo.get(user_id, goal_id), "goal")

    async def _check_portfolio(self, user_id: uuid.UUID, portfolio_id: uuid.UUID | None) -> None:
        """A missing portfolio and another user's are refused alike (no existence leak)."""
        if portfolio_id is None:
            return
        try:
            await self._summaries.figures(user_id, portfolio_id)
        except ResourceNotFoundError as e:
            raise InvalidValueError("portfolio_id: no such portfolio") from e


def _check_date(target_date: date, today: date) -> None:
    if target_date <= today:
        raise InvalidValueError("target_date must be after today")
    if calc.months_between(today, target_date) > MAX_YEARS_AHEAD * 12:
        raise InvalidValueError(f"target_date must be at most {MAX_YEARS_AHEAD} years ahead")


def _assumption_values(a: GoalAssumptions) -> dict[str, Any]:
    return {
        "contribution": a.contribution.amount,
        "contribution_frequency": a.contribution_frequency.value,
        "contribution_growth_percent": a.contribution_growth_percent,
        "inflation_percent": a.inflation_percent,
        "annual_fee_percent": a.annual_fee_percent,
        "compounding_frequency": a.compounding_frequency.value,
    }


def _out(row: Goal, returns: dict[str, Decimal]) -> GoalOut:
    """Stored columns have a fixed scale (8 for amounts, 4 for percentages); values never had
    more digits than the currency's minor units or 2, so they are shown at that precision."""
    places = minor_units(row.target_currency)

    def money(amount: Decimal) -> Money:
        return Money(
            amount=amount.quantize(Decimal(1).scaleb(-places)), currency=row.target_currency
        )

    return GoalOut(
        id=row.id,
        name=row.name,
        goal_type=row.goal_type,
        target=money(row.target_amount),
        target_date=row.target_date,
        target_in_todays_money=row.target_in_todays_money,
        portfolio_id=row.portfolio_id,
        assumptions=GoalAssumptions(
            contribution=money(row.contribution),
            contribution_frequency=Frequency(row.contribution_frequency),
            contribution_growth_percent=_percent(row.contribution_growth_percent),
            inflation_percent=_percent(row.inflation_percent),
            annual_fee_percent=_percent(row.annual_fee_percent),
            compounding_frequency=Frequency(row.compounding_frequency),
            returns=GoalReturns(**{k: _percent(v) for k, v in returns.items()}),
        ),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _percent(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))


def _conflict(error: IntegrityError) -> Exception:
    if _NAME_TAKEN in str(error.orig):
        return ConflictError("You already have a goal with this name.")
    return error
