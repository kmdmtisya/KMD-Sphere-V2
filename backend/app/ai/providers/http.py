"""The HTTP boundary of the LLM adapters (P10-T05).

Adapters talk to a vendor only through `LlmHttp`, so contract tests run them offline against
recorded payloads, and one place decides how transport and HTTP failures map to provider errors.
Error messages name the provider and the status, never the URL, headers, key, prompt or body.
JSON is parsed with decimals for fractional numbers (ADR-0003)."""

import json
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Protocol

import httpx

from app.ai.providers.errors import (
    LlmAuthError,
    LlmBadRequest,
    LlmInvalidOutput,
    LlmRateLimited,
    LlmUnavailable,
)


@dataclass(frozen=True)
class HttpResult:
    status: int
    text: str
    headers: Mapping[str, str] = field(default_factory=dict)


class LlmHttp(Protocol):
    async def post(
        self, url: str, headers: Mapping[str, str], body: Mapping[str, Any]
    ) -> HttpResult: ...

    def post_stream(
        self, url: str, headers: Mapping[str, str], body: Mapping[str, Any]
    ) -> AsyncIterator[str]:
        """Server-sent-event lines of a streamed answer. A failed status raises before any line."""
        ...


class HttpxLlm:
    """The real client. A generous read timeout (models are slow); no retries here."""

    def __init__(
        self, timeout_seconds: float = 60.0, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._timeout = timeout_seconds
        self._transport = transport  # tests inject a mock transport

    async def post(
        self, url: str, headers: Mapping[str, str], body: Mapping[str, Any]
    ) -> HttpResult:
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, transport=self._transport
            ) as client:
                response = await client.post(url, headers=dict(headers), json=body)
        except httpx.HTTPError as error:
            # The exception text can include the URL; keep only its type.
            raise LlmUnavailable(f"transport error: {type(error).__name__}") from None
        return HttpResult(
            response.status_code,
            response.text,
            {k.lower(): v for k, v in response.headers.items()},
        )

    async def post_stream(
        self, url: str, headers: Mapping[str, str], body: Mapping[str, Any]
    ) -> AsyncIterator[str]:
        try:
            async with (
                httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client,
                client.stream("POST", url, headers=dict(headers), json=body) as response,
            ):
                if response.status_code >= 400:
                    await response.aread()
                    raise_for_status("llm", HttpResult(response.status_code, ""))
                async for line in response.aiter_lines():
                    yield line
        except httpx.HTTPError as error:
            raise LlmUnavailable(f"transport error: {type(error).__name__}") from None


def raise_for_status(provider: str, result: HttpResult) -> None:
    """Raise the right provider error for a failed status; return for a success."""
    status = result.status
    if status == 429:
        raise LlmRateLimited(f"{provider} rate limited")
    if status in (401, 403):
        raise LlmAuthError(f"{provider} refused the credentials (HTTP {status})")
    if status >= 500:
        raise LlmUnavailable(f"{provider} server error (HTTP {status})")
    if status >= 400:
        raise LlmBadRequest(f"{provider} rejected the request (HTTP {status})")


def parse_json(provider: str, text: str) -> Any:
    try:
        return json.loads(text, parse_float=Decimal)
    except ValueError:
        raise LlmInvalidOutput(f"{provider} returned invalid JSON") from None


def parse_tool_arguments(provider: str, raw: str) -> dict[str, Any]:
    """A tool call's arguments arrive as JSON text from the model: untrusted, and it may be
    malformed. Anything but a JSON object is refused (the registry validates the fields)."""
    if not raw.strip():
        return {}
    try:
        value = json.loads(raw)
    except ValueError:
        raise LlmInvalidOutput(f"{provider} sent tool arguments that are not JSON") from None
    if not isinstance(value, dict):
        raise LlmInvalidOutput(f"{provider} sent tool arguments that are not an object")
    return value
