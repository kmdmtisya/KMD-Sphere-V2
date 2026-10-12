"""Request and response schemas for /api/v1/devices (P09-T08)."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Platform = Literal["android", "ios"]


class DeviceRegister(BaseModel):
    """A device push token from FCM (Android) or APNs through FCM (iOS)."""

    model_config = ConfigDict(extra="forbid")

    platform: Platform
    token: str = Field(min_length=8, max_length=4096, pattern=r"^[A-Za-z0-9_:\-.]+$")


class DeviceOut(BaseModel):
    id: uuid.UUID
    platform: Platform
    token_hint: str = Field(description="The last 6 characters of the token, to tell devices apart")
    created_at: datetime
    last_seen_at: datetime
