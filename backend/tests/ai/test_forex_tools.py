# ruff: noqa: F811 (imported pytest fixtures are used by name as test parameters)
"""The Forex Copilot's tools on the real database (P13-T10.1, T10.6), called through the
registry's single door: each returns structured data with its time, source and data types; a
stale or missing price is reported as incomplete, never filled in; forecasts carry the model
version and calibration label; the risk tool gives the API's figures; the paper tool reads only
the caller's own accounts; unknown arguments are refused; and with forex off there is no forex
tool."""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.tools.base import ToolContext, ToolOutcome
from app.ai.tools.factory import build_tool_registry
from app.ai.tools.forex import FOREX_TOOLS
from app.core.audit import AuditEvent
from app.modules.forex.backtest import runner
from app.modules.forex.backtest.store import save
from app.modules.forex.calendar.ingest import ingest
from app.modules.forex.calendar.sources import DemoCalendarSource
from app.modules.forex.forecast.store import ForexForecast, ForexModelVersion
from app.modules.forex.paper.service import PaperService
from app.modules.forex.risk.specs import load_file
from tests.authz_harness import TestUser, make_user
from tests.db_fixtures import migrated_settings  # noqa: F401
from tests.forex.test_backtest_core import synthetic
from tests.forex.test_forex_api import app, http, sessions, user  # noqa: F401
from tests.forex.test_paper_api import quote
from tests.forex.test_signals_api import store_trend

pytestmark = [pytest.mark.integration, pytest.mark.security]
D = Decimal


def registry(app: FastAPI) -> Any:
    settings = app.state.settings.model_copy(update={"ai_tool_calls_per_minute": 10_000})
    return build_tool_registry(settings)


async def call(app: FastAPI, who: TestUser, name: str, arguments: dict[str, Any]) -> ToolOutcome:
    sessions: async_sessionmaker[AsyncSession] = app.state.db.session_factory
    async with sessions() as session:
        ctx = ToolContext(uuid.UUID(who.id), session, "forex-tools", "fake-model", "fake")
        outcome: ToolOutcome = await registry(app).execute(name, arguments, ctx)
        return outcome


def test_forex_tools_exist_only_while_forex_is_on(app: FastAPI) -> None:
    assert set(FOREX_TOOLS) <= registry(app).names
    off = app.state.settings.model_copy(update={"forex_enabled": False})
    assert not set(FOREX_TOOLS) & build_tool_registry(off).names


async def test_quotes_fresh_stale_and_missing(
    app: FastAPI, user: TestUser, sessions: async_sessionmaker[AsyncSession]
) -> None:
    await quote(sessions, "EUR_USD", "1.08610", "1.08622")
    fresh = await call(app, user, "get_forex_quote", {"instrument": "EUR_USD"})
    assert fresh.ok and fresh.data is not None
    assert fresh.data["status"] == "fresh" and fresh.data["complete"] is True
    assert fresh.data["bid"] == "1.0861" and fresh.data["spread_pips"] == "1.2"
    assert fresh.data["data_type"] == "simulated" and "provider: fake" in fresh.data["source"]
    await quote(
        sessions, "USD_CHF", "0.88000", "0.88010", at=datetime.now(UTC) - timedelta(minutes=10)
    )
    stale = await call(app, user, "get_forex_quote", {"instrument": "USD_CHF"})
    assert stale.data is not None and stale.data["status"] == "stale"
    assert stale.data["complete"] is False  # the server will qualify the answer
    unknown = await call(app, user, "get_forex_quote", {"instrument": "EUR_SEK"})
    assert not unknown.ok and unknown.error_code == "not_found"
    smuggled = await call(app, user, "get_forex_quote", {"instrument": "EUR_USD", "user_id": "x"})
    assert not smuggled.ok and smuggled.error_code == "invalid_arguments"


