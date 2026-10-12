"""A throwaway, fully migrated database per test module. Needs the compose stack or the CI service
container; skipped when no database credentials are configured."""

import asyncio
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import asyncpg
import pytest
from alembic import command
from alembic.config import Config

from app.core.config import Settings

BACKEND = Path(__file__).resolve().parents[1]


@asynccontextmanager
async def throwaway_database(base: Settings) -> AsyncIterator[Settings]:
    """A new database migrated to head, dropped on exit; yields settings pointing at it."""
    name = f"ws_test_{uuid.uuid4().hex[:12]}"
    admin = await asyncpg.connect(base.database_dsn, timeout=5)
    try:
        await admin.execute(f'CREATE DATABASE "{name}"')
    finally:
        await admin.close()
    settings = base.model_copy(
        update={
            "postgres_db": name,
            "oidc_issuer": "",
            "rate_limit_storage": "memory",
            "analytics_cache": "memory",
        }
    )
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    cfg.attributes["sqlalchemy_url"] = settings.sqlalchemy_url
    try:
        await asyncio.to_thread(command.upgrade, cfg, "head")
        yield settings
    finally:
        admin = await asyncpg.connect(base.database_dsn, timeout=5)
        try:
            await admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        finally:
            await admin.close()


@pytest.fixture(scope="module")
async def migrated_settings() -> AsyncIterator[Settings]:
    base = Settings(environment="test")
    if not base.postgres_user or not base.postgres_password.get_secret_value():
        pytest.skip("no database credentials configured")
    async with throwaway_database(base) as settings:
        yield settings
