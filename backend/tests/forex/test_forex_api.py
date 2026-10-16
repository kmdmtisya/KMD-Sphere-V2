"""Forex market data on the real database (P13-T02.2 to T02.5, T02.7): the registry and the
configurable universe, monthly partitions, stored quotes with a database-derived mid, the quote
board (fresh, stale, unavailable, never invented), candles with gaps left absent, the feature
flag, the feed (storage, fan-out, backfill) and the authenticated WebSocket with its limits."""

import asyncio
import time
from collections.abc import AsyncIterator, Callable, Iterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.main import create_app
from app.modules.forex.instruments.registry import load_registry, sync
from app.modules.forex.marketdata.fake import FakeForexProvider, Silence
from app.modules.forex.marketdata.feed import ForexFeed, prepare
from app.modules.forex.marketdata.gateway import QuoteHub
from app.modules.forex.marketdata.models import ForexQuote
from app.modules.forex.marketdata.monitor import FeedMonitor, HeartbeatPolicy
from app.modules.forex.marketdata.partitions import ensure_months, partition_name
from app.modules.forex.marketdata.repository import store_candles, store_quotes
from app.modules.forex.marketdata.stream import StreamClient
from app.modules.forex.marketdata.types import (
    Candle,
    DataType,
    FeedStatus,
    Heartbeat,
    PriceBasis,
    Quality,
    Quote,
    ReceivedQuote,
    Timeframe,
)
from app.modules.identity.models import User
from tests import auth_helpers as ah
from tests.authz_harness import TestUser, make_user
from tests.db_fixtures import migrated_settings  # noqa: F401
from tests.forex.test_stream_client import FakeWaiter
from tests.forex.ws import AsgiWebSocket

pytestmark = [pytest.mark.integration, pytest.mark.security]
D = Decimal


def now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


@pytest.fixture(scope="module")
async def app(migrated_settings: Settings) -> AsyncIterator[FastAPI]:  # noqa: F811
    settings = migrated_settings.model_copy(update={"forex_enabled": True})
    application = create_app(settings, readiness_checks={}, token_verifier=ah.verifier())
    application.state.forex_stream_heartbeat_seconds = 0.05
    await prepare(application.state.db.session_factory, settings, now())
    yield application
    await application.state.db.dispose()


@pytest.fixture
def sessions(app: FastAPI) -> async_sessionmaker[AsyncSession]:
    factory: async_sessionmaker[AsyncSession] = app.state.db.session_factory
    return factory


