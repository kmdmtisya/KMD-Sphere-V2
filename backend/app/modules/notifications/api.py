"""/api/v1/devices: the signed-in user's devices that receive alert notifications (P09-T08)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api_responses import UNAUTHORIZED, conflict, invalid, not_found
from app.db.session import get_session
from app.modules.identity.dependencies import CurrentUserDep
from app.modules.notifications.schemas import DeviceOut, DeviceRegister
from app.modules.notifications.service import DeviceService

router = APIRouter(prefix="/api/v1/devices", tags=["notifications"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.post(
    "",
    response_model=DeviceOut,
    status_code=201,
    responses={
        200: {"description": "The token was already registered (refreshed)"},
        **UNAUTHORIZED,
        **invalid("device"),
        **conflict("Too many devices"),
    },
)
async def register_device(
    body: DeviceRegister, user: CurrentUserDep, session: SessionDep, response: Response
) -> DeviceOut:
    """Registers this device push token. Sending it again refreshes it (200)."""
    device, created = await DeviceService(session).register(user.id, body)
    if not created:
        response.status_code = 200
    return device


@router.get("", response_model=list[DeviceOut], responses=UNAUTHORIZED)
async def list_devices(user: CurrentUserDep, session: SessionDep) -> list[DeviceOut]:
    """Your registered devices (only the last characters of each token)."""
    return await DeviceService(session).list(user.id)


@router.delete(
    "/{device_id}",
    status_code=204,
    responses={**UNAUTHORIZED, **not_found("device")},
)
async def remove_device(
    device_id: uuid.UUID, user: CurrentUserDep, session: SessionDep
) -> Response:
    """Stops notifications to a device (for example at sign-out)."""
    await DeviceService(session).remove(user.id, device_id)
    return Response(status_code=204)
