"""Migration pipeline tests.

The single-head test needs no database. The round-trip test creates a throwaway database on the
configured server (needs CREATEDB, available in the compose stack and CI service container),
runs upgrade -> check -> downgrade -> upgrade, and always drops the database afterwards.
"""

import uuid
from collections.abc import AsyncIterator
from decimal import Decimal
from pathlib import Path

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import Settings

BACKEND = Path(__file__).resolve().parents[1]


def _config(url: str | None = None) -> Config:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    if url:
        cfg.attributes["sqlalchemy_url"] = url
    return cfg


def test_there_is_exactly_one_migration_head() -> None:
    heads = ScriptDirectory.from_config(_config()).get_heads()
    assert len(heads) == 1, f"multiple Alembic heads: {heads}; merge them before committing"


def test_baseline_is_the_only_root() -> None:
    script = ScriptDirectory.from_config(_config())
    assert script.get_bases() == ["0001"]


def test_migrations_do_not_embed_credentials() -> None:
    for path in (BACKEND / "migrations").rglob("*.py"):
        body = path.read_text(encoding="utf-8").lower()
        assert "postgresql://" not in body, path
        assert "password" not in body, path
    assert "sqlalchemy.url" not in (BACKEND / "alembic.ini").read_text(encoding="utf-8")


@pytest.fixture
async def scratch_db() -> AsyncIterator[str]:
    settings = Settings(environment="test")
    if not settings.postgres_user or not settings.postgres_password.get_secret_value():
        pytest.skip("no database credentials configured")
    name = f"ws_migtest_{uuid.uuid4().hex[:12]}"
    admin = await asyncpg.connect(settings.database_dsn, timeout=5)
    try:
        await admin.execute(f'CREATE DATABASE "{name}"')
    finally:
        await admin.close()
    try:
        yield settings.model_copy(update={"postgres_db": name}).sqlalchemy_url
    finally:
        admin = await asyncpg.connect(settings.database_dsn, timeout=5)
        try:
            await admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        finally:
            await admin.close()


@pytest.mark.integration
async def test_upgrade_check_downgrade_upgrade_round_trip(scratch_db: str) -> None:
    import asyncio

    cfg = _config(scratch_db)
    # Alembic's command API is synchronous and runs its own event loop, so run it in a thread.
    await asyncio.to_thread(command.upgrade, cfg, "head")
    await asyncio.to_thread(command.check, cfg)  # models and migrations agree

    engine = create_async_engine(scratch_db)
    try:
        async with engine.connect() as conn:
            version = (
                await conn.execute(text("SELECT version_num FROM alembic_version"))
            ).scalar_one()
            extensions = {
                row[0] for row in await conn.execute(text("SELECT extname FROM pg_extension"))
            }
        head = ScriptDirectory.from_config(_config()).get_current_head()
        assert version == head
        assert {"pgcrypto", "vector"} <= extensions
    finally:
        await engine.dispose()

    await asyncio.to_thread(command.downgrade, cfg, "base")
    engine = create_async_engine(scratch_db)
    try:
        async with engine.connect() as conn:
            remaining = (
                await conn.execute(text("SELECT count(*) FROM alembic_version"))
            ).scalar_one()
        assert remaining == 0
    finally:
        await engine.dispose()

    await asyncio.to_thread(command.upgrade, cfg, "head")


@pytest.mark.integration
async def test_0007_copies_existing_income_entries(scratch_db: str) -> None:
    """Income entries posted before income_events existed are copied in; a reversed one and
    its reversal are not, nor are other entry types."""
    import asyncio

    cfg = _config(scratch_db)
    await asyncio.to_thread(command.upgrade, cfg, "0006")
    conn = await asyncpg.connect(scratch_db.replace("postgresql+asyncpg://", "postgresql://"))
    try:
        user = await conn.fetchval(
            "INSERT INTO users (issuer, subject) VALUES ('test', $1) RETURNING id", "u"
        )
        pid = await conn.fetchval(
            "INSERT INTO portfolios (user_id, name, base_currency) VALUES ($1, 'P', 'USD') "
            "RETURNING id",
            user,
        )

        async def entry(kind: str, gross: str, reverses: uuid.UUID | None = None) -> uuid.UUID:
            return uuid.UUID(
                str(
                    await conn.fetchval(
                        "INSERT INTO transactions (portfolio_id, transaction_type, trade_date, "
                        "gross_amount, taxes, currency, fx_rate_to_portfolio_currency, "
                        "created_by_user_id, reverses_transaction_id) "
                        "VALUES ($1, $2, DATE '2026-05-01', $3, 1.5, 'EUR', 1.1, $4, $5) "
                        "RETURNING id",
                        pid,
                        kind,
                        Decimal(gross),
                        user,
                        reverses,
                    )
                )
            )

        await entry("DEPOSIT", "1000")
        kept = await entry("INTEREST", "12.34")
        wrong = await entry("INTEREST", "99")
        await entry("INTEREST", "99", reverses=wrong)
    finally:
        await conn.close()

    await asyncio.to_thread(command.upgrade, cfg, "head")
    conn = await asyncpg.connect(scratch_db.replace("postgresql+asyncpg://", "postgresql://"))
    try:
        rows = await conn.fetch("SELECT * FROM income_events")
    finally:
        await conn.close()
    assert len(rows) == 1
    row = rows[0]
    assert (row["transaction_id"], row["portfolio_id"], row["income_type"]) == (
        kept,
        pid,
        "INTEREST",
    )
    assert (str(row["gross"]), str(row["taxes"]), row["currency"], str(row["fx_rate"])) == (
        "12.34000000",
        "1.50000000",
        "EUR",
        "1.100000000000",
    )
    assert str(row["paid_on"]) == "2026-05-01" and row["asset_id"] is None

    await asyncio.to_thread(command.downgrade, cfg, "0006")
    conn = await asyncpg.connect(scratch_db.replace("postgresql+asyncpg://", "postgresql://"))
    try:
        assert await conn.fetchval("SELECT to_regclass('income_events')") is None
    finally:
        await conn.close()
