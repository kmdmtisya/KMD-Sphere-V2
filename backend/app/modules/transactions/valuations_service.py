"""Manual valuations (P05-T07): values for assets without a market price.

Selection rule ("latest as of"): for an asset in a portfolio, the valuation with the greatest
`as_of` at or before the moment asked about. The database allows one valuation per asset per
instant, so the choice is always unique. Corrections and deletions are audited."""

import base64
import binascii
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select, text, tuple_, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import Actor, AuditWriter
from app.core.authz import owned_by, require_found
from app.core.errors import ConflictError, InvalidValueError
from app.core.money import Money, decimals_of, minor_units, round_half_up
from app.modules.assets.service import AssetService
from app.modules.portfolio.models import Portfolio
from app.modules.transactions.models import Valuation
from app.modules.transactions.valuations_schemas import (
    ValuationCreate,
    ValuationOut,
    ValuationPage,
    ValuationUpdate,
)

MAX_PAGE = 100
FUTURE_SLACK = timedelta(days=1)


class ValuationService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._assets = AssetService(session)
        self._audit = AuditWriter(session)

    # ------------------------------------------------------------------------------ writes

    async def create(
        self, user_id: uuid.UUID, portfolio_id: uuid.UUID, body: ValuationCreate
    ) -> ValuationOut:
        await self._writable(user_id, portfolio_id)
        _check_money(body.value)
        _check_as_of(body.as_of)
        if not await self._assets.is_visible(user_id, body.asset_id):
            raise InvalidValueError("asset_id: no such asset")
        row = Valuation(
            portfolio_id=portfolio_id,
            asset_id=body.asset_id,
            value=body.value.amount,
            currency=body.value.currency,
            as_of=body.as_of,
            source=body.source,
            note=body.note,
            created_by_user_id=user_id,
        )
        self._session.add(row)
        try:
            await self._session.flush()
        except IntegrityError as e:
            await self._session.rollback()
            raise ConflictError(
                "This asset already has a valuation at that moment; correct it instead."
            ) from e
        await self._session.refresh(row)
        await self._record("transactions.valuation.created", user_id, row, ["value", "source"])
        await self._session.commit()
        return _out(row)

    async def update(
        self,
        user_id: uuid.UUID,
        portfolio_id: uuid.UUID,
        valuation_id: uuid.UUID,
        change: ValuationUpdate,
    ) -> ValuationOut:
        await self._writable(user_id, portfolio_id)
        current = await self._get(portfolio_id, valuation_id)
        sent = change.model_dump(exclude_unset=True)
        for key in ("value", "source"):
            if key in sent and sent[key] is None:
                raise InvalidValueError(f"{key} cannot be cleared")
        values: dict[str, Any] = {}
        if change.value is not None:
            _check_money(change.value)
            values.update(value=change.value.amount, currency=change.value.currency)
        if "source" in sent:
            values["source"] = change.source
        if "note" in sent:
            values["note"] = change.note
        if values:
            await self._session.execute(
                update(Valuation)
                .where(Valuation.id == current.id, Valuation.portfolio_id == portfolio_id)
                .values(**values, updated_at=text("now()"))
            )
            await self._session.refresh(current)
            await self._record("transactions.valuation.updated", user_id, current, sorted(sent))
            await self._session.commit()
        return _out(current)

    async def delete(
        self, user_id: uuid.UUID, portfolio_id: uuid.UUID, valuation_id: uuid.UUID
    ) -> None:
        await self._writable(user_id, portfolio_id)
        current = await self._get(portfolio_id, valuation_id)
        await self._record("transactions.valuation.deleted", user_id, current, [])
        await self._session.execute(
            delete(Valuation).where(
                Valuation.id == current.id, Valuation.portfolio_id == portfolio_id
            )
        )
        await self._session.commit()

    # ------------------------------------------------------------------------------- reads

    async def get(
        self, user_id: uuid.UUID, portfolio_id: uuid.UUID, valuation_id: uuid.UUID
    ) -> ValuationOut:
        await self._owned(user_id, portfolio_id)
        return _out(await self._get(portfolio_id, valuation_id))

    async def page(
        self,
        user_id: uuid.UUID,
        portfolio_id: uuid.UUID,
        asset_id: uuid.UUID | None,
        cursor: str | None,
        limit: int,
    ) -> ValuationPage:
        await self._owned(user_id, portfolio_id)
        limit = min(limit, MAX_PAGE)
        stmt = select(Valuation).where(Valuation.portfolio_id == portfolio_id)
        if asset_id:
            stmt = stmt.where(Valuation.asset_id == asset_id)
        after = _decode(cursor)
        if after:
            stmt = stmt.where(tuple_(Valuation.as_of, Valuation.id) < tuple_(*after))
        stmt = stmt.order_by(Valuation.as_of.desc(), Valuation.id.desc()).limit(limit + 1)
        rows = list((await self._session.execute(stmt)).scalars())
        page = rows[:limit]
        return ValuationPage(
            items=[_out(r) for r in page],
            next_cursor=_encode(page[-1]) if len(rows) > limit else None,
        )

    async def latest(
        self, user_id: uuid.UUID, portfolio_id: uuid.UUID, at: datetime | None
    ) -> list[ValuationOut]:
        """Per asset, the valuation with the greatest as-of at or before `at` (default: now)."""
        await self._owned(user_id, portfolio_id)
        return [_out(v) for v in await self.latest_rows(portfolio_id, at)]

    async def latest_rows(self, portfolio_id: uuid.UUID, at: datetime | None) -> list[Valuation]:
        """For other services (the summary); the caller has authorised the portfolio."""
        moment = at or datetime.now(UTC)
        newest = (
            select(Valuation.asset_id, func.max(Valuation.as_of).label("as_of"))
            .where(Valuation.portfolio_id == portfolio_id, Valuation.as_of <= moment)
            .group_by(Valuation.asset_id)
            .subquery()
        )
        result = await self._session.execute(
            select(Valuation)
            .join(
                newest,
                (Valuation.asset_id == newest.c.asset_id) & (Valuation.as_of == newest.c.as_of),
            )
            .where(Valuation.portfolio_id == portfolio_id)
            .order_by(Valuation.asset_id)
        )
        return list(result.scalars())

    # ----------------------------------------------------------------------------- helpers

    async def _owned(self, user_id: uuid.UUID, portfolio_id: uuid.UUID) -> Portfolio:
        result = await self._session.execute(
            owned_by(Portfolio, user_id).where(Portfolio.id == portfolio_id)
        )
        return require_found(result.scalar_one_or_none(), "portfolio")

    async def _writable(self, user_id: uuid.UUID, portfolio_id: uuid.UUID) -> Portfolio:
        portfolio = await self._owned(user_id, portfolio_id)
        if portfolio.archived_at is not None:
            raise ConflictError("An archived portfolio cannot be changed.")
        return portfolio

    async def _get(self, portfolio_id: uuid.UUID, valuation_id: uuid.UUID) -> Valuation:
        result = await self._session.execute(
            select(Valuation)
            .where(Valuation.id == valuation_id, Valuation.portfolio_id == portfolio_id)
            .execution_options(populate_existing=True)
        )
        return require_found(result.scalar_one_or_none(), "valuation")

    async def _record(
        self, action: str, user_id: uuid.UUID, row: Valuation, changed: list[str]
    ) -> None:
        await self._audit.record(
            action,
            Actor.user(user_id),
            resource_type="valuation",
            resource_id=row.id,
            details={
                "portfolio_id": str(row.portfolio_id),
                "asset_id": str(row.asset_id),
                "as_of": row.as_of.isoformat(),
                "changed": changed,
            },
        )