async def test_candles_indicators_structure_and_opportunities(
    app: FastAPI, user: TestUser, sessions: async_sessionmaker[AsyncSession]
) -> None:
    now = datetime.now(UTC)
    end = now.replace(minute=now.minute - now.minute % 15, second=0, microsecond=0)
    await store_trend(sessions, "AUD_USD", end)
    candles = await call(
        app, user, "get_candles", {"instrument": "AUD_USD", "timeframe": "15m", "count": 10}
    )
    assert candles.ok and candles.data is not None and len(candles.data["bars"]) == 10
    assert candles.data["data_types"] == ["simulated"] and candles.data["complete"] is True
    indicators = await call(
        app, user, "get_indicators", {"instrument": "AUD_USD", "timeframe": "15m"}
    )
    assert indicators.ok and indicators.data is not None
    values = indicators.data["values"]
    assert {"rsi_14", "atr_14", "adx_14", "macd", "bollinger_upper"} <= set(values)
    assert D(values["rsi_14"]) > 50  # a rising series
    structure = await call(
        app, user, "get_market_structure", {"instrument": "AUD_USD", "timeframe": "15m"}
    )
    assert structure.ok and structure.data is not None and "levels" in structure.data
    ranking = await call(app, user, "get_opportunities", {"timeframe": "15m", "count": 10})
    assert ranking.ok and ranking.data is not None
    assert "not recommendations" in ranking.data["notice"]
    assert any(i["instrument"] == "AUD_USD" for i in ranking.data["items"])
    empty = await call(app, user, "get_indicators", {"instrument": "NZD_USD", "timeframe": "1D"})
    assert empty.ok and empty.data is not None and empty.data["complete"] is False


async def test_forecasts_carry_the_model_version_and_calibration(
    app: FastAPI, user: TestUser, sessions: async_sessionmaker[AsyncSession]
) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    async with sessions() as s:
        version = ForexModelVersion(
            instrument="GBP_JPY",
            horizon="1w",
            timeframe="1D",
            bars_ahead=5,
            model_name="lightgbm",
            family="tree",
            version="v-test",
            params={},
            feature_set_hash="f" * 16,
            data_snapshot_hash="d" * 16,
            code_version="test",
            seed=7,
            trained_at=now,
            train_rows=100,
            test_rows=50,
            folds=4,
            evaluation=[],
            volatility={},
            calibration_status="requires_calibration",
            probability_source="raw",
            edge=False,
            drift={},
            drift_status="ok",
            status="active",
            data_types=["simulated"],
        )
        s.add(version)
        await s.flush()
        for k, prob in ((2, "0.5400"), (1, "0.5800")):
            s.add(
                ForexForecast(
                    model_version_id=version.id,
                    instrument="GBP_JPY",
                    horizon="1w",
                    as_of=now - timedelta(hours=k),
                    generated_at=now - timedelta(hours=k),
                    last_close=D("191.4"),
                    prob_up=D(prob),
                    prob_up_raw=D(prob),
                    return_quantiles=["-0.02", "-0.01", "0.001", "0.012", "0.021"],
                    price_quantiles=["187.5", "189.5", "191.6", "193.7", "195.4"],
                    expected_volatility=D("0.012"),
                    volatility_model="ewma",
                    data_types=["simulated"],
                )
            )
        await s.commit()
    fc = await call(app, user, "get_forecast", {"instrument": "GBP_JPY", "horizon": "1w"})
    assert fc.ok and fc.data is not None and fc.data["status"] == "available"
    assert fc.data["model"]["version"] == "v-test" and fc.data["prob_up"] == "0.58"
    assert fc.data["probability_label"] == "Requires calibration"
    assert fc.data["price_interval_80"] == ["187.5", "195.4"]
    change = await call(
        app, user, "explain_forecast_change", {"instrument": "GBP_JPY", "horizon": "1w"}
    )
    assert change.ok and change.data is not None and change.data["status"] == "compared"
    assert change.data["prob_up_change"] == "0.04" and change.data["model_changed"] is False
    none = await call(app, user, "get_forecast", {"instrument": "USD_ZAR", "horizon": "15m"})
    assert none.ok and none.data is not None and none.data["status"] == "unavailable"
    assert none.data["complete"] is False


