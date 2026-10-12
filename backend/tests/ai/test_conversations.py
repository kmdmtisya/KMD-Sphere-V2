"""Stored conversations (P10-T07): user-scoped messages and tool calls, deletion, retention."""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import asyncpg
import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.conversations.service import ConversationService, RecordedToolCall
from app.core.authz import ResourceNotFoundError
from app.core.config import Settings
from app.core.errors import InvalidValueError
from app.main import create_app
from tests import auth_helpers as ah
from tests.authz_harness import TwoUsers, two_users  # noqa: F401
from tests.db_fixtures import migrated_settings  # noqa: F401

pytestmark = [pytest.mark.integration, pytest.mark.security]
CALL = RecordedToolCall("get_net_worth", "a" * 64, True, None, 12, "corr-1")


@pytest.fixture(scope="module")
async def app(migrated_settings: Settings) -> AsyncIterator[FastAPI]:  # noqa: F811
    application = create_app(migrated_settings, readiness_checks={}, token_verifier=ah.verifier())
    yield application
    await application.state.db.dispose()


@pytest.fixture
async def http(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def raw(migrated_settings: Settings) -> AsyncIterator[asyncpg.Connection]:  # noqa: F811
    conn = await asyncpg.connect(migrated_settings.database_dsn, timeout=5)
    yield conn
    await conn.close()


@pytest.fixture
async def session(app: FastAPI) -> AsyncIterator[AsyncSession]:
    sessions: async_sessionmaker[AsyncSession] = app.state.db.session_factory
    async with sessions() as s:
        yield s


def uid(value: str) -> uuid.UUID:
    return uuid.UUID(value)


async def test_a_conversation_keeps_its_messages_in_order(
    session: AsyncSession,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    service = ConversationService(session)
    alice = uid(two_users.alice.id)
    conversation = await service.create(alice, title="Net worth")
    await service.append(alice, conversation.id, "user", "What is my net worth?")
    answer = await service.append(
        alice,
        conversation.id,
        "assistant",
        "Here it is.",
        structured={"observed": []},
        model="fake-1",
        provider="fake",
    )
    await service.record_tool_call(alice, conversation.id, CALL, answer.id)
    await session.commit()

    messages = await service.messages(alice, conversation.id)
    assert [(m.position, m.role) for m in messages] == [(1, "user"), (2, "assistant")]
    assert messages[1].structured == {"observed": []}
    calls = await service.tool_calls(alice, conversation.id)
    assert [(c.tool_name, c.status, c.message_id) for c in calls] == [
        ("get_net_worth", "ok", answer.id)
    ]
    assert [m.position for m in await service.messages(alice, conversation.id, limit=1)] == [2]


async def test_bob_cannot_reach_alices_conversation(
    session: AsyncSession,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    service = ConversationService(session)
    alice, bob = uid(two_users.alice.id), uid(two_users.bob.id)
    conversation = await service.create(alice)
    await service.append(alice, conversation.id, "user", "private question")
    await session.commit()

    for attempt in (
        service.get(bob, conversation.id),
        service.messages(bob, conversation.id),
        service.tool_calls(bob, conversation.id),
        service.append(bob, conversation.id, "user", "injected"),
        service.record_tool_call(bob, conversation.id, CALL),
        service.delete(bob, conversation.id),
    ):
        with pytest.raises(ResourceNotFoundError):
            await attempt
    assert await service.recent(bob) == []
    assert len(await service.messages(alice, conversation.id)) == 1


async def test_the_user_can_delete_one_conversation_or_all(
    session: AsyncSession,
    raw: asyncpg.Connection,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    service = ConversationService(session)
    alice, bob = uid(two_users.alice.id), uid(two_users.bob.id)
    first, second, bobs = (
        await service.create(alice),
        await service.create(alice),
        await service.create(bob),
    )
    for c, owner in ((first, alice), (second, alice), (bobs, bob)):
        message = await service.append(owner, c.id, "user", "hello")
        await service.record_tool_call(owner, c.id, CALL, message.id)
    await session.commit()

    await service.delete(alice, first.id)
    await session.commit()
    assert [c.id for c in await service.recent(alice)] == [second.id]
    assert (
        await raw.fetchval("SELECT count(*) FROM ai_messages WHERE conversation_id = $1", first.id)
        == 0
    )
    assert (
        await raw.fetchval(
            "SELECT count(*) FROM ai_tool_calls WHERE conversation_id = $1", first.id
        )
        == 0
    )

    assert await service.delete_all(alice) == 1
    await session.commit()
    assert await service.recent(alice) == []
    assert [c.id for c in await service.recent(bob)] == [bobs.id]


async def test_retention_removes_only_conversations_past_the_period(
    session: AsyncSession,
    raw: asyncpg.Connection,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    service = ConversationService(session)
    alice = uid(two_users.alice.id)
    old, fresh, edge = (
        await service.create(alice),
        await service.create(alice),
        await service.create(alice),
    )
    for c in (old, fresh, edge):
        await service.append(alice, c.id, "user", "hello")
    await session.commit()
    now = datetime.now(UTC)
    for c, age in ((old, 91), (edge, 89)):
        await raw.execute(
            "UPDATE ai_conversations SET updated_at = $1 WHERE id = $2",
            now - timedelta(days=age),
            c.id,
        )

    removed = await service.purge_expired(now, retention_days=90)
    await session.commit()
    kept = {c.id for c in await service.recent(alice)}
    assert removed >= 1
    assert old.id not in kept
    assert {fresh.id, edge.id} <= kept
    assert (
        await raw.fetchval("SELECT count(*) FROM ai_messages WHERE conversation_id = $1", old.id)
        == 0
    )

    # A shorter period reaches the 89-day-old one too.
    await service.purge_expired(now, retention_days=30)
    await session.commit()
    assert edge.id not in {c.id for c in await service.recent(alice)}


async def test_a_new_message_extends_the_retention_clock(
    session: AsyncSession,
    raw: asyncpg.Connection,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    service = ConversationService(session)
    alice = uid(two_users.alice.id)
    c = await service.create(alice)
    await service.append(alice, c.id, "user", "first")
    await session.commit()
    now = datetime.now(UTC)
    await raw.execute(
        "UPDATE ai_conversations SET updated_at = $1 WHERE id = $2", now - timedelta(days=200), c.id
    )
    await service.append(alice, c.id, "assistant", "second")
    await session.commit()
    await service.purge_expired(now, retention_days=90)
    await session.commit()
    assert c.id in {x.id for x in await service.recent(alice)}


async def test_messages_are_validated(
    session: AsyncSession,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    service = ConversationService(session)
    alice = uid(two_users.alice.id)
    c = await service.create(alice)
    for role, content in (("system", "x"), ("user", ""), ("user", "x" * 20_001)):
        with pytest.raises(InvalidValueError):
            await service.append(alice, c.id, role, content)


async def test_a_tool_call_row_holds_no_arguments_or_results(raw: asyncpg.Connection) -> None:
    columns = {
        r["column_name"]
        for r in await raw.fetch(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'ai_tool_calls'"
        )
    }
    assert columns == {
        "id",
        "conversation_id",
        "message_id",
        "user_id",
        "tool_name",
        "arguments_hash",
        "status",
        "error_code",
        "duration_ms",
        "correlation_id",
        "created_at",
    }


async def test_deleting_the_account_removes_the_history(
    session: AsyncSession,
    raw: asyncpg.Connection,
    http: httpx.AsyncClient,
) -> None:
    from tests.authz_harness import make_user

    user = await make_user(http, "carol")
    service = ConversationService(session)
    c = await service.create(uid(user.id))
    await service.append(uid(user.id), c.id, "user", "hello")
    await session.commit()
    await raw.execute("DELETE FROM users WHERE id = $1", uid(user.id))
    assert await raw.fetchval("SELECT count(*) FROM ai_conversations WHERE id = $1", c.id) == 0
    assert (
        await raw.fetchval("SELECT count(*) FROM ai_messages WHERE user_id = $1", uid(user.id)) == 0
    )


def test_the_retention_period_is_configurable_and_defaults_to_ninety_days() -> None:
    assert Settings().ai_conversation_retention_days == 90
    assert Settings(ai_conversation_retention_days=30).ai_conversation_retention_days == 30
    with pytest.raises(ValueError):
        Settings(ai_conversation_retention_days=0)
