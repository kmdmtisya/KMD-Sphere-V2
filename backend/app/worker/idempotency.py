"""Idempotent jobs (P08-T04.2): running a job again with the same key does not repeat its work.

A job asks for the key it is about to process (for example `price-ingest:2026-10-12`). The claim is
one atomic `INSERT ... ON CONFLICT DO UPDATE ... WHERE` on a unique (job, key):

- no row yet                     -> inserted as `running`: this worker owns the work;
- row is `done`                  -> not touched: the work was already completed, skip;
- row is `failed`                -> taken again (`running`, attempts + 1): a retry;
- row is `running` and stale     -> taken over (the worker that held it died);
- row is `running` and recent    -> not touched: another worker is on it, skip.

Two workers that claim at the same moment cannot both win. This guarantees a job's *claim*; the
work itself must still be written as an upsert, so a crash between doing the work and marking it
`done` re-runs it safely (P08-T05 stores prices with ON CONFLICT upserts)."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.worker.models import JobRun

DEFAULT_LOCK_TIMEOUT = timedelta(minutes=15)
_ERROR_LIMIT = 500


@dataclass(frozen=True)
class RunOutcome[T]:
    skipped: bool
    value: T | None = None


def _now() -> datetime:
    return datetime.now(UTC)


async def claim(
    session: AsyncSession,
    job: str,
    key: str,
    *,
    lock_timeout: timedelta = DEFAULT_LOCK_TIMEOUT,
    now: datetime | None = None,
) -> bool:
    """Try to own (job, key). True when this caller must do the work."""
    moment = now or _now()
    base = insert(JobRun).values(
        job_name=job, idempotency_key=key, status="running", attempts=1, started_at=moment
    )
    stmt = base.on_conflict_do_update(
        constraint="uq_job_runs_job_name_key",
        set_={
            "status": "running",
            "attempts": JobRun.attempts + 1,
            "started_at": moment,
            "finished_at": None,
            "last_error": None,
        },
        where=(JobRun.status == "failed")
        | ((JobRun.status == "running") & (JobRun.started_at < moment - lock_timeout)),
    ).returning(JobRun.id)
    result = await session.execute(stmt)
    owned = result.first() is not None
    await session.commit()
    return owned


async def _finish(
    session: AsyncSession, job: str, key: str, *, error: str | None, now: datetime | None = None
) -> None:
    await session.execute(
        update(JobRun)
        .where(JobRun.job_name == job, JobRun.idempotency_key == key)
        .values(
            status="failed" if error is not None else "done",
            finished_at=now or _now(),
            last_error=None if error is None else error[:_ERROR_LIMIT],
        )
    )
    await session.commit()


async def run_once[T](
    sessions: async_sessionmaker[AsyncSession],
    job: str,
    key: str,
    work: Callable[[AsyncSession], Awaitable[T]],
    *,
    lock_timeout: timedelta = DEFAULT_LOCK_TIMEOUT,
) -> RunOutcome[T]:
    """Do `work` at most once successfully for (job, key).

    `work` gets its own session (committed by `work` itself when it succeeds). If it raises, the
    run is marked `failed` (so a retry can claim it again) and the exception propagates."""
    async with sessions() as session:
        if not await claim(session, job, key, lock_timeout=lock_timeout):
            return RunOutcome(skipped=True)
    try:
        async with sessions() as work_session:
            value = await work(work_session)
    except Exception as error:
        async with sessions() as session:
            await _finish(session, job, key, error=f"{type(error).__name__}: {error}")
        raise
    async with sessions() as session:
        await _finish(session, job, key, error=None)
    return RunOutcome(skipped=False, value=value)