def _check_money(value: Money) -> None:
    places = minor_units(value.currency)
    if decimals_of(value.amount) > places:
        raise InvalidValueError(f"value: {value.currency} amounts have at most {places} decimals")
    if value.amount < 0:
        raise InvalidValueError("value: must not be negative")


def _check_as_of(as_of: datetime) -> None:
    if as_of > datetime.now(UTC) + FUTURE_SLACK:
        raise InvalidValueError("as_of: must not be in the future")


def _out(row: Valuation) -> ValuationOut:
    return ValuationOut(
        id=row.id,
        portfolio_id=row.portfolio_id,
        asset_id=row.asset_id,
        value=Money(
            amount=round_half_up(row.value, minor_units(row.currency)), currency=row.currency
        ),
        as_of=row.as_of,
        source=row.source,
        note=row.note,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _encode(row: Valuation) -> str:
    raw = json.dumps([row.as_of.isoformat(), str(row.id)])
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def _decode(cursor: str | None) -> tuple[datetime, uuid.UUID] | None:
    if cursor is None:
        return None
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        as_of, ident = json.loads(base64.urlsafe_b64decode(padded))
        return datetime.fromisoformat(as_of), uuid.UUID(ident)
    except (ValueError, TypeError, binascii.Error) as e:
        raise InvalidValueError("cursor: not a valid cursor") from e
