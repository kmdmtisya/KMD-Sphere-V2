"""Watchlist, alert and preference use cases (P08-T07).

Rules:
- Only the owner sees or changes a watchlist item, alert, event or preference; anyone else gets
  "not found" (ADR-0011). A portfolio or asset that is missing or not the user's is refused the
  same way (422), so ids cannot be used to probe other users' data.
- A price alert is in the watched asset's own currency. An allocation alert watches an asset
  class's share of one of the user's portfolios.
- Limits: 100 watchlist items and 50 alerts per user.
- Create, update and delete write audit events (the type, never the thresholds)."""

import builtins
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import Actor, AuditWriter
from app.core.authz import owned_by, require_found
from app.core.errors import ConflictError, InvalidValueError
from app.core.money import Money, minor_units, round_half_up
from app.modules.alerts.models import Alert, AlertEvent, AlertPreference, WatchlistItem
from app.modules.alerts.schemas import (
    AlertCreate,
    AlertEventOut,
    AlertOut,
    AlertPreferences,
    AlertUpdate,
    LatestPriceOut,
    WatchlistItemOut,
)
from app.modules.assets.models import AssetClass
from app.modules.assets.schemas import AssetSummary
from app.modules.assets.service import AssetService
from app.modules.market_data.freshness import kind_for_asset_class
from app.modules.market_data.ingestion import latest_price
from app.modules.portfolio.repository import PortfolioRepository

MAX_WATCHLIST = 100
MAX_ALERTS = 50
MAX_EVENTS = 100


def _price(amount: Decimal, currency: str) -> Money:
    return Money(amount=round_half_up(amount, minor_units(currency)), currency=currency)


class WatchlistService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._assets = AssetService(session)
        self._audit = AuditWriter(session)

    async def add(self, user_id: uuid.UUID, asset_id: uuid.UUID) -> tuple[WatchlistItemOut, bool]:
        """Adds an asset; adding one already on the list returns it (False = nothing new)."""
        if not await self._assets.is_visible(user_id, asset_id):
            raise InvalidValueError("asset_id: no such asset")
        existing = await self._get(user_id, asset_id)
        if existing is not None:
            return await self._out(user_id, existing), False
        count = (
            await self._session.execute(
                select(func.count())
                .select_from(WatchlistItem)
                .where(WatchlistItem.user_id == user_id)
            )
        ).scalar_one()
        if count >= MAX_WATCHLIST:
            raise ConflictError(f"A watchlist can hold at most {MAX_WATCHLIST} assets.")
        row = WatchlistItem(user_id=user_id, asset_id=asset_id)
        self._session.add(row)
        try:
            await self._session.flush()
        except IntegrityError:
            # A concurrent add of the same asset: the list already has it.
            await self._session.rollback()
            found = require_found(await self._get(user_id, asset_id), "watchlist item")
            return await self._out(user_id, found), False
        await self._audit.record(
            "alerts.watchlist.added",
            Actor.user(user_id),
            resource_type="watchlist_item",
            resource_id=row.id,
            details={},
        )
        await self._session.commit()
        return await self._out(user_id, row), True

    async def list(self, user_id: uuid.UUID) -> list[WatchlistItemOut]:
        rows = (
            await self._session.execute(
                owned_by(WatchlistItem, user_id).order_by(
                    WatchlistItem.created_at, WatchlistItem.id
                )
            )
        ).scalars()
        return [await self._out(user_id, r) for r in rows]

    async def remove(self, user_id: uuid.UUID, asset_id: uuid.UUID) -> None:
        row = require_found(await self._get(user_id, asset_id), "watchlist item")
        await self._session.execute(
            delete(WatchlistItem).where(
                WatchlistItem.id == row.id, WatchlistItem.user_id == user_id
            )
        )
        await self._audit.record(
            "alerts.watchlist.removed",
            Actor.user(user_id),
            resource_type="watchlist_item",
            resource_id=row.id,
            details={},
        )
        await self._session.commit()

    async def _get(self, user_id: uuid.UUID, asset_id: uuid.UUID) -> WatchlistItem | None:
        return (
            await self._session.execute(
                owned_by(WatchlistItem, user_id).where(WatchlistItem.asset_id == asset_id)
            )
        ).scalar_one_or_none()

    async def _out(self, user_id: uuid.UUID, row: WatchlistItem) -> WatchlistItemOut:
        summaries = await self._assets.summaries(user_id, [row.asset_id])
        asset = summaries[row.asset_id]
        kind = kind_for_asset_class(asset.asset_class)
        price = await latest_price(self._session, row.asset_id, kind) if kind is not None else None
        return WatchlistItemOut(
            asset=asset,
            added_at=row.created_at,
            latest_price=None
            if price is None
            else LatestPriceOut(
                price=price.price,
                currency=price.currency,
                as_of=price.as_of,
                provider=price.provider,
                stale=price.stale,
            ),
        )


