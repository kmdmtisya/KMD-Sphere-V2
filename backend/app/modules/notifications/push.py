"""Push delivery behind an interface (ADR-0016).

A notification payload carries an event type, ids and an in-app route only: never an amount, a
price, a holding or an asset name. The app fetches the figures after the user has signed in.

The FCM/APNs sender is added when the Firebase project and the APNs key exist; until then
`NullPushSender` is used and nothing leaves the server (the in-app inbox still shows every alert).
"""

import logging
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.notifications.models import Device

logger = logging.getLogger(__name__)

ALERTS_ROUTE = "/more/alerts"


@dataclass(frozen=True)
class PushTarget:
    device_id: uuid.UUID
    platform: str
    token: str


class PushSender(Protocol):
    async def send(self, target: PushTarget, payload: Mapping[str, str]) -> None: ...


@dataclass
class NullPushSender:
    """Sends nothing. Records what would have been sent (for tests and metrics)."""

    sent: list[tuple[uuid.UUID, dict[str, str]]] = field(default_factory=list)

    async def send(self, target: PushTarget, payload: Mapping[str, str]) -> None:
        self.sent.append((target.device_id, dict(payload)))


def alert_payload(alert_id: uuid.UUID, event_id: uuid.UUID) -> dict[str, str]:
    """What a device receives when an alert fires: identifiers and a route only."""
    return {
        "type": "alert_triggered",
        "alert_id": str(alert_id),
        "event_id": str(event_id),
        "route": ALERTS_ROUTE,
    }


async def notify_user(
    session: AsyncSession,
    sender: PushSender,
    user_id: uuid.UUID,
    payload: Mapping[str, str],
) -> int:
    """Sends `payload` to every device of `user_id`. A failing device does not stop the others;
    failures are logged by type only (no token, no payload). Returns how many sends succeeded."""
    devices = (await session.execute(select(Device).where(Device.user_id == user_id))).scalars()
    delivered = 0
    for d in devices:
        try:
            await sender.send(PushTarget(d.id, d.platform, d.token), payload)
            delivered += 1
        except Exception as error:
            logger.warning("push to one device failed: %s", type(error).__name__)
    return delivered


def build_push_sender() -> PushSender:
    """The sender the worker uses. Only the no-op sender exists until FCM/APNs is configured
    (ADR-0016); this is the one place that changes when it is."""
    return NullPushSender()
