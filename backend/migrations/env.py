"""Alembic environment (async). The URL comes from application settings or, for tests and
tooling, from `config.attributes["sqlalchemy_url"]`."""

import asyncio
import re
from logging.config import fileConfig
from typing import Any

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings
from app.db.base import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# Import every module's models here so autogenerate and `alembic check` see them.
import app.ai.conversations.models  # noqa: E402
import app.core.audit  # noqa: E402
import app.modules.alerts.models  # noqa: E402
import app.modules.assets.models  # noqa: E402
import app.modules.forex.instruments.models  # noqa: E402
import app.modules.forex.marketdata.models  # noqa: E402
import app.modules.fx.models  # noqa: E402
import app.modules.fx.snapshot  # noqa: E402
import app.modules.goals.models  # noqa: E402
import app.modules.identity.models  # noqa: E402
import app.modules.market_data.models  # noqa: E402
import app.modules.networth.models  # noqa: E402
import app.modules.notifications.models  # noqa: E402
import app.modules.opportunities.models  # noqa: E402
import app.modules.portfolio.models  # noqa: E402
import app.modules.research.models  # noqa: E402
import app.modules.transactions.models  # noqa: E402
import app.modules.universe.models  # noqa: E402
import app.worker.models  # noqa: E402, F401

target_metadata = Base.metadata

# Partitions of the forex time series are made by a job, not by models (P13-T02.3).
_PARTITION = re.compile(r"^forex_(quotes|candles)_(default|p\d{6})$")


def _include_object(
    obj: Any, name: str | None, type_: str, reflected: bool, compare_to: Any
) -> bool:
    return not (type_ == "table" and reflected and name and _PARTITION.match(name))


def _url() -> str:
    override = config.attributes.get("sqlalchemy_url")
    return str(override) if override else get_settings().sqlalchemy_url


def run_migrations_offline() -> None:
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        include_object=_include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        include_object=_include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(_url(), poolclass=pool.NullPool)
    async with engine.connect() as connection:
        await connection.run_sync(_do_run)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
