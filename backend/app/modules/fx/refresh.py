"""Refreshing the reporting-currency rates (P11-T03.2-T03.4).

One refresh fetches every active currency against the pivot (DEC-27) in as few provider requests
as possible: each provider is asked, in the configured order (DEC-25), for the currencies the
previous ones could not supply, in one batch request when it can. A provider that fails is skipped
(fallback); bad data is never replaced by a guess; a currency no provider supplies stays missing.

At most one refresh runs per window (`fx_refresh_window_minutes`), whoever asks: the hourly job
and users pressing refresh share the window, so the provider is never called per screen or per
request. With a 15-minute window that is at most 4 requests an hour per provider, about 3,000 a
month, inside the 30,000 of the commercial plan (checked by a test). Retries with exponential
backoff happen inside a refresh (the resilient provider) and across refreshes (the job)."""

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.fx.models import Currency
from app.modules.market_data.models import FxRate
from app.modules.market_data.providers.base import MarketDataProvider
from app.modules.market_data.providers.batch import fetch_fx_batch
from app.modules.market_data.providers.errors import ProviderError, ProviderUnavailable
from app.modules.market_data.providers.models import FxQuote
from app.worker.idempotency import run_once

JOB = "fx_refresh"


@dataclass
class ProviderAttempt:
    provider: str
    stored: int = 0
    duplicates: int = 0
    supplied: list[str] = field(default_factory=list)
    unsupported: list[str] = field(default_factory=list)
    # The error class only (never its text, which could carry vendor details).
    error: str | None = None


@dataclass
class RefreshOutcome:
    pivot: str
    attempts: list[ProviderAttempt]
    missing: list[str]

    @property
    def stored(self) -> int:
        return sum(a.stored for a in self.attempts)

    @property
    def every_provider_failed(self) -> bool:
        return bool(self.attempts) and all(a.error for a in self.attempts)


@dataclass(frozen=True)
class CoalescedRefresh:
    """`ran` is False when another refresh already ran in this window."""

    ran: bool
    window: str
    outcome: RefreshOutcome | None


async def active_currencies(session: AsyncSession) -> list[str]:
    rows = await session.execute(
        select(Currency.code).where(Currency.is_active.is_(True)).order_by(Currency.code)
    )
    return list(rows.scalars())


def _row(rate: FxQuote) -> dict[str, object]:
    return {
        "base_currency": rate.base,
        "quote_currency": rate.quote,
        "rate": rate.rate,
        "provider": rate.provenance.provider,
        "rate_timestamp": rate.provenance.as_of,
        "retrieved_at": rate.provenance.retrieved_at,
        "rate_type": rate.rate_type,
        "rate_path": list(rate.path) if rate.path else None,
    }


async def store_rates(session: AsyncSession, rates: list[FxQuote]) -> tuple[int, int]:
    """Stores rates once per (pair, provider, timestamp); returns (stored, duplicates)."""
    if not rates:
        return 0, 0
    stmt = (
        insert(FxRate)
        .values([_row(r) for r in rates])
        .on_conflict_do_nothing(constraint="uq_fx_rates_pair_provider_timestamp")
        .returning(FxRate.id)
    )
    stored = len((await session.execute(stmt)).all())
    await session.commit()
    return stored, len(rates) - stored


async def refresh_rates(
    session: AsyncSession,
    sources: tuple[MarketDataProvider, ...],
    pivot: str,
    currencies: list[str],
) -> RefreshOutcome:
    remaining = [c for c in dict.fromkeys(currencies) if c != pivot]
    attempts: list[ProviderAttempt] = []
    for source in sources:
        if not remaining:
            break
        attempt = ProviderAttempt(source.name)
        attempts.append(attempt)
        try:
            batch = await fetch_fx_batch(source, pivot, remaining)
        except ProviderError as error:
            attempt.error = type(error).__name__
            continue
        usable = [r for r in batch.rates if r.base == pivot and r.quote in remaining]
        attempt.stored, attempt.duplicates = await store_rates(session, usable)
        attempt.supplied = sorted(r.quote for r in usable)
        attempt.unsupported = sorted(batch.unsupported)
        remaining = [c for c in remaining if c not in set(attempt.supplied)]
    return RefreshOutcome(pivot, attempts, remaining)


def window_key(now: datetime, minutes: int) -> str:
    """The refresh window `now` falls in, e.g. 2026-10-12T21:45 for 15-minute windows."""
    floored = now.replace(minute=now.minute - now.minute % minutes, second=0, microsecond=0)
    return floored.strftime("%Y-%m-%dT%H:%M")


async def refresh_once_per_window(
    sessions: async_sessionmaker[AsyncSession],
    sources: tuple[MarketDataProvider, ...],
    pivot: str,
    now: datetime,
    window_minutes: int,
) -> CoalescedRefresh:
    """Runs a refresh unless one already ran in this window. When every provider fails, the
    window is released (so a retry may run) and `ProviderUnavailable` is raised."""
    # One refresh per window and pivot (a deployment has one pivot; tests use their own).
    key = f"{pivot}:{window_key(now, window_minutes)}"

    async def work(session: AsyncSession) -> RefreshOutcome:
        outcome = await refresh_rates(session, sources, pivot, await active_currencies(session))
        if outcome.every_provider_failed:
            raise ProviderUnavailable("every FX provider failed")
        return outcome

    run = await run_once(sessions, JOB, key, work)
    return CoalescedRefresh(not run.skipped, key, run.value)
