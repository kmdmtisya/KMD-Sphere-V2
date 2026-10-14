# ruff: noqa: F811 (imported pytest fixtures are used by name as test parameters)
"""Forecasts on the real database (P13-T05.8): training from stored candles, the published
forecast with its labels and provenance, the full evaluation, unavailable states (no history,
drift), retraining approval, validation, the flag and the hourly job."""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.worker.tasks as tasks
from app.core.config import Settings
from app.main import create_app
from app.modules.forex.candles.sync import sync_minutes
from app.modules.forex.forecast import service, store
from app.modules.forex.marketdata.fake import FakeForexProvider
from app.worker.db import run_async
from tests import auth_helpers as ah
from tests.authz_harness import TestUser, make_user
from tests.db_fixtures import migrated_settings  # noqa: F401
from tests.forex.test_forex_api import app, http, sessions, user  # noqa: F401
from tests.forex.test_marketdata_core import Clock

pytestmark = [pytest.mark.integration, pytest.mark.security]
PATH = "/api/v1/forex"
NOW = datetime(2026, 10, 8, 20, 0, tzinfo=UTC)  # Thursday evening: three trading days behind it


async def seed_minutes(sessions: async_sessionmaker[AsyncSession], pair: str) -> None:
    """Three trading days of simulated one-minute candles (idempotent: a second call adds none)."""
    provider = FakeForexProvider(clock=Clock(NOW))
    async with sessions() as s:
        await sync_minutes(s, provider, [pair], NOW, timedelta(days=3, hours=4))
        stored = await s.scalar(
            text("SELECT count(*) FROM forex_candles WHERE instrument = :p AND timeframe = '1m'"),
            {"p": pair},
        )
    assert stored is not None and stored > 4000


async def trained(
    sessions: async_sessionmaker[AsyncSession], settings: Settings, pair: str, horizon: str = "15m"
) -> service.Outcome:
    async with sessions() as s:
        return await service.train(s, settings, pair, horizon, NOW)


# --------------------------------------------------------------------------------- training
async def test_training_from_stored_candles_publishes_a_forecast_with_its_evaluation(
    app: Any, http: httpx.AsyncClient, user: TestUser, sessions: async_sessionmaker[AsyncSession]
) -> None:
    await seed_minutes(sessions, "EUR_USD")
    outcome = await trained(sessions, app.state.settings, "EUR_USD")
    assert outcome.result == "published", outcome
    r = await http.get(
        f"{PATH}/forecasts",
        params={"instrument": "EUR_USD", "horizon": "15m"},
        headers=user.headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["status"], body["timeframe"], body["bars_ahead"]) == ("available", "5m", 3)
    f = body["forecast"]
    assert f["as_of"] < NOW.isoformat().replace("+00:00", "Z") and f["data_types"] == ["simulated"]
    assert f["probability_label"] in ("Requires calibration", "Calibrated")
    assert f["probability_note"] == "A model probability, not a success rate."
    assert abs(float(f["prob_up"]) + float(f["prob_down"]) - 1) < 1e-9
    q = [float(f["return_quantiles"][k]) for k in ("q10", "q25", "q50", "q75", "q90")]
    assert q == sorted(q)
    p80, p50 = f["price_interval_80"], f["price_interval_50"]
    assert (
        float(p80["low"])
        <= float(p50["low"])
        <= float(f["price_median"])
        <= float(p50["high"])
        <= float(p80["high"])
    )
    assert float(f["expected_volatility"]) > 0 and f["volatility_model"] in ("ewma", "har")
    assert f["fresh"] is False and f["age_seconds"] > 0  # NOW is in the past: honest age
    model = body["model"]
    assert len(model["version"]) == 16 and model["feature_set_hash"] and model["data_snapshot_hash"]
    assert model["seed"] == 7 and model["drift_status"] == "ok"
    assert model["statement"].startswith("demonstrated edge") == model["edge"]
    # Trained on the simulated feed: whatever it shows is no evidence about real markets.
    assert model["data_types"] == ["simulated"]
    assert model["statement"].endswith("(on simulated data: not evidence about real markets)")
    oos = body["out_of_sample"]
    assert oos["folds"] >= 3 and oos["test_rows"] >= 100
    assert set(oos["baselines"]) == {"no_change", "random_walk", "drift"}
    assert "never a guaranteed return" in body["notice"]
    e = (
        await http.get(
            f"{PATH}/forecasts/evaluation",
            params={"instrument": "EUR_USD", "horizon": "15m"},
            headers=user.headers,
        )
    ).json()
    names = {r["name"] for r in e["results"]}
    assert names >= {
        "no_change",
        "random_walk",
        "drift",
        "arima",
        "random_forest",
        "lightgbm",
        "xgboost",
        "ensemble",
    }
    for res in e["results"]:
        if res["family"] != "baseline" and not res["error"]:
            assert set(res["versus_baselines"]) == {"no_change", "random_walk", "drift"}
    assert set(e["volatility"]) >= {"ewma_rmse", "chosen"} and e["drift"]["status"] == "ok"


async def test_retraining_supersedes_and_keeps_history(
    app: Any, sessions: async_sessionmaker[AsyncSession]
) -> None:
    await seed_minutes(sessions, "EUR_USD")
    await trained(sessions, app.state.settings, "EUR_USD")
    await trained(sessions, app.state.settings, "EUR_USD")
    async with sessions() as s:
        from sqlalchemy import select

        rows = (
            (
                await s.execute(
                    select(store.ForexModelVersion.status)
                    .where(
                        store.ForexModelVersion.instrument == "EUR_USD",
                        store.ForexModelVersion.horizon == "15m",
                    )
                    .order_by(
                        store.ForexModelVersion.trained_at, store.ForexModelVersion.created_at
                    )
                )
            )
            .scalars()
            .all()
        )
    assert rows[-1] == "active" and set(rows[:-1]) == {"superseded"} and len(rows) >= 2


