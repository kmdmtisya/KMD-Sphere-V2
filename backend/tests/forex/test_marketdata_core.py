"""The forex market-data core without a database (P13-T02.1, T02.2, T02.5, T02.6): validated
values with a derived mid, quality and freshness rules, the feed monitor on an injected clock,
the instrument registry, the simulated provider and the reused retry policy."""

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from app.modules.forex.instruments.registry import InstrumentSpec, load_registry
from app.modules.forex.marketdata.fake import (
    REFERENCE,
    FakeForexProvider,
    last_open_second,
    market_open,
)
from app.modules.forex.marketdata.monitor import FeedMonitor, HeartbeatPolicy, status_for
from app.modules.forex.marketdata.provider import ForexProvider, ResilientForexProvider
from app.modules.forex.marketdata.quality import (
    Freshness,
    QualityPolicy,
    age,
    assess,
    freshness,
)
from app.modules.forex.marketdata.stream import Backoff
from app.modules.forex.marketdata.types import (
    Candle,
    DataType,
    FeedStatus,
    PriceBasis,
    Quality,
    Quote,
    Timeframe,
)
from app.modules.market_data.providers.errors import (
    ProviderDataError,
    ProviderUnavailable,
    SymbolNotFound,
    UnsupportedKind,
)
from app.modules.market_data.providers.resilience import RetryPolicy

D = Decimal
T0 = datetime(2026, 10, 14, 10, 0, tzinfo=UTC)  # a Wednesday


class Clock:
    def __init__(self, at: datetime = T0) -> None:
        self.now = at

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


def q(bid: str, ask: str, at: datetime = T0, instrument: str = "EUR_USD") -> Quote:
    return Quote("fake", instrument, D(bid), D(ask), at, DataType.SIMULATED)


# ---------------------------------------------------------------------------- values (T02.1)
def test_mid_is_derived_exactly_from_bid_and_ask() -> None:
    quote = q("1.08501", "1.08512")
    assert quote.mid == D("1.085065")  # (bid + ask) / 2, not rounded
    assert not quote.crossed


@pytest.mark.parametrize(
    ("bid", "ask"), [("0", "1.1"), ("-1.1", "1.1"), ("1.1", "NaN"), ("1.1", "Infinity")]
)
def test_non_positive_or_non_finite_prices_are_refused(bid: str, ask: str) -> None:
    with pytest.raises(ProviderDataError):
        q(bid, ask)


def test_naive_times_and_bad_codes_are_refused() -> None:
    with pytest.raises(ProviderDataError):
        Quote("fake", "EUR_USD", D(1), D(1), datetime(2026, 1, 1), DataType.SIMULATED)
    with pytest.raises(ProviderDataError):
        q("1", "1", instrument="EURUSD")


def test_times_are_normalised_to_utc() -> None:
    from zoneinfo import ZoneInfo

    nairobi = datetime(2026, 10, 14, 13, 0, tzinfo=ZoneInfo("Africa/Nairobi"))
    assert q("1", "1.1", at=nairobi).ts_provider == T0
    assert q("1", "1.1", at=nairobi).ts_provider.tzinfo is UTC


def test_float_prices_are_refused() -> None:
    with pytest.raises(ProviderDataError):
        Quote("fake", "EUR_USD", 1.1, D(1), T0, DataType.SIMULATED)  # type: ignore[arg-type]


def candle(o: str, h: str, low: str, c: str) -> Candle:
    return Candle(
        "fake",
        "EUR_USD",
        Timeframe.M1,
        PriceBasis.MID,
        T0,
        D(o),
        D(h),
        D(low),
        D(c),
        4,
        complete=True,
        data_type=DataType.SIMULATED,
    )


def test_candle_bounds_are_checked() -> None:
    candle("1.1", "1.2", "1.0", "1.15")
    for o, h, low, c in [("1.1", "1.05", "1.0", "1.0"), ("1.1", "1.2", "1.12", "1.15")]:
        with pytest.raises(ProviderDataError):
            candle(o, h, low, c)


