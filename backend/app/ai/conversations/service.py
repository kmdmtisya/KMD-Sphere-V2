"""Repositories for stored conversations (P10-T07). Owner-scoped (ADR-0011): another user's
conversation does not exist for the caller. Nothing here logs message text."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.conversations.models import MAX_MESSAGE_CHARS, ROLES, Conversation, Message, ToolCall
from app.core.authz import owned_by, require_found
from app.core.errors import InvalidValueError

MAX_TITLE_CHARS = 200
KIND = "conversation"


@dataclass(frozen=True)
class RecordedToolCall:
    tool_name: str
    arguments_hash: str
    ok: bool
    error_code: str | None
    duration_ms: int
    correlation_id: str | None


class ConversationService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------ conversations
    async def create(
        self, user_id: uuid.UUID, title: str | None = None, portfolio_id: uuid.UUID | None = None
    ) -> Conversation:
        conversation = Conversation(
            user_id=user_id,
            title=title[:MAX_TITLE_CHARS] if title else None,
            portfolio_id=portfolio_id,
        )
        self._session.add(conversation)
        await self._session.flush()
        return conversation

    async def get(self, user_id: uuid.UUID, conversation_id: uuid.UUID) -> Conversation:
        found = (
            await self._session.execute(
                owned_by(Conversation, user_id).where(Conversation.id == conversation_id)
            )
        ).scalar_one_or_none()
        return require_found(found, KIND)

    async def recent(
        self, user_id: uuid.UUID, limit: int = 50, offset: int = 0
    ) -> list[Conversation]:
        rows = await self._session.execute(
            owned_by(Conversation, user_id)
            .order_by(Conversation.updated_at.desc(), Conversation.id)
            .limit(limit)
            .offset(offset)
        )
        return list(rows.scalars())

    async def delete(self, user_id: uuid.UUID, conversation_id: uuid.UUID) -> None:
        conversation = await self.get(user_id, conversation_id)
        await self._session.delete(conversation)
        await self._session.flush()

    async def delete_all(self, user_id: uuid.UUID) -> int:
        result = await self._session.execute(
            delete(Conversation).where(Conversation.user_id == user_id)
        )
        return int(getattr(result, "rowcount", 0) or 0)

    # --------------------------------------------------------------------- messages
    async def append(
        self,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        role: str,
        content: str,
        *,
        structured: dict[str, object] | None = None,
        model: str | None = None,
        provider: str | None = None,
    ) -> Message:
        if role not in ROLES:
            raise InvalidValueError("Unknown message role.")
        if not content or len(content) > MAX_MESSAGE_CHARS:
            raise InvalidValueError("The message is empty or too long.")
        conversation = await self.get(user_id, conversation_id)
        position = (
            await self._session.execute(
                select(func.coalesce(func.max(Message.position), 0)).where(
                    Message.conversation_id == conversation.id
                )
            )
        ).scalar_one() + 1
        message = Message(
            conversation_id=conversation.id,
            user_id=user_id,
            position=position,
            role=role,
            content=content,
            structured=structured,
            model=model,
            provider=provider,
        )
        self._session.add(message)
        conversation.updated_at = datetime.now(UTC)
        await self._session.flush()
        return message

    async def messages(
        self, user_id: uuid.UUID, conversation_id: uuid.UUID, limit: int | None = None
    ) -> list[Message]:
        """Oldest first; with `limit`, the most recent `limit` messages in order."""
        conversation = await self.get(user_id, conversation_id)
        query = owned_by(Message, user_id).where(Message.conversation_id == conversation.id)
        if limit is None:
            rows = await self._session.execute(query.order_by(Message.position))
            return list(rows.scalars())
        rows = await self._session.execute(query.order_by(Message.position.desc()).limit(limit))
        return list(reversed(list(rows.scalars())))

    # ------------------------------------------------------------------- tool calls
    async def record_tool_call(
        self,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        call: RecordedToolCall,
        message_id: uuid.UUID | None = None,
    ) -> ToolCall:
        conversation = await self.get(user_id, conversation_id)
        row = ToolCall(
            conversation_id=conversation.id,
            message_id=message_id,
            user_id=user_id,
            tool_name=call.tool_name,
            arguments_hash=call.arguments_hash,
            status="ok" if call.ok else "error",
            error_code=call.error_code,
            duration_ms=call.duration_ms,
            correlation_id=call.correlation_id,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def tool_calls(self, user_id: uuid.UUID, conversation_id: uuid.UUID) -> list[ToolCall]:
        conversation = await self.get(user_id, conversation_id)
        rows = await self._session.execute(
            owned_by(ToolCall, user_id)
            .where(ToolCall.conversation_id == conversation.id)
            .order_by(ToolCall.created_at, ToolCall.id)
        )
        return list(rows.scalars())

    # -------------------------------------------------------------------- retention
    async def purge_expired(self, now: datetime, retention_days: int) -> int:
        """Deletes conversations whose last message is older than the retention period (their
        messages and tool-call rows go with them). Returns how many conversations were removed."""
        cutoff = now - timedelta(days=retention_days)
        result = await self._session.execute(
            delete(Conversation).where(Conversation.updated_at < cutoff)
        )
        return int(getattr(result, "rowcount", 0) or 0)
