# ruff: noqa: F811 (imported pytest fixtures are used by name as test parameters)
"""The Opportunity Ranking API on the real database (P13-T06.5): a stored uptrend is ranked as a
research candidate with every factor, illustrative timestamped levels, costs and freshness;
filters; stale data excluded; the per-pair setups; validation, sign-in and the flag."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.orchestrator.guards import guarantee_problems
from app.core.config import Settings
from app.main import create_app
from app.modules.forex.marketdata.repository import store_candles, store_quotes
from app.modules.forex.marketdata.types import (
    Candle,
    DataType,
    FeedStatus,
    PriceBasis,
    Quality,
    Quote,
    ReceivedQuote,
    Timeframe,
)
from app.modules.forex.signals import api as signals_api
from app.modules.forex.signals.scoring import COMPONENTS
from tests import auth_helpers as ah
from tests.authz_harness import TestUser, make_user
from tests.db_fixtures import migrated_settings  # noqa: F401
from tests.forex.test_forex_api import app, http, sessions, user  # noqa: F401

pytestmark = [pytest.mark.integration, pytest.mark.security]
PATH = "/api/v1/forex"
D = Decimal
NOW = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)  # Wednesday; the market is open
STEP = timedelta(minutes=15)


class FixedDatetime(datetime):
    @classmethod
    def now(cls, tz: object = None) -> "FixedDatetime":
        return cls(2026, 10, 7, 12, 0, tzinfo=UTC)


@pytest.fixture
def frozen(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(signals_api, "datetime", FixedDatetime)


async def store_trend(
    sessions: async_sessionmaker[AsyncSession], pair: str, end: datetime, n: int = 120
) -> None:
    rows = []
    for k in range(n):
        ts = end - STEP * (n - k)
        close = D("0.6600") + D("0.0004") * k + (D("0.0001") if k % 3 == 0 else 0)
        open_ = close - D("0.0002")
        rows.append(
            Candle(
                "fake",
                pair,
                Timeframe.M15,
                PriceBasis.MID,
                ts,
                open_,
                close + D("0.0002"),
                open_ - D("0.0002"),
                close,
                10,
                True,
                DataType.SIMULATED,
            )
        )
    async with sessions() as s:
        await store_candles(s, rows, end)


async def store_quote(sessions: async_sessionmaker[AsyncSession], pair: str, at: datetime) -> None:
    q = Quote("fake", pair, D("0.70000"), D("0.70012"), at, DataType.SIMULATED)
    async with sessions() as s:
        await store_quotes(s, [ReceivedQuote(q, at, Quality.OK, FeedStatus.CONNECTED)])


def strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in strings(v)]
    return []


async def test_a_trend_is_ranked_as_a_fully_explained_research_candidate(
    http: httpx.AsyncClient,
    user: TestUser,
    sessions: async_sessionmaker[AsyncSession],
    frozen: None,
) -> None:
    await store_trend(sessions, "AUD_USD", NOW)
    await store_quote(sessions, "AUD_USD", NOW - timedelta(seconds=5))
    r = await http.get(f"{PATH}/opportunities", params={"timeframe": "15m"}, headers=user.headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["weights_version"] == 1 and set(body["weights"]) == set(COMPONENTS)
    assert (
        body["weights"]["macro_event_risk"] == "-0.2"
        and "not a probability of profit" in body["notice"]
    )
    item = next(i for i in body["items"] if i["instrument"] == "AUD_USD")
    assert item["rank"] >= 1 and item["label"] == "Research candidate"
    assert item["scenario"] == "Bullish scenario" and item["tier"] == "major"
    assert item["opportunity_type"] in ("trend_continuation", "momentum", "breakout")
    assert item["market_condition"] in (
        "trending",
        "momentum_strengthening",
        "high_volatility",
        "mixed",
        "consolidating",
    )
    assert item["risk"] in ("low", "medium", "medium_high", "high")
    lv = item["levels"]
    assert D(lv["stop"]) < D(lv["entry"]) < D(lv["target"])
    assert lv["as_of"] == (NOW - STEP).isoformat().replace("+00:00", "Z")  # the last closed bar
    assert D(lv["risk_pips"]) > 0 and D(lv["reward_pips"]) > 0
    names = [f["name"] for f in item["factors"]]
    assert len(names) == 10 and "macro_event_risk" in names and "strategy_history" in names
    total = sum(D(f["contribution"]) for f in item["factors"])
    assert abs(min(max(total, D(0)), D(1)) * 100 - D(item["score"])) <= D("0.1")
    assert item["costs"]["spread_pips"] == "1.2" and "swaps" in item["costs"]["note"]
    fresh = item["freshness"]
    assert fresh["data_types"] == ["simulated"] and fresh["quote_age_seconds"] == 5
    assert item["rule_version"] == 1 and item["evidence"] and item["assumptions"] and item["risks"]
    texts = strings(item)
    assert guarantee_problems(texts, forecast_used=True) == []
    lowered = " ".join(texts).lower()
    assert " buy" not in lowered and " sell" not in lowered


async def test_filters_and_the_per_pair_setups(
    http: httpx.AsyncClient,
    user: TestUser,
    sessions: async_sessionmaker[AsyncSession],
    frozen: None,
) -> None:
    await store_trend(sessions, "AUD_USD", NOW)
    exotic = (
        await http.get(
            f"{PATH}/opportunities",
            params={"timeframe": "15m", "tier": "exotic"},
            headers=user.headers,
        )
    ).json()
    assert all(i["tier"] == "exotic" for i in exotic["items"])
    assert not any(i["instrument"] == "AUD_USD" for i in exotic["items"])
    ranges = (
        await http.get(
            f"{PATH}/opportunities",
            params={"timeframe": "15m", "setup": "range"},
            headers=user.headers,
        )
    ).json()
    assert all(i["opportunity_type"] == "range" for i in ranges["items"])
    setups = (
        await http.get(
            f"{PATH}/opportunities/setups",
            params={"instrument": "AUD_USD", "timeframe": "15m"},
            headers=user.headers,
        )
    ).json()
    assert setups["items"] and all(
        i["instrument"] == "AUD_USD" and i["rank"] is None for i in setups["items"]
    )
    scores = [D(i["score"]) for i in setups["items"]]
    assert scores == sorted(scores, reverse=True)


async def test_stale_data_is_excluded_not_ranked(
    http: httpx.AsyncClient,
    user: TestUser,
    sessions: async_sessionmaker[AsyncSession],
    frozen: None,
) -> None:
    await store_trend(sessions, "NZD_USD", NOW - timedelta(hours=3))
    body = (
        await http.get(f"{PATH}/opportunities", params={"timeframe": "15m"}, headers=user.headers)
    ).json()
    assert not any(i["instrument"] == "NZD_USD" for i in body["items"])
    stale = [i for i in body["excluded"] if i["instrument"] == "NZD_USD"]
    assert stale and stale[0]["rank"] is None and any("stale" in a for a in stale[0]["adjustments"])


async def test_bad_requests_sign_in_and_the_flag(
    http: httpx.AsyncClient, user: TestUser, migrated_settings: Settings
) -> None:
    for params in (
        {"timeframe": "2H"},
        {"risk": "extreme"},
        {"setup": "scalp"},
        {"tier": "frontier"},
    ):
        assert (
            await http.get(f"{PATH}/opportunities", params=params, headers=user.headers)
        ).status_code == 422
    assert (
        await http.get(
            f"{PATH}/opportunities/setups", params={"instrument": "EUR_SEK"}, headers=user.headers
        )
    ).status_code == 404
    assert (await http.get(f"{PATH}/opportunities")).status_code == 401
    off = create_app(
        migrated_settings.model_copy(update={"forex_enabled": False}),
        readiness_checks={},
        token_verifier=ah.verifier(),
    )
    transport = httpx.ASGITransport(app=off, raise_app_exceptions=False)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            someone = await make_user(client, "signals-off")
            assert (
                await client.get(f"{PATH}/opportunities", headers=someone.headers)
            ).status_code == 404
    finally:
        await off.state.db.dispose()


def test_the_weights_setting_is_validated() -> None:
    from tests.conftest import make_settings

    with pytest.raises(ValueError):
        make_settings(forex_signal_weights={"trend_strength": "1"})
