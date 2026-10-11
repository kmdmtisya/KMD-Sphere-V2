"""CoinGecko crypto prices (ADR-0014). Needs a key; production needs a paid commercial plan and the
attribution line "Data provided by CoinGecko" wherever the data is shown.

The key is sent in a header, never in the URL, and is held as a `SecretStr`: it cannot leak
through a repr, a log line or an error message. Prices are quoted in USD. Our symbols (`BTC`) map
to CoinGecko coin ids (`bitcoin`); an unmapped symbol is `SymbolNotFound`.

Response shapes (from the public API reference; the contract fixtures are synthetic in these
shapes and are to be re-recorded once a key exists):
- `GET /simple/price?ids=bitcoin&vs_currencies=usd&include_last_updated_at=true`
  -> `{"bitcoin": {"usd": 64800.12, "last_updated_at": 1760000000}}`
- `GET /coins/bitcoin/market_chart/range?vs_currency=usd&from=..&to=..`
  -> `{"prices": [[1759881600000, 64210.5], ...]}` (milliseconds)"""

from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import SecretStr

from app.modules.market_data.providers.errors import (
    ProviderAuthError,
    ProviderDataError,
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

DEMO_URL = "https://api.coingecko.com/api/v3"
PRO_URL = "https://pro-api.coingecko.com/api/v3"
DEFAULT_COIN_IDS = {"BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana", "XRP": "ripple"}


def _decimal(value: Any, what: str) -> Decimal:
    try:
        result = Decimal(value) if not isinstance(value, Decimal) else value
    except (InvalidOperation, TypeError, ValueError):
        raise ProviderDataError(f"coingecko returned an invalid {what}") from None
    if not result.is_finite() or result <= 0:
        raise ProviderDataError(f"coingecko returned a non-positive {what}")
    return result


class CoinGeckoProvider:
    name = "coingecko"
    supported_kinds = frozenset({AssetKind.CRYPTO})

    def __init__(
        self,
        api_key: SecretStr,
        client: HttpClient | None = None,
        limiter: RateLimiter | None = None,
        coin_ids: dict[str, str] | None = None,
        plan: str = "demo",
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._api_key = api_key
        self._client = client or HttpxClient()
        # The demo plan allows about 30 calls a minute.
        self._limiter = limiter or RateLimiter(30, timedelta(minutes=1))
        self._ids = dict(DEFAULT_COIN_IDS if coin_ids is None else coin_ids)
        self._pro = plan == "pro"
        self._now: Callable[[], datetime] = clock or (lambda: datetime.now(UTC))

    def __repr__(self) -> str:
        return f"CoinGeckoProvider(plan={'pro' if self._pro else 'demo'})"

    def _headers(self) -> dict[str, str]:
        key = self._api_key.get_secret_value()
        if not key:
            raise ProviderAuthError("coingecko is not configured (no API key)")
        return {("x-cg-pro-api-key" if self._pro else "x-cg-demo-api-key"): key}

    async def _get(self, path: str, params: dict[str, str]) -> Any:
        headers = self._headers()
        await self._limiter.acquire()
        base = PRO_URL if self._pro else DEMO_URL
        response = await self._client.get(f"{base}{path}", params=params, headers=headers)
        if response.status == 404:
            raise SymbolNotFound("coingecko does not know this coin")
        check_status(self.name, response)
        return parse_json(self.name, response.text)

    def _coin(self, symbol: str, kind: AssetKind) -> str:
        if kind is not AssetKind.CRYPTO:
            raise UnsupportedKind("coingecko serves crypto only")
        coin = self._ids.get(symbol)
        if coin is None:
            raise SymbolNotFound(symbol)
        return coin

    async def get_quote(self, symbol: str, kind: AssetKind) -> PriceQuote:
        coin = self._coin(symbol, kind)
        data = await self._get(
            "/simple/price",
            {"ids": coin, "vs_currencies": "usd", "include_last_updated_at": "true"},
        )
        entry = data.get(coin) if isinstance(data, dict) else None
        if not isinstance(entry, dict) or "usd" not in entry:
            raise SymbolNotFound(symbol)
        price = _decimal(entry["usd"], "price")
        retrieved = self._now()
        stamp = entry.get("last_updated_at")
        as_of = datetime.fromtimestamp(int(stamp), UTC) if stamp is not None else retrieved
        return PriceQuote(
            symbol,
            kind,
            price,
            "USD",
            Provenance(self.name, min(as_of, retrieved), retrieved),
        )

    async def get_history(
        self, symbol: str, kind: AssetKind, start: date, end: date
    ) -> list[PricePoint]:
        coin = self._coin(symbol, kind)
        first = int(datetime(start.year, start.month, start.day, tzinfo=UTC).timestamp())
        last = int(datetime(end.year, end.month, end.day, 23, 59, 59, tzinfo=UTC).timestamp())
        data = await self._get(
            f"/coins/{coin}/market_chart/range",
            {"vs_currency": "usd", "from": str(first), "to": str(last)},
        )
        rows = data.get("prices") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            raise ProviderDataError("coingecko returned no price series")
        retrieved = self._now()
        closes: dict[date, tuple[datetime, Decimal]] = {}
        for row in rows:
            try:
                moment = datetime.fromtimestamp(int(row[0]) / 1000, UTC)
                value = _decimal(row[1], "close")
            except (IndexError, TypeError, ValueError):
                raise ProviderDataError("coingecko returned a malformed price row") from None
            # The close of a UTC day is its last observation.
            if start <= moment.date() <= end and (
                moment.date() not in closes or moment > closes[moment.date()][0]
            ):
                closes[moment.date()] = (moment, value)
        return [
            PricePoint(
                symbol,
                day,
                value,
                "USD",
                Provenance(self.name, min(moment, retrieved), retrieved),
            )
            for day, (moment, value) in sorted(closes.items())
        ]

    async def get_fx_rate(self, base: str, quote: str) -> FxQuote:
        raise UnsupportedKind("coingecko is not used for FX")

    async def get_fx_history(self, base: str, quote: str, start: date, end: date) -> list[FxQuote]:
        raise UnsupportedKind("coingecko is not used for FX")
