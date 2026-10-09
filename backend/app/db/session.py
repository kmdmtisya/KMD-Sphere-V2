"""Async engine and session management."""

from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings


class Database:
    """Owns the async engine; created lazily so importing the app never opens connections."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._engine: AsyncEngine | None = None
        self._factory: async_sessionmaker[AsyncSession] | None = None

    @property
    def engine(self) -> AsyncEngine:
        if self._engine is None:
            self._engine = create_async_engine(
                self._settings.sqlalchemy_url,
                pool_size=self._settings.db_pool_size,
                max_overflow=self._settings.db_max_overflow,
                pool_pre_ping=True,
                connect_args={"timeout": self._settings.db_connect_timeout_seconds},
            )
        return self._engine

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        if self._factory is None:
            self._factory = async_sessionmaker(self.engine, expire_on_commit=False)
        return self._factory

    async def dispose(self) -> None:
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
            self._factory = None


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request, rolled back on error and always closed."""
    db: Database = request.app.state.db
    async with db.session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
