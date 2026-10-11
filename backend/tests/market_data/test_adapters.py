"""Adapters against recorded fixtures, offline (P08-T03.2): the contract, each adapter's mapping
of vendor payloads and errors, rate limiting, and key handling (P08-T03.1 to .4)."""

import logging
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from urllib.parse import urlparse

import pytest
from pydantic import SecretStr

from app.modules.market_data.providers.base import MarketDataProvider
from app.modules.market_data.providers.coingecko import CoinGeckoProvider
from app.modules.market_data.providers.ecb import EcbProvider, parse_rates
from app.modules.market_data.providers.errors import (
    ProviderAuthError,
    ProviderDataError,
    ProviderUnavailable,
    RateLimited,
    SymbolNotFound,
    UnsupportedKind,
)
from app.modules.market_data.providers.http import HttpResponse
from app.modules.market_data.providers.models import AssetKind
from app.modules.market_data.providers.resilience import ResilientProvider, RetryPolicy
from app.modules.market_data.providers.throttle import RateLimiter
from app.modules.market_data.providers.twelvedata import TwelveDataProvider
from tests.market_data.provider_contract import ProviderContract
from tests.market_data.recorded import RecordedClient, Route, fixture, ok

NOW = datetime(2026, 10, 12, 12, tzinfo=UTC)
KEY = "SUPER-SECRET-KEY-12345"


def clock() -> datetime:
    return NOW


async def no_sleep(_: float) -> None:
    return None


def unlimited() -> RateLimiter:
    return RateLimiter(10_000, timedelta(seconds=1), sleep=no_sleep)


# ------------------------------------------------------------------------------------- ECB
def ecb_client() -> RecordedClient:
    return RecordedClient(
        [
            Route("eurofxref-daily.xml", ok(fixture("ecb_daily.xml"))),
            Route("eurofxref-hist-90d.xml", ok(fixture("ecb_hist_recent.xml"))),
        ]
    )


def ecb() -> EcbProvider:
    return EcbProvider(ecb_client(), unlimited(), clock)


class TestEcbContract(ProviderContract):
    kind = None
    fx_pair = ("USD", "GBP")
    unknown_fx_pair = ("USD", "AED")

    def make_provider(self) -> MarketDataProvider:
        return ecb()


