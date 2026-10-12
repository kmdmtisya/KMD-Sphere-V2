"""ExchangeRate-API (DEC-25): the commercial FX source for pairs the ECB does not publish (AED,
KES) and the fallback when the ECB is down.

Built from the public v6 documentation (standard, pair and historical requests) with synthetic
fixtures in its documented response shapes; no key has been issued and no live call has been made
(P11-T03, fixture-only approval). Production use waits for written confirmation of the licence for
in-app display and caching (P11-T12).

- `GET /v6/{key}/latest/{base}`: every rate against `base` in one request (batch refresh).
- `GET /v6/{key}/pair/{base}/{quote}`: one rate.
- `GET /v6/{key}/history/{base}/{year}/{month}/{day}`: one day (paid plans only).

The documentation calls the rates "indicative mid-rates", one per update, not for settlement; they
are stored as `indicative`. The key is part of the URL path, so URLs are never logged or put in an
error message (the HTTP boundary keeps only the status)."""

import json
from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import SecretStr

from app.modules.market_data.providers.errors import (
    ProviderAuthError,
    ProviderDataError,
    RateLimited,
    UnsupportedKind,
)
from app.modules.market_data.providers.http import HttpClient, HttpxClient, check_status
from app.modules.market_data.providers.models import (
    AssetKind,
    FxBatch,
    FxQuote,
    PricePoint,
    PriceQuote,
    Provenance,
)
from app.modules.market_data.providers.throttle import RateLimiter

BASE_URL = "https://v6.exchangerate-api.com/v6"
NAME = "exchangerate_api"
# Each historical day is one request; a longer range would spend the monthly quota.
MAX_HISTORY_DAYS = 31


def _decimal(value: Any, what: str) -> Decimal:
    if isinstance(value, bool):
        raise ProviderDataError(f"{NAME} returned an invalid {what}")
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ProviderDataError(f"{NAME} returned an invalid {what}") from None
    if not result.is_finite() or result <= 0:
        raise ProviderDataError(f"{NAME} returned a non-positive {what}")
    return result


def _timestamp(data: dict[str, Any]) -> datetime:
    stamp = data.get("time_last_update_unix")
    if not isinstance(stamp, (int, Decimal)) or isinstance(stamp, bool):
        raise ProviderDataError(f"{NAME} returned no update time")
    return datetime.fromtimestamp(int(stamp), tz=UTC)


class ExchangeRateApiProvider:
    name = NAME
    supported_kinds: frozenset[AssetKind] = frozenset()

    def __init__(
        self,
        api_key: SecretStr,
        client: HttpClient | None = None,
        limiter: RateLimiter | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not api_key.get_secret_value():
            raise ValueError("ExchangeRate-API needs an API key")
        self._key = api_key
        self._client = client or HttpxClient()
        self._limiter = limiter or RateLimiter(30, timedelta(minutes=1))
        self._now: Callable[[], datetime] = clock or (lambda: datetime.now(UTC))

    async def _get(self, *path: str) -> dict[str, Any]:
        await self._limiter.acquire()
        url = "/".join([BASE_URL, self._key.get_secret_value(), *path])
        response = await self._client.get(url)
        check_status(self.name, response)
        try:
            data = json.loads(response.text, parse_float=Decimal)
        except ValueError:
            raise ProviderDataError(f"{NAME} returned invalid JSON") from None
        if not isinstance(data, dict):
            raise ProviderDataError(f"{NAME} returned an unexpected document")
        if data.get("result") == "error":
            self._raise_for(data.get("error-type"))
        if data.get("result") != "success":
            raise ProviderDataError(f"{NAME} returned no result")
        return data

    def _raise_for(self, error_type: object) -> None:
        if error_type == "unsupported-code":
            raise UnsupportedKind(f"{NAME} does not publish this currency")
        if error_type in ("invalid-key", "inactive-account"):
            raise ProviderAuthError(f"{NAME} refused the key ({error_type})")
        if error_type == "quota-reached":
            raise RateLimited(f"{NAME} monthly quota reached", None)
        raise ProviderDataError(f"{NAME} rejected the request ({error_type or 'unknown'})")

    def _quote(self, base: str, quote: str, rate: Any, as_of: datetime) -> FxQuote:
        retrieved = max(self._now(), as_of)
        return FxQuote(base, quote, _decimal(rate, "rate"), Provenance(self.name, as_of, retrieved))

    def _check_base(self, data: dict[str, Any], base: str) -> None:
        if data.get("base_code") != base:
            raise ProviderDataError(f"{NAME} answered for another base currency")

    async def get_fx_rate(self, base: str, quote: str) -> FxQuote:
        data = await self._get("pair", base, quote)
        self._check_base(data, base)
        if data.get("target_code") != quote:
            raise ProviderDataError(f"{NAME} answered for another quote currency")
        return self._quote(base, quote, data.get("conversion_rate"), _timestamp(data))

    async def get_fx_rates(self, base: str, quotes: list[str]) -> FxBatch:
        """All `quotes` against `base` from one `latest` request."""
        data = await self._get("latest", base)
        self._check_base(data, base)
        table = data.get("conversion_rates")
        if not isinstance(table, dict):
            raise ProviderDataError(f"{NAME} returned no rates")
        as_of = _timestamp(data)
        found: list[FxQuote] = []
        unsupported: list[str] = []
        for quote in quotes:
            if quote == base:
                continue
            if quote not in table:
                unsupported.append(quote)
                continue
            found.append(self._quote(base, quote, table[quote], as_of))
        return FxBatch(found, unsupported)

    async def get_fx_history(self, base: str, quote: str, start: date, end: date) -> list[FxQuote]:
        if end < start:
            return []
        if (end - start).days + 1 > MAX_HISTORY_DAYS:
            raise ProviderDataError(f"{NAME} history is fetched at most {MAX_HISTORY_DAYS} days")
        points: list[FxQuote] = []
        day = start
        while day <= end:
            data = await self._get("history", base, str(day.year), str(day.month), str(day.day))
            self._check_base(data, base)
            if (data.get("year"), data.get("month"), data.get("day")) != (
                day.year,
                day.month,
                day.day,
            ):
                raise ProviderDataError(f"{NAME} answered for another day")
            table = data.get("conversion_rates")
            if not isinstance(table, dict):
                raise ProviderDataError(f"{NAME} returned no rates")
            if quote in table:
                # One indicative rate per calendar day; stamped at the end of that day (UTC).
                as_of = min(datetime.combine(day, time(23, 59, 59), tzinfo=UTC), self._now())
                points.append(self._quote(base, quote, table[quote], as_of))
            day += timedelta(days=1)
        if not points:
            raise UnsupportedKind(f"{NAME} has no {base}/{quote} rates for these days")
        return points

    async def get_quote(self, symbol: str, kind: AssetKind) -> PriceQuote:
        raise UnsupportedKind(f"{NAME} serves FX only")

    async def get_history(
        self, symbol: str, kind: AssetKind, start: date, end: date
    ) -> list[PricePoint]:
        raise UnsupportedKind(f"{NAME} serves FX only")
