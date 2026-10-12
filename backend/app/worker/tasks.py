"""Registered jobs. Later tasks add theirs here (price and FX ingestion, alert evaluation)."""

import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime

import redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.alerts.evaluation import EvaluationResult, evaluate_alerts
from app.modules.market_data.ingestion import (
    IngestFailure,
    IngestResult,
    backfill_fx,
    backfill_prices,
    fx_pairs_needed,
    ingest_fx,
    ingest_quotes,
    market_assets,
)
from app.modules.market_data.providers.errors import ProviderUnavailable
from app.modules.market_data.providers.registry import build_providers
from app.modules.notifications.push import build_push_sender
from app.worker.celery_app import celery_app
from app.worker.db import SessionFactory, run_async
from app.worker.idempotency import run_once
from app.worker.jobs import JobTask

logger = logging.getLogger(__name__)

HEARTBEAT_KEY = "worker:heartbeat"
HEARTBEAT_TTL_SECONDS = 180


@celery_app.task(base=JobTask, name="app.worker.tasks.ping")
def ping() -> str:
    """The smallest possible job: proves a worker picks tasks up."""
    return "pong"


def write_heartbeat(client: redis.Redis, now: datetime | None = None) -> str:
    stamp = (now or datetime.now(UTC)).isoformat()
    client.set(HEARTBEAT_KEY, stamp, ex=HEARTBEAT_TTL_SECONDS)
    return stamp


@celery_app.task(base=JobTask, name="app.worker.tasks.heartbeat")
def heartbeat() -> str:
    """Writes the current time to Redis. If it expires, the worker or beat is not running."""
    cfg = get_settings()
    client = redis.Redis(
        host=cfg.redis_host,
        port=cfg.redis_port,
        password=cfg.redis_password.get_secret_value() or None,
        socket_timeout=5,
        decode_responses=True,
    )
    try:
        return write_heartbeat(client)
    finally:
        client.close()


# ------------------------------------------------------------------------------ market data
# Each job claims an idempotency key first (job_runs), so a repeated or overlapping run does
# nothing; the stores themselves are ON CONFLICT DO NOTHING, so even a crash between the work
# and the claim being marked done cannot duplicate a price.


def _bucket(now: datetime, minutes: int) -> str:
    floored = now.replace(minute=now.minute - now.minute % minutes, second=0, microsecond=0)
    return floored.strftime("%Y-%m-%dT%H:%M")


async def _guarded(
    sessions: SessionFactory,
    job: str,
    key: str,
    work: Callable[[AsyncSession], Awaitable[IngestResult]],
) -> dict[str, object]:
    async def run(session: AsyncSession) -> IngestResult:
        result = await work(session)
        if result.attempted_all_and_failed:
            # Probably an outage: fail the run so it is retried, rather than report success.
            first = result.failures[0]
            raise ProviderUnavailable(
                f"all {len(result.failures)} ingestions failed (first: {first.subject}: "
                f"{first.error_type})"
            )
        return result

    outcome = await run_once(sessions, job, key, run)
    if outcome.skipped or outcome.value is None:
        return {"skipped": True}
    result = outcome.value
    if result.failures:
        logger.warning("%s: %d of the items failed", job, len(result.failures))
    return {
        "stored": result.stored,
        "duplicates": result.duplicates,
        "failed": len(result.failures),
    }


@celery_app.task(base=JobTask, name="app.worker.tasks.ingest_prices")
def ingest_prices(bucket: str | None = None) -> dict[str, object]:
    """Latest quotes of every market-valued asset that has a provider."""
    providers = build_providers(get_settings())
    if not providers.by_kind:
        return {"skipped": "no price provider configured"}
    key = bucket or _bucket(datetime.now(UTC), 15)

    async def go(sessions: SessionFactory) -> dict[str, object]:
        return await _guarded(
            sessions, "ingest_prices", key, lambda s: ingest_quotes(s, providers.by_kind)
        )

    return run_async(go)


@celery_app.task(base=JobTask, name="app.worker.tasks.ingest_fx")
def ingest_fx_job(day: str | None = None) -> dict[str, object]:
    """Latest FX rates for the pairs the portfolios need."""
    fx = build_providers(get_settings()).fx
    if fx is None:
        return {"skipped": "no FX provider configured"}
    key = day or datetime.now(UTC).date().isoformat()

    async def go(sessions: SessionFactory) -> dict[str, object]:
        async def work(session: AsyncSession) -> IngestResult:
            return await ingest_fx(session, fx, await fx_pairs_needed(session))

        return await _guarded(sessions, "ingest_fx", key, work)

    return run_async(go)


@celery_app.task(base=JobTask, name="app.worker.tasks.backfill_prices")
def backfill_prices_job(asset_id: str, start: str, end: str) -> dict[str, object]:
    """Daily closes of one asset over [start, end]. Safe to run again, also over a larger range."""
    providers = build_providers(get_settings())
    asset_uuid = uuid.UUID(asset_id)
    first, last = date.fromisoformat(start), date.fromisoformat(end)

    async def go(sessions: SessionFactory) -> dict[str, object]:
        async def work(session: AsyncSession) -> IngestResult:
            found = [(a, k) for a, k in await market_assets(session) if a.id == asset_uuid]
            if not found:
                return IngestResult(
                    failures=[IngestFailure(asset_id, "NotFound", "not a market asset")]
                )
            asset, kind = found[0]
            provider = providers.by_kind.get(kind)
            if provider is None:
                return IngestResult(failures=[IngestFailure(asset_id, "NoProvider", str(kind))])
            return await backfill_prices(session, provider, asset, kind, first, last)

        return await _guarded(sessions, "backfill_prices", f"{asset_id}:{start}:{end}", work)

    return run_async(go)


@celery_app.task(base=JobTask, name="app.worker.tasks.backfill_fx")
def backfill_fx_job(base: str, quote: str, start: str, end: str) -> dict[str, object]:
    """Daily rates of one pair over [start, end]. Safe to run again."""
    fx = build_providers(get_settings()).fx
    if fx is None:
        return {"skipped": "no FX provider configured"}
    first, last = date.fromisoformat(start), date.fromisoformat(end)

    async def go(sessions: SessionFactory) -> dict[str, object]:
        async def work(session: AsyncSession) -> IngestResult:
            return await backfill_fx(session, fx, base, quote, first, last)

        return await _guarded(sessions, "backfill_fx", f"{base}{quote}:{start}:{end}", work)

    return run_async(go)


# ----------------------------------------------------------------------------------- alerts
@celery_app.task(base=JobTask, name="app.worker.tasks.evaluate_alerts")
def evaluate_alerts_job(bucket: str | None = None) -> dict[str, object]:
    """Fires the active alerts whose condition holds on fresh data. Runs after price ingestion;
    evaluating the same data again fires nothing more."""
    key = bucket or _bucket(datetime.now(UTC), 15)

    async def go(sessions: SessionFactory) -> dict[str, object]:
        sender = build_push_sender()

        async def work(session: AsyncSession) -> EvaluationResult:
            return await evaluate_alerts(session, sender=sender)

        outcome = await run_once(sessions, "evaluate_alerts", key, work)
        if outcome.skipped or outcome.value is None:
            return {"skipped": True}
        r = outcome.value
        return {
            "evaluated": r.evaluated,
            "triggered": r.triggered,
            "skipped_by_preferences": r.skipped_by_preferences,
            "skipped_no_fresh_data": r.skipped_no_fresh_data,
        }

    return run_async(go)
