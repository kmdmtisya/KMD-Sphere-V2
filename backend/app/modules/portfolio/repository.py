"""Portfolio queries. Every read starts from `owned_by` and every write repeats the owner in its
WHERE clause (ADR-0011)."""

import uuid
from typing import Any

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authz import owned_by
from app.modules.portfolio.models import Portfolio


class PortfolioRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def count(self, user_id: uuid.UUID) -> int:
        result = await self._session.execute(
            select(func.count()).select_from(Portfolio).where(Portfolio.user_id == user_id)
        )
        return int(result.scalar_one())

    async def add(self, user_id: uuid.UUID, values: dict[str, Any]) -> Portfolio:
        row = Portfolio(user_id=user_id, **values)
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return row

    async def list(self, user_id: uuid.UUID, include_archived: bool) -> list[Portfolio]:
        stmt = owned_by(Portfolio, user_id)
        if not include_archived:
            stmt = stmt.where(Portfolio.archived_at.is_(None))
        result = await self._session.execute(stmt.order_by(Portfolio.created_at, Portfolio.id))
        return list(result.scalars())

    async def get(self, user_id: uuid.UUID, portfolio_id: uuid.UUID) -> Portfolio | None:
        """The caller's portfolio, or None if it does not exist or belongs to someone else."""
        result = await self._session.execute(
            owned_by(Portfolio, user_id)
            .where(Portfolio.id == portfolio_id)
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def update(
        self, user_id: uuid.UUID, portfolio_id: uuid.UUID, values: dict[str, Any]
    ) -> bool:
        """Updates only an active portfolio owned by `user_id`. Returns whether a row changed."""
        result = await self._session.execute(
            update(Portfolio)
            .where(
                Portfolio.id == portfolio_id,
                Portfolio.user_id == user_id,
                Portfolio.archived_at.is_(None),
            )
            .values(**values, updated_at=text("now()"))
            .returning(Portfolio.id)
        )
        return result.scalar_one_or_none() is not None
