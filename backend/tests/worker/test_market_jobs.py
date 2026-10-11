"""The ingestion jobs end to end (P08-T05): claim, ingest, retry on an outage, idempotent reruns,
backfill. Tasks run eagerly against the migrated test database with the fake provider."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import SecretStr
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.worker.tasks as tasks
from app.core.config import Settings
from app.modules.assets.models import Asset, AssetClass
from app.modules.market_data.models import FxRate, MarketPrice
from app.modules.market_data.providers.fake import FakeProvider
from app.modules.market_data.providers.models import AssetKind
from app.modules.market_data.providers.registry import MarketProviders, build_providers
from app.worker.celery_app import celery_app
from app.worker.db import run_async
from app.worker.jobs import JobTask
from app.worker.models import JobRun
from app.worker.schedule import build_schedule
from tests.db_fixtures import migrated_settings  # noqa: F401

pytestmark = pytest.mark.integration

NOW = datetime(2026, 10, 12, 12, tzinfo=UTC)


@pytest.fixture
async def env(
    migrated_settings: Settings,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[tuple[async_sessionmaker[AsyncSession], FakeProvider]]:
    engine = create_async_engine(migrated_settings.sqlalchemy_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        for table in ("market_prices", "fx_rates", "job_runs", "portfolios"):
            await s.execute(text(f"DELETE FROM {table}"))  # noqa: S608 (fixed table names)
        await s.execute(text("DELETE FROM assets WHERE symbol LIKE 'DEMO-%'"))
        cls = (await s.execute(select(AssetClass).where(AssetClass.code == "etf"))).scalar_one()
        s.add(Asset(asset_class_id=cls.id, symbol="DEMO-GEQ", name="Test", currency="USD"))
        await s.commit()

    fake = FakeProvider(clock=lambda: NOW)
    monkeypatch.setattr(
        tasks,
        "build_providers",
        lambda settings: MarketProviders(dict.fromkeys(AssetKind, fake), fake),
    )
    monkeypatch.setattr(tasks, "run_async", lambda work: run_async(work, migrated_settings))
    try:
        yield factory, fake
    finally:
        await engine.dispose()


async def count(factory: async_sessionmaker[AsyncSession], model: type) -> int:
    async with factory() as s:
        return (await s.execute(select(func.count()).select_from(model))).scalar_one()


async def run_task(task: Any, *args: Any) -> Any:
    import asyncio

    # The task starts its own event loop, so it runs in a worker thread.
    return await asyncio.to_thread(task.apply, args=args)


async def test_the_price_job_ingests_and_a_rerun_with_the_same_key_is_skipped(
    env: tuple[async_sessionmaker[AsyncSession], FakeProvider],
) -> None:
    factory, _ = env
    first = await run_task(tasks.ingest_prices, "2026-10-12T12:00")
    assert first.get() == {"stored": 1, "duplicates": 0, "failed": 0}
    again = await run_task(tasks.ingest_prices, "2026-10-12T12:00")
    assert again.get() == {"skipped": True}
    assert await count(factory, MarketPrice) == 1


async def test_a_new_bucket_runs_but_an_unchanged_quote_is_not_stored_again(
    env: tuple[async_sessionmaker[AsyncSession], FakeProvider],
) -> None:
    factory, _ = env
    await run_task(tasks.ingest_prices, "2026-10-12T12:00")
    second = await run_task(tasks.ingest_prices, "2026-10-12T12:15")
    assert second.get() == {"stored": 0, "duplicates": 1, "failed": 0}
    assert await count(factory, MarketPrice) == 1
    assert await count(factory, JobRun) == 2


async def test_an_outage_fails_the_run_and_the_retry_succeeds_after_it(
    env: tuple[async_sessionmaker[AsyncSession], FakeProvider],
) -> None:
    factory, fake = env
    fake.fail_next(1)  # the first attempt finds the provider down
    result = await run_task(tasks.ingest_prices, "2026-10-12T13:00")
    assert result.state == "SUCCESS"
    assert result.get()["stored"] == 1
    async with factory() as s:
        run = (
            await s.execute(select(JobRun).where(JobRun.idempotency_key == "2026-10-12T13:00"))
        ).scalar_one()
    assert (run.status, run.attempts) == ("done", 2), "the failed claim was retaken"


async def test_a_persistent_outage_ends_as_a_failure_not_silent_success(
    env: tuple[async_sessionmaker[AsyncSession], FakeProvider],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory, fake = env
    fake.set_outage(True)
    monkeypatch.setattr(JobTask, "_publish_dead_letter", lambda *a, **k: None)
    monkeypatch.setattr(JobTask, "max_retries", 1, raising=False)
    result = await run_task(tasks.ingest_prices, "2026-10-12T14:00")
    assert result.state == "FAILURE"
    assert await count(factory, MarketPrice) == 0
    async with factory() as s:
        run = (
            await s.execute(select(JobRun).where(JobRun.idempotency_key == "2026-10-12T14:00"))
        ).scalar_one()
    assert run.status == "failed"
    assert "ProviderUnavailable" in (run.last_error or "")


async def test_the_price_job_does_nothing_without_a_provider(
    env: tuple[async_sessionmaker[AsyncSession], FakeProvider],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tasks, "build_providers", lambda s: MarketProviders({}, None))
    result = await run_task(tasks.ingest_prices)
    assert result.get() == {"skipped": "no price provider configured"}


async def test_the_fx_job_stores_the_pairs_the_portfolios_need(
    env: tuple[async_sessionmaker[AsyncSession], FakeProvider],
) -> None:
    factory, _ = env
    from app.modules.identity.models import User
    from app.modules.portfolio.models import Portfolio

    async with factory() as s:
        user = User(issuer="https://issuer.test", subject="fx-job-user")
        s.add(user)
        await s.flush()
        s.add(Portfolio(user_id=user.id, name="p", base_currency="AED"))
        await s.commit()
    result = await run_task(tasks.ingest_fx_job, "2026-10-12")
    # USD/AED is a pair the fake provider knows; AED/USD is its inverse.
    assert result.get() == {"stored": 1, "duplicates": 0, "failed": 0}
    assert await count(factory, FxRate) == 1
    assert (await run_task(tasks.ingest_fx_job, "2026-10-12")).get() == {"skipped": True}


async def test_the_price_backfill_job_is_idempotent_and_overlapping_safe(
    env: tuple[async_sessionmaker[AsyncSession], FakeProvider],
) -> None:
    factory, _ = env
    async with factory() as s:
        asset_id = str(
            (await s.execute(select(Asset.id).where(Asset.symbol == "DEMO-GEQ"))).scalar_one()
        )
    first = await run_task(tasks.backfill_prices_job, asset_id, "2026-10-05", "2026-10-09")
    assert first.get() == {"stored": 5, "duplicates": 0, "failed": 0}
    assert (
        await run_task(tasks.backfill_prices_job, asset_id, "2026-10-05", "2026-10-09")
    ).get() == {"skipped": True}
    wider = await run_task(tasks.backfill_prices_job, asset_id, "2026-10-01", "2026-10-09")
    assert wider.get() == {"stored": 2, "duplicates": 5, "failed": 0}
    assert await count(factory, MarketPrice) == 7


async def test_backfilling_something_that_is_not_a_market_asset_fails_loudly(
    env: tuple[async_sessionmaker[AsyncSession], FakeProvider],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(JobTask, "_publish_dead_letter", lambda *a, **k: None)
    result = await run_task(
        tasks.backfill_prices_job,
        "00000000-0000-0000-0000-000000000000",
        "2026-10-05",
        "2026-10-09",
    )
    assert result.state == "FAILURE"


async def test_the_fx_backfill_job_is_idempotent(
    env: tuple[async_sessionmaker[AsyncSession], FakeProvider],
) -> None:
    factory, _ = env
    first = await run_task(tasks.backfill_fx_job, "USD", "AED", "2026-10-05", "2026-10-09")
    assert first.get() == {"stored": 5, "duplicates": 0, "failed": 0}
    again = await run_task(tasks.backfill_fx_job, "USD", "AED", "2026-10-05", "2026-10-09")
    assert again.get() == {"skipped": True}
    assert await count(factory, FxRate) == 5


def test_the_schedule_runs_the_ingestion_jobs() -> None:
    schedule = build_schedule()
    assert schedule["price-ingest"]["task"] == "app.worker.tasks.ingest_prices"
    assert schedule["fx-ingest"]["task"] == "app.worker.tasks.ingest_fx"
    for name in (
        "app.worker.tasks.ingest_prices",
        "app.worker.tasks.ingest_fx",
        "app.worker.tasks.backfill_prices",
        "app.worker.tasks.backfill_fx",
    ):
        assert name in celery_app.tasks


def test_the_bucket_is_the_quarter_hour() -> None:
    assert tasks._bucket(datetime(2026, 10, 12, 12, 44, 59, tzinfo=UTC), 15) == "2026-10-12T12:30"
    assert tasks._bucket(datetime(2026, 10, 12, 12, 0, tzinfo=UTC), 15) == "2026-10-12T12:00"


class TestRegistry:
    def test_fake_mode_serves_every_kind_from_one_fake(self) -> None:
        providers = build_providers(Settings(environment="test", market_data_mode="fake"))
        assert set(providers.by_kind) == set(AssetKind)
        assert providers.fx is not None
        assert providers.configured

    def test_real_mode_without_keys_has_only_the_keyless_ecb_for_fx(self) -> None:
        providers = build_providers(Settings(environment="test", market_data_mode="real"))
        assert providers.by_kind == {}
        assert providers.fx is not None
        assert providers.fx.name == "ecb"

    def test_keys_switch_the_providers_on(self) -> None:
        providers = build_providers(
            Settings(
                environment="test",
                market_data_mode="real",
                coingecko_api_key=SecretStr("k1"),
                twelvedata_api_key=SecretStr("k2"),
            )
        )
        assert providers.by_kind[AssetKind.CRYPTO].name == "coingecko"
        assert providers.by_kind[AssetKind.ETF].name == "twelvedata"
        assert providers.by_kind[AssetKind.EQUITY].name == "twelvedata"
        # FX: ECB first, Twelve Data for the pairs the ECB does not publish.
        assert providers.fx is not None
        assert providers.fx.name == "ecb+twelvedata"