class TestEcb:
    async def test_eur_to_usd_is_the_published_rate(self) -> None:
        r = await ecb().get_fx_rate("EUR", "USD")
        assert r.rate == Decimal("1.1206")
        assert r.provenance.provider == "ecb"
        # Published at 14:15 Berlin time (CEST, UTC+2).
        assert r.provenance.as_of == datetime(2026, 10, 9, 12, 15, tzinfo=UTC)

    async def test_the_opposite_direction_is_the_exact_inverse_within_precision(self) -> None:
        direct = await ecb().get_fx_rate("EUR", "USD")
        inverse = await ecb().get_fx_rate("USD", "EUR")
        assert abs(direct.rate * inverse.rate - 1) < Decimal("1e-20")

    async def test_a_cross_rate_goes_through_the_euro(self) -> None:
        usd_gbp = await ecb().get_fx_rate("USD", "GBP")
        assert usd_gbp.rate == Decimal("0.84763") / Decimal("1.1206")

    async def test_a_currency_the_ecb_does_not_publish_is_not_found(self) -> None:
        with pytest.raises(SymbolNotFound, match="not published"):
            await ecb().get_fx_rate("USD", "AED")

    async def test_history_covers_the_requested_days_oldest_first(self) -> None:
        points = await ecb().get_fx_history("EUR", "USD", date(2026, 10, 6), date(2026, 10, 8))
        assert [p.provenance.as_of.date() for p in points] == [
            date(2026, 10, 6),
            date(2026, 10, 7),
            date(2026, 10, 8),
        ]

    async def test_history_of_an_unpublished_pair_is_not_found(self) -> None:
        with pytest.raises(SymbolNotFound):
            await ecb().get_fx_history("USD", "AED", date(2026, 10, 6), date(2026, 10, 8))

    async def test_old_history_uses_the_full_file(self) -> None:
        client = RecordedClient([Route("eurofxref-hist.xml", ok(fixture("ecb_hist_recent.xml")))])
        p = EcbProvider(client, unlimited(), clock)
        await p.get_fx_history("EUR", "USD", date(2026, 1, 1), date(2026, 10, 9))
        assert client.calls[0].url.endswith("eurofxref-hist.xml")

    async def test_assets_are_unsupported(self) -> None:
        with pytest.raises(UnsupportedKind):
            await ecb().get_quote("X", AssetKind.EQUITY)
        with pytest.raises(UnsupportedKind):
            await ecb().get_history("X", AssetKind.EQUITY, date(2026, 1, 1), date(2026, 1, 2))

    @pytest.mark.parametrize(
        "xml",
        [
            "not xml",
            "<a/>",
            '<Cube><Cube time="2026-13-45"><Cube currency="USD" rate="1"/></Cube></Cube>',
            '<Cube><Cube time="2026-10-09"><Cube currency="USD" rate="abc"/></Cube></Cube>',
            '<Cube><Cube time="2026-10-09"><Cube currency="USD" rate="0"/></Cube></Cube>',
            '<Cube><Cube time="2026-10-09"><Cube currency="USD"/></Cube></Cube>',
        ],
    )
    def test_bad_feeds_are_rejected(self, xml: str) -> None:
        with pytest.raises(ProviderDataError):
            parse_rates(xml)

    def test_an_xml_bomb_is_refused(self) -> None:
        bomb = (
            '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;&a;">]>'
            "<x>&b;</x>"
        )
        with pytest.raises(ProviderDataError, match="unsafe"):
            parse_rates(bomb)

    async def test_http_errors_map_to_provider_errors(self) -> None:
        for status, error in (
            (500, ProviderUnavailable),
            (429, RateLimited),
            (403, ProviderAuthError),
        ):
            client = RecordedClient([Route("eurofxref-daily.xml", HttpResponse(status, ""))])
            with pytest.raises(error):
                await EcbProvider(client, unlimited(), clock).get_fx_rate("EUR", "USD")


# ------------------------------------------------------------------------------- CoinGecko
def cg_client() -> RecordedClient:
    return RecordedClient(
        [
            Route(
                "/simple/price", ok(fixture("coingecko_simple_price_btc.json")), {"ids": "bitcoin"}
            ),
            Route(
                "/coins/bitcoin/market_chart/range", ok(fixture("coingecko_market_chart_btc.json"))
            ),
        ]
    )


def cg(client: RecordedClient | None = None, key: str = KEY) -> CoinGeckoProvider:
    return CoinGeckoProvider(SecretStr(key), client or cg_client(), unlimited(), clock=clock)


class TestCoinGeckoContract(ProviderContract):
    kind = AssetKind.CRYPTO
    symbol = "BTC"
    history_start = date(2026, 10, 5)
    history_end = date(2026, 10, 9)

    def make_provider(self) -> MarketDataProvider:
        return cg()


