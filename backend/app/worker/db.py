"""Database access from a Celery task. Tasks are synchronous; the data layer is async, so each
call runs in its own event loop with its own short-lived engine (no connection pool is shared
across loops, and a worker process never holds idle connections)."""

import asyncio
from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import Settings, get_settings

SessionFactory = async_sessionmaker[AsyncSession]


def run_async[T](
    work: Callable[[SessionFactory], Awaitable[T]], settings: Settings | None = None
) -> T:
    """Run `work(session_factory)` to completion and return its result."""
    cfg = settings or get_settings()

    async def _go() -> T:
        engine = create_async_engine(
            cfg.sqlalchemy_url,
            poolclass=NullPool,
            connect_args={"timeout": cfg.db_connect_timeout_seconds},
        )
        try:
            return await work(async_sessionmaker(engine, expire_on_commit=False))
        finally:
            await engine.dispose()

    return asyncio.run(_go())
