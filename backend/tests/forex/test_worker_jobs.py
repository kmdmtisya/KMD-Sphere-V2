"""The forex worker jobs on the real database (P13-T02.3, P13-T03): registry and partition
maintenance, and the one-minute candle sync (switched off with the module; idempotent per slot)."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.worker.tasks as tasks
from app.core.config import Settings
from app.db.session import Database
from app.modules.forex.marketdata.fake import FakeForexProvider
from app.worker.db import run_async
from tests.db_fixtures import migrated_settings  # noqa: F401
from tests.forex.test_marketdata_core import Clock

pytestmark = [pytest.mark.integration]
WED = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)


class FixedDatetime(datetime):
    @classmethod
    def now(cls, tz: object = None) -> "FixedDatetime":
        return cls(2026, 10, 7, 12, 0, tzinfo=UTC)


def use(monkeypatch: pytest.MonkeyPatch, settings: Settings) -> None:
    monkeypatch.setattr(tasks, "get_settings", lambda: settings)
    monkeypatch.setattr(tasks, "run_async", lambda work: run_async(work, settings))


async def test_maintenance_syncs_the_registry_and_creates_partitions_ahead_once_per_day(
    migrated_settings: Settings,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    use(monkeypatch, migrated_settings)
    day = "2033-02-10"
    result = (await asyncio.to_thread(tasks.forex_maintenance_job.apply, args=(day,))).get()
    assert result["active"] == 12 and result["added"] in (0, 12)
    assert set(result["partitions_created"]) >= {
        "forex_quotes_p203302",
        "forex_quotes_p203303",
        "forex_quotes_p203304",
        "forex_candles_p203302",
        "forex_candles_p203303",
        "forex_candles_p203304",
    }
    again = (await asyncio.to_thread(tasks.forex_maintenance_job.apply, args=(day,))).get()
    assert again == {"skipped": True}


async def test_the_candle_sync_is_off_with_the_module(
    migrated_settings: Settings,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    use(monkeypatch, migrated_settings.model_copy(update={"forex_enabled": False}))
    result = (await asyncio.to_thread(tasks.forex_candle_sync_job.apply, args=("s-off",))).get()
    assert result == {"forex": "disabled"}


async def test_the_candle_sync_stores_provider_minutes_once_per_slot(
    migrated_settings: Settings,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = migrated_settings.model_copy(
        update={"forex_enabled": True, "forex_candle_sync_max_hours": 1}
    )
    use(monkeypatch, settings)
    # Make sure the registry exists (the maintenance job normally does this first).
    await asyncio.to_thread(tasks.forex_maintenance_job.apply, args=("2026-10-07",))
    monkeypatch.setattr(tasks, "datetime", FixedDatetime)
    monkeypatch.setattr(
        tasks, "build_forex_provider", lambda _settings: FakeForexProvider(clock=Clock(WED))
    )
    slot = f"slot-{uuid.uuid4()}"
    result = (await asyncio.to_thread(tasks.forex_candle_sync_job.apply, args=(slot,))).get()
    assert result == {"stored": 12 * 60, "failed": []}  # 12 pairs, one hour each
    again = (await asyncio.to_thread(tasks.forex_candle_sync_job.apply, args=(slot,))).get()
    assert again == {"skipped": True}

    db = Database(settings)
    sessions: async_sessionmaker[AsyncSession] = db.session_factory
    try:
        async with sessions() as s:
            newest = await s.scalar(
                text("SELECT max(ts) FROM forex_candles WHERE instrument = 'EUR_USD'")
            )
        assert newest == WED - timedelta(minutes=1)
    finally:
        await db.dispose()


async def test_the_calendar_ingest_is_off_with_the_module_and_idempotent_per_run(
    migrated_settings: Settings,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    use(monkeypatch, migrated_settings.model_copy(update={"forex_enabled": False}))
    off = (
        await asyncio.to_thread(tasks.forex_calendar_ingest_job.apply, args=("2026-10-07T10",))
    ).get()
    assert off == {"forex": "disabled"}
    use(monkeypatch, migrated_settings.model_copy(update={"forex_enabled": True}))
    key = "2026-10-07T10"
    result = (await asyncio.to_thread(tasks.forex_calendar_ingest_job.apply, args=(key,))).get()
    assert result["source"] == "demo" and result["added"] > 0 and result["rates"] > 0
    again = (await asyncio.to_thread(tasks.forex_calendar_ingest_job.apply, args=(key,))).get()
    assert again == {"skipped": True}
