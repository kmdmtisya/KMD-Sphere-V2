"""Liability persistence. Every query and write is scoped to the owner (ADR-0011)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authz import owned_by
from app.modules.networth.models import Liability


class LiabilityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def count(self, user_id: uuid.UUID) -> int:
        result = await self._session.execute(
            select(func.count()).select_from(Liability).where(Liability.user_id == user_id)
        )
        return int(result.scalar_one())

    async def add(self, user_id: uuid.UUID, values: dict[str, Any]) -> Liability:
        row = Liability(user_id=user_id, **values)
        self._session.add(row)
        await self._session.flush()
        return row

    async def get(self, user_id: uuid.UUID, liability_id: uuid.UUID) -> Liability | None:
        result = await self._session.execute(
            owned_by(Liability, user_id).where(Liability.id == liability_id)
        )
        return result.scalar_one_or_none()

    async def list_for(self, user_id: uuid.UUID) -> list[Liability]:
        result = await self._session.execute(
            owned_by(Liability, user_id).order_by(Liability.name, Liability.id)
        )
        return list(result.scalars())

    async def update(
        self,
        user_id: uuid.UUID,
        liability_id: uuid.UUID,
        values: dict[str, Any],
        expected_updated_at: datetime | None = None,
    ) -> bool:
        """Returns whether a row changed; with `expected_updated_at`, only if it is still that
        version (optimistic concurrency, app/core/concurrency.py)."""
        statement = update(Liability).where(
            Liability.id == liability_id, Liability.user_id == user_id
        )
        if expected_updated_at is not None:
            statement = statement.where(Liability.updated_at == expected_updated_at)
        result = await self._session.execute(
            statement.values(**values, updated_at=func.now()).returning(Liability.id)
        )
        return result.scalar_one_or_none() is not None

    async def delete(self, user_id: uuid.UUID, liability_id: uuid.UUID) -> None:
        await self._session.execute(
            delete(Liability).where(Liability.id == liability_id, Liability.user_id == user_id)
        )