# --------------------------------------------------------------------- quality (T02.5)
POLICY = QualityPolicy(stale_after=timedelta(seconds=60))


def test_a_crossed_quote_is_suspect() -> None:
    assert assess(q("1.10010", "1.10000"), None, T0, POLICY) is Quality.SUSPECT


def test_a_jump_beyond_the_band_is_suspect_and_within_it_is_ok() -> None:
    assert assess(q("1.20", "1.21"), D("1.10"), T0, POLICY) is Quality.SUSPECT  # +9.5%
    assert assess(q("1.12", "1.13"), D("1.10"), T0, POLICY) is Quality.OK  # +2.3%


def test_a_quote_already_old_on_arrival_is_stale() -> None:
    late = T0 + timedelta(seconds=61)
    assert assess(q("1.1", "1.2"), None, late, POLICY) is Quality.STALE
    assert assess(q("1.1", "1.2"), None, T0 + timedelta(seconds=60), POLICY) is Quality.OK


def test_freshness_and_true_age() -> None:
    assert freshness(None, T0, POLICY) is Freshness.UNAVAILABLE
    assert freshness(T0, T0 + timedelta(seconds=60), POLICY) is Freshness.FRESH
    assert freshness(T0, T0 + timedelta(seconds=61), POLICY) is Freshness.STALE
    assert age(T0, T0 + timedelta(hours=50)) == timedelta(hours=50)
    assert age(T0 + timedelta(seconds=2), T0) == timedelta(0)  # provider clock ahead


def test_policies_refuse_nonsense() -> None:
    with pytest.raises(ValueError):
        QualityPolicy(stale_after=timedelta(0))
    with pytest.raises(ValueError):
        QualityPolicy(band=D(1))
    with pytest.raises(ValueError):
        HeartbeatPolicy(timedelta(seconds=30), timedelta(seconds=10))


# ------------------------------------------------------------- feed monitor (T02.4, clock)
def test_feed_monitor_moves_connected_degraded_disconnected_on_the_injected_clock() -> None:
    clock = Clock()
    monitor = FeedMonitor(HeartbeatPolicy(timedelta(seconds=10), timedelta(seconds=30)), clock)

    def status() -> FeedStatus:
        return monitor.status

    assert status() is FeedStatus.DISCONNECTED  # never connected
    monitor.on_connect()
    assert status() is FeedStatus.CONNECTED
    clock.advance(9.999)
    assert status() is FeedStatus.CONNECTED
    clock.advance(0.001)
    assert status() is FeedStatus.DEGRADED  # exactly the window: degraded
    monitor.on_message()  # a heartbeat restores it
    assert status() is FeedStatus.CONNECTED
    clock.advance(29.999)
    assert status() is FeedStatus.DEGRADED
    clock.advance(0.001)
    assert status() is FeedStatus.DISCONNECTED
    monitor.on_message()
    monitor.on_disconnect()
    assert status() is FeedStatus.DISCONNECTED  # a closed connection is never connected


def test_status_for_is_pure() -> None:
    policy = HeartbeatPolicy()
    assert status_for(None, T0, policy) is FeedStatus.DISCONNECTED
    assert status_for(T0, T0 + timedelta(seconds=20), policy) is FeedStatus.DEGRADED


def test_backoff_grows_caps_and_jitters_within_bounds() -> None:
    b = Backoff(timedelta(seconds=1), 2.0, timedelta(seconds=8), jitter=0.2)
    assert [b.delay(n, 0.5) for n in range(1, 6)] == [1.0, 2.0, 4.0, 8.0, 8.0]
    assert b.delay(3, 0.0) == pytest.approx(3.2)
    assert b.delay(3, 0.999999) == pytest.approx(4.8, abs=1e-5)