async def test_calendar_risk_and_backtests(
    app: FastAPI, user: TestUser, sessions: async_sessionmaker[AsyncSession]
) -> None:
    now = datetime.now(UTC)
    async with sessions() as s:
        await ingest(s, DemoCalendarSource(), now.date(), (now + timedelta(days=8)).date(), now)
    events = await call(app, user, "get_economic_events", {"hours_ahead": 168})
    assert events.ok and events.data is not None
    assert all(e["demo"] is True for e in events.data["events"])
    usd = await call(app, user, "get_economic_events", {"currency": "USD", "hours_ahead": 168})
    assert usd.data is not None and all("USD" in e["currencies"] for e in usd.data["events"])
    await quote(sessions, "EUR_USD", "1.09994", "1.10006")
    risk = await call(
        app,
        user,
        "calculate_trade_risk",
        {
            "instrument": "EUR_USD",
            "direction": "long",
            "entry": "1.10000",
            "stop": "1.09500",
            "target": "1.11000",
            "balance": "10000",
            "account_currency": "USD",
            "risk_percent": "1",
        },
    )
    assert risk.ok and risk.data is not None
    calc = risk.data["calculation"]
    assert calc["size"]["units"] == "19000"  # the same figure as the API (test_risk_api)
    assert any("gap or slip" in d for d in calc["disclosures"])
    bad = await call(
        app,
        user,
        "calculate_trade_risk",
        {
            "instrument": "EUR_USD",
            "direction": "long",
            "entry": "1.1",
            "stop": "1.2",
            "balance": "1000",
            "account_currency": "USD",
            "risk_percent": "1",
        },
    )
    assert not bad.ok and bad.error_code == "invalid"
    _, _, specs = load_file()
    data = runner.PairData(
        "USD_CAD",
        "1H",
        synthetic(520, seed=21),
        ["simulated"],
        -4,
        5,
        "major",
        specs["USD_CAD"],
        1,
        False,
    )
    settings = runner.Settings(random_runs=2, audit_cuts=1, audit_lookback=3)
    async with sessions() as s:
        for report in runner.run_pair(data, settings, now, ("breakout",)):
            await save(s, report)
    bt = await call(app, user, "get_backtest_summary", {"instrument": "USD_CAD", "timeframe": "1H"})
    assert bt.ok and bt.data is not None and bt.data["label"] == "backtested"
    assert any(r["rule"] == "breakout" and r["leakage_audit_passed"] for r in bt.data["reports"])


async def test_paper_performance_reads_only_the_callers_accounts(
    app: FastAPI, http: httpx.AsyncClient, user: TestUser
) -> None:
    sessions: async_sessionmaker[AsyncSession] = app.state.db.session_factory
    other = await make_user(http, "copilot-other")
    async with sessions() as s:
        service = PaperService(s, app.state.settings)
        mine = await service.create_account(uuid.UUID(user.id), "Mine", "USD", D(10000), True)
        theirs = await service.create_account(uuid.UUID(other.id), "Theirs", "USD", D(5000), False)
    all_mine = await call(app, user, "get_paper_performance", {})
    assert all_mine.ok and all_mine.data is not None and all_mine.data["mode"] == "PAPER TRADING"
    ids = {a["account_id"] for a in all_mine.data["accounts"]}
    assert str(mine.id) in ids and str(theirs.id) not in ids
    one = await call(app, user, "get_paper_performance", {"account_id": str(mine.id)})
    assert one.ok and one.data is not None and len(one.data["accounts"]) == 1
    foreign = await call(app, user, "get_paper_performance", {"account_id": str(theirs.id)})
    assert not foreign.ok and foreign.error_code == "not_found"
    async with sessions() as s:
        audited = (
            await s.execute(
                select(AuditEvent).where(
                    AuditEvent.action == "ai.tool.call",
                    AuditEvent.actor_user_id == uuid.UUID(user.id),
                    AuditEvent.correlation_id == "forex-tools",
                )
            )
        ).scalars()
        assert any(e.details.get("tool") == "get_paper_performance" for e in audited)


def test_the_paper_tool_cannot_be_asked_for_a_date(app: FastAPI) -> None:
    spec = next(s for s in registry(app).specs() if s.name == "get_paper_performance")
    assert set(spec.parameters["properties"]) == {"account_id"}
    assert date.today()  # the tool takes no user id, no date and no write argument
