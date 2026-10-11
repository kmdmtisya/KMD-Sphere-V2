"""Liabilities and net worth (P06-T07).

Rules:
- Only the owner sees or changes a liability; anyone else gets "not found" (ADR-0011).
- A liability can name the asset that secures it; an asset the user cannot see is refused like
  a missing one (422).
- Balances are user-entered figures with the date they applied, never in the future.
- Create, update and delete write audit events (no amounts in the details).
- Net worth = the value of the user's active portfolios - their liabilities, in one currency,
  with every FX rate used (docs/design/net-worth.md)."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import Actor, AuditWriter
from app.core.authz import require_found
from app.core.errors import ConflictError, InvalidValueError
from app.core.money import Money, minor_units, round_half_up
from app.modules.analytics.allocation import Dimension
from app.modules.assets.service import AssetService
from app.modules.networth import networth as calc
from app.modules.networth.models import Liability
from app.modules.networth.repository import LiabilityRepository
from app.modules.networth.schemas import (
    AssetClassShare,
    FxRateUsed,
    LiabilityCreate,
    LiabilityLine,
    LiabilityOut,
    LiabilityTypeTotal,
    LiabilityUpdate,
    NetWorthFreshness,
    NetWorthOut,
)
from app.modules.portfolio.allocation_service import AllocationService
from app.modules.portfolio.service import PortfolioService
from app.modules.portfolio.summary_service import SummaryService

MAX_LIABILITIES_PER_USER = 100
_NAME_TAKEN = "uq_liabilities_user_id_name"


class LiabilityService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = LiabilityRepository(session)
        self._assets = AssetService(session)
        self._audit = AuditWriter(session)

    async def create(self, user_id: uuid.UUID, body: LiabilityCreate, today: date) -> LiabilityOut:
        if await self._repo.count(user_id) >= MAX_LIABILITIES_PER_USER:
            raise ConflictError(f"A user can have at most {MAX_LIABILITIES_PER_USER} liabilities.")
        _check_date(body.balance_as_of, today)
        await self._check_asset(user_id, body.asset_id)
        values = {
            "name": body.name,
            "liability_type": body.liability_type,
            "currency": body.balance.currency,
            "balance": body.balance.amount,
            "balance_as_of": body.balance_as_of,
            "interest_rate_percent": body.interest_rate_percent,
            "asset_id": body.asset_id,
        }
        try:
            row = await self._repo.add(user_id, values)
        except IntegrityError as e:
            await self._session.rollback()
            raise _conflict(e) from e
        await self._audit.record(
            "networth.liability.created",
            Actor.user(user_id),
            resource_type="liability",
            resource_id=row.id,
            details={"liability_type": row.liability_type, "currency": row.currency},
        )
        await self._session.commit()
        return await self.get(user_id, row.id)

    async def list(self, user_id: uuid.UUID) -> list[LiabilityOut]:
        return [_out(r) for r in await self._repo.list_for(user_id)]

    async def get(self, user_id: uuid.UUID, liability_id: uuid.UUID) -> LiabilityOut:
        return _out(await self._owned(user_id, liability_id))

    async def update(
        self, user_id: uuid.UUID, liability_id: uuid.UUID, change: LiabilityUpdate, today: date
    ) -> LiabilityOut:
        await self._owned(user_id, liability_id)
        given = change.model_dump(exclude_unset=True)
        for key in ("name", "liability_type", "balance", "balance_as_of"):
            if key in given and given[key] is None:
                raise InvalidValueError(f"{key} cannot be cleared")
        if change.balance_as_of is not None:
            _check_date(change.balance_as_of, today)
        if "asset_id" in given:
            await self._check_asset(user_id, change.asset_id)
        values: dict[str, Any] = {
            k: given[k]
            for k in (
                "name",
                "liability_type",
                "balance_as_of",
                "interest_rate_percent",
                "asset_id",
            )
            if k in given
        }
        if change.balance is not None:
            values |= {"balance": change.balance.amount, "currency": change.balance.currency}
        if values:
            try:
                await self._repo.update(user_id, liability_id, values)
            except IntegrityError as e:
                await self._session.rollback()
                raise _conflict(e) from e
            await self._audit.record(
                "networth.liability.updated",
                Actor.user(user_id),
                resource_type="liability",
                resource_id=liability_id,
                details={"changed": sorted(given)},
            )
            await self._session.commit()
        return await self.get(user_id, liability_id)

    async def delete(self, user_id: uuid.UUID, liability_id: uuid.UUID) -> None:
        await self._owned(user_id, liability_id)
        await self._repo.delete(user_id, liability_id)
        await self._audit.record(
            "networth.liability.deleted",
            Actor.user(user_id),
            resource_type="liability",
            resource_id=liability_id,
        )
        await self._session.commit()

    async def _owned(self, user_id: uuid.UUID, liability_id: uuid.UUID) -> Liability:
        return require_found(await self._repo.get(user_id, liability_id), "liability")

    async def _check_asset(self, user_id: uuid.UUID, asset_id: uuid.UUID | None) -> None:
        if asset_id is not None and not await self._assets.is_visible(user_id, asset_id):
            raise InvalidValueError("asset_id: no such asset")


class NetWorthService:
    def __init__(self, session: AsyncSession) -> None:
        self._summaries = SummaryService(session)
        self._portfolios = PortfolioService(session)
        self._allocation = AllocationService(session)
        self._liabilities = LiabilityRepository(session)

    async def user(self, user_id: uuid.UUID, currency: str | None, now: datetime) -> NetWorthOut:
        reporting = await self._summaries.reporting_currency(user_id, currency)
        assets = await self._summaries.figures_in(user_id, reporting)
        rows = await self._liabilities.list_for(user_id)
        bases = {p.base_currency for p in await self._portfolios.list(user_id, False)}
        rates = await self._summaries.rates(bases | {r.currency for r in rows}, reporting)
        result = calc.compute(
            reporting,
            assets.total_value,
            [
                calc.Debt(r.id, r.name, r.liability_type, r.currency, r.balance, r.balance_as_of)
                for r in rows
            ],
            rates,
        )
        by_class = (await self._allocation.of(assets)).by[Dimension.ASSET_CLASS]
        places = minor_units(reporting)

        def money(amount: Decimal) -> Money:
            return Money(amount=round_half_up(amount, places), currency=reporting)

        unconverted = sorted(assets.unconverted_currencies | result.unconverted)
        return NetWorthOut(
            currency=reporting,
            assets=money(result.assets),
            liabilities=money(result.liabilities),
            net_worth=money(result.net_worth),
            assets_by_class=[
                AssetClassShare(
                    asset_class=s.key or "unclassified",
                    value=money(s.value),
                    share_percent=s.weight_percent,
                )
                for s in by_class.slices
            ],
            liabilities_by_type=[
                LiabilityTypeTotal(
                    liability_type=t.liability_type,
                    value=money(t.value),
                    count=t.count,
                )
                for t in result.by_type
            ],
            liability_lines=[
                LiabilityLine(
                    id=c.debt.id,
                    name=c.debt.name,
                    liability_type=c.debt.liability_type,
                    balance=_money(c.debt.balance, c.debt.currency),
                    value=None if c.converted is None else money(c.converted),
                    balance_as_of=c.debt.balance_as_of,
                )
                for c in result.debts
            ],
            fx_rates=[
                FxRateUsed(
                    currency=r.currency,
                    rate=r.rate,
                    as_of=r.as_of,
                    provider=r.provider,
                    stale=r.stale,
                    inverted=r.inverted,
                )
                for r in sorted(rates.values(), key=lambda r: r.currency)
            ],
            freshness=NetWorthFreshness(
                computed_at=now,
                data_as_of=min([assets.data_as_of(now), *(r.as_of for r in rates.values())]),
                complete=assets.complete and not result.unconverted,
                unpriced_assets=len(assets.unpriced_assets),
                unconverted_currencies=unconverted,
                stale_fx=sorted(assets.stale_fx | {r.currency for r in rates.values() if r.stale}),
                oldest_liability_balance=min((r.balance_as_of for r in rows), default=None),
            ),
            as_of=now,
        )


def _check_date(balance_as_of: date, today: date) -> None:
    if balance_as_of > today:
        raise InvalidValueError("balance_as_of must not be in the future")


def _money(amount: Decimal, currency: str) -> Money:
    """A stored amount (scale 8) at its currency's minor units (it never had more digits)."""
    return Money(
        amount=amount.quantize(Decimal(1).scaleb(-minor_units(currency))), currency=currency
    )


def _out(row: Liability) -> LiabilityOut:
    return LiabilityOut(
        id=row.id,
        name=row.name,
        liability_type=row.liability_type,
        balance=_money(row.balance, row.currency),
        balance_as_of=row.balance_as_of,
        interest_rate_percent=None
        if row.interest_rate_percent is None
        else row.interest_rate_percent.quantize(Decimal("0.01")),
        asset_id=row.asset_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _conflict(error: IntegrityError) -> Exception:
    if _NAME_TAKEN in str(error.orig):
        return ConflictError("You already have a liability with this name.")
    return error
