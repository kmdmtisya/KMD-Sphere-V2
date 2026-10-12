"""/api/v1/fx: the reporting-currency rates and their status, and a user-triggered refresh
(P11-T03). Reads never call a provider; a refresh calls one at most once per window, whoever
asks, and each user may ask a few times an hour."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api_responses import UNAUTHORIZED
from app.core.config import Settings
from app.core.ratelimit import RateLimit, RateLimitedError
from app.db.session import get_session
from app.modules.fx.board import RateBoard, invalidate
from app.modules.fx.refresh import refresh_once_per_window
from app.modules.fx.schemas import (
    FxProviderAttemptOut,
    FxRateLineOut,
    FxRefreshOut,
    FxStatusOut,
)
from app.modules.fx.status import StatusPolicy
from app.modules.identity.dependencies import CurrentUserDep
from app.modules.market_data.providers.errors import ProviderUnavailable
from app.modules.market_data.providers.registry import build_providers

router = APIRouter(prefix="/api/v1/fx", tags=["fx"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def _status(request: Request, session: AsyncSession) -> FxStatusOut:
    settings: Settings = request.app.state.settings
    board = RateBoard(
        session,
        StatusPolicy.from_settings(settings),
        getattr(request.app.state, "cache_store", None),
        settings.fx_status_cache_seconds,
    )
    now = datetime.now(UTC)
    lines = await board.lines(settings.fx_pivot_currency, now)
    return FxStatusOut(
        pivot_currency=settings.fx_pivot_currency,
        checked_at=now,
        rates=[
            FxRateLineOut(
                currency=line.currency,
                status=line.status.value,
                rate=line.rate,
                provider=line.provider,
                rate_type=line.rate_type,
                rate_timestamp=line.rate_timestamp,
                retrieved_at=line.retrieved_at,
                path=line.path,
                age_seconds=line.age_seconds,
            )
            for line in lines
        ],
    )


@router.get(
    "/status",
    response_model=FxStatusOut,
    summary="Reporting-currency rates and their freshness",
    responses=UNAUTHORIZED,
)
async def fx_status(request: Request, user: CurrentUserDep, session: SessionDep) -> FxStatusOut:
    """The latest stored rate of every supported currency against the pivot currency, with the
    provider, the kind of rate, when it was published and fetched, and its status. Cached rates
    are never labelled current; a currency without any rate is `unavailable`."""
    return await _status(request, session)


@router.post(
    "/refresh",
    response_model=FxRefreshOut,
    summary="Ask for fresh rates",
    responses=UNAUTHORIZED,
)
async def fx_refresh(request: Request, user: CurrentUserDep, session: SessionDep) -> FxRefreshOut:
    """Fetches new rates unless a refresh already ran in the current window (then the stored
    rates are returned and no provider is called). Each user may ask a few times an hour. When
    every provider fails, the last stored rates are returned with their status and age; no rate
    is ever invented."""
    settings: Settings = request.app.state.settings
    limiter = request.app.state.rate_limiter
    if limiter is not None:
        decision = await limiter.hit(
            RateLimit("fx_refresh", settings.fx_refresh_per_user_per_hour, 3600), str(user.id)
        )
        if not decision.allowed:
            raise RateLimitedError(decision.retry_after)

    # Tests (and later a shared instance) may provide the providers; otherwise from settings.
    providers = getattr(request.app.state, "market_providers", None) or build_providers(settings)
    attempts: list[FxProviderAttemptOut] = []
    missing: list[str] = []
    refreshed = False
    window = ""
    try:
        run = await refresh_once_per_window(
            request.app.state.db.session_factory,
            providers.fx_sources,
            settings.fx_pivot_currency,
            datetime.now(UTC),
            settings.fx_refresh_window_minutes,
        )
        refreshed, window = run.ran, run.window
        if run.outcome is not None:
            attempts = [
                FxProviderAttemptOut(
                    provider=a.provider,
                    supplied=a.supplied,
                    unsupported=a.unsupported,
                    failed=a.error is not None,
                )
                for a in run.outcome.attempts
            ]
            missing = run.outcome.missing
            await invalidate(getattr(request.app.state, "cache_store", None))
    except ProviderUnavailable:
        refreshed = False
        attempts = [
            FxProviderAttemptOut(provider=p.name, supplied=[], unsupported=[], failed=True)
            for p in providers.fx_sources
        ]
    return FxRefreshOut(
        refreshed=refreshed,
        window=window,
        attempts=attempts,
        missing=missing,
        status=await _status(request, session),
    )
