"""The signed-in user's devices (P09-T08). Owner-scoped (ADR-0011); audited."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import Actor, AuditWriter
from app.core.authz import owned_by, require_found
from app.core.errors import ConflictError
from app.modules.notifications.models import Device
from app.modules.notifications.schemas import DeviceOut, DeviceRegister

MAX_DEVICES = 10


def _out(d: Device) -> DeviceOut:
    return DeviceOut(
        id=d.id,
        platform=d.platform,
        token_hint=d.token[-6:],
        created_at=d.created_at,
        last_seen_at=d.last_seen_at,
    )


class DeviceService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._audit = AuditWriter(session)

    async def _mine(self, user_id: uuid.UUID, token: str) -> Device | None:
        return (
            await self._session.execute(owned_by(Device, user_id).where(Device.token == token))
        ).scalar_one_or_none()

    async def register(self, user_id: uuid.UUID, body: DeviceRegister) -> tuple[DeviceOut, bool]:
        """Registers a token; registering it again refreshes it (False = not new)."""
        existing = await self._mine(user_id, body.token)
        if existing is not None:
            existing.last_seen_at = datetime.now(UTC)
            existing.platform = body.platform
            await self._session.commit()
            return _out(existing), False
        count = (
            await self._session.execute(
                select(func.count()).select_from(Device).where(Device.user_id == user_id)
            )
        ).scalar_one()
        if count >= MAX_DEVICES:
            raise ConflictError(f"At most {MAX_DEVICES} devices can receive notifications.")
        inserted = (
            await self._session.execute(
                insert(Device)
                .values(user_id=user_id, platform=body.platform, token=body.token)
                .on_conflict_do_nothing(constraint="uq_devices_user_id_token")
                .returning(Device.id)
            )
        ).scalar_one_or_none()
        if inserted is None:  # registered concurrently: the same token is there now
            await self._session.rollback()
            found = require_found(await self._mine(user_id, body.token), "device")
            return _out(found), False
        await self._audit.record(
            "notifications.device.registered",
            Actor.user(user_id),
            resource_type="device",
            resource_id=inserted,
            details={"platform": body.platform},
        )
        await self._session.commit()
        row = require_found(await self._mine(user_id, body.token), "device")
        return _out(row), True

    async def list(self, user_id: uuid.UUID) -> list[DeviceOut]:
        rows = (
            await self._session.execute(owned_by(Device, user_id).order_by(Device.created_at))
        ).scalars()
        return [_out(d) for d in rows]

    async def remove(self, user_id: uuid.UUID, device_id: uuid.UUID) -> None:
        require_found(
            (
                await self._session.execute(owned_by(Device, user_id).where(Device.id == device_id))
            ).scalar_one_or_none(),
            "device",
        )
        await self._session.execute(
            delete(Device).where(Device.id == device_id, Device.user_id == user_id)
        )
        await self._audit.record(
            "notifications.device.removed",
            Actor.user(user_id),
            resource_type="device",
            resource_id=device_id,
            details={},
        )
        await self._session.commit()
