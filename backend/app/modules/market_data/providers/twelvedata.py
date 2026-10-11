"""Twelve Data equities, ETFs and FX (ADR-0014). Needs a key.

**Licence condition:** Twelve Data's Individual plans are for personal, internal, non-commercial
use. This adapter must not be used for production display until a commercial or display licence
is in place (ADR-0014 section 4). It is built so the code is ready either way.

The key is sent in the `Authorization` header and held as a `SecretStr`. Twelve Data answers many
errors with HTTP 200 and a body `{"status": "error", "code": 404, "message": ...}`; those are
mapped to provider errors here. Numbers arrive as strings (and the FX rate as a JSON number,
parsed as a decimal).

Response shapes (public API reference; the contract fixtures are synthetic in these shapes and are
to be re-recorded once a key exists):
- `GET /quote?symbol=X` -> `{"symbol": "X", "currency": "USD", "datetime": "2026-10-09",
  "timestamp": 1760025600, "close": "187.40", ...}`
- `GET /time_series?symbol=X&interval=1day&start_date=..&end_date=..&order=ASC`
  -> `{"meta": {"symbol": "X", "currency": "USD"}, "values": [{"datetime": "2026-10-08",
  "close": "187.10"}, ...], "status": "ok"}`
- `GET /exchange_rate?symbol=USD/AED`
  -> `{"symbol": "USD/AED", "rate": 3.6725, "timestamp": ...}`"""

from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import SecretStr

from app.modules.market_data.providers.errors import (
    ProviderAuthError,
    ProviderDataError,
    ProviderUnavailable,
    RateLimited,
    SymbolNotFound,
    UnsupportedKind,
)
from app.modules.market_data.providers.http import (
    HttpClient,
    HttpxClient,
    check_status,
    parse_json,
)
from app.modules.market_data.providers.models import (
    AssetKind,
    FxQuote,
    PricePoint,
    PriceQuote,
    Provenance,
)
from app.modules.market_data.providers.throttle import RateLimiter

BASE_URL = "https://api.twelvedata.com"


def _decimal(value: Any, what: str) -> Decimal:
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ProviderDataError(f"twelvedata returned an invalid {what}") from None
    if not result.is_finite() or result <= 0:
        raise ProviderDataError(f"twelvedata returned a non-positive {what}")
    return result


def _day_end(day: date) -> datetime:
    """A daily close is final at the end of its UTC day."""
    return (
        datetime(day.year, day.month, day.day, tzinfo=UTC)
        + timedelta(days=1)
        - timedelta(seconds=1)
    )


class TwelveDataProvider:
    name = "twelvedata"
    supported_kinds = frozenset({AssetKind.EQUITY, AssetKind.ETF, AssetKind.INDEX})

    def __init__(
        self,
        api_key: SecretStr,
        client: HttpClient | None = None,
        limiter: RateLimiter | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._api_key = api_key
        self._client = client or HttpxClient()
        # The free Basic plan allows 8 calls a minute.
        self._limiter = limiter or RateLimiter(8, timedelta(minutes=1))
        self._now: Callable[[], datetime] = clock or (lambda: datetime.now(UTC))

    def __repr__(self) -> str:
        return "TwelveDataProvider()"

    async def _get(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        key = self._api_key.get_secret_value()
        if not key:
            raise ProviderAuthError("twelvedata is not configured (no API key)")
        await self._limiter.acquire()
        response = await self._client.get(
            f"{BASE_URL}{path}", params=params, headers={"Authorization": f"apikey {key}"}
        )
        check_status(self.name, response)
        data = parse_json(self.name, response.text)
        if not isinstance(data, dict):
            raise ProviderDataError("twelvedata returned an unexpected payload")
        if data.get("status") == "error":
            self._raise_body_error(data)
        return data

    def _raise_body_error(self, data: dict[str, Any]) -> None:
        code = data.get("code")
        if code == 404:
            raise SymbolNotFound("twelvedata does not know this symbol")
        if code == 429:
            raise RateLimited("twelvedata rate limited")
        if code in (401, 403):
            raise ProviderAuthError(f"twelvedata refused the credentials (code {code})")
        if isinstance(code, int) and code >= 500:
            raise ProviderUnavailable(f"twelvedata server error (code {code})")
        raise ProviderDataError(f"twelvedata rejected the request (code {code})")

    def _check_kind(self, kind: AssetKind) -> None:
        if kind not in self.supported_kinds:
            raise UnsupportedKind(f"twelvedata does not serve {kind}")

    async def get_quote(self, symbol: str, kind: AssetKind) -> PriceQuote:
        self._check_kind(kind)
        data = await self._get("/quote", {"symbol": symbol})
        retrieved = self._now()
        stamp = data.get("timestamp")
        if stamp is None:
            raise ProviderDataError("twelvedata quote has no timestamp")
        as_of = datetime.fromtimestamp(int(stamp), UTC)
        return PriceQuote(
            symbol,
            kind,
            _decimal(data.get("close"), "price"),
            str(data.get("currency", "")),
            Provenance(self.name, min(as_of, retrieved), retrieved),
        )

    async def get_history(
        self, symbol: str, kind: AssetKind, start: date, end: date
    ) -> list[PricePoint]:
        self._check_kind(kind)
        data = await self._get(
            "/time_series",
            {
                "symbol": symbol,
                "interval": "1day",
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "order": "ASC",
            },
        )
        meta = data.get("meta")
        rows = data.get("values")
        if not isinstance(meta, dict) or not isinstance(rows, list):
            raise ProviderDataError("twelvedata returned no price series")
        currency = str(meta.get("currency", ""))
        retrieved = self._now()
        points: list[PricePoint] = []
        for row in rows:
            try:
                day = date.fromisoformat(str(row["datetime"])[:10])
                close = _decimal(row["close"], "close")
            except (KeyError, TypeError, ValueError):
                raise ProviderDataError("twelvedata returned a malformed price row") from None
            if start <= day <= end:
                points.append(
                    PricePoint(
                        symbol,
                        day,
                        close,
                        currency,
                        Provenance(self.name, min(_day_end(day), retrieved), retrieved),
                    )
                )
        return sorted(points, key=lambda p: p.day)

    async def get_fx_rate(self, base: str, quote: str) -> FxQuote:
        data = await self._get("/exchange_rate", {"symbol": f"{base}/{quote}"})
        retrieved = self._now()
        stamp = data.get("timestamp")
        as_of = datetime.fromtimestamp(int(stamp), UTC) if stamp is not None else retrieved
        return FxQuote(
            base,
            quote,
            _decimal(data.get("rate"), "rate"),
            Provenance(self.name, min(as_of, retrieved), retrieved),
        )

    async def get_fx_history(self, base: str, quote: str, start: date, end: date) -> list[FxQuote]:
        data = await self._get(
            "/time_series",
            {
                "symbol": f"{base}/{quote}",
                "interval": "1day",
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "order": "ASC",
            },
        )
        rows = data.get("values")
        if not isinstance(rows, list):
            raise ProviderDataError("twelvedata returned no rate series")
        retrieved = self._now()
        points: list[FxQuote] = []
        for row in rows:
            try:
                day = date.fromisoformat(str(row["datetime"])[:10])
                rate = _decimal(row["close"], "rate")
            except (KeyError, TypeError, ValueError):
                raise ProviderDataError("twelvedata returned a malformed rate row") from None
            if start <= day <= end:
                points.append(
                    FxQuote(
                        base,
                        quote,
                        rate,
                        Provenance(self.name, min(_day_end(day), retrieved), retrieved),
                    )
                )
        return sorted(points, key=lambda p: p.provenance.as_of)