# --------------------------------------------------------------------- registry (T02.2)
def test_registry_file_is_valid_and_covers_the_launch_currencies() -> None:
    registry = load_registry()
    codes = set(registry.by_code)
    assert {"EUR_USD", "GBP_USD", "USD_JPY", "USD_KES", "USD_ZAR"} <= codes
    assert registry.by_code["USD_JPY"].pip_location == -2
    assert registry.by_code["EUR_USD"].pip_location == -4
    # Less liquid pairs are indicative by default (design 4.2).
    assert registry.by_code["USD_KES"].default_data_type is DataType.INDICATIVE_RATE
    assert registry.by_code["EUR_USD"].default_data_type is DataType.TRADABLE_QUOTE


def test_the_universe_is_configuration() -> None:
    registry = load_registry()
    assert len(registry.active([])) == len(registry.specs)
    assert [s.code for s in registry.active(["USD_KES", "EUR_USD"])] == ["EUR_USD", "USD_KES"]
    with pytest.raises(ValueError, match="XXX_YYY"):
        registry.active(["XXX_YYY"])


@pytest.mark.parametrize(
    "spec",
    [
        {"code": "EUR_EUR", "pip_location": -4, "display_precision": 5, "liquidity_tier": "major"},
        {"code": "EUR_USD", "pip_location": 1, "display_precision": 5, "liquidity_tier": "major"},
        {"code": "EUR_USD", "pip_location": -4, "display_precision": 3, "liquidity_tier": "major"},
        {"code": "EUR_USD", "pip_location": -4, "display_precision": 5, "liquidity_tier": "x"},
    ],
)
def test_bad_specs_are_refused(spec: dict[str, object]) -> None:
    with pytest.raises((ValueError, ProviderDataError)):
        InstrumentSpec(**spec)  # type: ignore[arg-type]


def test_duplicate_codes_are_refused(tmp_path: Path) -> None:
    item = {
        "code": "EUR_USD",
        "pip_location": -4,
        "display_precision": 5,
        "liquidity_tier": "major",
    }
    path = tmp_path / "u.json"
    path.write_text(json.dumps({"spec_version": 1, "instruments": [item, item]}))
    with pytest.raises(ValueError, match="unique"):
        load_registry(path)


# --------------------------------------------------------------- simulated provider (T02.6)
def test_the_fake_provider_is_a_forex_provider_and_every_value_is_simulated() -> None:
    fake = FakeForexProvider(clock=Clock())
    assert isinstance(fake, ForexProvider)
    assert set(REFERENCE) == set(load_registry().by_code)


async def test_simulated_quotes_are_deterministic_labelled_and_at_display_precision() -> None:
    clock = Clock()
    first = await FakeForexProvider(clock=clock).snapshot(["EUR_USD", "USD_JPY"])
    again = await FakeForexProvider(clock=clock).snapshot(["EUR_USD", "USD_JPY"])
    assert first == again
    eur, jpy = first
    assert eur.data_type is DataType.SIMULATED and jpy.data_type is DataType.SIMULATED
    assert eur.bid.as_tuple().exponent == -5 and jpy.bid.as_tuple().exponent == -3
    assert eur.ask - eur.bid == D("0.00012")  # 1.2 pips
    assert abs(eur.mid - REFERENCE["EUR_USD"]) <= REFERENCE["EUR_USD"] * D("0.0023")
    assert eur.ts_provider == T0


async def test_while_the_simulated_market_is_closed_the_latest_quote_keeps_its_close_time() -> None:
    saturday = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)
    assert not market_open(saturday)
    close = last_open_second(saturday)
    assert close == datetime(2026, 10, 16, 20, 59, 59, tzinfo=UTC)
    [quote] = await FakeForexProvider(clock=Clock(saturday)).snapshot(["EUR_USD"])
    assert quote.ts_provider == close  # its true time, never "now"
    assert last_open_second(T0) == T0
    sunday_late = datetime(2026, 10, 18, 21, 30, tzinfo=UTC)
    assert market_open(sunday_late)


