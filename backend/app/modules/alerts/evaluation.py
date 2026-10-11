"""Alert evaluation (P08-T07.3).

Run by a worker job after prices are ingested. For every **active** alert of a user who has alerts
turned on (and that kind turned on):

- **Price alerts** compare the asset's latest stored price with the threshold. A **stale** price,
  or no price, is skipped: an alert never fires on old or missing data.
- **Allocation alerts** compare the asset class's share of the portfolio (the same allocation the
  analytics API publishes) with the threshold. A share that cannot be measured is skipped.

A firing alert records one event and becomes `triggered` (one-shot; the user re-arms it). The event
is unique per (alert, trigger key), where the key is the price observation or the day, so
evaluating the same data again changes nothing. Alerts of users who turned alerts off stay active
and are not evaluated; nothing is queued for later. Delivery of a notification is P09-T07."""

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import Actor, AuditWriter
from app.core.authz import ResourceNotFoundError
from app.modules.alerts.models import Alert, AlertEvent, AlertPreference
from app.modules.analytics.allocation import Dimension
from app.modules.assets.models import Asset, AssetClass
from app.modules.market_data.freshness import kind_for_asset_class
from app.modules.market_data.ingestion import latest_price
from app.modules.portfolio.allocation_service import AllocationService

logger = logging.getLogger(__name__)


@dataclass
class EvaluationResult:
    evaluated: int = 0
    triggered: int = 0
    skipped_by_preferences: int = 0
    skipped_no_fresh_data: int = 0


async def evaluate_alerts(session: AsyncSession, now: datetime | None = None) -> EvaluationResult:
    moment = now or datetime.now(UTC)
    result = EvaluationResult()
    rows = (
        await session.execute(
            select(Alert, AssetClass.code, AlertPreference)
            .outerjoin(Asset, Asset.id == Alert.asset_id)
            .outerjoin(AssetClass, AssetClass.id == Asset.asset_class_id)
            .outerjoin(AlertPreference, AlertPreference.user_id == Alert.user_id)
            .where(Alert.status == "active")
            .order_by(Alert.created_at, Alert.id)
        )
    ).all()
    for alert, asset_class_code, prefs in rows:
        if not _wanted(alert.alert_type, prefs):
            result.skipped_by_preferences += 1
            continue
        observed = await _observe(session, alert, asset_class_code, moment)
        if observed is None:
            result.skipped_no_fresh_data += 1
            continue
        result.evaluated += 1
        value, as_of, key = observed
        if _crosses(alert, value) and await _fire(session, alert, key, value, as_of, moment):
            result.triggered += 1
    return result


def _wanted(alert_type: str, prefs: AlertPreference | None) -> bool:
    if prefs is None:
        return True
    if not prefs.alerts_enabled:
        return False
    if alert_type == "allocation_above":
        return prefs.allocation_alerts_enabled
    return prefs.price_alerts_enabled


async def _observe(
    session: AsyncSession, alert: Alert, asset_class_code: str | None, now: datetime
) -> tuple[Decimal, datetime, str] | None:
    """(value, as-of time, trigger key) to compare with the threshold, or None when there is no
    fresh, measurable value."""
    if alert.alert_type in ("price_above", "price_below"):
        kind = kind_for_asset_class(asset_class_code) if asset_class_code else None
        if kind is None or alert.asset_id is None:
            return None
        price = await latest_price(session, alert.asset_id, kind, now)
        if price is None or price.stale:
            return None
        return price.price, price.as_of, price.as_of.isoformat()
    if alert.portfolio_id is None or alert.asset_class is None:
        return None
    try:
        allocation = await AllocationService(session).portfolio(alert.user_id, alert.portfolio_id)
    except ResourceNotFoundError:
        return None  # the portfolio is gone or no longer the user's
    for part in allocation.by[Dimension.ASSET_CLASS].slices:
        if part.key == alert.asset_class and part.weight_percent is not None:
            return part.weight_percent, now, now.date().isoformat()
    return None


def _crosses(alert: Alert, value: Decimal) -> bool:
    if alert.alert_type == "price_below":
        return value <= alert.threshold
    return value >= alert.threshold  # price_above and allocation_above


async def _fire(
    session: AsyncSession,
    alert: Alert,
    key: str,
    value: Decimal,
    as_of: datetime,
    now: datetime,
) -> bool:
    alert_id: uuid.UUID = alert.id
    user_id: uuid.UUID = alert.user_id
    # Take the alert first: only one evaluator can move it from active to triggered.
    taken = await session.execute(
        update(Alert)
        .where(Alert.id == alert_id, Alert.status == "active")
        .values(status="triggered", triggered_at=now)
        .returning(Alert.id)
    )
    if taken.first() is None:
        await session.rollback()
        return False
    inserted = await session.execute(
        insert(AlertEvent)
        .values(
            alert_id=alert_id,
            user_id=user_id,
            trigger_key=key,
            observed_value=value,
            observed_as_of=as_of,
        )
        .on_conflict_do_nothing(constraint="uq_alert_events_alert_id_trigger_key")
        .returning(AlertEvent.id)
    )
    if inserted.first() is None:
        await session.rollback()
        return False
    await AuditWriter(session).record(
        "alerts.alert.triggered",
        Actor.system(),
        resource_type="alert",
        resource_id=alert_id,
        details={"alert_type": alert.alert_type},
    )
    await session.commit()
    logger.info("alert triggered: %s", alert.alert_type)
    return True
