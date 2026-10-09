from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager

from fastapi import FastAPI
from opentelemetry.sdk.trace import SpanProcessor

from app.api import health, metrics
from app.core.config import Settings, get_settings
from app.core.correlation import CorrelationIdMiddleware
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.telemetry import Telemetry
from app.db.session import Database


def create_app(
    settings: Settings | None = None,
    readiness_checks: dict[str, health.ReadinessCheck] | None = None,
    span_processors: Sequence[SpanProcessor] = (),
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    db = Database(settings)
    telemetry = Telemetry(settings, span_processors)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await db.dispose()
        telemetry.shutdown()

    app = FastAPI(
        lifespan=lifespan,
        title="WealthSphere API",
        version="0.1.0",
        summary="Portfolio and wealth intelligence API",
        description=(
            "Backend for the WealthSphere mobile apps. The backend is authoritative for all "
            "financial calculations. Money, quantities and rates are JSON strings. Errors use "
            "RFC 7807 problem+json and every response carries X-Correlation-ID."
        ),
        contact={"name": "WealthSphere", "url": "https://github.com/kmdmtisya/KMD-Sphere-V2"},
        servers=[{"url": "http://127.0.0.1:8000", "description": "Local development"}],
        openapi_tags=[{"name": "health", "description": "Liveness and readiness probes"}],
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
    )
    app.state.settings = settings
    app.state.db = db
    app.state.telemetry = telemetry
    app.state.readiness_checks = (
        readiness_checks if readiness_checks is not None else health.default_checks(settings)
    )
    app.add_middleware(CorrelationIdMiddleware)
    register_exception_handlers(app)
    app.include_router(health.router)
    app.include_router(metrics.router)
    telemetry.instrument(app)
    return app


app = create_app()