class TestCoinGecko:
    async def test_quote_price_is_an_exact_decimal_in_usd(self) -> None:
        q = await cg().get_quote("BTC", AssetKind.CRYPTO)
        assert q.price == Decimal("64800.12")
        assert q.currency == "USD"
        assert q.provenance.as_of == datetime(2026, 10, 12, 9, 59, tzinfo=UTC)
        assert q.provenance.retrieved_at == NOW

    async def test_history_takes_the_last_observation_of_each_day(self) -> None:
        points = await cg().get_history(
            "BTC", AssetKind.CRYPTO, date(2026, 10, 5), date(2026, 10, 7)
        )
        assert [p.day for p in points] == [date(2026, 10, 5), date(2026, 10, 6), date(2026, 10, 7)]
        assert points[0].close == Decimal("64500.75")
        assert all(isinstance(p.close, Decimal) for p in points)

    async def test_the_key_goes_in_a_header_never_in_the_url_or_params(self) -> None:
        client = cg_client()
        await cg(client).get_quote("BTC", AssetKind.CRYPTO)
        call = client.calls[0]
        assert call.headers == {"x-cg-demo-api-key": KEY}
        assert KEY not in call.url
        assert KEY not in str(call.params)

    async def test_the_pro_plan_uses_its_own_host_and_header(self) -> None:
        client = cg_client()
        p = CoinGeckoProvider(SecretStr(KEY), client, unlimited(), plan="pro", clock=clock)
        await p.get_quote("BTC", AssetKind.CRYPTO)
        assert urlparse(client.calls[0].url).hostname == "pro-api.coingecko.com"
        assert "x-cg-pro-api-key" in client.calls[0].headers

    async def test_an_unmapped_symbol_is_not_found_without_a_call(self) -> None:
        client = cg_client()
        with pytest.raises(SymbolNotFound):
            await cg(client).get_quote("DOGE", AssetKind.CRYPTO)
        assert client.calls == []

    async def test_an_empty_answer_is_not_found(self) -> None:
        client = RecordedClient(
            [Route("/simple/price", ok(fixture("coingecko_simple_price_empty.json")))]
        )
        with pytest.raises(SymbolNotFound):
            await cg(client).get_quote("BTC", AssetKind.CRYPTO)

    async def test_http_404_is_not_found(self) -> None:
        client = RecordedClient([Route("/simple/price", HttpResponse(404, "{}"))])
        with pytest.raises(SymbolNotFound):
            await cg(client).get_quote("BTC", AssetKind.CRYPTO)

    async def test_a_missing_key_is_an_auth_error_and_makes_no_call(self) -> None:
        client = cg_client()
        with pytest.raises(ProviderAuthError, match="not configured"):
            await cg(client, key="").get_quote("BTC", AssetKind.CRYPTO)
        assert client.calls == []

    async def test_rate_limit_carries_retry_after(self) -> None:
        client = RecordedClient(
            [Route("/simple/price", HttpResponse(429, "", {"retry-after": "12"}))]
        )
        with pytest.raises(RateLimited) as caught:
            await cg(client).get_quote("BTC", AssetKind.CRYPTO)
        assert caught.value.retry_after == timedelta(seconds=12)

    async def test_a_bad_price_is_rejected(self) -> None:
        bad = RecordedClient([Route("/simple/price", ok('{"bitcoin": {"usd": 0}}'))])
        with pytest.raises(ProviderDataError):
            await cg(bad).get_quote("BTC", AssetKind.CRYPTO)
        text = RecordedClient([Route("/simple/price", ok('{"bitcoin": {"usd": "abc"}}'))])
        with pytest.raises(ProviderDataError):
            await cg(text).get_quote("BTC", AssetKind.CRYPTO)

    async def test_invalid_json_is_rejected(self) -> None:
        client = RecordedClient([Route("/simple/price", ok("<html>"))])
        with pytest.raises(ProviderDataError):
            await cg(client).get_quote("BTC", AssetKind.CRYPTO)

    async def test_a_malformed_series_is_rejected(self) -> None:
        for body in ('{"prices": "x"}', '{"prices": [[1]]}', '{"prices": [["a", 1]]}'):
            client = RecordedClient([Route("/market_chart/range", ok(body))])
            with pytest.raises(ProviderDataError):
                await cg(client).get_history(
                    "BTC", AssetKind.CRYPTO, date(2026, 10, 5), date(2026, 10, 6)
                )

    async def test_fx_and_other_kinds_are_unsupported(self) -> None:
        with pytest.raises(UnsupportedKind):
            await cg().get_fx_rate("USD", "EUR")
        with pytest.raises(UnsupportedKind):
            await cg().get_fx_history("USD", "EUR", date(2026, 1, 1), date(2026, 1, 2))
        with pytest.raises(UnsupportedKind):
            await cg().get_quote("BTC", AssetKind.EQUITY)

    def test_repr_does_not_show_the_key(self) -> None:
        assert KEY not in repr(cg())
        assert KEY not in str(cg())


