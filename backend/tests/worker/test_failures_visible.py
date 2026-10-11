"""Failed jobs are recorded and visible (P08-T04.3). Needs the migrated test database."""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.worker.jobs as jobs
from app.core.config import Settings
from app.worker.cli import acknowledge, format_failure, list_failures
from app.worker.db import run_async
from app.worker.models import JobFailure
from tests.db_fixtures import migrated_settings  # noqa: F401

pytestmark = pytest.mark.integration


@pytest.fixture
async def sessions(
    migrated_settings: Settings,  # noqa: F811
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(migrated_settings.sqlalchemy_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        await s.execute(text("DELETE FROM job_failures"))
        await s.commit()
    try:
        yield factory
    finally:
        await engine.dispose()


async def add(sessions: async_sessionmaker[AsyncSession], job: str, minutes_ago: int) -> uuid.UUID:
    async with sessions() as s:
        failure = JobFailure(
            task_id="t",
            job_name=job,
            error_type="ValueError",
            error_message="bad",
            attempts=3,
            failed_at=datetime.now(UTC) - timedelta(minutes=minutes_ago),
        )
        s.add(failure)
        await s.commit()
        return failure.id


async def test_open_failures_are_listed_newest_first(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    await add(sessions, "older", 10)
    await add(sessions, "newer", 1)
    rows = await list_failures(sessions, include_acknowledged=False)
    assert [r.job_name for r in rows] == ["newer", "older"]


async def test_acknowledging_hides_it_unless_all_are_asked_for(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    failure_id = await add(sessions, "job", 1)
    assert await acknowledge(sessions, failure_id) is True
    assert await acknowledge(sessions, failure_id) is False, "already acknowledged"
    assert await list_failures(sessions, include_acknowledged=False) == []
    assert len(await list_failures(sessions, include_acknowledged=True)) == 1
    assert await acknowledge(sessions, uuid.uuid4()) is False


async def test_the_listing_line_says_what_failed_and_whether_it_is_open(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    await add(sessions, "price-ingest", 1)
    (row,) = await list_failures(sessions, include_acknowledged=False)
    line = format_failure(row)
    assert "OPEN" in line
    assert "price-ingest" in line
    assert "ValueError: bad" in line
    assert "attempts=3" in line


async def test_the_job_base_records_a_failure_row(
    migrated_settings: Settings,  # noqa: F811
    sessions: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio

    monkeypatch.setattr(jobs, "run_async", lambda work: run_async(work, migrated_settings))
    when = datetime.now(UTC)
    # run_async starts its own event loop, so call it from a worker thread.
    await asyncio.to_thread(
        jobs._record_failure, "task-1", "price-ingest", RuntimeError("x" * 900), 4, when
    )
    (row,) = await list_failures(sessions, include_acknowledged=False)
    assert (row.task_id, row.job_name, row.error_type, row.attempts) == (
        "task-1",
        "price-ingest",
        "RuntimeError",
        4,
    )
    assert len(row.error_message) == 500
    assert row.acknowledged_at is None