async def test_simulated_candles_skip_the_closed_market_and_never_reach_the_future() -> None:
    friday_evening = datetime(2026, 10, 16, 20, 58, 30, tzinfo=UTC)
    clock = Clock(datetime(2026, 10, 19, 0, 0, tzinfo=UTC))  # Monday
    fake = FakeForexProvider(clock=clock)
    candles = await fake.candles(
        "EUR_USD", Timeframe.M1, friday_evening, datetime(2026, 10, 18, 21, 2, tzinfo=UTC)
    )
    times = [c.ts for c in candles]
    assert times[:2] == [
        datetime(2026, 10, 16, 20, 59, tzinfo=UTC),
        datetime(2026, 10, 18, 21, 0, tzinfo=UTC),  # nothing in between: absent, not filled
    ]
    assert all(c.low <= min(c.open, c.close) and c.high >= max(c.open, c.close) for c in candles)
    assert all(c.complete for c in candles)

    now = Clock(T0 + timedelta(seconds=20))
    [forming] = await FakeForexProvider(clock=now).candles(
        "EUR_USD", Timeframe.M1, T0, T0 + timedelta(minutes=5)
    )
    assert not forming.complete and forming.volume == 2  # :00 and :15 only, never the future


async def test_higher_timeframes_aggregate_minutes_and_weeks_are_left_to_the_backend() -> None:
    fake = FakeForexProvider(clock=Clock(T0 + timedelta(hours=2)))
    [hour] = await fake.candles("EUR_USD", Timeframe.H1, T0, T0 + timedelta(hours=1))
    minutes = await fake.candles("EUR_USD", Timeframe.M1, T0, T0 + timedelta(hours=1))
    assert len(minutes) == 60
    assert hour.open == minutes[0].open and hour.close == minutes[-1].close
    assert hour.high == max(m.high for m in minutes) and hour.low == min(m.low for m in minutes)
    assert hour.volume == 240
    with pytest.raises(UnsupportedKind):
        await fake.candles("EUR_USD", Timeframe.W1, T0, T0 + timedelta(days=7))


async def test_outages_and_unknown_pairs_raise_and_never_invent_a_price() -> None:
    fake = FakeForexProvider(clock=Clock())
    fake.down = True
    with pytest.raises(ProviderUnavailable):
        await fake.snapshot(["EUR_USD"])
    with pytest.raises(ProviderUnavailable):
        await fake.candles("EUR_USD", Timeframe.M1, T0, T0 + timedelta(minutes=1))
    fake.down = False
    with pytest.raises(SymbolNotFound):
        await fake.candles("EUR_XYZ", Timeframe.M1, T0, T0 + timedelta(minutes=1))
    assert await fake.snapshot(["EUR_XYZ"]) == []  # absent, not guessed


async def test_the_resilient_wrapper_reuses_the_p08_retry_and_breaker() -> None:
    fake = FakeForexProvider(clock=Clock())
    slept: list[float] = []

    async def sleep(seconds: float) -> None:
        slept.append(seconds)
        fake.down = False  # the outage clears while we wait

    resilient = ResilientForexProvider(fake, RetryPolicy(max_attempts=3), sleep=sleep)
    fake.down = True
    [quote] = await resilient.snapshot(["EUR_USD"])
    assert quote.data_type is DataType.SIMULATED
    assert slept == [0.5]
    fake.down = True
    slept.clear()

    async def stay_down(seconds: float) -> None:
        slept.append(seconds)

    stubborn = ResilientForexProvider(fake, RetryPolicy(max_attempts=2), sleep=stay_down)
    with pytest.raises(ProviderUnavailable):
        await stubborn.candles("EUR_USD", Timeframe.M1, T0, T0 + timedelta(minutes=1))
    assert slept == [0.5]