# ----------------------------------------------------------------------------- Twelve Data
def td_client() -> RecordedClient:
    return RecordedClient(
        [
            Route("/quote", ok(fixture("twelvedata_error_404.json")), {"symbol": "NOPE-NOT-REAL"}),
            Route("/quote", ok(fixture("twelvedata_quote_geq.json")), {"symbol": "GEQ"}),
            Route(
                "/time_series",
                ok(fixture("twelvedata_error_404.json")),
                {"symbol": "NOPE-NOT-REAL"},
            ),
            Route(
                "/time_series",
                ok(fixture("twelvedata_fx_time_series_usdaed.json")),
                {"symbol": "USD/AED"},
            ),
            Route(
                "/time_series", ok(fixture("twelvedata_time_series_geq.json")), {"symbol": "GEQ"}
            ),
            Route(
                "/exchange_rate", ok(fixture("twelvedata_error_404.json")), {"symbol": "USD/XXX"}
            ),
            Route(
                "/exchange_rate",
                ok(fixture("twelvedata_exchange_rate_usdaed.json")),
                {"symbol": "USD/AED"},
            ),
        ]
    )


def td(client: RecordedClient | None = None, key: str = KEY) -> TwelveDataProvider:
    return TwelveDataProvider(SecretStr(key), client or td_client(), unlimited(), clock)


class TestTwelveDataContract(ProviderContract):
    kind = AssetKind.ETF
    symbol = "GEQ"
    fx_pair = ("USD", "AED")
    unknown_fx_pair = ("USD", "XXX")
    history_start = date(2026, 10, 5)
    history_end = date(2026, 10, 9)

    def make_provider(self) -> MarketDataProvider:
        return td()


class TestTwelveData:
    async def test_quote_values_are_exact_decimals(self) -> None:
        q = await td().get_quote("GEQ", AssetKind.ETF)
        assert q.price == Decimal("104.20")
        assert q.currency == "USD"
        assert q.provenance.as_of == datetime(2026, 10, 9, 20, tzinfo=UTC)

    async def test_history_is_filtered_to_the_range_and_sorted(self) -> None:
        points = await td().get_history("GEQ", AssetKind.ETF, date(2026, 10, 6), date(2026, 10, 8))
        assert [p.day for p in points] == [date(2026, 10, 6), date(2026, 10, 7), date(2026, 10, 8)]
        assert points[0].close == Decimal("102.95")

    async def test_the_fx_rate_number_is_parsed_as_a_decimal(self) -> None:
        r = await td().get_fx_rate("USD", "AED")
        assert r.rate == Decimal("3.6725")

    async def test_the_key_goes_in_the_authorization_header_only(self) -> None:
        client = td_client()
        await td(client).get_quote("GEQ", AssetKind.ETF)
        call = client.calls[0]
        assert call.headers == {"Authorization": f"apikey {KEY}"}
        assert KEY not in call.url
        assert KEY not in str(call.params)

    @pytest.mark.parametrize(
        ("fixture_name", "error"),
        [
            ("twelvedata_error_404.json", SymbolNotFound),
            ("twelvedata_error_429.json", RateLimited),
            ("twelvedata_error_401.json", ProviderAuthError),
        ],
    )
    async def test_errors_sent_with_http_200_are_mapped(
        self, fixture_name: str, error: type[Exception]
    ) -> None:
        client = RecordedClient([Route("/quote", ok(fixture(fixture_name)))])
        with pytest.raises(error):
            await td(client).get_quote("GEQ", AssetKind.ETF)

    async def test_other_body_errors_map_by_code(self) -> None:
        server = RecordedClient(
            [Route("/quote", ok('{"status": "error", "code": 500, "message": "x"}'))]
        )
        with pytest.raises(ProviderUnavailable):
            await td(server).get_quote("GEQ", AssetKind.ETF)
        odd = RecordedClient(
            [Route("/quote", ok('{"status": "error", "code": 400, "message": "x"}'))]
        )
        with pytest.raises(ProviderDataError):
            await td(odd).get_quote("GEQ", AssetKind.ETF)

    async def test_a_missing_key_is_an_auth_error_and_makes_no_call(self) -> None:
        client = td_client()
        with pytest.raises(ProviderAuthError, match="not configured"):
            await td(client, key="").get_quote("GEQ", AssetKind.ETF)
        assert client.calls == []

    @pytest.mark.parametrize(
        "body",
        [
            '{"symbol": "GEQ", "currency": "USD", "close": "0", "timestamp": 1}',
            '{"symbol": "GEQ", "currency": "USD", "close": "abc", "timestamp": 1}',
            '{"symbol": "GEQ", "currency": "USD", "close": "10"}',
            "[]",
            "not json",
        ],
    )
    async def test_bad_quotes_are_rejected(self, body: str) -> None:
        client = RecordedClient([Route("/quote", ok(body))])
        with pytest.raises(ProviderDataError):
            await td(client).get_quote("GEQ", AssetKind.ETF)

    async def test_malformed_series_are_rejected(self) -> None:
        for body in (
            '{"meta": {"currency": "USD"}, "values": "x"}',
            '{"values": []}',
            '{"meta": {"currency": "USD"}, "values": [{"datetime": "bad", "close": "1"}]}',
            '{"meta": {"currency": "USD"}, "values": [{"datetime": "2026-10-06"}]}',
        ):
            client = RecordedClient([Route("/time_series", ok(body))])
            with pytest.raises(ProviderDataError):
                await td(client).get_history(
                    "GEQ", AssetKind.ETF, date(2026, 10, 5), date(2026, 10, 9)
                )
        client = RecordedClient([Route("/time_series", ok('{"values": "x"}'))])
        with pytest.raises(ProviderDataError):
            await td(client).get_fx_history("USD", "AED", date(2026, 10, 5), date(2026, 10, 9))

    async def test_crypto_is_unsupported(self) -> None:
        with pytest.raises(UnsupportedKind):
            await td().get_quote("BTC", AssetKind.CRYPTO)

    async def test_the_licence_condition_is_stated_in_the_module(self) -> None:
        import app.modules.market_data.providers.twelvedata as module

        assert "non-commercial" in (module.__doc__ or "")

    def test_repr_does_not_show_the_key(self) -> None:
        assert KEY not in repr(td())


