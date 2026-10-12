"""Conversation history and the tool-call ledger (P10-T07, ADR-0017, docs/ai-governance.md).

Every row carries `user_id` and every query goes through `owned_by` (ADR-0011). Message text is the
user's own conversation, kept so a chat can continue, and deleted after the retention period or on
request. A tool-call row holds the tool, the argument hash, status and timing only: never arguments
or results (the audit trail follows the audit policy, not this retention)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

ROLES = ("user", "assistant")
MAX_MESSAGE_CHARS = 20_000


class Conversation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ai_conversations"
    __table_args__ = (
        Index("ix_ai_conversations_user_id_updated_at", "user_id", "updated_at"),
        Index("ix_ai_conversations_updated_at", "updated_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str | None] = mapped_column(String(200), default=None)
    # The scope the client asked for (validated by the orchestrator); null means everything.
    portfolio_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("portfolios.id", ondelete="SET NULL"), default=None
    )


class Message(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "ai_messages"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant')", name="role"),
        CheckConstraint(f"length(content) <= {MAX_MESSAGE_CHARS}", name="content_length"),
        UniqueConstraint(
            "conversation_id", "position", name="uq_ai_messages_conversation_position"
        ),
        Index("ix_ai_messages_user_id", "user_id"),
    )

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ai_conversations.id", ondelete="CASCADE")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(9))
    content: Mapped[str] = mapped_column(Text)
    # The validated four-section answer (P10-T08) for assistant messages.
    structured: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=None)
    model: Mapped[str | None] = mapped_column(String(100), default=None)
    provider: Mapped[str | None] = mapped_column(String(20), default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=sql_text("now()"))


class ToolCall(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "ai_tool_calls"
    __table_args__ = (
        CheckConstraint("status IN ('ok', 'error')", name="status"),
        Index("ix_ai_tool_calls_user_id", "user_id"),
        Index("ix_ai_tool_calls_conversation_id", "conversation_id"),
    )

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ai_conversations.id", ondelete="CASCADE")
    )
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ai_messages.id", ondelete="SET NULL"), default=None
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    tool_name: Mapped[str] = mapped_column(String(64))
    arguments_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(5))
    error_code: Mapped[str | None] = mapped_column(String(32), default=None)
    duration_ms: Mapped[int] = mapped_column(Integer)
    correlation_id: Mapped[str | None] = mapped_column(String(64), default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=sql_text("now()"))
