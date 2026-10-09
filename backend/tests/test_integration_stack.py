"""Runs against the docker compose stack (make up) or CI service containers.

Skipped automatically when no PostgreSQL credentials are configured.
"""

import httpx
import pytest

from app.core.config import Settings
from app.main import create_app

pytestmark = pytest.mark.integration


async def test_ready_against_real_postgres_and_redis() -> None:
    settings = Settings(environment="test")  # reads the environment and the root .env
    if not settings.postgres_user or not settings.postgres_password.get_secret_value():
        pytest.skip("no database credentials configured")
    app = create_app(settings)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        response = await c.get("/health/ready")
    assert response.status_code == 200, response.text
    assert response.json() == {"status": "ready", "checks": {"database": "ok", "redis": "ok"}}