@pytest.fixture
async def http(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
async def user(http: httpx.AsyncClient) -> TestUser:
    return await make_user(http, "trader")


@pytest.fixture
def settings_override(app: FastAPI) -> Iterator[Callable[..., None]]:
    original = app.state.settings

    def apply(**changes: Any) -> None:
        app.state.settings = original.model_copy(update=changes)

    yield apply
    app.state.settings = original


def received(
    pair: str,
    at: datetime,
    bid: str = "1.27001",
    ask: str = "1.27013",
    quality: Quality = Quality.OK,
    data_type: DataType = DataType.SIMULATED,
) -> ReceivedQuote:
    quote = Quote("fake", pair, D(bid), D(ask), at, data_type)
    return ReceivedQuote(quote, at + timedelta(milliseconds=200), quality, FeedStatus.CONNECTED)


# ----------------------------------------------------------------- registry (T02.2)
async def test_the_registry_is_stored_and_listed(
    http: httpx.AsyncClient, user: TestUser, sessions: async_sessionmaker[AsyncSession]
) -> None:
    response = await http.get("/api/v1/forex/instruments", headers=user.headers)
    assert response.status_code == 200, response.text
    body = response.json()
    codes = [i["code"] for i in body["items"]]
    assert codes == sorted(load_registry().by_code)
    kes = next(i for i in body["items"] if i["code"] == "USD_KES")
    assert kes == {
        "code": "USD_KES",
        "base": "USD",
        "quote": "KES",
        "pip_location": -2,
        "display_precision": 3,
        "liquidity_tier": "exotic",
        "default_data_type": "indicative_rate",
        "spec_version": 1,
    }
    assert "not a broker" in body["notice"]
    async with sessions() as s:
        again = await sync(s, load_registry(), [])
    assert (again.added, again.changed, again.active) == (0, 0, len(codes))


async def test_the_universe_is_configuration_and_dropped_pairs_are_deactivated(
    http: httpx.AsyncClient, user: TestUser, sessions: async_sessionmaker[AsyncSession]
) -> None:
    async with sessions() as s:
        await sync(s, load_registry(), ["EUR_USD", "USD_KES"])
    try:
        body = (await http.get("/api/v1/forex/instruments", headers=user.headers)).json()
        assert [i["code"] for i in body["items"]] == ["EUR_USD", "USD_KES"]
        r = await http.get("/api/v1/forex/quotes?instrument=GBP_USD", headers=user.headers)
        assert r.status_code == 422  # inactive
    finally:
        async with sessions() as s:
            await sync(s, load_registry(), [])


# ---------------------------------------------------------------- storage (T02.3)
async def test_a_stored_quote_carries_every_field_and_the_database_derives_the_mid(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    at = now() - timedelta(hours=3)
    quote = received("EUR_CHF" if False else "USD_CHF", at, "0.88001", "0.88014")
    async with sessions() as s:
        assert await store_quotes(s, [quote]) == 1
        assert await store_quotes(s, [quote]) == 0  # (provider, pair, time) is unique
        row = (
            await s.execute(
                select(ForexQuote).where(
                    ForexQuote.instrument == "USD_CHF", ForexQuote.ts_provider == at
                )
            )
        ).scalar_one()
    assert row.mid == D("0.880075")  # (bid + ask) / 2, computed by PostgreSQL
    assert (row.provider, row.bid, row.ask) == ("fake", D("0.88001"), D("0.88014"))
    assert row.ts_provider == at and row.ts_received == at + timedelta(milliseconds=200)
    assert (row.data_type, row.quality, row.feed_status) == ("simulated", "ok", "connected")


async def test_the_mid_cannot_be_written_and_invalid_values_are_refused(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    from sqlalchemy.exc import DBAPIError

    async with sessions() as s:
        for sql in (
            "INSERT INTO forex_quotes (provider, instrument, ts_provider, ts_received, bid, ask, "
            "mid, data_type, quality, feed_status) VALUES ('fake', 'EUR_USD', now(), now(), 1, 2, "
            "9, 'simulated', 'ok', 'connected')",
            "INSERT INTO forex_quotes (provider, instrument, ts_provider, ts_received, bid, ask, "
            "data_type, quality, feed_status) VALUES ('fake', 'EUR_USD', now(), now(), 1, 2, "
            "'live', 'ok', 'connected')",
            "INSERT INTO forex_quotes (provider, instrument, ts_provider, ts_received, bid, ask, "
            "data_type, quality, feed_status) VALUES ('fake', 'XXX_YYY', now(), now(), 1, 2, "
            "'simulated', 'ok', 'connected')",
        ):
            with pytest.raises(DBAPIError):
                await s.execute(text(sql))
            await s.rollback()


async def test_monthly_partitions_are_made_ahead_and_rows_move_out_of_default(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    month = date(2031, 3, 1)
    at = datetime(2031, 3, 15, 12, tzinfo=UTC)
    async with sessions() as s:
        await store_quotes(s, [received("NZD_USD", at, "0.60001", "0.60013")])
        assert (
            await s.scalar(
                text("SELECT count(*) FROM forex_quotes_default WHERE ts_provider = :t"), {"t": at}
            )
        ) == 1
        created = await ensure_months(s, "forex_quotes", month, 2)
        assert created == ["forex_quotes_p203103", "forex_quotes_p203104"]
        assert await ensure_months(s, "forex_quotes", month, 2) == []  # idempotent
        where = (
            await s.execute(
                text(
                    "SELECT tableoid::regclass::text, mid FROM forex_quotes WHERE ts_provider = :t"
                ),
                {"t": at},
            )
        ).one()
    assert where[0] == partition_name("forex_quotes", month)
    assert where[1] == D("0.60007")  # moved unchanged, mid recomputed identically


async def test_the_preparation_made_partitions_for_this_month_and_the_next_two(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    today = now().date().replace(day=1)
    async with sessions() as s:
        names = set(
            (
                await s.execute(
                    text(
                        "SELECT c.relname FROM pg_inherits i JOIN pg_class c ON c.oid = i.inhrelid "
                        "JOIN pg_class p ON p.oid = i.inhparent WHERE p.relname = 'forex_candles'"
                    )
                )
            ).scalars()
        )
    from app.modules.forex.marketdata.partitions import add_months

    expected = {partition_name("forex_candles", add_months(today, i)) for i in range(3)}
    assert expected | {"forex_candles_default"} <= names


# ---------------------------------------------------------- quote board (T02.5)
async def test_the_quote_board_shows_fresh_stale_and_unavailable_and_invents_nothing(
    http: httpx.AsyncClient, user: TestUser, sessions: async_sessionmaker[AsyncSession]
) -> None:
    t = now()
    async with sessions() as s:
        await store_quotes(
            s,
            [
                received("GBP_USD", t - timedelta(seconds=5)),
                received("USD_JPY", t - timedelta(minutes=10), "149.501", "149.513"),
                # Only a suspect quote for AUD_USD: it is never served.
                received(
                    "AUD_USD", t - timedelta(seconds=2), "0.66100", "0.66000", Quality.SUSPECT
                ),
                # An older good USD_CAD quote and a newer suspect one: the good one is served.
                received("USD_CAD", t - timedelta(seconds=20), "1.36001", "1.36013"),
                received("USD_CAD", t - timedelta(seconds=1), "1.99", "1.98", Quality.SUSPECT),
            ],
        )
    pairs = ["GBP_USD", "USD_JPY", "AUD_USD", "USD_CAD", "EUR_JPY"]
    response = await http.get(
        "/api/v1/forex/quotes", params=[("instrument", p) for p in pairs], headers=user.headers
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["provider"] == "fake"
    assert body["feed_status"] == "disconnected"  # no feed runs in this process
    items = {i["instrument"]: i for i in body["items"]}
    assert [i["instrument"] for i in body["items"]] == pairs

    gbp = items["GBP_USD"]
    assert (gbp["freshness"], gbp["quality"], gbp["data_type"]) == ("fresh", "ok", "simulated")
    assert (gbp["bid"], gbp["ask"], gbp["mid"], gbp["mid_derived"]) == (
        "1.27001",
        "1.27013",
        "1.27007",
        True,
    )
    assert 5 <= gbp["age_seconds"] <= 30

    jpy = items["USD_JPY"]
    assert (jpy["freshness"], jpy["quality"]) == ("stale", "stale")
    assert jpy["age_seconds"] >= 600 and jpy["bid"] == "149.501"  # true age, not "now"

    for pair in ("AUD_USD", "EUR_JPY"):
        gone = items[pair]
        assert gone["freshness"] == "unavailable"
        assert all(
            gone[k] is None
            for k in ("bid", "ask", "mid", "ts_provider", "age_seconds", "data_type")
        )
    assert items["USD_CAD"]["bid"] == "1.36001"


async def test_quotes_older_than_the_lookback_are_unavailable(
    http: httpx.AsyncClient, user: TestUser, sessions: async_sessionmaker[AsyncSession]
) -> None:
    async with sessions() as s:
        await store_quotes(
            s, [received("GBP_JPY", now() - timedelta(days=8), "190.001", "190.021")]
        )
    r = await http.get("/api/v1/forex/quotes?instrument=GBP_JPY", headers=user.headers)
    assert r.json()["items"][0]["freshness"] == "unavailable"


async def test_bad_quote_requests_are_refused(http: httpx.AsyncClient, user: TestUser) -> None:
    for query in ("instrument=eur_usd", "instrument=EUR_XYZ", "instrument=EURUSD"):
        r = await http.get(f"/api/v1/forex/quotes?{query}", headers=user.headers)
        assert r.status_code == 422, query


async def test_all_active_pairs_are_listed_when_none_are_named(
    http: httpx.AsyncClient, user: TestUser
) -> None:
    body = (await http.get("/api/v1/forex/quotes", headers=user.headers)).json()
    assert len(body["items"]) == len(load_registry().specs)


# ------------------------------------------------------------------- candles
def candle(pair: str, at: datetime, close: str, complete: bool = True) -> Candle:
    return Candle(
        "fake",
        pair,
        Timeframe.M1,
        PriceBasis.MID,
        at,
        D(close),
        D(close) + D("0.0002"),
        D(close) - D("0.0002"),
        D(close),
        3,
        complete=complete,
        data_type=DataType.SIMULATED,
    )


async def test_candles_are_served_with_gaps_left_absent_and_forming_ones_not_stored(
    http: httpx.AsyncClient,
    user: TestUser,
    sessions: async_sessionmaker[AsyncSession],
    settings_override: Any,
) -> None:
    t0 = now().replace(second=0) - timedelta(hours=2)
    rows = [
        candle("EUR_GBP", t0, "0.85500"),
        candle("EUR_GBP", t0 + timedelta(minutes=1), "0.85510"),
        candle("EUR_GBP", t0 + timedelta(minutes=3), "0.85520"),  # minute 2 is missing
        candle("EUR_GBP", t0 + timedelta(minutes=4), "0.85530", complete=False),
    ]
    async with sessions() as s:
        assert await store_candles(s, rows, now()) == 3
        assert await store_candles(s, rows, now()) == 0
    params = {
        "instrument": "EUR_GBP",
        "start": t0.isoformat(),
        "end": (t0 + timedelta(minutes=10)).isoformat(),
    }
    r = await http.get("/api/v1/forex/candles", params=params, headers=user.headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert [c["close"] for c in body["items"]] == ["0.855", "0.8551", "0.8552"]
    stamps = [datetime.fromisoformat(c["ts"]) for c in body["items"]]
    assert stamps == [t0, t0 + timedelta(minutes=1), t0 + timedelta(minutes=3)]
    assert body["truncated"] is False and "never filled" in body["notice"]
    assert {c["data_type"] for c in body["items"]} == {"simulated"}

    settings_override(forex_candles_max=2)
    r = await http.get("/api/v1/forex/candles", params=params, headers=user.headers)
    assert len(r.json()["items"]) == 2 and r.json()["truncated"] is True


async def test_larger_candles_are_built_from_stored_minutes_when_the_provider_published_none(
    http: httpx.AsyncClient,
    user: TestUser,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    # A Tuesday in the past: the whole hour is inside the trading week and every period is closed.
    t0 = datetime(2026, 10, 13, 10, 0, tzinfo=UTC)
    rows = [candle("EUR_GBP", t0 + timedelta(minutes=m), f"0.85{500 + m:03d}") for m in range(60)]
    async with sessions() as s:
        await store_candles(s, rows, now())
    params = {
        "instrument": "EUR_GBP",
        "timeframe": "15m",
        "start": t0.isoformat(),
        "end": (t0 + timedelta(hours=1)).isoformat(),
    }
    r = await http.get("/api/v1/forex/candles", params=params, headers=user.headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["timeframe"] == "15m"
    stamps = [datetime.fromisoformat(c["ts"]) for c in body["items"]]
    assert stamps == [t0 + timedelta(minutes=15 * i) for i in range(4)]
    first = body["items"][0]
    # Built from minutes 0-14: open of the first, close of the last, extremes of all.
    assert D(first["open"]) == D("0.85500") and D(first["close"]) == D("0.85514")
    assert D(first["high"]) == D("0.85514") + D("0.0002")
    assert D(first["low"]) == D("0.85500") - D("0.0002")
    assert {c["data_type"] for c in body["items"]} == {"simulated"}


async def test_bad_candle_requests_are_refused(http: httpx.AsyncClient, user: TestUser) -> None:
    t = now()
    cases = [
        ({"start": "2026-10-14T10:00:00", "end": "2026-10-14T11:00:00"}, 422),  # naive
        ({"start": t.isoformat(), "end": t.isoformat()}, 422),
        ({"start": (t - timedelta(days=400)).isoformat(), "end": t.isoformat()}, 422),
        (
            {
                "start": (t - timedelta(hours=1)).isoformat(),
                "end": t.isoformat(),
                "timeframe": "2m",
            },
            422,
        ),
    ]
    for extra, status in cases:
        r = await http.get(
            "/api/v1/forex/candles", params={"instrument": "EUR_USD", **extra}, headers=user.headers
        )
        assert r.status_code == status, (extra, r.text)
    r = await http.get(
        "/api/v1/forex/candles",
        params={
            "instrument": "EUR_SEK",
            "start": (t - timedelta(hours=1)).isoformat(),
            "end": t.isoformat(),
        },
        headers=user.headers,
    )
    assert r.status_code == 404


# ------------------------------------------------------------------- feature flag
async def test_with_the_flag_off_every_route_is_404_after_authentication(
    migrated_settings: Settings,  # noqa: F811
) -> None:
    off = create_app(
        migrated_settings.model_copy(update={"forex_enabled": False}),
        readiness_checks={},
        token_verifier=ah.verifier(),
    )
    transport = httpx.ASGITransport(app=off, raise_app_exceptions=False)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            someone = await make_user(client, "flag")
            for path in ("/api/v1/forex/instruments", "/api/v1/forex/quotes"):
                assert (await client.get(path)).status_code == 401
                assert (await client.get(path, headers=someone.headers)).status_code == 404
            async with AsgiWebSocket(off) as ws:
                await ws.send({"type": "auth", "token": someone.token})
                assert await ws.closed_with() == 4404
    finally:
        await off.state.db.dispose()


# ------------------------------------------------------------- feed (T02.4, T02.5)
async def test_the_feed_stores_publishes_and_reports_status(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    from tests.forex.test_marketdata_core import Clock

    start = now() - timedelta(minutes=30)
    clock = Clock(start)
    q1 = Quote("fake", "EUR_USD", D("1.08501"), D("1.08513"), start, DataType.SIMULATED)
    q2 = Quote(
        "fake", "EUR_USD", D("1.09"), D("1.08"), start + timedelta(seconds=1), DataType.SIMULATED
    )
    provider = FakeForexProvider(clock=clock, scripts=[[Heartbeat("fake", start), q1, q2]])
    hub = QuoteHub()
    feed = ForexFeed(sessions, hub, provider, clock)
    client = StreamClient(
        provider,
        ["EUR_USD"],
        feed,
        FeedMonitor(HeartbeatPolicy(), clock),
        clock=clock,
        waiter=FakeWaiter(clock),
    )
    await client.run(connections=1)
    assert feed.stored == 2 and feed.failures == 0  # the suspect one is kept for the record
    assert hub.last_good["EUR_USD"].quote == q1  # but never published as the latest
    assert hub.feed_status["fake"] is FeedStatus.DISCONNECTED  # the script ended
    async with sessions() as s:
        qualities = (
            (
                await s.execute(
                    select(ForexQuote.quality)
                    .where(ForexQuote.instrument == "EUR_USD", ForexQuote.ts_provider >= start)
                    .order_by(ForexQuote.ts_provider)
                )
            )
            .scalars()
            .all()
        )
    assert qualities == ["ok", "suspect"]


async def test_a_gap_is_backfilled_from_the_provider_and_an_outage_is_survived(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    from tests.forex.test_marketdata_core import Clock

    wednesday = datetime(2026, 10, 14, 9, 0, tzinfo=UTC)
    clock = Clock(wednesday + timedelta(hours=1))
    provider = FakeForexProvider(clock=clock)
    feed = ForexFeed(sessions, QuoteHub(), provider, clock)
    await feed.on_gap("fake", "AUD_USD", wednesday, wednesday + timedelta(minutes=10))
    assert feed.backfilled == 10
    provider.down = True
    await feed.on_gap("fake", "AUD_USD", wednesday, wednesday + timedelta(minutes=20))
    assert feed.failures == 1 and feed.backfilled == 10  # nothing invented for the outage


# -------------------------------------------------------------------- WebSocket
async def test_the_stream_authenticates_subscribes_and_fans_out(
    app: FastAPI, user: TestUser, sessions: async_sessionmaker[AsyncSession]
) -> None:
    hub: QuoteHub = app.state.forex_hub
    t = now()
    async with sessions() as s:
        await store_quotes(s, [received("NZD_USD", t - timedelta(seconds=3), "0.60001", "0.60013")])
    async with AsgiWebSocket(app) as ws:
        await ws.send({"type": "auth", "token": user.token})
        ready = await ws.receive()
        assert ready["type"] == "ready" and ready["max_instruments"] == 20
        assert "places no trades" in ready["notice"]
        await ws.send({"type": "subscribe", "instruments": ["NZD_USD", "EUR_JPY"]})
        subscribed = await ws.receive_type("subscribed")
        assert subscribed["instruments"] == ["EUR_JPY", "NZD_USD"]
        snapshot = {q["instrument"]: q for q in subscribed["snapshot"]}
        assert (
            snapshot["NZD_USD"]["bid"] == "0.60001" and snapshot["NZD_USD"]["freshness"] == "fresh"
        )
        assert (
            snapshot["EUR_JPY"]["freshness"] == "unavailable" and snapshot["EUR_JPY"]["bid"] is None
        )

        hub.publish(received("EUR_JPY", t, "162.001", "162.025", Quality.SUSPECT))
        hub.publish(received("GBP_USD", t))  # not subscribed
        hub.publish(received("EUR_JPY", t, "162.001", "162.025"))
        quote = await ws.receive_type("quote")
        assert (quote["instrument"], quote["bid"], quote["data_type"]) == (
            "EUR_JPY",
            "162.001",
            "simulated",
        )
        assert quote["mid"] == "162.013" and quote["freshness"] == "fresh"

        hub.publish_status("fake", FeedStatus.DEGRADED)
        status = await ws.receive_type("status")
        assert status == {"type": "status", "provider": "fake", "feed_status": "degraded"}
        assert (await ws.receive())["type"] == "heartbeat"

        await ws.send({"type": "unsubscribe", "instruments": ["EUR_JPY"]})
        assert (await ws.receive_type("unsubscribed"))["instruments"] == ["NZD_USD"]
        await ws.send({"type": "ping"})
        assert (await ws.receive_type("pong"))["type"] == "pong"
    assert hub.connections == 0  # the socket's subscription is released


@pytest.mark.parametrize(
    "first",
    [
        {"type": "auth", "token": "not-a-jwt"},
        {"type": "auth", "token": ""},
        {"type": "subscribe", "instruments": ["EUR_USD"]},
        {"type": "auth"},
    ],
)
async def test_the_stream_closes_without_valid_authentication(
    app: FastAPI, first: dict[str, Any]
) -> None:
    async with AsgiWebSocket(app) as ws:
        await ws.send(first)
        assert await ws.closed_with() == 4401


async def test_expired_wrong_key_and_disabled_accounts_are_refused(
    app: FastAPI, http: httpx.AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    t = int(time.time())
    for token in (
        ah.token("late", exp=t - 3600, iat=t - 3900, nbf=t - 3900),
        ah.token("forger", key=ah.other_private_key()),
    ):
        async with AsgiWebSocket(app) as ws:
            await ws.send({"type": "auth", "token": token})
            assert await ws.closed_with() == 4401
    banned = await make_user(http, "banned")
    async with sessions() as s:
        await s.execute(
            update(User).where(User.subject == banned.subject).values(status="disabled")
        )
        await s.commit()
    async with AsgiWebSocket(app) as ws:
        await ws.send({"type": "auth", "token": banned.token})
        assert await ws.closed_with() == 4401


async def test_authentication_must_come_in_time(app: FastAPI, settings_override: Any) -> None:
    settings_override(forex_stream_auth_timeout_seconds=0.05)
    async with AsgiWebSocket(app) as ws:
        assert await ws.closed_with() == 4401


async def test_the_socket_closes_when_the_token_expires(
    app: FastAPI, http: httpx.AsyncClient
) -> None:
    subject = "short-lived"
    token = ah.token(subject, exp=int(time.time()) + 1)
    assert (await http.get("/api/v1/me", headers=ah.bearer(token))).status_code == 200
    async with AsgiWebSocket(app) as ws:
        await ws.send({"type": "auth", "token": token})
        assert (await ws.receive())["type"] == "ready"
        assert await ws.closed_with(seconds=5) == 4401


async def test_per_user_limits_on_connections_pairs_and_messages(
    app: FastAPI, user: TestUser, settings_override: Any
) -> None:
    sockets = [AsgiWebSocket(app) for _ in range(3)]
    for ws in sockets:
        await ws.__aenter__()
        await ws.send({"type": "auth", "token": user.token})
        assert (await ws.receive())["type"] == "ready"
    try:
        async with AsgiWebSocket(app) as fourth:
            await fourth.send({"type": "auth", "token": user.token})
            assert await fourth.closed_with() == 4429
    finally:
        for ws in sockets:
            await ws.__aexit__(None, None, None)

    async with AsgiWebSocket(app) as ws:
        await ws.send({"type": "auth", "token": user.token})
        await ws.receive_type("ready")
        too_many = sorted(load_registry().by_code)  # 12 known pairs
        app.state.forex_hub.max_instruments = 5
        try:
            await ws.send({"type": "subscribe", "instruments": too_many})
            assert (await ws.receive_type("error"))["code"] == "too_many_instruments"
        finally:
            app.state.forex_hub.max_instruments = 20
        await ws.send({"type": "subscribe", "instruments": ["EUR_SEK"]})
        assert (await ws.receive_type("error"))["code"] == "unknown_instrument"
        await ws.send({"type": "subscribe", "instruments": ["eur_usd"]})
        assert (await ws.receive_type("error"))["code"] == "invalid_instruments"
        await ws.send({"type": "subscribe", "instruments": "EUR_USD"})
        assert (await ws.receive_type("error"))["code"] == "invalid_instruments"
        await ws.send({"type": "order", "instrument": "EUR_USD"})
        assert (await ws.receive_type("error"))["code"] == "unknown_message"

    settings_override(forex_stream_messages_per_minute=3)
    async with AsgiWebSocket(app) as ws:
        await ws.send({"type": "auth", "token": user.token})
        await ws.receive_type("ready")
        for _ in range(4):
            await ws.send({"type": "ping"})
        assert await ws.closed_with() == 4429


async def test_oversized_and_malformed_messages_close_the_socket(
    app: FastAPI, user: TestUser
) -> None:
    async with AsgiWebSocket(app) as ws:
        await ws.send("x" * 5000)
        assert await ws.closed_with() == 1009
    async with AsgiWebSocket(app) as ws:
        await ws.send("not json")
        assert await ws.closed_with() == 1008
    async with AsgiWebSocket(app) as ws:
        await ws.send({"type": "auth", "token": user.token})
        await ws.receive_type("ready")
        await ws.send("[1, 2]")
        assert await ws.closed_with() == 1008


async def test_a_silent_simulated_feed_is_unknown_not_invented(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """A connection that goes quiet before its first message is never reported connected."""
    from tests.forex.test_marketdata_core import Clock

    clock = Clock(now())
    hub = QuoteHub()
    provider = FakeForexProvider(clock=clock, scripts=[[Silence()]])
    client = StreamClient(
        provider,
        ["EUR_USD"],
        ForexFeed(sessions, hub, provider, clock),
        FeedMonitor(HeartbeatPolicy(), clock),
        clock=clock,
        waiter=FakeWaiter(clock),
    )
    await asyncio.wait_for(client.run(connections=1), 5)
    assert hub.last_good == {} and hub.feed_status == {"fake": FeedStatus.DISCONNECTED}


async def test_the_app_starts_and_stops_the_simulated_feed_when_asked(
    migrated_settings: Settings,  # noqa: F811
) -> None:
    """With both flags on, the lifespan starts the feed (it connects on any day: while the
    simulated market is closed it still sends heartbeats) and stops it with the app."""
    settings = migrated_settings.model_copy(
        update={"forex_enabled": True, "forex_feed_enabled": True, "forex_universe": ["EUR_USD"]}
    )
    live = create_app(settings, readiness_checks={}, token_verifier=ah.verifier())
    hub: QuoteHub = live.state.forex_hub
    try:
        async with live.router.lifespan_context(live):
            for _ in range(100):
                if hub.feed_status.get("fake") is FeedStatus.CONNECTED:
                    break
                await asyncio.sleep(0.05)
            assert hub.feed_status["fake"] is FeedStatus.CONNECTED
        stopped = dict(hub.feed_status)  # read after the app stopped
        assert stopped["fake"] is FeedStatus.DISCONNECTED
    finally:
        await live.state.db.dispose()


async def test_run_feed_stores_and_publishes_simulated_quotes(
    app: FastAPI, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """The feed as the app runs it, on a clock pinned to a Wednesday (market open) that moves
    with real time."""
    from app.modules.forex.marketdata.feed import run_feed

    started = time.monotonic()
    wednesday = datetime(2026, 10, 14, 9, 30, tzinfo=UTC)

    def clock() -> datetime:
        return wednesday + timedelta(seconds=time.monotonic() - started)

    settings = app.state.settings.model_copy(update={"forex_universe": ["USD_ZAR"]})
    hub, stop = QuoteHub(), asyncio.Event()
    task = asyncio.create_task(run_feed(settings, sessions, hub, stop, clock=clock))
    try:
        for _ in range(100):
            if "USD_ZAR" in hub.last_good:
                break
            await asyncio.sleep(0.05)
        latest = hub.last_good["USD_ZAR"]
    finally:
        stop.set()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        async with sessions() as s:
            await sync(s, load_registry(), [])  # run_feed narrowed the universe
    assert latest.quote.data_type is DataType.SIMULATED
    async with sessions() as s:
        stored = await s.scalar(
            select(ForexQuote.data_type).where(
                ForexQuote.instrument == "USD_ZAR",
                ForexQuote.ts_provider == latest.quote.ts_provider,
            )
        )
    assert stored == "simulated"