class AlertService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._assets = AssetService(session)
        self._portfolios = PortfolioRepository(session)
        self._audit = AuditWriter(session)

    async def create(self, user_id: uuid.UUID, body: AlertCreate) -> AlertOut:
        count = (
            await self._session.execute(
                select(func.count()).select_from(Alert).where(Alert.user_id == user_id)
            )
        ).scalar_one()
        if count >= MAX_ALERTS:
            raise ConflictError(f"A user can have at most {MAX_ALERTS} alerts.")
        values: dict[str, object]
        if body.alert_type in ("price_above", "price_below"):
            assert body.asset_id is not None and body.threshold_price is not None  # noqa: S101
            summaries = await self._assets.summaries(user_id, [body.asset_id])
            asset = summaries.get(body.asset_id)
            if asset is None or not await self._assets.is_visible(user_id, body.asset_id):
                raise InvalidValueError("asset_id: no such asset")
            if body.threshold_price.currency != asset.currency:
                raise InvalidValueError(
                    f"threshold_price: must be in the asset's currency ({asset.currency})"
                )
            values = {"asset_id": body.asset_id, "threshold": body.threshold_price.amount}
        else:
            assert body.portfolio_id is not None  # noqa: S101
            assert body.asset_class is not None and body.threshold_percent is not None  # noqa: S101
            if await self._portfolios.get(user_id, body.portfolio_id) is None:
                raise InvalidValueError("portfolio_id: no such portfolio")
            if not await self._class_exists(body.asset_class):
                raise InvalidValueError("asset_class: unknown asset class")
            values = {
                "portfolio_id": body.portfolio_id,
                "asset_class": body.asset_class,
                "threshold": body.threshold_percent,
            }
        row = Alert(user_id=user_id, alert_type=body.alert_type, note=body.note, **values)
        self._session.add(row)
        await self._session.flush()
        await self._audit.record(
            "alerts.alert.created",
            Actor.user(user_id),
            resource_type="alert",
            resource_id=row.id,
            details={"alert_type": row.alert_type},
        )
        await self._session.commit()
        return await self._out(user_id, row)

    async def list(self, user_id: uuid.UUID) -> list[AlertOut]:
        rows = (
            await self._session.execute(
                owned_by(Alert, user_id).order_by(Alert.created_at, Alert.id)
            )
        ).scalars()
        return [await self._out(user_id, r) for r in rows]

    async def get(self, user_id: uuid.UUID, alert_id: uuid.UUID) -> AlertOut:
        return await self._out(user_id, await self._owned(user_id, alert_id))

    async def update(self, user_id: uuid.UUID, alert_id: uuid.UUID, body: AlertUpdate) -> AlertOut:
        row = await self._owned(user_id, alert_id)
        values: dict[str, object] = {}
        if body.threshold_price is not None:
            if row.alert_type == "allocation_above":
                raise InvalidValueError("threshold_price: not for an allocation alert")
            summaries = (
                await self._assets.summaries(user_id, [row.asset_id]) if row.asset_id else {}
            )
            asset = summaries.get(row.asset_id) if row.asset_id else None
            if body.threshold_price.amount <= 0:
                raise InvalidValueError("threshold_price: must be above zero")
            if asset is not None and body.threshold_price.currency != asset.currency:
                raise InvalidValueError(
                    f"threshold_price: must be in the asset's currency ({asset.currency})"
                )
            values["threshold"] = body.threshold_price.amount
        if body.threshold_percent is not None:
            if row.alert_type != "allocation_above":
                raise InvalidValueError("threshold_percent: only for an allocation alert")
            if not Decimal(0) < body.threshold_percent <= Decimal(100):
                raise InvalidValueError("threshold_percent: must be above 0 and at most 100")
            values["threshold"] = body.threshold_percent
        if body.note is not None:
            values["note"] = body.note
        if body.status is not None:
            values["status"] = body.status
            if body.status == "active":
                values["triggered_at"] = None  # re-armed
        if values:
            await self._session.execute(
                update(Alert)
                .where(Alert.id == alert_id, Alert.user_id == user_id)
                .values(**values, updated_at=func.now())
            )
            await self._audit.record(
                "alerts.alert.updated",
                Actor.user(user_id),
                resource_type="alert",
                resource_id=alert_id,
                details={"fields": sorted(values)},
            )
            await self._session.commit()
            await self._session.refresh(row)
        return await self._out(user_id, row)

    async def delete(self, user_id: uuid.UUID, alert_id: uuid.UUID) -> None:
        await self._owned(user_id, alert_id)
        await self._session.execute(
            delete(Alert).where(Alert.id == alert_id, Alert.user_id == user_id)
        )
        await self._audit.record(
            "alerts.alert.deleted",
            Actor.user(user_id),
            resource_type="alert",
            resource_id=alert_id,
            details={},
        )
        await self._session.commit()

    # ------------------------------------------------------------------------------ events
    async def events(self, user_id: uuid.UUID, unseen_only: bool) -> builtins.list[AlertEventOut]:
        stmt = (
            select(AlertEvent, Alert.alert_type)
            .join(Alert, Alert.id == AlertEvent.alert_id)
            .where(AlertEvent.user_id == user_id)
            .order_by(AlertEvent.triggered_at.desc(), AlertEvent.id)
            .limit(MAX_EVENTS)
        )
        if unseen_only:
            stmt = stmt.where(AlertEvent.seen_at.is_(None))
        rows = (await self._session.execute(stmt)).all()
        return [_event_out(e, t) for e, t in rows]

    async def mark_seen(self, user_id: uuid.UUID, event_id: uuid.UUID) -> AlertEventOut:
        found = (
            await self._session.execute(
                select(AlertEvent, Alert.alert_type)
                .join(Alert, Alert.id == AlertEvent.alert_id)
                .where(AlertEvent.id == event_id, AlertEvent.user_id == user_id)
            )
        ).first()
        event, alert_type = require_found(found, "alert event")
        if event.seen_at is None:
            event.seen_at = datetime.now(UTC)
            await self._session.commit()
        return _event_out(event, alert_type)

    # ---------------------------------------------------------------------------- helpers
    async def _owned(self, user_id: uuid.UUID, alert_id: uuid.UUID) -> Alert:
        return require_found(
            (
                await self._session.execute(owned_by(Alert, user_id).where(Alert.id == alert_id))
            ).scalar_one_or_none(),
            "alert",
        )

    async def _class_exists(self, code: str) -> bool:
        if code == "cash":
            return True  # the allocation reports cash as its own slice
        found = await self._session.execute(select(AssetClass.id).where(AssetClass.code == code))
        return found.first() is not None

    async def _out(self, user_id: uuid.UUID, row: Alert) -> AlertOut:
        asset: AssetSummary | None = None
        price: Money | None = None
        percent: Decimal | None = None
        if row.asset_id is not None:
            asset = (await self._assets.summaries(user_id, [row.asset_id]))[row.asset_id]
            price = _price(row.threshold, asset.currency)
        else:
            percent = row.threshold
        return AlertOut(
            id=row.id,
            alert_type=row.alert_type,
            status=row.status,
            asset=asset,
            threshold_price=price,
            portfolio_id=row.portfolio_id,
            asset_class=row.asset_class,
            threshold_percent=percent,
            note=row.note,
            created_at=row.created_at,
            triggered_at=row.triggered_at,
        )


