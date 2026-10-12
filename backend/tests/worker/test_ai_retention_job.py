"""The daily conversation purge job (P10-T07): past-retention deletion, once a day."""

import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.worker.tasks as tasks
from app.core.config import Settings
from app.worker.celery_app import celery_app
from app.worker.db import run_async
from app.worker.schedule import build_schedule
from tests.db_fixtures import migrated_settings  # noqa: F401

pytestmark = pytest.mark.integration


@pytest.fixture
async def factory(
    migrated_settings: Settings,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(migrated_settings.sqlalchemy_url)
    monkeypatch.setattr(tasks, "run_async", lambda work: run_async(work, migrated_settings))
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


async def test_the_purge_job_deletes_only_expired_conversations_and_runs_once_a_day(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    user, old, fresh = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    now = datetime.now(UTC)
    async with factory() as s:
        await s.execute(
            text("INSERT INTO users (id, issuer, subject) VALUES (:u, 'https://purge.test', :sub)"),
            {"u": user, "sub": str(user)},
        )
        for cid, age in ((old, 120), (fresh, 5)):
            await s.execute(
                text("INSERT INTO ai_conversations (id, user_id, updated_at) VALUES (:c, :u, :t)"),
                {"c": cid, "u": user, "t": now - timedelta(days=age)},
            )
            await s.execute(
                text(
                    "INSERT INTO ai_messages (conversation_id, user_id, position, role, content) "
                    "VALUES (:c, :u, 1, 'user', 'hello')"
                ),
                {"c": cid, "u": user},
            )
        await s.commit()

    day = f"purge-test-{uuid.uuid4()}"
    first = await asyncio.to_thread(tasks.purge_ai_conversations_job.apply, args=(day,))
    assert first.get()["removed"] >= 1
    again = await asyncio.to_thread(tasks.purge_ai_conversations_job.apply, args=(day,))
    assert again.get() == {"skipped": True}

    async with factory() as s:
        rows = (
            await s.execute(text("SELECT id FROM ai_conversations WHERE user_id = :u"), {"u": user})
        ).all()
        assert [r.id for r in rows] == [fresh]
        await s.execute(text("DELETE FROM users WHERE id = :u"), {"u": user})
        await s.commit()


def test_the_purge_is_scheduled_daily() -> None:
    entry = build_schedule()["ai-conversation-purge"]
    assert entry["task"] == "app.worker.tasks.purge_ai_conversations"
    assert entry["task"] in celery_app.tasks
