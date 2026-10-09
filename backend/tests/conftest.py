from collections.abc import AsyncIterator, Callable

import httpx
import pytest
from fastapi import FastAPI

from app.api.health import ReadinessCheck
from app.core.config import Settings
from app.main import create_app


def make_settings(**overrides: object) -> Settings:
    """Settings that ignore any local .env so tests never depend on developer secrets."""
    values: dict[str, object] = {"environment": "test", **overrides}
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


async def _ok() -> None:
    return None


@pytest.fixture
def app() -> FastAPI:
    checks: dict[str, ReadinessCheck] = {"database": _ok, "redis": _ok}
    return create_app(make_settings(), readiness_checks=checks)


@pytest.fixture
def client_for() -> Callable[[FastAPI], httpx.AsyncClient]:
    def build(application: FastAPI) -> httpx.AsyncClient:
        transport = httpx.ASGITransport(app=application, raise_app_exceptions=False)
        return httpx.AsyncClient(transport=transport, base_url="http://test")

    return build


@pytest.fixture
async def client(
    app: FastAPI, client_for: Callable[[FastAPI], httpx.AsyncClient]
) -> AsyncIterator[httpx.AsyncClient]:
    async with client_for(app) as c:
        yield c
