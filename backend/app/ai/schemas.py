"""Request and response schemas for /api/v1/ai (P10-T06)."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_QUESTION_CHARS = 4000


class ChatScope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    portfolio_id: uuid.UUID | None = Field(
        default=None,
        description="Limit the chat to one of your portfolios. Checked on the server; fixed for "
        "the life of a conversation.",
    )


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(
        min_length=1, max_length=MAX_QUESTION_CHARS, description="Your question, in plain text."
    )
    conversation_id: uuid.UUID | None = Field(
        default=None, description="Continue this conversation. Omit to start a new one."
    )
    scope: ChatScope | None = None

    @field_validator("message")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("The message is empty.")
        return stripped


class ConversationOut(BaseModel):
    id: uuid.UUID
    title: str | None
    portfolio_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class MessageOut(BaseModel):
    id: uuid.UUID
    position: int
    role: Literal["user", "assistant"]
    content: str
    structured: dict[str, Any] | None = None
    model: str | None = None
    created_at: datetime


class ToolCallOut(BaseModel):
    tool_name: str
    status: Literal["ok", "error"]
    error_code: str | None = None
    message_id: uuid.UUID | None = None


class ConversationDetailOut(ConversationOut):
    messages: list[MessageOut]
    tool_calls: list[ToolCallOut]
