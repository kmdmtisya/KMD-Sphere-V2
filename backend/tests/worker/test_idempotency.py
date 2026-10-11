"""Idempotent jobs: running a job again with the same key does not repeat its work (P08-T04.2).
Needs the migrated test database."""

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.worker.idempotency import claim, run_once
from app.worker.models import JobRun
from tests.db_fixtures import migrated_settings  # noqa: F401

pytestmark = pytest.mark.integration

JOB = "test-job"


@pytest.fixture
async def sessions(
    migrated_settings: Settings,  # noqa: F811
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(migrated_settings.sqlalchemy_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        await s.execute(text("DELETE FROM job_runs"))
        await s.commit()
    try:
        yield factory
    finally:
        await engine.dispose()


async def row(sessions: async_sessionmaker[AsyncSession], key: str) -> JobRun:
    async with sessions() as s:
        return (
            await s.execute(
                select(JobRun).where(JobRun.job_name == JOB, JobRun.idempotency_key == key)
            )
        ).scalar_one()


class Work:
    def __init__(self, fail_times: int = 0) -> None:
        self.calls = 0
        self.fail_times = fail_times

    async def __call__(self, session: AsyncSession) -> str:
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError("boom")
        return f"done {self.calls}"


class TestClaim:
    async def test_first_claim_wins_and_a_repeat_while_running_does_not(
        self, sessions: async_sessionmaker[AsyncSession]
    ) -> None:
        async with sessions() as s:
            assert await claim(s, JOB, "k1") is True
        async with sessions() as s:
            assert await claim(s, JOB, "k1") is False
        assert (await row(sessions, "k1")).status == "running"

    async def test_different_keys_and_jobs_are_independent(
        self, sessions: async_sessionmaker[AsyncSession]
    ) -> None:
        async with sessions() as s:
            assert await claim(s, JOB, "a")
            assert await claim(s, JOB, "b")
            assert await claim(s, "other-job", "a")

    async def test_a_stale_running_claim_is_taken_over(
        self, sessions: async_sessionmaker[AsyncSession]
    ) -> None:
        past = datetime.now(UTC) - timedelta(hours=1)
        async with sessions() as s:
            assert await claim(s, JOB, "k2", now=past)
        async with sessions() as s:
            assert await claim(s, JOB, "k2", lock_timeout=timedelta(minutes=15)) is True
        assert (await row(sessions, "k2")).attempts == 2

    async def test_a_recent_running_claim_is_not_taken_over(
        self, sessions: async_sessionmaker[AsyncSession]
    ) -> None:
        async with sessions() as s:
            assert await claim(s, JOB, "k3")
        async with sessions() as s:
            assert await claim(s, JOB, "k3", lock_timeout=timedelta(minutes=15)) is False

    async def test_concurrent_claims_have_exactly_one_winner(
        self, sessions: async_sessionmaker[AsyncSession]
    ) -> None:
        async def attempt() -> bool:
            async with sessions() as s:
                return await claim(s, JOB, "race")

        results = await asyncio.gather(*(attempt() for _ in range(8)))
        assert results.count(True) == 1
        async with sessions() as s:
            count = (
                await s.execute(
                    select(func.count()).select_from(JobRun).where(JobRun.idempotency_key == "race")
                )
            ).scalar_one()
        assert count == 1


class TestRunOnce:
    async def test_the_work_runs_once_however_often_the_job_is_run(
        self, sessions: async_sessionmaker[AsyncSession]
    ) -> None:
        work = Work()
        first = await run_once(sessions, JOB, "day-1", work)
        second = await run_once(sessions, JOB, "day-1", work)
        third = await run_once(sessions, JOB, "day-1", work)
        assert (first.skipped, first.value) == (False, "done 1")
        assert second.skipped and third.skipped
        assert work.calls == 1
        done = await row(sessions, "day-1")
        assert done.status == "done"
        assert done.finished_at is not None
        assert done.last_error is None

    async def test_a_new_key_runs_again(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        work = Work()
        await run_once(sessions, JOB, "day-1", work)
        await run_once(sessions, JOB, "day-2", work)
        assert work.calls == 2

    async def test_a_failure_is_recorded_and_the_retry_runs_the_work(
        self, sessions: async_sessionmaker[AsyncSession]
    ) -> None:
        work = Work(fail_times=1)
        with pytest.raises(RuntimeError, match="boom"):
            await run_once(sessions, JOB, "day-3", work)
        failed = await row(sessions, "day-3")
        assert failed.status == "failed"
        assert failed.last_error == "RuntimeError: boom"

        retry = await run_once(sessions, JOB, "day-3", work)
        assert retry.skipped is False
        assert work.calls == 2
        finished = await row(sessions, "day-3")
        assert (finished.status, finished.attempts, finished.last_error) == ("done", 2, None)

    async def test_a_long_error_message_is_truncated(
        self, sessions: async_sessionmaker[AsyncSession]
    ) -> None:
        async def work(session: AsyncSession) -> None:
            raise RuntimeError("x" * 2000)

        with pytest.raises(RuntimeError):
            await run_once(sessions, JOB, "long", work)
        assert len((await row(sessions, "long")).last_error or "") == 500

    async def test_concurrent_runs_do_the_work_once(
        self, sessions: async_sessionmaker[AsyncSession]
    ) -> None:
        work = Work()

        async def slow(session: AsyncSession) -> str:
            await asyncio.sleep(0.05)
            return await work(session)

        outcomes = await asyncio.gather(*(run_once(sessions, JOB, "same", slow) for _ in range(5)))
        assert sum(1 for o in outcomes if not o.skipped) == 1
        assert work.calls == 1

    async def test_the_table_refuses_a_second_row_for_the_same_key(
        self, sessions: async_sessionmaker[AsyncSession]
    ) -> None:
        async with sessions() as s:
            s.add(
                JobRun(
                    job_name=JOB,
                    idempotency_key="dup",
                    status="done",
                    attempts=1,
                    started_at=datetime.now(UTC),
                )
            )
            await s.commit()
        async with sessions() as s:
            s.add(
                JobRun(
                    job_name=JOB,
                    idempotency_key="dup",
                    status="done",
                    attempts=1,
                    started_at=datetime.now(UTC),
                )
            )
            with pytest.raises(Exception, match="uq_job_runs_job_name_key"):
                await s.commit()
