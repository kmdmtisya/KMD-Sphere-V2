"""/api/v1/watchlist, /api/v1/alerts and /api/v1/alert-preferences: the signed-in user's own
watchlist, alerts and notification preferences (P08-T07). Delivery of a notification is P09-T07."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api_responses import UNAUTHORIZED, conflict, invalid, not_found
from app.db.session import get_session
from app.modules.alerts.schemas import (
    AlertCreate,
    AlertEventOut,
    AlertEventPage,
    AlertOut,
    AlertPreferences,
    AlertUpdate,
    WatchlistAdd,
    WatchlistItemOut,
)
from app.modules.alerts.service import AlertService, PreferenceService, WatchlistService
from app.modules.identity.dependencies import CurrentUserDep

watchlist_router = APIRouter(prefix="/api/v1/watchlist", tags=["watchlist"])
alerts_router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])
preferences_router = APIRouter(prefix="/api/v1/alert-preferences", tags=["alerts"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


# ------------------------------------------------------------------------------ watchlist
@watchlist_router.post(
    "",
    response_model=WatchlistItemOut,
    status_code=201,
    responses={
        200: {"description": "The asset was already on the watchlist"},
        **UNAUTHORIZED,
        **invalid("asset"),
        **conflict("The watchlist is full"),
    },
)
async def add_to_watchlist(
    body: WatchlistAdd, user: CurrentUserDep, session: SessionDep, response: Response
) -> WatchlistItemOut:
    """Adds an asset to the watchlist. Adding one that is already there returns it (200)."""
    item, created = await WatchlistService(session).add(user.id, body.asset_id)
    if not created:
        response.status_code = 200
    return item


@watchlist_router.get("", response_model=list[WatchlistItemOut], responses=UNAUTHORIZED)
async def list_watchlist(user: CurrentUserDep, session: SessionDep) -> list[WatchlistItemOut]:
    """The watchlist with each asset's latest stored price (and whether it is stale)."""
    return await WatchlistService(session).list(user.id)


@watchlist_router.delete(
    "/{asset_id}",
    status_code=204,
    responses={**UNAUTHORIZED, **not_found("watchlist item")},
)
async def remove_from_watchlist(
    asset_id: uuid.UUID, user: CurrentUserDep, session: SessionDep
) -> Response:
    await WatchlistService(session).remove(user.id, asset_id)
    return Response(status_code=204)


# --------------------------------------------------------------------------------- alerts
@alerts_router.post(
    "",
    response_model=AlertOut,
    status_code=201,
    responses={
        **UNAUTHORIZED,
        **invalid("alert (shape, asset, currency, portfolio or class)"),
        **conflict("The alert limit is reached"),
    },
)
async def create_alert(body: AlertCreate, user: CurrentUserDep, session: SessionDep) -> AlertOut:
    """A price alert (above or below a price in the asset's currency) or an allocation alert (an
    asset class above a share of one of your portfolios). It fires once; re-arm it by setting it
    active."""
    return await AlertService(session).create(user.id, body)


@alerts_router.get("", response_model=list[AlertOut], responses=UNAUTHORIZED)
async def list_alerts(user: CurrentUserDep, session: SessionDep) -> list[AlertOut]:
    return await AlertService(session).list(user.id)


@alerts_router.get("/events", response_model=AlertEventPage, responses=UNAUTHORIZED)
async def list_alert_events(
    user: CurrentUserDep,
    session: SessionDep,
    unseen: Annotated[bool, Query(description="Only events not yet marked seen")] = False,
) -> AlertEventPage:
    """Alerts that fired, newest first (at most 100)."""
    return AlertEventPage(items=await AlertService(session).events(user.id, unseen))


@alerts_router.post(
    "/events/{event_id}/seen",
    response_model=AlertEventOut,
    responses={**UNAUTHORIZED, **not_found("alert event")},
)
async def mark_alert_event_seen(
    event_id: uuid.UUID, user: CurrentUserDep, session: SessionDep
) -> AlertEventOut:
    return await AlertService(session).mark_seen(user.id, event_id)


@alerts_router.get(
    "/{alert_id}",
    response_model=AlertOut,
    responses={**UNAUTHORIZED, **not_found("alert")},
)
async def get_alert(alert_id: uuid.UUID, user: CurrentUserDep, session: SessionDep) -> AlertOut:
    return await AlertService(session).get(user.id, alert_id)


@alerts_router.patch(
    "/{alert_id}",
    response_model=AlertOut,
    responses={**UNAUTHORIZED, **not_found("alert"), **invalid("alert change")},
)
async def update_alert(
    alert_id: uuid.UUID, body: AlertUpdate, user: CurrentUserDep, session: SessionDep
) -> AlertOut:
    """Pause, re-arm, or change the threshold or note."""
    return await AlertService(session).update(user.id, alert_id, body)


@alerts_router.delete(
    "/{alert_id}",
    status_code=204,
    responses={**UNAUTHORIZED, **not_found("alert")},
)
async def delete_alert(alert_id: uuid.UUID, user: CurrentUserDep, session: SessionDep) -> Response:
    await AlertService(session).delete(user.id, alert_id)
    return Response(status_code=204)


# ------------------------------------------------------------------------------ preferences
@preferences_router.get("", response_model=AlertPreferences, responses=UNAUTHORIZED)
async def get_alert_preferences(user: CurrentUserDep, session: SessionDep) -> AlertPreferences:
    """What you want to hear about. With nothing saved, everything is on."""
    return await PreferenceService(session).get(user.id)


@preferences_router.put("", response_model=AlertPreferences, responses=UNAUTHORIZED)
async def put_alert_preferences(
    body: AlertPreferences, user: CurrentUserDep, session: SessionDep
) -> AlertPreferences:
    """Turning alerts (or one kind) off stops them being evaluated; they stay as they are."""
    return await PreferenceService(session).put(user.id, body)
