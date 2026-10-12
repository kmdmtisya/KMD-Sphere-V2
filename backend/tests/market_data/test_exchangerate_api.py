"""ExchangeRate-API adapter (P11-T03.1, DEC-25) against synthetic fixtures in the documented
response shapes. No key exists and no live call is made (fixture-only approval)."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from pydantic import SecretStr

from app.modules.market_data.providers.base import MarketDataProvider
from app.modules.market_data.providers.batch import fetch_fx_batch
from app.modules.market_data.providers.errors import (
    ProviderAuthError,
    ProviderDataError,
    ProviderUnavailable,
    RateLimited,
    UnsupportedKind,
)
from app.modules.market_data.providers.exchangerate_api import ExchangeRateApiProvider
from app.modules.market_data.providers.http import HttpResponse
from app.modules.market_data.providers.models import AssetKind
from app.modules.market_data.providers.resilience import ResilientProvider, RetryPolicy
from app.modules.market_data.providers.throttle import RateLimiter
from tests.market_data.provider_contract import ProviderContract
from tests.market_data.recorded import RecordedClient, Route, fixture, ok

NOW = datetime(2026, 10, 12, 12, tzinfo=UTC)
KEY = "test-key-not-real-0123"


def client(extra: list[Route] | None = None) -> RecordedClient:
    routes = [
        Route(f"{KEY}/latest/USD", ok(fixture("exchangerate_api_latest_usd.json"))),
        Route(f"{KEY}/pair/USD/AED", ok(fixture("exchangerate_api_pair_usd_aed.json"))),
        Route(f"{KEY}/pair/USD/XXX", ok(fixture("exchangerate_api_error_unsupported.json"))),
    ]
    routes += [
        Route(
            f"{KEY}/history/USD/2026/10/{d}",
            ok(fixture(f"exchangerate_api_history_usd_2026_10_{d}.json")),
        )
        for d in range(5, 10)
    ]
    return RecordedClient((extra or []) + routes)


def provider(c: RecordedClient | None = None) -> ExchangeRateApiProvider:
    return ExchangeRateApiProvider(
        SecretStr(KEY),
        client=c or client(),
        limiter=RateLimiter(1000, __import__("datetime").timedelta(minutes=1)),
        clock=lambda: NOW,
    )


class TestExchangeRateApiContract(ProviderContract):
    kind = None
    fx_pair = ("USD", "AED")
    unknown_fx_pair = ("USD", "XXX")

    def make_provider(self) -> MarketDataProvider:
        return provider()


async def test_a_pair_is_an_exact_decimal_with_the_published_time() -> None:
    r = await provider().get_fx_rate("USD", "AED")
    assert r.rate == Decimal("3.6725")
    assert isinstance(r.rate, Decimal)
    assert r.provenance.provider == "exchangerate_api"
    assert r.provenance.as_of == datetime(2026, 10, 12, 0, 0, 1, tzinfo=UTC)
    assert r.provenance.retrieved_at == NOW
    assert r.rate_type == "indicative"
    assert r.path is None


async def test_one_latest_request_answers_every_quote() -> None:
    c = client()
    batch = await fetch_fx_batch(provider(c), "USD", ["AED", "KES", "JPY", "USD", "XYZ"])
    assert {r.quote: r.rate for r in batch.rates} == {
        "AED": Decimal("3.6725"),
        "KES": Decimal("129.15"),
        "JPY": Decimal("149.83"),
    }
    assert batch.unsupported == ["XYZ"]
    assert len(c.calls) == 1, "a batch is one request"


async def test_history_is_one_request_per_day_with_end_of_day_stamps() -> None:
    c = client()
    points = await provider(c).get_fx_history("USD", "KES", date(2026, 10, 5), date(2026, 10, 9))
    assert [p.provenance.as_of.date() for p in points] == [date(2026, 10, d) for d in range(5, 10)]
    assert points[0].rate == Decimal("129.1")
    assert len(c.calls) == 5


async def test_history_refuses_a_long_range_that_would_spend_the_quota() -> None:
    with pytest.raises(ProviderDataError):
        await provider().get_fx_history("USD", "KES", date(2026, 8, 1), date(2026, 10, 9))
    assert await provider().get_fx_history("USD", "KES", date(2026, 10, 9), date(2026, 10, 5)) == []


async def test_a_history_day_mismatch_is_bad_data() -> None:
    wrong = Route(
        f"{KEY}/history/USD/2026/10/4", ok(fixture("exchangerate_api_history_usd_2026_10_5.json"))
    )
    with pytest.raises(ProviderDataError):
        await provider(client([wrong])).get_fx_history(
            "USD", "KES", date(2026, 10, 4), date(2026, 10, 4)
        )


@pytest.mark.parametrize(
    ("fixture_name", "error"),
    [
        ("exchangerate_api_error_unsupported.json", UnsupportedKind),
        ("exchangerate_api_error_invalid_key.json", ProviderAuthError),
        ("exchangerate_api_error_quota.json", RateLimited),
        ("exchangerate_api_error_malformed.json", ProviderDataError),
    ],
)
async def test_documented_error_types_map_to_provider_errors(
    fixture_name: str, error: type[Exception]
) -> None:
    c = RecordedClient([Route(f"{KEY}/pair/USD/EUR", ok(fixture(fixture_name)))])
    with pytest.raises(error):
        await provider(c).get_fx_rate("USD", "EUR")


@pytest.mark.parametrize(
    ("status", "error"),
    [
        (500, ProviderUnavailable),
        (503, ProviderUnavailable),
        (429, RateLimited),
        (403, ProviderAuthError),
    ],
)
async def test_http_failures_map_to_provider_errors(status: int, error: type[Exception]) -> None:
    c = RecordedClient([Route(f"{KEY}/pair/USD/EUR", HttpResponse(status, "{}"))])
    with pytest.raises(error):
        await provider(c).get_fx_rate("USD", "EUR")


@pytest.mark.parametrize(
    "body",
    [
        "not json",
        "[]",
        '{"result": "success", "base_code": "EUR", "target_code": "AED", '
        '"conversion_rate": 3.6, "time_last_update_unix": 1791763201}',
        '{"result": "success", "base_code": "USD", "target_code": "AED", '
        '"conversion_rate": -3.6, "time_last_update_unix": 1791763201}',
        '{"result": "success", "base_code": "USD", "target_code": "AED", "conversion_rate": 3.6}',
        '{"result": "success", "base_code": "USD", "target_code": "AED", '
        '"conversion_rate": true, "time_last_update_unix": 1791763201}',
        '{"result": "maybe"}',
    ],
)
async def test_unusable_answers_are_bad_data_never_a_rate(body: str) -> None:
    c = RecordedClient([Route(f"{KEY}/pair/USD/AED", ok(body))])
    with pytest.raises(ProviderDataError):
        await provider(c).get_fx_rate("USD", "AED")


async def test_the_key_never_appears_in_an_error() -> None:
    c = RecordedClient([Route(f"{KEY}/pair/USD/EUR", HttpResponse(500, "{}"))])
    with pytest.raises(ProviderUnavailable) as caught:
        await provider(c).get_fx_rate("USD", "EUR")
    assert KEY not in str(caught.value)


async def test_it_serves_fx_only_and_needs_a_key() -> None:
    with pytest.raises(UnsupportedKind):
        await provider().get_quote("GEQ", AssetKind.ETF)
    with pytest.raises(UnsupportedKind):
        await provider().get_history("GEQ", AssetKind.ETF, date(2026, 10, 5), date(2026, 10, 9))
    with pytest.raises(ValueError):
        ExchangeRateApiProvider(SecretStr(""))


async def test_the_resilient_wrapper_retries_a_batch_and_passes_it_through() -> None:
    answers = [HttpResponse(503, "{}"), ok(fixture("exchangerate_api_latest_usd.json"))]

    class Flaky(RecordedClient):
        async def get(self, url: str, params=None, headers=None):  # type: ignore[no-untyped-def]
            self.calls.append(url)  # type: ignore[arg-type]
            return answers.pop(0)

    async def no_sleep(_: float) -> None:
        return None

    wrapped = ResilientProvider(
        provider(Flaky([])), retry=RetryPolicy(max_attempts=2), sleep=no_sleep
    )
    batch = await wrapped.get_fx_rates("USD", ["AED"])
    assert [r.quote for r in batch.rates] == ["AED"]
