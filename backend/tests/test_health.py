import asyncio
from collections.abc import Callable

import httpx
from fastapi import FastAPI

from app.api.health import ReadinessCheck
from app.main import create_app
from tests.conftest import make_settings


async def test_live_returns_ok(client: httpx.AsyncClient) -> None:
    response = await client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_ready_ok_when_all_checks_pass(client: httpx.AsyncClient) -> None:
    response = await client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "checks": {"database": "ok", "redis": "ok"}}


async def test_ready_503_when_a_dependency_fails_and_no_detail_leaks(
    client_for: Callable[[FastAPI], httpx.AsyncClient],
) -> None:
    async def ok() -> None:
        return None

    async def broken() -> None:
        raise ConnectionError("password authentication failed for user secret-user at db.internal")

    checks: dict[str, ReadinessCheck] = {"database": broken, "redis": ok}
    app = create_app(make_settings(), readiness_checks=checks)
    async with client_for(app) as c:
        response = await c.get("/health/ready")
    assert response.status_code == 503
    body = response.json()
    assert body == {"status": "not_ready", "checks": {"database": "failed", "redis": "ok"}}
    assert "secret-user" not in response.text
    assert "db.internal" not in response.text


async def test_ready_503_when_a_check_times_out(
    client_for: Callable[[FastAPI], httpx.AsyncClient],
) -> None:
    async def hangs() -> None:
        await asyncio.sleep(30)

    app = create_app(
        make_settings(readiness_timeout_seconds=0.05), readiness_checks={"database": hangs}
    )
    async with client_for(app) as c:
        response = await c.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["checks"] == {"database": "failed"}


async def test_default_checks_fail_closed_without_credentials(
    client_for: Callable[[FastAPI], httpx.AsyncClient],
) -> None:
    # No readiness_checks override: the real checks run against an unreachable port and
    # empty credentials, so the service must report not_ready rather than pretending.
    app = create_app(make_settings(postgres_port=1, redis_port=1, readiness_timeout_seconds=0.2))
    async with client_for(app) as c:
        response = await c.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["checks"] == {"database": "failed", "redis": "failed"}