def _event_out(e: AlertEvent, alert_type: str) -> AlertEventOut:
    return AlertEventOut(
        id=e.id,
        alert_id=e.alert_id,
        alert_type=alert_type,
        observed_value=e.observed_value,
        observed_as_of=e.observed_as_of,
        triggered_at=e.triggered_at,
        seen_at=e.seen_at,
    )


class PreferenceService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._audit = AuditWriter(session)

    async def get(self, user_id: uuid.UUID) -> AlertPreferences:
        row = (
            await self._session.execute(
                select(AlertPreference).where(AlertPreference.user_id == user_id)
            )
        ).scalar_one_or_none()
        if row is None:
            return AlertPreferences(
                alerts_enabled=True, price_alerts_enabled=True, allocation_alerts_enabled=True
            )
        return AlertPreferences(
            alerts_enabled=row.alerts_enabled,
            price_alerts_enabled=row.price_alerts_enabled,
            allocation_alerts_enabled=row.allocation_alerts_enabled,
        )

    async def put(self, user_id: uuid.UUID, body: AlertPreferences) -> AlertPreferences:
        from sqlalchemy.dialects.postgresql import insert

        values = body.model_dump()
        stmt = insert(AlertPreference).values(user_id=user_id, **values)
        await self._session.execute(
            stmt.on_conflict_do_update(
                index_elements=[AlertPreference.user_id],
                set_={**values, "updated_at": func.now()},
            )
        )
        await self._audit.record(
            "alerts.preferences.updated",
            Actor.user(user_id),
            resource_type="alert_preferences",
            resource_id=user_id,
            details={},
        )
        await self._session.commit()
        return body