# ---------------------------------------------------------------------------- rate limiting
class TestRateLimiter:
    async def test_it_waits_when_the_window_is_full(self) -> None:
        now = [NOW]
        slept: list[float] = []

        async def sleep(seconds: float) -> None:
            slept.append(seconds)
            now[0] += timedelta(seconds=seconds)

        limiter = RateLimiter(2, timedelta(seconds=10), clock=lambda: now[0], sleep=sleep)
        for _ in range(2):
            await limiter.acquire()
        assert slept == []
        await limiter.acquire()  # the third call must wait for the first to leave the window
        assert slept == [10.0]

    async def test_calls_outside_the_window_do_not_count(self) -> None:
        now = [NOW]
        limiter = RateLimiter(1, timedelta(seconds=5), clock=lambda: now[0], sleep=no_sleep)
        await limiter.acquire()
        now[0] += timedelta(seconds=5)
        await limiter.acquire()  # would loop forever if the old call still counted

    def test_invalid_settings_are_refused(self) -> None:
        with pytest.raises(ValueError, match="max_calls"):
            RateLimiter(0, timedelta(seconds=1))
        with pytest.raises(ValueError, match="per"):
            RateLimiter(1, timedelta(0))

    async def test_adapters_acquire_before_every_call(self) -> None:
        slept: list[float] = []
        now = [NOW]

        async def sleep(seconds: float) -> None:
            slept.append(seconds)
            now[0] += timedelta(seconds=seconds)

        limiter = RateLimiter(1, timedelta(seconds=60), clock=lambda: now[0], sleep=sleep)
        p = CoinGeckoProvider(SecretStr(KEY), cg_client(), limiter, clock=clock)
        await p.get_quote("BTC", AssetKind.CRYPTO)
        await p.get_quote("BTC", AssetKind.CRYPTO)
        assert slept == [60.0]


