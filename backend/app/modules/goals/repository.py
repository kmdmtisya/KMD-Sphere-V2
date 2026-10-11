"""Goal persistence. Every query is scoped to the owner (ADR-0011)."""

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authz import owned_by
from app.modules.goals.models import Goal, GoalScenario


class GoalRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def count(self, user_id: uuid.UUID) -> int:
        result = await self._session.execute(
            select(func.count()).select_from(Goal).where(Goal.user_id == user_id)
        )
        return int(result.scalar_one())

    async def add(self, user_id: uuid.UUID, values: dict[str, Any]) -> Goal:
        row = Goal(user_id=user_id, **values)
        self._session.add(row)
        await self._session.flush()
        return row

    async def get(self, user_id: uuid.UUID, goal_id: uuid.UUID) -> Goal | None:
        result = await self._session.execute(owned_by(Goal, user_id).where(Goal.id == goal_id))
        return result.scalar_one_or_none()

    async def list_for(self, user_id: uuid.UUID) -> list[Goal]:
        result = await self._session.execute(
            owned_by(Goal, user_id).order_by(Goal.target_date, Goal.name, Goal.id)
        )
        return list(result.scalars())

    async def update(self, user_id: uuid.UUID, goal_id: uuid.UUID, values: dict[str, Any]) -> None:
        await self._session.execute(
            update(Goal)
            .where(Goal.id == goal_id, Goal.user_id == user_id)
            .values(**values, updated_at=func.now())
        )

    async def delete(self, user_id: uuid.UUID, goal_id: uuid.UUID) -> None:
        await self._session.execute(delete(Goal).where(Goal.id == goal_id, Goal.user_id == user_id))

    async def returns(self, goal_ids: list[uuid.UUID]) -> dict[uuid.UUID, dict[str, Decimal]]:
        """Scenario returns per goal (the caller has authorised the goals)."""
        out: dict[uuid.UUID, dict[str, Decimal]] = {g: {} for g in goal_ids}
        if goal_ids:
            result = await self._session.execute(
                select(GoalScenario).where(GoalScenario.goal_id.in_(goal_ids))
            )
            for s in result.scalars():
                out[s.goal_id][s.kind] = s.annual_return_percent
        return out

    async def set_returns(self, goal_id: uuid.UUID, returns: dict[str, Decimal]) -> None:
        await self._session.execute(delete(GoalScenario).where(GoalScenario.goal_id == goal_id))
        for kind, rate in returns.items():
            self._session.add(GoalScenario(goal_id=goal_id, kind=kind, annual_return_percent=rate))
        await self._session.flush()