async def test_without_enough_history_nothing_is_shown(
    app: Any, http: httpx.AsyncClient, user: TestUser, sessions: async_sessionmaker[AsyncSession]
) -> None:
    outcome = await trained(sessions, app.state.settings, "USD_CHF", "1w")
    assert outcome.result == "insufficient_history"
    body = (
        await http.get(
            f"{PATH}/forecasts",
            params={"instrument": "USD_CHF", "horizon": "1w"},
            headers=user.headers,
        )
    ).json()
    assert (
        body["status"] == "unavailable"
        and body["forecast"] is None
        and "not enough history" in body["reason"]
    )
    e = (
        await http.get(
            f"{PATH}/forecasts/evaluation",
            params={"instrument": "USD_CHF", "horizon": "1w"},
            headers=user.headers,
        )
    ).json()
    assert e["status"] == "unavailable" and e["results"] == []


async def test_drift_disables_forecasts_until_retraining_is_approved(
    app: Any,
    http: httpx.AsyncClient,
    user: TestUser,
    sessions: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await seed_minutes(sessions, "GBP_USD")
    from app.modules.forex.forecast import drift as drift_module
    from app.modules.forex.forecast import pipeline

    def always_breached(*args: Any, **kwargs: Any) -> drift_module.DriftReport:
        return drift_module.DriftReport(
            {}, {}, None, None, "breached", ["broad feature drift: test"]
        )

    monkeypatch.setattr(pipeline, "check", always_breached)
    assert (await trained(sessions, app.state.settings, "GBP_USD")).result == "disabled"
    body = (
        await http.get(
            f"{PATH}/forecasts",
            params={"instrument": "GBP_USD", "horizon": "15m"},
            headers=user.headers,
        )
    ).json()
    assert (
        body["status"] == "unavailable" and body["forecast"] is None and "drift" in body["reason"]
    )
    assert body["model"]["drift_status"] == "breached"
    monkeypatch.undo()
    # Blocked: the job does not retrain until someone approves it.
    assert (await trained(sessions, app.state.settings, "GBP_USD")).result == "skipped"
    async with sessions() as s:
        with pytest.raises(ValueError):
            await store.approve_retraining(s, "GBP_USD", "15m", " ", NOW)
        approved = await store.approve_retraining(
            s, "GBP_USD", "15m", "user (mtisya@gmail.com)", NOW
        )
        assert approved.retraining_approved_by == "user (mtisya@gmail.com)"
    assert (await trained(sessions, app.state.settings, "GBP_USD")).result == "published"
    body = (
        await http.get(
            f"{PATH}/forecasts",
            params={"instrument": "GBP_USD", "horizon": "15m"},
            headers=user.headers,
        )
    ).json()
    assert body["status"] == "available"
    async with sessions() as s:
        with pytest.raises(ValueError):  # nothing disabled any more
            await store.approve_retraining(s, "GBP_USD", "15m", "someone", NOW)


# ------------------------------------------------------------------------------ validation
async def test_bad_requests_and_unknown_pairs(http: httpx.AsyncClient, user: TestUser) -> None:
    for path in ("forecasts", "forecasts/evaluation"):
        assert (
            await http.get(
                f"{PATH}/{path}",
                params={"instrument": "EUR_USD", "horizon": "2h"},
                headers=user.headers,
            )
        ).status_code == 422
        assert (
            await http.get(f"{PATH}/{path}", params={"instrument": "eur_usd"}, headers=user.headers)
        ).status_code == 422
        assert (
            await http.get(f"{PATH}/{path}", params={"instrument": "EUR_SEK"}, headers=user.headers)
        ).status_code == 404
        assert (
            await http.get(f"{PATH}/{path}", params={"instrument": "EUR_USD"})
        ).status_code == 401


async def test_the_flag_switches_forecasts_off(migrated_settings: Settings) -> None:
    off = create_app(
        migrated_settings.model_copy(update={"forex_enabled": False}),
        readiness_checks={},
        token_verifier=ah.verifier(),
    )
    transport = httpx.ASGITransport(app=off, raise_app_exceptions=False)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            someone = await make_user(client, "forecast-off")
            for path in ("forecasts", "forecasts/evaluation"):
                r = await client.get(
                    f"{PATH}/{path}", params={"instrument": "EUR_USD"}, headers=someone.headers
                )
                assert r.status_code == 404
    finally:
        await off.state.db.dispose()


# ------------------------------------------------------------------------------------- job
async def test_the_hourly_job_is_off_with_the_module_and_runs_once_per_hour(
    migrated_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    def use(settings: Settings) -> None:
        monkeypatch.setattr(tasks, "get_settings", lambda: settings)
        monkeypatch.setattr(tasks, "run_async", lambda work: run_async(work, settings))

    use(migrated_settings.model_copy(update={"forex_enabled": False}))
    off = (
        await asyncio.to_thread(tasks.forex_forecast_train_job.apply, args=("2026-10-08T20",))
    ).get()
    assert off == {"forex": "disabled"}
    use(
        migrated_settings.model_copy(
            update={"forex_enabled": True, "forex_forecast_horizons": ["1w"]}
        )
    )
    result = (
        await asyncio.to_thread(tasks.forex_forecast_train_job.apply, args=("2026-10-08T20",))
    ).get()
    assert sum(v for v in result.values() if isinstance(v, int)) >= 12  # every active pair tried
    assert set(result) <= {"published", "disabled", "skipped", "insufficient_history"}
    again = (
        await asyncio.to_thread(tasks.forex_forecast_train_job.apply, args=("2026-10-08T20",))
    ).get()
    assert again == {"skipped": True}
