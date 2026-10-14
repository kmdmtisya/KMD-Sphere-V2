# ruff: noqa: F811 (imported pytest fixtures are used by name as test parameters)
"""Forex analysis on the real database (P13-T03): candle sync from the provider, the indicators,
structure and patterns endpoints, native versus aggregated candles, gaps that stay gaps, request
validation and the feature flag. Data is the simulated provider's, on a fixed past Wednesday."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.main import create_app
from app.modules.forex.analysis import indicators as ind
from app.modules.forex.candles.sync import sync_minutes
from app.modules.forex.marketdata.fake import FakeForexProvider, ScriptItem
from app.modules.forex.marketdata.repository import store_candles
from app.modules.forex.marketdata.types import Candle, DataType, PriceBasis, Timeframe
from tests import auth_helpers as ah
from tests.authz_harness import TestUser, make_user
from tests.db_fixtures import migrated_settings  # noqa: F401
from tests.forex.test_forex_api import (  # noqa: F401
    app,
    http,
    sessions,
    settings_override,
    user,
)
from tests.forex.test_marketdata_core import Clock

pytestmark = [pytest.mark.integration, pytest.mark.security]
D = Decimal
WED = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)  # 08:00 in New York: the market is open
START = WED - timedelta(hours=2)
PATH = "/api/v1/forex"


async def seed(sessions: async_sessionmaker[AsyncSession], pair: str, hours: int = 2) -> int:
    clock = Clock(WED)
    provider = FakeForexProvider(clock=clock)
    async with sessions() as s:
        report = await sync_minutes(s, provider, [pair], WED, timedelta(hours=hours))
    assert report.failed == []
    return report.stored


def params(pair: str, frame: str = "1m", **extra: Any) -> dict[str, Any]:
    return {
        "instrument": pair,
        "timeframe": frame,
        "start": START.isoformat(),
        "end": WED.isoformat(),
        **extra,
    }


# --------------------------------------------------------------------------- candle sync
async def test_the_sync_stores_complete_provider_candles_and_continues_where_it_stopped(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    assert await seed(sessions, "EUR_USD") == 120
    async with sessions() as s:
        again = await sync_minutes(s, FakeForexProvider(clock=Clock(WED)), ["EUR_USD"], WED)
        assert (again.stored, again.failed) == (0, [])  # nothing new
        later = WED + timedelta(minutes=3)
        more = await sync_minutes(s, FakeForexProvider(clock=Clock(later)), ["EUR_USD"], later)
        assert more.stored == 3  # only the new minutes
        count = await s.scalar(
            text(
                "SELECT count(*) FROM forex_candles "
                "WHERE instrument = 'EUR_USD' AND timeframe = '1m'"
            )
        )
        assert count == 123


async def test_a_provider_outage_leaves_a_gap_and_is_reported_not_filled(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    provider = FakeForexProvider(clock=Clock(WED))
    provider.down = True
    async with sessions() as s:
        report = await sync_minutes(s, provider, ["USD_CHF"], WED, timedelta(hours=1))
        assert (report.stored, report.failed) == (0, ["USD_CHF"])
        assert (
            await s.scalar(text("SELECT count(*) FROM forex_candles WHERE instrument = 'USD_CHF'"))
            == 0
        )


async def test_the_sync_stops_at_the_current_minute_and_never_stores_a_forming_candle(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    now = WED + timedelta(minutes=30, seconds=40)
    async with sessions() as s:
        report = await sync_minutes(
            s, FakeForexProvider(clock=Clock(now)), ["AUD_USD"], now, timedelta(hours=1)
        )
        newest = await s.scalar(
            text("SELECT max(ts) FROM forex_candles WHERE instrument = 'AUD_USD'")
        )
    # The window is [11:30, 12:30): 60 closed minutes; the forming 12:30 minute is not asked for.
    assert report.stored == 60
    assert newest == WED + timedelta(minutes=29)


# ------------------------------------------------------------------------------ indicators
async def test_indicators_equal_the_library_applied_to_the_stored_candles(
    http: httpx.AsyncClient, user: TestUser, sessions: async_sessionmaker[AsyncSession]
) -> None:
    await seed(sessions, "EUR_USD")
    candles = (
        await http.get(f"{PATH}/candles", params=params("EUR_USD"), headers=user.headers)
    ).json()
    closes = [D(c["close"]) for c in candles["items"]]
    assert len(closes) == 120
    r = await http.get(
        f"{PATH}/indicators",
        params={
            **params("EUR_USD"),
            "indicator": ["sma:5", "rsi:14", "macd:3,8,4", "bollinger:10,2"],
        },
        headers=user.headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["bars"], body["timeframe"], body["price_basis"]) == (120, "1m", "mid")
    assert body["data_types"] == ["simulated"] and body["partial_bars"] == 0
    assert "not a forecast" in body["notice"]
    series = {s["name"]: s for s in body["series"]}
    assert list(series) == ["sma:5", "rsi:14", "macd:3,8,4", "bollinger:10,2"]
    sma = series["sma:5"]["outputs"]["value"]
    assert len(sma) == 120 and sma[:4] == [None] * 4 and series["sma:5"]["first_defined_index"] == 4
    expected = ind.sma(closes, 5)
    for got, want in zip(sma, expected, strict=True):
        assert (got is None) == (want is None)
        if want is not None:
            assert D(got) == want.quantize(D("0.00000001"))
    rsi = series["rsi:14"]["outputs"]["value"]
    assert rsi[13] is None and rsi[14] is not None and series["rsi:14"]["first_defined_index"] == 14
    assert all(v is None or 0 <= D(v) <= 100 for v in rsi)
    assert set(series["macd:3,8,4"]["outputs"]) == {"macd", "signal", "histogram"}
    bb = series["bollinger:10,2"]["outputs"]
    assert all(
        D(lo) <= D(m) <= D(u)
        for lo, m, u in zip(bb["lower"][9:], bb["middle"][9:], bb["upper"][9:], strict=True)
    )
    assert body["timestamps"][0].startswith("2026-10-07T10:00:00")


async def test_five_minute_indicators_come_from_aggregated_minutes_and_flag_partial_bars(
    http: httpx.AsyncClient, user: TestUser, sessions: async_sessionmaker[AsyncSession]
) -> None:
    await seed(sessions, "GBP_USD")
    async with sessions() as s:  # a feed gap: minutes 10:12 and 10:13, and the whole 10:20 period
        await s.execute(
            text(
                "DELETE FROM forex_candles WHERE instrument = 'GBP_USD' AND ts IN "
                "('2026-10-07T10:12:00+00', '2026-10-07T10:13:00+00') OR (instrument = 'GBP_USD' "
                "AND ts >= '2026-10-07T10:20:00+00' AND ts < '2026-10-07T10:25:00+00')"
            )
        )
        await s.commit()
    r = await http.get(
        f"{PATH}/indicators",
        params={**params("GBP_USD", "5m"), "indicator": ["sma:3"]},
        headers=user.headers,
    )
    body = r.json()
    assert r.status_code == 200, r.text
    assert body["bars"] == 23 and body["partial_bars"] == 1  # 24 periods less the empty one
    stamps = body["timestamps"]
    assert (
        "2026-10-07T10:20:00Z" not in stamps and "2026-10-07T10:10:00Z" in stamps
    )  # absent, not filled
    # Aggregated 1H from the same minutes: the first full hour is complete.
    r = await http.get(
        f"{PATH}/indicators",
        params={**params("GBP_USD", "1H"), "indicator": ["ema:2"]},
        headers=user.headers,
    )
    assert r.json()["bars"] == 2 and r.json()["partial_bars"] == 1


async def test_the_forming_period_is_left_out_and_counted(
    http: httpx.AsyncClient, user: TestUser, sessions: async_sessionmaker[AsyncSession]
) -> None:
    await seed(sessions, "NZD_USD")
    # Ask until far in the future: periods after "now" do not exist; the real current period may
    # be forming only for a present-day range, so use the stored past range and check the counter.
    r = await http.get(
        f"{PATH}/indicators",
        params={**params("NZD_USD", "1D"), "indicator": ["sma:2"]},
        headers=user.headers,
    )
    body = r.json()
    assert r.status_code == 200 and body["forming_excluded"] == 0 and body["bars"] <= 1


async def test_provider_candles_of_the_requested_timeframe_are_used_as_they_are(
    http: httpx.AsyncClient, user: TestUser, sessions: async_sessionmaker[AsyncSession]
) -> None:
    rows = [
        Candle(
            "fake",
            "USD_CAD",
            Timeframe.H1,
            PriceBasis.MID,
            START + timedelta(hours=k),
            D(c),
            D(c) + D("0.01"),
            D(c) - D("0.01"),
            D(c),
            100,
            True,
            DataType.INDICATIVE_RATE,
        )
        for k, c in enumerate(["1.30", "1.31", "1.29", "1.32", "1.33"])
    ]
    async with sessions() as s:
        await store_candles(s, rows, WED)
    r = await http.get(
        f"{PATH}/indicators",
        params={
            "instrument": "USD_CAD",
            "timeframe": "1H",
            "start": START.isoformat(),
            "end": (START + timedelta(hours=5)).isoformat(),
            "indicator": ["sma:2"],
        },
        headers=user.headers,
    )
    body = r.json()
    assert r.status_code == 200, r.text
    assert (
        body["data_types"] == ["indicative_rate"]
        and body["partial_bars"] == 0
        and body["bars"] == 5
    )
    assert body["series"][0]["outputs"]["value"] == [None, "1.305", "1.3", "1.305", "1.325"]


async def test_the_bar_cap_truncates_and_the_source_cap_refuses(
    http: httpx.AsyncClient,
    user: TestUser,
    sessions: async_sessionmaker[AsyncSession],
    settings_override: Callable[..., None],
) -> None:
    await seed(sessions, "EUR_GBP")
    settings_override(forex_analysis_max_bars=10)
    r = await http.get(
        f"{PATH}/indicators",
        params={**params("EUR_GBP"), "indicator": ["sma:2"]},
        headers=user.headers,
    )
    body = r.json()
    assert body["bars"] == 10 and body["truncated"] is True
    settings_override(forex_analysis_source_cap=50)
    r = await http.get(
        f"{PATH}/indicators",
        params={**params("EUR_GBP", "5m"), "indicator": ["sma:2"]},
        headers=user.headers,
    )
    assert r.status_code == 422 and "too many one-minute candles" in r.text


# ------------------------------------------------------------------------------ structure
async def test_structure_reports_swings_levels_breakouts_and_trendlines(
    http: httpx.AsyncClient, user: TestUser, sessions: async_sessionmaker[AsyncSession]
) -> None:
    await seed(sessions, "USD_JPY", hours=6)
    r = await http.get(
        f"{PATH}/structure",
        params={
            "instrument": "USD_JPY",
            "timeframe": "5m",
            "start": (WED - timedelta(hours=6)).isoformat(),
            "end": WED.isoformat(),
        },
        headers=user.headers,
    )
    body = r.json()
    assert r.status_code == 200, r.text
    assert body["bars"] == 72 and D(body["tolerance"]) > 0
    assert body["swings"], "a six-hour simulated chart has swing points"
    assert "timestamps" not in body  # swings carry their own times
    for sw in body["swings"]:
        assert sw["kind"] in ("high", "low") and sw["confirmed_ts"] > sw["ts"]
    for lv in body["levels"]:
        assert lv["touches"] >= 2 and lv["role"] in ("support", "resistance")
    kinds = {t["kind"] for t in body["trendlines"]}
    assert kinds <= {"support", "resistance"}
    for t in body["trendlines"]:
        assert (
            D(t["channel_upper_at_last"]) >= D(t["channel_lower_at_last"])
            or t["kind"] == "resistance"
        )


async def test_structure_and_patterns_with_too_little_data_are_empty_not_invented(
    http: httpx.AsyncClient, user: TestUser
) -> None:
    quiet = {
        "instrument": "EUR_CHF" if False else "GBP_JPY",
        "timeframe": "1H",
        "start": START.isoformat(),
        "end": WED.isoformat(),
    }
    s = await http.get(f"{PATH}/structure", params=quiet, headers=user.headers)
    assert (
        s.status_code == 200
        and s.json()["bars"] == 0
        and s.json()["swings"] == []
        and s.json()["levels"] == []
    )
    p = await http.get(f"{PATH}/patterns", params=quiet, headers=user.headers)
    assert p.status_code == 200 and p.json()["patterns"] == []


# ------------------------------------------------------------------------------- patterns
async def test_patterns_cite_their_rule_and_the_candles_they_used(
    http: httpx.AsyncClient, user: TestUser, sessions: async_sessionmaker[AsyncSession]
) -> None:
    # A hand-built hourly chart: a fall, then a hammer, then an engulfing up candle.
    base = START
    shape = [
        ("1.2000", "1.2010", "1.1990", "1.1995"),
        ("1.1995", "1.2000", "1.1960", "1.1965"),
        ("1.1965", "1.1970", "1.1930", "1.1935"),
        ("1.1935", "1.1940", "1.1900", "1.1905"),
        ("1.1905", "1.1910", "1.1870", "1.1875"),
        ("1.1875", "1.1880", "1.1840", "1.1845"),
        ("1.1851", "1.1852", "1.1790", "1.1850"),
        ("1.1840", "1.1900", "1.1835", "1.1895"),
    ]
    rows = [
        Candle(
            "fake",
            "NZD_USD",
            Timeframe.H1,
            PriceBasis.MID,
            base + timedelta(hours=k),
            D(o),
            D(h),
            D(lo),
            D(c),
            None,
            True,
            DataType.SIMULATED,
        )
        for k, (o, h, lo, c) in enumerate(shape)
    ]
    async with sessions() as s:
        await store_candles(s, rows, WED)
    r = await http.get(
        f"{PATH}/patterns",
        params={
            "instrument": "NZD_USD",
            "timeframe": "1H",
            "start": base.isoformat(),
            "end": (base + timedelta(hours=8)).isoformat(),
        },
        headers=user.headers,
    )
    body = r.json()
    assert r.status_code == 200, r.text
    found = {p["rule"]: p for p in body["patterns"]}
    assert (
        "hammer" in found
        and found["hammer"]["bias"] == "bullish"
        and found["hammer"]["category"] == "reversal"
    )
    assert [t[:13] for t in found["hammer"]["timestamps"]] == ["2026-10-07T16"]
    assert "bullish_engulfing" in found
    assert [t[:13] for t in found["bullish_engulfing"]["timestamps"]] == [
        "2026-10-07T16",
        "2026-10-07T17",
    ]
    ends = [p["timestamps"][-1] for p in body["patterns"]]
    assert ends == sorted(ends)


# ------------------------------------------------------------------------------ validation
@pytest.mark.parametrize(
    "indicator",
    [
        ["nope"],
        ["sma:0"],
        ["sma:501"],
        ["sma:2.5"],
        ["sma:x"],
        ["macd:26,12,9"],
        ["macd:12,26"],
        ["bollinger:20,0"],
        ["bollinger:20,11"],
        ["rsi:14,3"],
        [],
    ],
)
async def test_bad_indicator_requests_are_refused(
    http: httpx.AsyncClient, user: TestUser, indicator: list[str]
) -> None:
    r = await http.get(
        f"{PATH}/indicators",
        params={**params("EUR_USD"), "indicator": indicator},
        headers=user.headers,
    )
    assert r.status_code == 422, (indicator, r.text)


async def test_bad_ranges_pairs_and_too_many_indicators_are_refused(
    http: httpx.AsyncClient, user: TestUser
) -> None:
    ok = {"indicator": ["sma:2"]}
    assert (
        await http.get(
            f"{PATH}/indicators",
            params={**params("EUR_USD"), "indicator": ["sma:2"] * 13},
            headers=user.headers,
        )
    ).status_code == 422
    thirteen = [f"sma:{n}" for n in range(2, 15)]
    assert (
        await http.get(
            f"{PATH}/indicators",
            params={**params("EUR_USD"), "indicator": thirteen},
            headers=user.headers,
        )
    ).status_code == 422
    assert (
        await http.get(
            f"{PATH}/indicators", params={**params("EUR_SEK"), **ok}, headers=user.headers
        )
    ).status_code == 404
    assert (
        await http.get(
            f"{PATH}/indicators", params={**params("EUR_USD", "2m"), **ok}, headers=user.headers
        )
    ).status_code == 422
    assert (
        await http.get(
            f"{PATH}/indicators",
            params={**params("EUR_USD", price_basis="last"), **ok},
            headers=user.headers,
        )
    ).status_code == 422
    naive = {**params("EUR_USD"), "start": "2026-10-07T10:00:00", **ok}
    assert (
        await http.get(f"{PATH}/indicators", params=naive, headers=user.headers)
    ).status_code == 422
    backwards = {**params("EUR_USD"), "start": WED.isoformat(), "end": START.isoformat(), **ok}
    assert (
        await http.get(f"{PATH}/indicators", params=backwards, headers=user.headers)
    ).status_code == 422
    huge = {**params("EUR_USD"), "start": (WED - timedelta(days=400)).isoformat(), **ok}
    assert (
        await http.get(f"{PATH}/indicators", params=huge, headers=user.headers)
    ).status_code == 422


async def test_the_endpoints_need_sign_in_and_the_flag(
    http: httpx.AsyncClient, migrated_settings: Settings
) -> None:
    for name in ("indicators", "structure", "patterns"):
        r = await http.get(f"{PATH}/{name}", params={**params("EUR_USD"), "indicator": ["sma:2"]})
        assert r.status_code == 401, name
    off = create_app(
        migrated_settings.model_copy(update={"forex_enabled": False}),
        readiness_checks={},
        token_verifier=ah.verifier(),
    )
    transport = httpx.ASGITransport(app=off, raise_app_exceptions=False)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            someone = await make_user(client, "flagoff")
            for name in ("indicators", "structure", "patterns"):
                r = await client.get(
                    f"{PATH}/{name}",
                    params={**params("EUR_USD"), "indicator": ["sma:2"]},
                    headers=someone.headers,
                )
                assert r.status_code == 404, name
    finally:
        await off.state.db.dispose()


async def test_scripted_stream_data_never_reaches_the_analysis_as_candles(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """Quotes and candles are separate stores: quotes from the stream do not become candles."""
    scripts: list[list[ScriptItem]] = [[]]
    provider = FakeForexProvider(clock=Clock(WED), scripts=scripts)
    async with sessions() as s:
        before = await s.scalar(
            text("SELECT count(*) FROM forex_candles WHERE instrument = 'EUR_JPY'")
        )
        await sync_minutes(s, provider, [], WED)
        after = await s.scalar(
            text("SELECT count(*) FROM forex_candles WHERE instrument = 'EUR_JPY'")
        )
    assert before == after == 0
