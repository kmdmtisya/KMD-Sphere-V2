from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import health
from app.core.config import Settings, get_settings
from app.core.correlation import CorrelationIdMiddleware
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.db.session import Database


def create_app(
    settings: Settings | None = None,
    readiness_checks: dict[str, health.ReadinessCheck] | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    db = Database(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await db.dispose()

    app = FastAPI(
        lifespan=lifespan,
        title="WealthSphere API",
        version="0.1.0",
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
    )
    app.state.settings = settings
    app.state.db = db
    app.state.readiness_checks = (
        readiness_checks if readiness_checks is not None else health.default_checks(settings)
    )
    app.add_middleware(CorrelationIdMiddleware)
    register_exception_handlers(app)
    app.include_router(health.router)
    return app


app = create_app()
