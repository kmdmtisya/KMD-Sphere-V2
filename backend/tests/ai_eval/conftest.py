"""Fixtures of the AI evaluation suite and the results file written at the end of a run."""

from collections.abc import AsyncIterator

import asyncpg
import httpx
import pytest
from fastapi import FastAPI

from app.ai.providers.fake import FakeLlmProvider
from app.core.config import Settings
from app.main import create_app
from tests import auth_helpers as ah
from tests.ai_eval.harness import RECORDER, write_results
from tests.db_fixtures import migrated_settings  # noqa: F401


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    if RECORDER.outcomes:
        write_results()


@pytest.fixture
def llm() -> FakeLlmProvider:
    return FakeLlmProvider()


@pytest.fixture
async def app(migrated_settings: Settings, llm: FakeLlmProvider) -> AsyncIterator[FastAPI]:  # noqa: F811
    settings = migrated_settings.model_copy(
        update={
            "rate_limit_enabled": False,
            "ai_tool_calls_per_minute": 100_000,
            "ai_questions_per_day": 100_000,
        }
    )
    application = create_app(settings, readiness_checks={}, token_verifier=ah.verifier(), llm=llm)
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
