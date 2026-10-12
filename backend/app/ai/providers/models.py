"""The vendor-neutral shapes the orchestrator and the providers exchange."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from app.ai.tools.base import ToolSpec

Role = Literal["system", "user", "assistant", "tool"]


@dataclass(frozen=True)
class ToolCall:
    """The model asking for a tool. `arguments` is untrusted until the registry validates it."""

    id: str
    name: str
    arguments: Mapping[str, Any]


@dataclass(frozen=True)
class Message:
    role: Role
    content: str = ""
    # assistant messages that asked for tools
    tool_calls: tuple[ToolCall, ...] = ()
    # tool messages answer one call
    tool_call_id: str | None = None


@dataclass(frozen=True)
class ChatRequest:
    messages: tuple[Message, ...]
    tools: tuple[ToolSpec, ...] = ()
    max_output_tokens: int = 1024
    temperature: float | None = None  # None: the provider's default


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True)
class ChatResponse:
    content: str
    tool_calls: tuple[ToolCall, ...] = ()
    usage: Usage = field(default_factory=Usage)
    # What actually answered, recorded with every run (docs/ai-governance.md).
    provider: str = ""
    model: str = ""
    request_id: str | None = None
    finish_reason: str = "stop"


@dataclass(frozen=True)
class TextDelta:
    text: str


@dataclass(frozen=True)
class StreamDone:
    """The end of a streamed answer, with the assembled response."""

    response: ChatResponse


StreamEvent = TextDelta | StreamDone