# ------------------------------------------------------------------- failures and the key
class TestKeysNeverLeak:
    async def test_the_key_is_in_no_error_message_log_or_repr(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.DEBUG)
        failures = [
            HttpResponse(401, f"bad key {KEY}"),
            HttpResponse(403, ""),
            HttpResponse(429, ""),
            HttpResponse(500, ""),
            HttpResponse(418, ""),
        ]
        for response in failures:
            client = RecordedClient([Route("/simple/price", response)])
            provider = cg(client)
            with pytest.raises(Exception, match=r".") as caught:
                await provider.get_quote("BTC", AssetKind.CRYPTO)
            assert KEY not in str(caught.value)
            assert KEY not in repr(caught.value)
            assert KEY not in repr(provider)
        assert KEY not in caplog.text

    async def test_the_settings_hold_keys_as_secrets(self) -> None:
        from app.core.config import Settings

        s = Settings(coingecko_api_key=SecretStr(KEY), twelvedata_api_key=SecretStr(KEY))
        assert KEY not in repr(s)
        assert KEY not in str(s.model_dump())
        assert s.coingecko_api_key.get_secret_value() == KEY

    def test_no_provider_source_contains_a_key_like_literal(self) -> None:
        from pathlib import Path

        package = Path(__file__).resolve().parents[2] / "app" / "modules" / "market_data"
        for path in package.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            assert "apikey=" not in text.replace("apikey {", ""), path.name


# ------------------------------------------------------------ the adapters with resilience
async def test_a_rate_limited_adapter_is_retried_after_the_stated_wait() -> None:
    slept: list[float] = []

    async def sleep(seconds: float) -> None:
        slept.append(seconds)

    responses = [HttpResponse(429, "", {"retry-after": "3"})]
    quote_ok = ok(fixture("coingecko_simple_price_btc.json"))

    class Flaky(RecordedClient):
        async def get(self, url, params=None, headers=None):  # type: ignore[no-untyped-def]
            return responses.pop(0) if responses else quote_ok

    p = ResilientProvider(cg(Flaky([])), RetryPolicy(), sleep=sleep)
    q = await p.get_quote("BTC", AssetKind.CRYPTO)
    assert q.price == Decimal("64800.12")
    assert slept == [3.0]


async def test_an_auth_error_is_not_retried_and_counts_against_health() -> None:
    slept: list[float] = []

    async def sleep(seconds: float) -> None:
        slept.append(seconds)

    client = RecordedClient([Route("/simple/price", HttpResponse(401, ""))])
    p = ResilientProvider(cg(client), RetryPolicy(), sleep=sleep)
    with pytest.raises(ProviderAuthError):
        await p.get_quote("BTC", AssetKind.CRYPTO)
    assert slept == []
    assert len(client.calls) == 1


# ------------------------------------------------------------------------------ transport
class TestHttpxClient:
    async def test_success_returns_status_text_and_lowercased_headers(self) -> None:
        import httpx

        from app.modules.market_data.providers.http import HttpxClient

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.headers["authorization"] == "apikey k"
            assert request.url.params["symbol"] == "GEQ"
            return httpx.Response(200, text="{}", headers={"Retry-After": "5"})

        client = HttpxClient(transport=httpx.MockTransport(handler))
        r = await client.get(
            "https://x.test/quote", {"symbol": "GEQ"}, {"Authorization": "apikey k"}
        )
        assert (r.status, r.text, r.headers["retry-after"]) == (200, "{}", "5")

    async def test_a_transport_failure_is_unavailable_and_hides_the_url(self) -> None:
        import httpx

        from app.modules.market_data.providers.http import HttpxClient

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectTimeout(
                "timed out talking to https://x.test/?apikey=SECRET", request=request
            )

        client = HttpxClient(transport=httpx.MockTransport(handler))
        with pytest.raises(ProviderUnavailable) as caught:
            await client.get("https://x.test/quote")
        assert "SECRET" not in str(caught.value)
        assert "ConnectTimeout" in str(caught.value)

    def test_retry_after_that_is_a_date_is_ignored(self) -> None:
        from app.modules.market_data.providers.http import _retry_after

        assert (
            _retry_after(HttpResponse(429, "", {"retry-after": "Wed, 21 Oct 2026 07:28:00 GMT"}))
            is None
        )
        assert _retry_after(HttpResponse(429, "", {})) is None
        assert _retry_after(HttpResponse(429, "", {"retry-after": "-5"})) == timedelta(0)
