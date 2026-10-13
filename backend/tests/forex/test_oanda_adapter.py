"""Contract tests of the OANDA-style adapter against synthetic recorded responses (P13-T02.6,
DEC-19: fixture-only, no key, no live call). They pin the parsing of pricing snapshots, the
pricing stream and candles, the mapping of vendor failures onto provider errors, and that the
token never leaks into an error."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import SecretStr

from app.modules.forex.marketdata.oanda import OandaStyleProvider, parse_time
from app.modules.forex.marketdata.provider import ForexProvider
from app.modules.forex.marketdata.types import DataType, Heartbeat, PriceBasis, Quote, Timeframe
from app.modules.market_data.providers.errors import (
    ProviderAuthError,
    ProviderDataError,
    ProviderError,
    ProviderUnavailable,
    RateLimited,
    SymbolNotFound,
)
from app.modules.market_data.providers.http import HttpResponse

FIXTURES = Path(__file__).parent / "fixtures"
TOKEN = "test-token-not-a-real-key"
D = Decimal


class RecordedHttp:
    def __init__(self, response: HttpResponse) -> None:
        self.response = response
        self.calls: list[tuple[str, dict[str, str] | None, dict[str, str] | None]] = []

    async def get(
        self, url: str, params: dict[str, str] | None = None, headers: dict[str, str] | None = None
    ) -> HttpResponse:
        self.calls.append((url, params, headers))
        return self.response


class RecordedLines:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls: list[str] = []

    async def lines(
        self, url: str, params: dict[str, str], headers: dict[str, str]
    ) -> AsyncIterator[str]:
        self.calls.append(url)
        for line in self.text.split("\n"):
            yield line


def adapter(
    body: str = "{}", status: int = 200, headers: dict[str, str] | None = None, lines: str = ""
) -> tuple[OandaStyleProvider, RecordedHttp, RecordedLines]:
    http = RecordedHttp(HttpResponse(status, body, headers or {}))
    source = RecordedLines(lines)
    provider = OandaStyleProvider(
        http,
        source,
        "https://api.example.test",
        "https://stream.example.test",
        "001-001-0000000-001",
        SecretStr(TOKEN),
        DataType.TRADABLE_QUOTE,
    )
    return provider, http, source


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_it_implements_the_forex_provider_interface() -> None:
    assert isinstance(adapter()[0], ForexProvider)


def test_nanosecond_times_are_truncated_to_microseconds_in_utc() -> None:
    assert parse_time("2026-10-14T09:59:59.987654321Z") == datetime(
        2026, 10, 14, 9, 59, 59, 987654, tzinfo=UTC
    )
    assert parse_time("2026-10-14T10:00:00Z") == datetime(2026, 10, 14, 10, tzinfo=UTC)
    for bad in ("2026-10-14T10:00:00", "2026-10-14T10:00:00+03:00", 1760436000, None):
        with pytest.raises(ProviderDataError):
            parse_time(bad)


async def test_pricing_snapshot_uses_the_top_of_book_and_labels_each_price() -> None:
    provider, http, _ = adapter(fixture("oanda_pricing.json"))
    eur, kes = await provider.snapshot(["EUR_USD", "USD_KES", "USD_ZAR"])
    assert (eur.bid, eur.ask, eur.mid) == (D("1.08501"), D("1.08513"), D("1.08507"))
    assert eur.data_type is DataType.TRADABLE_QUOTE
    assert eur.ts_provider == datetime(2026, 10, 14, 9, 59, 59, 987654, tzinfo=UTC)
    # The vendor says it is not tradeable: shown as indicative, never as tradable.
    assert kes.data_type is DataType.INDICATIVE_RATE
    # USD_ZAR had no bid or ask: absent, not guessed.
    url, params, headers = http.calls[0]
    assert url == "https://api.example.test/v3/accounts/001-001-0000000-001/pricing"
    assert params == {"instruments": "EUR_USD,USD_KES,USD_ZAR"}
    assert headers == {"Authorization": f"Bearer {TOKEN}"}


async def test_stream_yields_heartbeats_and_prices_and_skips_keep_alive_lines() -> None:
    provider, _, source = adapter(lines=fixture("oanda_stream.ndjson"))
    events = [e async for e in provider.stream(["EUR_USD", "USD_KES"])]
    assert [type(e) for e in events] == [Heartbeat, Quote, Quote, Heartbeat]
    first_price = events[1]
    assert isinstance(first_price, Quote) and first_price.bid == D("1.08501")
    assert source.calls == [
        "https://stream.example.test/v3/accounts/001-001-0000000-001/pricing/stream"
    ]


async def test_a_garbled_stream_line_is_a_data_error() -> None:
    provider, _, _ = adapter(lines='{"type":"PRICE"\n')
    with pytest.raises(ProviderDataError):
        _ = [e async for e in provider.stream(["EUR_USD"])]
    provider, _, _ = adapter(lines='{"type":"ORDER_FILL"}\n')
    with pytest.raises(ProviderDataError):
        _ = [e async for e in provider.stream(["EUR_USD"])]


async def test_candles_are_parsed_in_order_with_gaps_left_absent() -> None:
    provider, http, _ = adapter(fixture("oanda_candles_m1.json"))
    start = datetime(2026, 10, 14, 9, 57, tzinfo=UTC)
    end = datetime(2026, 10, 14, 10, 1, tzinfo=UTC)
    candles = await provider.candles("EUR_USD", Timeframe.M1, start, end)
    assert [c.ts.minute for c in candles] == [57, 59, 0]  # 09:58 is missing and stays missing
    assert [c.complete for c in candles] == [True, True, False]
    assert candles[0].close == D("1.08500") and candles[0].volume == 42
    assert {c.price_basis for c in candles} == {PriceBasis.MID}
    _, params, _ = http.calls[0]
    assert params is not None and params["granularity"] == "M1" and params["price"] == "M"


async def test_candles_outside_the_requested_range_are_dropped() -> None:
    provider, _, _ = adapter(fixture("oanda_candles_m1.json"))
    start = datetime(2026, 10, 14, 9, 58, tzinfo=UTC)
    end = datetime(2026, 10, 14, 10, 0, tzinfo=UTC)
    candles = await provider.candles("EUR_USD", Timeframe.M1, start, end)
    assert [c.ts.minute for c in candles] == [59]


async def test_a_candle_without_the_requested_basis_is_a_data_error() -> None:
    provider, _, _ = adapter(fixture("oanda_candles_m1.json"))
    with pytest.raises(ProviderDataError):
        await provider.candles(
            "EUR_USD",
            Timeframe.M1,
            datetime(2026, 10, 14, tzinfo=UTC),
            datetime(2026, 10, 15, tzinfo=UTC),
            PriceBasis.BID,
        )


async def test_numeric_prices_are_refused() -> None:
    body = (
        '{"prices":[{"instrument":"EUR_USD","time":"2026-10-14T10:00:00Z","tradeable":true,'
        '"bids":[{"price":1.08501}],"asks":[{"price":"1.08513"}]}]}'
    )
    provider, _, _ = adapter(body)
    with pytest.raises(ProviderDataError):
        await provider.snapshot(["EUR_USD"])


@pytest.mark.parametrize(
    ("status", "headers", "error"),
    [
        (401, {}, ProviderAuthError),
        (403, {}, ProviderAuthError),
        (429, {"retry-after": "7"}, RateLimited),
        (400, {}, SymbolNotFound),
        (404, {}, SymbolNotFound),
        (500, {}, ProviderUnavailable),
        (503, {}, ProviderUnavailable),
        (302, {}, ProviderUnavailable),
    ],
)
async def test_vendor_failures_map_to_provider_errors_without_the_token(
    status: int, headers: dict[str, str], error: type[ProviderError]
) -> None:
    provider, _, _ = adapter('{"errorMessage":"no"}', status, headers)
    with pytest.raises(error) as raised:
        await provider.snapshot(["EUR_USD"])
    assert TOKEN not in str(raised.value)
    if isinstance(raised.value, RateLimited):
        assert raised.value.retry_after is not None
        assert raised.value.retry_after.total_seconds() == 7


async def test_a_body_that_is_not_json_is_a_data_error() -> None:
    provider, _, _ = adapter("<html>maintenance</html>")
    with pytest.raises(ProviderDataError):
        await provider.snapshot(["EUR_USD"])
    provider, _, _ = adapter("[]")
    with pytest.raises(ProviderDataError):
        await provider.snapshot(["EUR_USD"])


def test_a_vendor_feed_can_never_be_labelled_simulated() -> None:
    with pytest.raises(ValueError):
        OandaStyleProvider(
            RecordedHttp(HttpResponse(200, "{}")),
            RecordedLines(""),
            "https://a",
            "https://b",
            "acct",
            SecretStr(TOKEN),
            DataType.SIMULATED,
        )
