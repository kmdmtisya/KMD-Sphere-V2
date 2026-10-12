"""The typed server-sent events of /api/v1/ai/chat (docs/api-conventions.md, Streaming).

`tool` tells the user which tool is running or ran (name and status only, never arguments or
results); `source` names the trusted data an answer rests on, with its as-of time; `token` carries
text of the validated answer; `done` closes the turn; `error` is a fixed code and message."""

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field


class TokenEvent(BaseModel):
    type: Literal["token"] = "token"
    text: str


class ToolEvent(BaseModel):
    type: Literal["tool"] = "tool"
    name: str
    status: Literal["running", "ok", "error"]
    error_code: str | None = None


class SourceEvent(BaseModel):
    type: Literal["source"] = "source"
    tool: str
    as_of: datetime | None = None
    complete: bool = True


class DoneEvent(BaseModel):
    type: Literal["done"] = "done"
    conversation_id: uuid.UUID
    message_id: uuid.UUID
    model: str
    provider: str
    tool_calls: int
    # The validated answer in its four sections (or a refusal category), so a screen can render
    # the sections instead of the streamed text.
    structured: dict[str, Any] | None = None


class ErrorEvent(BaseModel):
    type: Literal["error"] = "error"
    code: Literal["ai_unavailable", "invalid_answer", "refused"]
    message: str


ChatEvent = Annotated[
    TokenEvent | ToolEvent | SourceEvent | DoneEvent | ErrorEvent, Field(discriminator="type")
]

EVENT_TYPES = ("token", "tool", "source", "done", "error")

ERROR_MESSAGES = {
    "ai_unavailable": "The assistant is unavailable right now. Please try again shortly.",
    "invalid_answer": "The assistant could not produce a reliable answer. Please try again.",
    "refused": "The assistant cannot answer that.",
}


def to_sse(event: TokenEvent | ToolEvent | SourceEvent | DoneEvent | ErrorEvent) -> str:
    """One server-sent event frame: `event: <type>` and one JSON `data:` line."""
    return f"event: {event.type}\ndata: {event.model_dump_json()}\n\n"
