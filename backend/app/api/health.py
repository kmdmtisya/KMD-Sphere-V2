"""Liveness and readiness endpoints (unauthenticated, no sensitive detail)."""

import asyncio
import logging
from collections.abc import Awaitable, Callable

import asyncpg
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from redis.asyncio import Redis

from app.core.config import Settings

logger = logging.getLogger(__name__)
ReadinessCheck = Callable[[], Awaitable[None]]
router = APIRouter(tags=["health"])


def default_checks(settings: Settings) -> dict[str, ReadinessCheck]:
    async def database() -> None:
        conn = await asyncpg.connect(
            settings.database_dsn, timeout=settings.readiness_timeout_seconds
        )
        try:
            await conn.execute("SELECT 1")
        finally:
            await conn.close()

    async def redis() -> None:
        client = Redis.from_url(
            settings.redis_url, socket_connect_timeout=settings.readiness_timeout_seconds
        )
        try:
            await client.ping()
        finally:
            await client.aclose()

    return {"database": database, "redis": redis}


@router.get("/health/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
async def ready(request: Request) -> JSONResponse:
    settings: Settings = request.app.state.settings
    checks: dict[str, ReadinessCheck] = request.app.state.readiness_checks

    async def run(name: str, check: ReadinessCheck) -> tuple[str, bool]:
        try:
            await asyncio.wait_for(check(), timeout=settings.readiness_timeout_seconds + 1)
        except Exception:
            # Detail goes to the log only; the response never reveals hosts or credentials.
            logger.warning("readiness check failed", extra={"check": name}, exc_info=True)
            return name, False
        return name, True

    results = dict(await asyncio.gather(*(run(n, c) for n, c in checks.items())))
    ok = all(results.values())
    return JSONResponse(
        {
            "status": "ready" if ok else "not_ready",
            "checks": {n: "ok" if v else "failed" for n, v in results.items()},
        },
        status_code=200 if ok else 503,
    )
