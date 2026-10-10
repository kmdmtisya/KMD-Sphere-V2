from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from opentelemetry.sdk.trace import SpanProcessor
from redis.asyncio import Redis

from app.api import health, metrics
from app.core.auth import JwksKeySource, TokenVerifier
from app.core.config import Settings, get_settings
from app.core.correlation import CorrelationIdMiddleware
from app.core.errors import register_exception_handlers
from app.core.http_protection import BodySizeLimitMiddleware, SecurityHeadersMiddleware
from app.core.logging import configure_logging
from app.core.ratelimit import (
    CounterStore,
    FallbackCounterStore,
    MemoryCounterStore,
    Policies,
    RateLimiter,
    RateLimitMiddleware,
    RedisCounterStore,
)
from app.core.telemetry import Telemetry
from app.db.session import Database
from app.modules.assets import api as assets_api
from app.modules.identity import api as identity_api
from app.modules.portfolio import api as portfolio_api
from app.modules.transactions import api as transactions_api


def create_app(
    settings: Settings | None = None,
    readiness_checks: dict[str, health.ReadinessCheck] | None = None,
    span_processors: Sequence[SpanProcessor] = (),
    token_verifier: TokenVerifier | None = None,
    rate_limit_store: CounterStore | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    db = Database(settings)
    telemetry = Telemetry(settings, span_processors)
    redis: Redis | None = None
    if rate_limit_store is None:
        if settings.rate_limit_storage == "memory":
            rate_limit_store = MemoryCounterStore()
        else:
            # Short timeouts: a slow Redis falls back to per-process limits, not slow requests.
            redis = Redis.from_url(
                settings.redis_url, socket_connect_timeout=0.25, socket_timeout=0.25
            )
            rate_limit_store = FallbackCounterStore(RedisCounterStore(redis))

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await db.dispose()
        if redis is not None:
            await redis.aclose()
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
        openapi_tags=[
            {"name": "health", "description": "Liveness and readiness probes"},
            {"name": "identity", "description": "The signed-in user, profile and preferences"},
            {
                "name": "assets",
                "description": "Asset classes, catalogue search and user-defined assets",
            },
            {"name": "portfolios", "description": "The signed-in user's portfolios"},
            {"name": "transactions", "description": "The append-only ledger of each portfolio"},
        ],
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
    app.state.token_verifier = token_verifier or _default_verifier(settings)
    policies = Policies.from_settings(settings)
    limiter = RateLimiter(rate_limit_store)
    app.state.rate_limiter = limiter if settings.rate_limit_enabled else None
    app.state.rate_limit_policies = policies
    # Added innermost first: headers wrap everything, so 413 and 429 answers carry them too.
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_request_body_bytes)
    if settings.rate_limit_enabled:
        app.add_middleware(RateLimitMiddleware, limiter=limiter, policies=policies)
    app.add_middleware(CorrelationIdMiddleware)
    if settings.cors_allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_allowed_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
            allow_headers=["Authorization", "Content-Type", "X-Correlation-ID"],
            expose_headers=["X-Correlation-ID", "Retry-After"],
            max_age=600,
        )
    app.add_middleware(SecurityHeadersMiddleware, hsts=settings.hsts_enabled)
    register_exception_handlers(app)
    app.include_router(health.router)
    app.include_router(metrics.router)
    app.include_router(identity_api.router)
    app.include_router(identity_api.risk_router)
    app.include_router(assets_api.classes_router)
    app.include_router(assets_api.router)
    app.include_router(portfolio_api.router)
    app.include_router(transactions_api.router)
    telemetry.instrument(app)
    return app


def _default_verifier(settings: Settings) -> TokenVerifier | None:
    """JWKS-backed verifier, or None (fail closed: every protected call is 401) if OIDC is not
    configured."""
    if not settings.oidc_issuer:
        return None
    return TokenVerifier(
        JwksKeySource(settings.jwks_url, cache_seconds=settings.jwks_cache_seconds),
        issuer=settings.oidc_issuer,
        audience=settings.oidc_audience,
        authorized_parties=settings.authorized_parties,
        leeway_seconds=settings.auth_leeway_seconds,
    )


app = create_app()
