"""Append-only audit events for material financial changes, security events and AI/tool activity.

An event records who did what to which resource, with what outcome, linked to the request by its
correlation ID. It is written in the caller's transaction, so the change and its audit event
commit (or roll back) together.

Append-only is enforced three times:
1. The database rejects UPDATE, DELETE and TRUNCATE on `audit_events` (triggers, migration 0003).
2. The ORM refuses to flush a change to or deletion of a loaded `AuditEvent`.
3. `AuditWriter` has no method that changes or removes an event.

`details` pass through `app.core.redaction.redact` before storage: credentials, tokens and
financial values never reach the audit table (an event names the resource; the resource's own
append-only history holds the amounts). Details are capped at `MAX_DETAILS_BYTES`.
"""

import hashlib
import json
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import CheckConstraint, Index, String, event, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, Mapper, mapped_column

from app.core.correlation import get_correlation_id
from app.core.redaction import REDACTED, redact
from app.db.base import Base

MAX_DETAILS_BYTES = 8192
ACTION_PATTERN = r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$"


class ActorType(StrEnum):
    USER = "user"
    SYSTEM = "system"
    AI = "ai"


class Outcome(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    DENIED = "denied"


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        CheckConstraint("actor_type IN ('user', 'system', 'ai')", name="actor_type"),
        CheckConstraint("outcome IN ('success', 'failure', 'denied')", name="outcome"),
        CheckConstraint(f"action ~ '{ACTION_PATTERN}'", name="action"),
        # A user (or the AI acting for one) is always identified; only system events may not be.
        CheckConstraint(
            "actor_type = 'system' OR actor_user_id IS NOT NULL", name="actor_user_required"
        ),
        Index("ix_audit_events_actor_user_id_occurred_at", "actor_user_id", "occurred_at"),
        Index("ix_audit_events_resource", "resource_type", "resource_id"),
        Index("ix_audit_events_correlation_id", "correlation_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    occurred_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    # No foreign key: the trail must outlive the rows it describes (retention: DEC-28).
    actor_type: Mapped[str] = mapped_column(String(16))
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column()
    action: Mapped[str] = mapped_column(String(100))
    resource_type: Mapped[str | None] = mapped_column(String(64))
    resource_id: Mapped[str | None] = mapped_column(String(128))
    outcome: Mapped[str] = mapped_column(String(16))
    correlation_id: Mapped[str | None] = mapped_column(String(64))
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))


class AuditImmutableError(RuntimeError):
    """Raised when code tries to change or delete an audit event."""


@event.listens_for(AuditEvent, "before_update")
def _refuse_update(_mapper: Mapper[Any], _connection: Any, _target: AuditEvent) -> None:
    raise AuditImmutableError("audit events are append-only")


@event.listens_for(AuditEvent, "before_delete")
def _refuse_delete(_mapper: Mapper[Any], _connection: Any, _target: AuditEvent) -> None:
    raise AuditImmutableError("audit events are append-only")


@dataclass(frozen=True)
class Actor:
    type: ActorType
    user_id: uuid.UUID | None = None

    @classmethod
    def user(cls, user_id: uuid.UUID) -> "Actor":
        return cls(ActorType.USER, user_id)

    @classmethod
    def ai(cls, on_behalf_of: uuid.UUID) -> "Actor":
        return cls(ActorType.AI, on_behalf_of)

    @classmethod
    def system(cls) -> "Actor":
        return cls(ActorType.SYSTEM)


def _json_safe(value: Any) -> Any:
    """JSON-compatible copy. Decimals become strings, never floats (CLAUDE.md money rule)."""
    if isinstance(value, Mapping):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, (Decimal, uuid.UUID, datetime, date)):
        return str(value)
    return REDACTED  # floats and unknown objects are not stored


def sanitise_details(details: Mapping[str, Any] | None) -> dict[str, Any]:
    """Redact, make JSON-safe and cap the size of an event's details."""
    if not details:
        return {}
    cleaned: dict[str, Any] = _json_safe(redact(dict(details)))
    if len(json.dumps(cleaned, separators=(",", ":")).encode()) > MAX_DETAILS_BYTES:
        return {"truncated": True, "keys": sorted(cleaned)[:50]}
    return cleaned


def hash_arguments(arguments: Mapping[str, Any]) -> str:
    """Stable SHA-256 of a tool call's arguments, so AI tool calls are auditable without storing
    the arguments themselves (docs/ai-governance.md)."""
    canonical = json.dumps(_json_safe(arguments), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


class AuditWriter:
    """Adds audit events to the caller's session. It can only append."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self,
        action: str,
        actor: Actor,
        *,
        resource_type: str | None = None,
        resource_id: uuid.UUID | str | None = None,
        outcome: Outcome = Outcome.SUCCESS,
        details: Mapping[str, Any] | None = None,
    ) -> AuditEvent:
        row = AuditEvent(
            actor_type=actor.type.value,
            actor_user_id=actor.user_id,
            action=action,
            resource_type=resource_type,
            resource_id=None if resource_id is None else str(resource_id),
            outcome=outcome.value,
            correlation_id=get_correlation_id(),
            details=sanitise_details(details),
        )
        self._session.add(row)
        await self._session.flush()
        return row
