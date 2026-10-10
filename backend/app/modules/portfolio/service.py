"""Portfolio use cases: create, list, read, update, archive.

Rules:
- Only the owner sees or changes a portfolio; anyone else gets "not found" (ADR-0011).
- Names are unique per user (409 on a clash).
- The base currency is fixed at creation, so amounts already converted into it keep their meaning.
- Archiving is permanent in this version and makes the portfolio read-only; nothing is deleted.
- Create, update and archive write audit events."""

import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import Actor, AuditWriter
from app.core.authz import require_found
from app.core.errors import ConflictError, InvalidValueError
from app.modules.portfolio.models import Portfolio
from app.modules.portfolio.repository import PortfolioRepository
from app.modules.portfolio.schemas import PortfolioCreate, PortfolioOut, PortfolioUpdate

MAX_PORTFOLIOS_PER_USER = 100
_NAME_TAKEN = "uq_portfolios_user_id_name"


class PortfolioService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = PortfolioRepository(session)
        self._audit = AuditWriter(session)

    async def create(self, user_id: uuid.UUID, body: PortfolioCreate) -> PortfolioOut:
        if await self._repo.count(user_id) >= MAX_PORTFOLIOS_PER_USER:
            raise ConflictError(f"A user can have at most {MAX_PORTFOLIOS_PER_USER} portfolios.")
        values = body.model_dump()
        try:
            row = await self._repo.add(user_id, values)
        except IntegrityError as e:
            await self._session.rollback()
            raise self._conflict(e) from e
        await self._audit.record(
            "portfolio.portfolio.created",
            Actor.user(user_id),
            resource_type="portfolio",
            resource_id=row.id,
            details={"portfolio_type": row.portfolio_type, "base_currency": row.base_currency},
        )
        await self._session.commit()
        return _out(row)

    async def list(self, user_id: uuid.UUID, include_archived: bool) -> list[PortfolioOut]:
        return [_out(r) for r in await self._repo.list(user_id, include_archived)]

    async def get(self, user_id: uuid.UUID, portfolio_id: uuid.UUID) -> PortfolioOut:
        return _out(await self._owned(user_id, portfolio_id))

    async def update(
        self, user_id: uuid.UUID, portfolio_id: uuid.UUID, change: PortfolioUpdate
    ) -> PortfolioOut:
        values: dict[str, Any] = change.model_dump(exclude_unset=True)
        for key in ("name", "portfolio_type"):
            if key in values and values[key] is None:
                raise InvalidValueError(f"{key} cannot be cleared")
        await self._owned(user_id, portfolio_id)  # 404 for a missing or foreign portfolio
        if values:
            try:
                changed = await self._repo.update(user_id, portfolio_id, values)
            except IntegrityError as e:
                await self._session.rollback()
                raise self._conflict(e) from e
            if not changed:  # the repository refuses archived portfolios
                raise ConflictError("An archived portfolio cannot be changed.")
            await self._audit.record(
                "portfolio.portfolio.updated",
                Actor.user(user_id),
                resource_type="portfolio",
                resource_id=portfolio_id,
                details={"changed": sorted(values)},
            )
            await self._session.commit()
        return await self.get(user_id, portfolio_id)

    async def archive(self, user_id: uuid.UUID, portfolio_id: uuid.UUID) -> PortfolioOut:
        """Idempotent: archiving again returns the portfolio unchanged and writes no event."""
        current = await self._owned(user_id, portfolio_id)
        if current.archived_at is None:
            await self._repo.update(user_id, portfolio_id, {"archived_at": text("now()")})
            await self._audit.record(
                "portfolio.portfolio.archived",
                Actor.user(user_id),
                resource_type="portfolio",
                resource_id=portfolio_id,
            )
            await self._session.commit()
        return await self.get(user_id, portfolio_id)

    async def _owned(self, user_id: uuid.UUID, portfolio_id: uuid.UUID) -> Portfolio:
        return require_found(await self._repo.get(user_id, portfolio_id), "portfolio")

    @staticmethod
    def _conflict(error: IntegrityError) -> Exception:
        if _NAME_TAKEN in str(error.orig):
            return ConflictError("You already have a portfolio with this name.")
        return error


def _out(row: Portfolio) -> PortfolioOut:
    return PortfolioOut.model_validate(row, from_attributes=True)
