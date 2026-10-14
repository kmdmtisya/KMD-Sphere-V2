# ruff: noqa: F811 (imported pytest fixtures are used by name as test parameters)
"""Backtests on the real database (P13-T08): reports from stored bars, stored once per hash; the
read-only API (summaries, the full typed report, filters); the daily job (off with the module,
idempotent); the Opportunity Ranking reading a rule's out-of-sample history; sign-in and the
flag."""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.worker.tasks as tasks
from app.core.config import Settings
from app.main import create_app
from app.modules.forex.backtest.service import run_and_store
from app.modules.forex.backtest.store import ForexBacktestReport, latest_by_rule
from app.modules.forex.instruments.models import ForexInstrument
from app.modules.forex.marketdata.repository import store_candles
from app.modules.forex.marketdata.types import Candle, DataType, PriceBasis, Timeframe
from tests import auth_helpers as ah
from tests.authz_harness import TestUser, make_user
from tests.db_fixtures import migrated_settings  # noqa: F401
from tests.forex.test_backtest_core import synthetic
from tests.forex.test_forex_api import app, http, sessions, user  # noqa: F401
from tests.forex.test_worker_jobs import use

pytestmark = [pytest.mark.integration, pytest.mark.security]
PATH = "/api/v1/forex"
PAIR = "USD_CAD"
START = datetime(2031, 3, 3, tzinfo=UTC)
N = 520
NOW = START + timedelta(hours=N)


class FixedDatetime(datetime):
    @classmethod
    def now(cls, tz: object = None) -> "FixedDatetime":
        return cls(NOW.year, NOW.month, NOW.day, NOW.hour, tzinfo=UTC)


@pytest.fixture(scope="module")
async def stored(app: FastAPI) -> str:
    """Stores 520 hourly bars of USD_CAD and backtests them once. Returns the outcome status."""
    sessions: async_sessionmaker[AsyncSession] = app.state.db.session_factory
    bars = synthetic(N, seed=11)
    rows = [
        Candle(
            "fake",
            PAIR,
            Timeframe.H1,
            PriceBasis.MID,
            START + timedelta(hours=k),
            bars.open[k],
            bars.high[k],
            bars.low[k],
            bars.close[k],
            10,
            True,
            DataType.SIMULATED,
        )
        for k in range(N)
    ]
    async with sessions() as s:
        await store_candles(s, rows, NOW)
        pair = await s.get(ForexInstrument, PAIR)
        assert pair is not None
        outcome = await run_and_store(s, app.state.settings, pair, NOW)
    return outcome.status


async def test_reports_are_stored_once_and_served_in_full(
    app: FastAPI,
    http: httpx.AsyncClient,
    user: TestUser,
    sessions: async_sessionmaker[AsyncSession],
    stored: str,
) -> None:
    assert stored in ("stored", "unchanged")
    r = await http.get(
        f"{PATH}/backtests", params={"instrument": PAIR, "timeframe": "1H"}, headers=user.headers
    )
    assert r.status_code == 200, r.text
    body = r.json()
    items = [i for i in body["items"] if i["period_end"].startswith("2031")]
    assert {i["rule"] for i in items} == {
        "trend_continuation",
        "breakout",
        "reversal",
        "range",
        "momentum",
        "mean_reversion",
    }
    assert all(i["label"] == "backtested" and i["leakage_audit_passed"] for i in items)
    assert all(i["data_types"] == ["simulated"] and i["bars"] == N - 199 for i in items)
    assert "not a forecast" in body["notice"]
    one = next(i for i in items if i["rule"] == "trend_continuation")
    full = await http.get(f"{PATH}/backtests/{one['id']}", headers=user.headers)
    assert full.status_code == 200, full.text
    report = full.json()
    assert report["report_hash"] == one["report_hash"] and report["label"] == "backtested"
    assert report["data"]["snapshot_hash"] and report["code_version"] and report["seed"] == 7
    assert len(report["walk_forward"]["windows"]) == 4 and len(report["cost_sensitivity"]) == 6
    assert report["walk_forward"]["out_of_sample"]["trades"] == one["out_of_sample_trades"]
    assert report["costs"]["contract_specification_review"] == "unreviewed"
    filtered = await http.get(
        f"{PATH}/backtests", params={"rule": "range", "limit": 3}, headers=user.headers
    )
    assert all(i["rule"] == "range" for i in filtered.json()["items"])
    async with sessions() as s:
        count = await s.scalar(
            select(func.count())
            .select_from(ForexBacktestReport)
            .where(ForexBacktestReport.instrument == PAIR)
        )
        pair = await s.get(ForexInstrument, PAIR)
        assert pair is not None
        again = await run_and_store(s, app.state.settings, pair, NOW)
        assert again.status == "unchanged" and again.reports == 0
        assert (
            await s.scalar(
                select(func.count())
                .select_from(ForexBacktestReport)
                .where(ForexBacktestReport.instrument == PAIR)
            )
            == count
        )


