"""An adapter in the shape of OANDA's v20 REST API (P13-T02, DEC-19): pricing snapshots, the
newline-delimited pricing stream and candles.

**Fixture-only.** It is built from the vendor's public documentation and tested against
synthetic recorded responses. Nothing wires it to the app (`registry.build_provider` serves the
simulated provider only), no key exists and no live call is made. Before any real use, the
vendor and its streaming, display and redistribution licence must be chosen (DEC-19,
QG-20.1), and these parsers checked by a contract test against the real API.

The caller states the `data_type` its licence grants (tradable, indicative or delayed); a price
the vendor marks as not tradeable is downgraded to `indicative_rate`. The access token is sent
in the Authorization header only and never appears in an error or a log."""

import json
import re
from collections.abc import AsyncIterator, Sequence
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol

from pydantic import SecretStr

from app.modules.forex.marketdata.provider import StreamEvent
from app.modules.forex.marketdata.types import (
    Candle,
    DataType,
    Heartbeat,
    PriceBasis,
    Quote,
    Timeframe,
)
from app.modules.market_data.providers.errors import (
    ProviderDataError,
    ProviderUnavailable,
    SymbolNotFound,
)
from app.modules.market_data.providers.http import (
    HttpClient,
    HttpResponse,
    check_status,
    parse_json,
)

NAME = "oanda"
GRANULARITY = {
    Timeframe.M1: "M1",
    Timeframe.M5: "M5",
    Timeframe.M15: "M15",
    Timeframe.M30: "M30",
    Timeframe.H1: "H1",
    Timeframe.H4: "H4",
    Timeframe.D1: "D",
    Timeframe.W1: "W",
    Timeframe.MN1: "M",
}
BASIS = {PriceBasis.MID: ("M", "mid"), PriceBasis.BID: ("B", "bid"), PriceBasis.ASK: ("A", "ask")}
_NANOS = re.compile(r"^(?P<head>[^.]+)(?:\.(?P<frac>\d+))?Z$")


class LineSource(Protocol):
    """A streaming HTTP GET that yields the response body line by line."""

    def lines(
        self, url: str, params: dict[str, str], headers: dict[str, str]
    ) -> AsyncIterator[str]: ...


def parse_time(raw: Any) -> datetime:
    """RFC 3339 in UTC with up to nanoseconds ("2026-10-13T09:30:00.123456789Z"), truncated to
    microseconds."""
    match = _NANOS.match(raw) if isinstance(raw, str) else None
    if match is None:
        raise ProviderDataError("time must be RFC 3339 in UTC")
    frac = (match["frac"] or "")[:6].ljust(6, "0")
    try:
        return datetime.fromisoformat(f"{match['head']}.{frac}+00:00")
    except ValueError:
        raise ProviderDataError("time must be RFC 3339 in UTC") from None


def _decimal(raw: Any) -> Decimal:
    if not isinstance(raw, str):  # the vendor sends prices as strings; a float is refused
        raise ProviderDataError("price must be a decimal string")
    try:
        return Decimal(raw)
    except InvalidOperation:
        raise ProviderDataError("price must be a decimal string") from None


def parse_price(item: dict[str, Any], data_type: DataType) -> Quote | None:
    """One PRICE object. None when it carries no bid or no ask (nothing to show)."""
    bids, asks = item.get("bids") or [], item.get("asks") or []
    if not bids or not asks:
        return None
    granted = data_type if item.get("tradeable", False) else DataType.INDICATIVE_RATE
    return Quote(
        NAME,
        str(item.get("instrument", "")),
        _decimal(bids[0].get("price")),
        _decimal(asks[0].get("price")),
        parse_time(item.get("time")),
        granted,
    )


def parse_stream_line(line: str, data_type: DataType) -> StreamEvent | None:
    """One line of the pricing stream: a PRICE or a HEARTBEAT. Blank lines are keep-alives."""
    if not line.strip():
        return None
    try:
        item = json.loads(line)
    except json.JSONDecodeError:
        raise ProviderDataError("stream line is not JSON") from None
    kind = item.get("type")
    if kind == "HEARTBEAT":
        return Heartbeat(NAME, parse_time(item.get("time")))
    if kind == "PRICE":
        return parse_price(item, data_type)
    raise ProviderDataError("unknown stream message type")


def parse_candles(
    body: dict[str, Any], timeframe: Timeframe, basis: PriceBasis, data_type: DataType
) -> list[Candle]:
    key = BASIS[basis][1]
    instrument = str(body.get("instrument", ""))
    out: list[Candle] = []
    for item in body.get("candles") or []:
        prices = item.get(key)
        if not isinstance(prices, dict):
            raise ProviderDataError(f"candle has no {key} prices")
        volume = item.get("volume")
        out.append(
            Candle(
                NAME,
                instrument,
                timeframe,
                basis,
                parse_time(item.get("time")),
                _decimal(prices.get("o")),
                _decimal(prices.get("h")),
                _decimal(prices.get("l")),
                _decimal(prices.get("c")),
                volume if isinstance(volume, int) else None,
                complete=bool(item.get("complete", False)),
                data_type=data_type,
            )
        )
    return sorted(out, key=lambda c: c.ts)


def _body(response: HttpResponse) -> dict[str, Any]:
    if response.status in (400, 404):  # the vendor's answer to an unknown or unpriced pair
        raise SymbolNotFound(f"{NAME} refused the instrument (HTTP {response.status})")
    check_status(NAME, response)
    if response.status != 200:
        raise ProviderUnavailable(f"{NAME} unexpected status (HTTP {response.status})")
    body = parse_json(NAME, response.text)
    if not isinstance(body, dict):
        raise ProviderDataError(f"{NAME} returned an unexpected body")
    return body


class OandaStyleProvider:
    def __init__(
        self,
        http: HttpClient,
        lines: LineSource,
        base_url: str,
        stream_url: str,
        account_id: str,
        token: SecretStr,
        data_type: DataType,
    ) -> None:
        if data_type is DataType.SIMULATED:
            raise ValueError("a vendor feed is never labelled simulated")
        self._http = http
        self._lines = lines
        self._base = base_url.rstrip("/")
        self._stream = stream_url.rstrip("/")
        self._account = account_id
        self._token = token
        self._data_type = data_type

    @property
    def name(self) -> str:
        return NAME

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token.get_secret_value()}"}

    async def snapshot(self, instruments: Sequence[str]) -> list[Quote]:
        response = await self._http.get(
            f"{self._base}/v3/accounts/{self._account}/pricing",
            params={"instruments": ",".join(instruments)},
            headers=self._headers(),
        )
        body = _body(response)
        return [
            q
            for item in body.get("prices") or []
            if (q := parse_price(item, self._data_type)) is not None
        ]

    async def stream(self, instruments: Sequence[str]) -> AsyncIterator[StreamEvent]:
        async for line in self._lines.lines(
            f"{self._stream}/v3/accounts/{self._account}/pricing/stream",
            {"instruments": ",".join(instruments)},
            self._headers(),
        ):
            event = parse_stream_line(line, self._data_type)
            if event is not None:
                yield event

    async def candles(
        self,
        instrument: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
        basis: PriceBasis = PriceBasis.MID,
    ) -> list[Candle]:
        response = await self._http.get(
            f"{self._base}/v3/instruments/{instrument}/candles",
            params={
                "granularity": GRANULARITY[timeframe],
                "price": BASIS[basis][0],
                "from": start.isoformat(),
                "to": end.isoformat(),
            },
            headers=self._headers(),
        )
        candles = parse_candles(_body(response), timeframe, basis, self._data_type)
        return [c for c in candles if start <= c.ts < end]
