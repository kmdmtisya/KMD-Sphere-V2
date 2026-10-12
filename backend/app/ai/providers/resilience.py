"""Retry and fallback around providers (P10-T05). Both are providers themselves, so the
orchestrator never knows it is talking to a chain."""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence

from app.ai.providers.base import LlmProvider
from app.ai.providers.errors import (
    LlmAuthError,
    LlmError,
    LlmInvalidOutput,
    LlmNotConfigured,
    LlmUnavailable,
)
from app.ai.providers.models import ChatRequest, ChatResponse, StreamDone, StreamEvent, TextDelta

Sleep = Callable[[float], Awaitable[None]]


class RetryingLlm:
    """Tries again after a transient failure (unavailable, rate limited, or an unusable answer).
    A refused key or a bad request is not retried: asking again changes nothing."""

    def __init__(
        self,
        inner: LlmProvider,
        attempts: int = 2,
        pause: float = 1.0,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self._inner = inner
        self._attempts = attempts
        self._pause = pause
        self._sleep = sleep

    @property
    def name(self) -> str:
        return self._inner.name

    @property
    def model(self) -> str:
        return self._inner.model

    async def complete(self, request: ChatRequest) -> ChatResponse:
        last: LlmError | None = None
        for attempt in range(self._attempts):
            try:
                return await self._inner.complete(request)
            except LlmAuthError:
                raise
            except (LlmUnavailable, LlmInvalidOutput) as error:
                last = error
                if attempt + 1 < self._attempts:
                    await self._sleep(self._pause * (attempt + 1))
        assert last is not None  # noqa: S101
        raise last

    async def stream(self, request: ChatRequest) -> AsyncIterator[StreamEvent]:
        # Retrying is only safe before the first token reached the user.
        for attempt in range(self._attempts):
            started = False
            try:
                async for event in self._inner.stream(request):
                    started = started or isinstance(event, TextDelta)
                    yield event
                return
            except LlmAuthError:
                raise
            except (LlmUnavailable, LlmInvalidOutput):
                if started or attempt + 1 >= self._attempts:
                    raise
                await self._sleep(self._pause * (attempt + 1))


class FallbackLlm:
    """Asks providers in order; moves on when one is down, refuses our key or is not configured."""

    def __init__(self, providers: Sequence[LlmProvider]) -> None:
        if not providers:
            raise ValueError("at least one provider is needed")
        self._providers = list(providers)

    @property
    def name(self) -> str:
        return self._providers[0].name

    @property
    def model(self) -> str:
        return self._providers[0].model

    async def complete(self, request: ChatRequest) -> ChatResponse:
        failures = 0
        for provider in self._providers:
            try:
                return await provider.complete(request)
            except (LlmUnavailable, LlmNotConfigured, LlmInvalidOutput):
                failures += 1
        raise LlmUnavailable(f"all {failures} providers failed")

    async def stream(self, request: ChatRequest) -> AsyncIterator[StreamEvent]:
        failures = 0
        for provider in self._providers:
            started = False
            try:
                async for event in provider.stream(request):
                    started = started or isinstance(event, (TextDelta, StreamDone))
                    yield event
                return
            except (LlmUnavailable, LlmNotConfigured, LlmInvalidOutput):
                if started:
                    raise
                failures += 1
        raise LlmUnavailable(f"all {failures} providers failed")
