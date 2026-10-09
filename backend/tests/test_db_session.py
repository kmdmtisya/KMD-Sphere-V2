import httpx
import pytest
from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.session import Database, get_session
from app.main import create_app
from tests.conftest import make_settings


def test_engine_is_created_lazily() -> None:
    db = Database(make_settings(postgres_user="u", postgres_password="s3cr3t-pw", postgres_db="d"))
    assert db._engine is None
    assert str(db.engine.url.drivername) == "postgresql+asyncpg"
    assert "s3cr3t-pw" not in str(db.engine.url)  # the URL repr masks the password


def test_sqlalchemy_url_uses_asyncpg_driver() -> None:
    s = make_settings(postgres_user="u", postgres_password="p@ss", postgres_db="d")
    assert s.sqlalchemy_url == "postgresql+asyncpg://u:p%40ss@127.0.0.1:5433/d"


async def test_dispose_is_safe_without_use_and_idempotent() -> None:
    db = Database(make_settings())
    await db.dispose()
    await db.dispose()


@pytest.mark.integration
async def test_session_dependency_runs_queries_and_rolls_back_on_error() -> None:
    settings = Settings(environment="test")
    if not settings.postgres_user or not settings.postgres_password.get_secret_value():
        pytest.skip("no database credentials configured")
    app: FastAPI = create_app(settings, readiness_checks={})

    @app.get("/_db")
    async def probe(session: AsyncSession = Depends(get_session)) -> dict[str, int]:  # noqa: B008
        return {"value": (await session.execute(text("SELECT 41 + 1"))).scalar_one()}

    @app.get("/_db_fail")
    async def failing(session: AsyncSession = Depends(get_session)) -> None:  # noqa: B008
        await session.execute(text("SELECT 1"))
        raise RuntimeError("boom")

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        ok = await c.get("/_db")
        bad = await c.get("/_db_fail")
        again = await c.get("/_db")  # pool still healthy after the failed request
    assert ok.json() == {"value": 42}
    assert bad.status_code == 500
    assert again.json() == {"value": 42}
    await app.state.db.dispose()
