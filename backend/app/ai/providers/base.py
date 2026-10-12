"""The interface every LLM provider implements."""

from collections.abc import AsyncIterator
from typing import Protocol

from app.ai.providers.models import ChatRequest, ChatResponse, StreamEvent


class LlmProvider(Protocol):
    @property
    def name(self) -> str:
        """Short provider name recorded in audit events (`openai`, `anthropic`, `fake`)."""

    @property
    def model(self) -> str:
        """The configured model id (the served one is in each response)."""

    async def complete(self, request: ChatRequest) -> ChatResponse: ...

    def stream(self, request: ChatRequest) -> AsyncIterator[StreamEvent]:
        """Text deltas as they arrive, then one `StreamDone` carrying the whole response (any
        tool calls are only known at the end)."""
        ...
