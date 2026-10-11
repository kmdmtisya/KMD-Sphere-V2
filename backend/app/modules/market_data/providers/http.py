"""The HTTP boundary of the adapters (P08-T03).

Adapters talk to a vendor only through `HttpClient`, so contract tests run them offline against
recorded fixtures, and so one place decides how transport failures map to provider errors.

- A timeout or connection error is `ProviderUnavailable`; 429 is `RateLimited` (with `Retry-After`
  when given); 401 and 403 are `ProviderAuthError`; 5xx is `ProviderUnavailable`.
- Error messages name the provider and the status, never the URL, headers or key.
- JSON is parsed with decimals (`parse_float=Decimal`), so a vendor's number never passes through
  a binary float (ADR-0003)."""

import json
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal
from typing import Any, Protocol

import httpx

from app.modules.market_data.providers.errors import (
    ProviderAuthError,
    ProviderDataError,
    ProviderUnavailable,
    RateLimited,
)


@dataclass(frozen=True)
class HttpResponse:
    status: int
    text: str
    headers: dict[str, str] = field(default_factory=dict)


class HttpClient(Protocol):
    async def get(
        self, url: str, params: dict[str, str] | None = None, headers: dict[str, str] | None = None
    ) -> HttpResponse: ...


class HttpxClient:
    """The real client. Short timeouts: a slow vendor must not hold a worker."""

    def __init__(
        self, timeout_seconds: float = 10.0, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._timeout = timeout_seconds
        self._transport = transport  # tests inject a mock transport

    async def get(
        self, url: str, params: dict[str, str] | None = None, headers: dict[str, str] | None = None
    ) -> HttpResponse:
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, transport=self._transport
            ) as client:
                response = await client.get(url, params=params, headers=headers)
        except httpx.HTTPError as error:
            # The exception text can include the URL; keep only its type.
            raise ProviderUnavailable(f"transport error: {type(error).__name__}") from None
        return HttpResponse(
            response.status_code,
            response.text,
            {k.lower(): v for k, v in response.headers.items()},
        )


def check_status(provider: str, response: HttpResponse) -> None:
    """Raise the right provider error for a failed status; return for a success."""
    status = response.status
    if status == 429:
        raise RateLimited(f"{provider} rate limited", _retry_after(response))
    if status in (401, 403):
        raise ProviderAuthError(f"{provider} refused the credentials (HTTP {status})")
    if status >= 500:
        raise ProviderUnavailable(f"{provider} server error (HTTP {status})")
    if status >= 400:
        raise ProviderDataError(f"{provider} rejected the request (HTTP {status})")


def _retry_after(response: HttpResponse) -> timedelta | None:
    raw = response.headers.get("retry-after")
    if raw is None:
        return None
    try:
        seconds = int(raw)
    except ValueError:
        return None  # an HTTP date: not worth parsing, the backoff applies instead
    return timedelta(seconds=max(seconds, 0))


def parse_json(provider: str, text: str) -> Any:
    """JSON with decimals for fractional numbers."""
    try:
        return json.loads(text, parse_float=Decimal)
    except ValueError:
        raise ProviderDataError(f"{provider} returned invalid JSON") from None
