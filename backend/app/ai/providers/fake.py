"""A scripted provider for development and tests (P10-T05). No network, no key.

Replies come from a queue the test fills, so every orchestrator behaviour (a tool call, a refusal,
a malformed answer, an outage) is reproducible. It records every request it receives, so tests can
inspect exactly what would have been sent to a real provider."""

from collections.abc import AsyncIterator, Callable
from typing import Any

from app.ai.providers.errors import LlmError
from app.ai.providers.models import (
    ChatRequest,
    ChatResponse,
    StreamDone,
    StreamEvent,
    TextDelta,
    ToolCall,
    Usage,
)

Reply = ChatResponse | LlmError | Callable[[ChatRequest], ChatResponse]


def text_reply(
    text: str, *, model: str = "fake-1", tokens: tuple[int, int] = (10, 5)
) -> ChatResponse:
    return ChatResponse(
        content=text,
        usage=Usage(*tokens),
        provider="fake",
        model=model,
        request_id="fake-request",
    )


def tool_reply(
    name: str, arguments: dict[str, Any] | None = None, *, call_id: str = "call-1"
) -> ChatResponse:
    return ChatResponse(
        content="",
        tool_calls=(ToolCall(call_id, name, arguments or {}),),
        usage=Usage(12, 3),
        provider="fake",
        model="fake-1",
        request_id="fake-request",
        finish_reason="tool_calls",
    )


class FakeLlmProvider:
    def __init__(self, replies: list[Reply] | None = None, *, model: str = "fake-1") -> None:
        self._replies: list[Reply] = list(replies or [])
        self._model = model
        self.requests: list[ChatRequest] = []

    def __repr__(self) -> str:
        return f"FakeLlmProvider(model={self._model!r})"

    @property
    def name(self) -> str:
        return "fake"

    @property
    def model(self) -> str:
        return self._model

    def queue(self, *replies: Reply) -> None:
        self._replies.extend(replies)

    def _next(self, request: ChatRequest) -> ChatResponse:
        self.requests.append(request)
        if not self._replies:
            raise AssertionError("the fake provider has no scripted reply left")
        reply = self._replies.pop(0)
        if isinstance(reply, LlmError):
            raise reply
        return reply(request) if callable(reply) else reply

    async def complete(self, request: ChatRequest) -> ChatResponse:
        return self._next(request)

    async def stream(self, request: ChatRequest) -> AsyncIterator[StreamEvent]:
        response = self._next(request)
        words = response.content.split(" ") if response.content else []
        for i, word in enumerate(words):
            yield TextDelta(word if i == len(words) - 1 else word + " ")
        yield StreamDone(response)