async def test_a_report_is_reference_data_the_same_for_every_user(
    http: httpx.AsyncClient, user: TestUser, stored: str
) -> None:
    """The IDOR check for `/backtests/{report_id}`: a report belongs to no one. It is made by the
    job from shared bars, holds no user column, and every signed-in user reads the same one."""
    columns = {c.name for c in ForexBacktestReport.__table__.columns}
    assert not {c for c in columns if "user" in c or "owner" in c}
    items = (
        await http.get(f"{PATH}/backtests", params={"instrument": PAIR}, headers=user.headers)
    ).json()["items"]
    report_id = items[0]["id"]
    other = await make_user(http, "backtest-reader")
    mine = await http.get(f"{PATH}/backtests/{report_id}", headers=user.headers)
    theirs = await http.get(f"{PATH}/backtests/{report_id}", headers=other.headers)
    assert mine.status_code == theirs.status_code == 200
    assert mine.json() == theirs.json()


async def test_the_ranking_reads_each_rules_history(
    sessions: async_sessionmaker[AsyncSession], stored: str
) -> None:
    async with sessions() as s:
        latest = await latest_by_rule(s, PAIR, "1H")
    assert len(latest) == 6
    for rule, row in latest.items():
        assert (
            row.rule == rule
            and row.oos_trades == row.report["walk_forward"]["out_of_sample"]["trades"]
        )
        pf = row.report["walk_forward"]["out_of_sample"]["profit_factor"]
        assert row.oos_profit_factor == (None if pf is None else Decimal(pf))


async def test_too_little_history_is_skipped(
    sessions: async_sessionmaker[AsyncSession], app: FastAPI
) -> None:
    async with sessions() as s:
        pair = await s.get(ForexInstrument, "USD_ZAR")
        assert pair is not None
        outcome = await run_and_store(s, app.state.settings, pair, datetime(2032, 1, 1, tzinfo=UTC))
    assert outcome.status == "skipped" and "needed" in outcome.detail


async def test_the_daily_job_is_off_with_the_module_and_idempotent(
    migrated_settings: Settings, monkeypatch: pytest.MonkeyPatch, stored: str
) -> None:
    use(monkeypatch, migrated_settings.model_copy(update={"forex_enabled": False}))
    off = (await asyncio.to_thread(tasks.forex_backtest_job.apply, args=("2031-03-24",))).get()
    assert off == {"forex": "disabled"}
    use(monkeypatch, migrated_settings.model_copy(update={"forex_enabled": True}))
    monkeypatch.setattr(tasks, "datetime", FixedDatetime)
    key = f"bt-{NOW.isoformat()}"
    result = (await asyncio.to_thread(tasks.forex_backtest_job.apply, args=(key,))).get()
    assert (
        result.get("unchanged") == 1 and sum(v for v in result.values() if isinstance(v, int)) == 12
    )
    again = (await asyncio.to_thread(tasks.forex_backtest_job.apply, args=(key,))).get()
    assert again == {"skipped": True}


async def test_bad_requests_sign_in_and_the_flag(
    http: httpx.AsyncClient, user: TestUser, migrated_settings: Settings
) -> None:
    for params in ({"instrument": "usdcad"}, {"timeframe": "2H"}, {"rule": "scalp"}, {"limit": 0}):
        assert (
            await http.get(f"{PATH}/backtests", params=params, headers=user.headers)
        ).status_code == 422
    missing = "00000000-0000-0000-0000-000000000000"
    assert (await http.get(f"{PATH}/backtests/{missing}", headers=user.headers)).status_code == 404
    assert (await http.get(f"{PATH}/backtests")).status_code == 401
    off = create_app(
        migrated_settings.model_copy(update={"forex_enabled": False}),
        readiness_checks={},
        token_verifier=ah.verifier(),
    )
    transport = httpx.ASGITransport(app=off, raise_app_exceptions=False)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            someone = await make_user(client, "backtest-off")
            assert (
                await client.get(f"{PATH}/backtests", headers=someone.headers)
            ).status_code == 404
    finally:
        await off.state.db.dispose()
