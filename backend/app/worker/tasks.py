"""Registered jobs. Later tasks add theirs here (price and FX ingestion, alert evaluation)."""

import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import asdict
from datetime import UTC, date, datetime, timedelta

import redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.conversations.service import ConversationService
from app.core.config import get_settings
from app.modules.alerts.evaluation import EvaluationResult, evaluate_alerts
from app.modules.forex.calendar.ingest import ingest as ingest_forex_calendar
from app.modules.forex.calendar.sources import DemoCalendarSource
from app.modules.forex.candles.sync import sync_minutes as sync_forex_minutes
from app.modules.forex.forecast.service import train as train_forex_forecast
from app.modules.forex.instruments.registry import active_instruments as active_forex_instruments
from app.modules.forex.instruments.registry import load_registry as load_forex_registry
from app.modules.forex.instruments.registry import sync as sync_forex_instruments
from app.modules.forex.marketdata.factory import build_provider as build_forex_provider
from app.modules.forex.marketdata.feed import MONTHS_AHEAD as FOREX_MONTHS_AHEAD
from app.modules.forex.marketdata.partitions import PARTITIONED as FOREX_PARTITIONED
from app.modules.forex.marketdata.partitions import ensure_months as ensure_forex_months
from app.modules.forex.risk.specs import sync as sync_forex_contract_specs
from app.modules.fx.refresh import refresh_once_per_window
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
from app.modules.research.embedding import build_embedder
from app.modules.research.service import ingest_research
from app.modules.research.sources import DemoResearchSource
from app.modules.universe.ingestion import (
    DEMO_SOURCE,
    DemoUniverseSource,
    deactivate_source,
)
from app.modules.universe.ingestion import (
    ingest as ingest_universe,
)
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


# ------------------------------------------------------------------------ AI conversations
@celery_app.task(base=JobTask, name="app.worker.tasks.purge_ai_conversations")
def purge_ai_conversations_job(day: str | None = None) -> dict[str, object]:
    """Deletes AI conversations past the retention period (ADR-0017: 90 days by default)."""
    now = datetime.now(UTC)
    key = day or now.date().isoformat()
    retention = get_settings().ai_conversation_retention_days

    async def go(sessions: SessionFactory) -> dict[str, object]:
        async def work(session: AsyncSession) -> int:
            removed = await ConversationService(session).purge_expired(now, retention)
            await session.commit()
            return removed

        outcome = await run_once(sessions, "purge_ai_conversations", key, work)
        if outcome.skipped or outcome.value is None:
            return {"skipped": True}
        return {"removed": outcome.value}

    return run_async(go)


# ------------------------------------------------------------------------- reporting-currency FX
@celery_app.task(base=JobTask, name="app.worker.tasks.refresh_fx")
def refresh_fx_job() -> dict[str, object]:
    """Rates of every active currency against the pivot (P11-T03). Shares the refresh window with
    user-triggered refreshes, so the provider is called at most once per window. When every
    provider fails the job raises (recorded as a failure); the window stays used, so the next
    attempt is the next window's (P11-T11)."""
    settings = get_settings()
    providers = build_providers(settings)
    if not providers.fx_sources:
        return {"skipped": "no FX provider configured"}

    async def go(sessions: SessionFactory) -> dict[str, object]:
        run = await refresh_once_per_window(
            sessions,
            providers.fx_sources,
            settings.fx_pivot_currency,
            datetime.now(UTC),
            settings.fx_refresh_window_minutes,
        )
        if not run.ran or run.outcome is None:
            return {"skipped": True, "window": run.window}
        return {
            "window": run.window,
            "stored": run.outcome.stored,
            "missing": run.outcome.missing,
            "failed": [a.provider for a in run.outcome.attempts if a.error],
        }

    return run_async(go)


# -------------------------------------------------------------------------- investment universe
@celery_app.task(base=JobTask, name="app.worker.tasks.ingest_universe")
def ingest_universe_job(day: str | None = None) -> dict[str, object]:
    """Loads the investment universe once a day (P12-T02.2). Only the synthetic DEMO universe
    exists; it is loaded only with fake market data, so fictional symbols never reach a real
    provider. With real market data any DEMO instruments are deactivated instead."""
    settings = get_settings()
    key = day or datetime.now(UTC).date().isoformat()

    async def go(sessions: SessionFactory) -> dict[str, object]:
        async def work(session: AsyncSession) -> dict[str, object]:
            if settings.market_data_mode != "fake":
                removed = await deactivate_source(session, DEMO_SOURCE)
                return {"demo_universe": "disabled", "deactivated": removed}
            report = await ingest_universe(session, DemoUniverseSource())
            return asdict(report)

        outcome = await run_once(sessions, "ingest_universe", key, work)
        if outcome.skipped or outcome.value is None:
            return {"skipped": True}
        return outcome.value

    return run_async(go)


# ---------------------------------------------------------------------------- research evidence
@celery_app.task(base=JobTask, name="app.worker.tasks.ingest_research")
def ingest_research_job(day: str | None = None) -> dict[str, object]:
    """Loads research evidence once a day (P12-T05.2). Only the synthetic DEMO notes exist; like
    the DEMO universe they are loaded only with fake market data. Nothing is fetched from the
    network (the EDGAR adapter is fixture-only until a live source is approved)."""
    settings = get_settings()
    key = day or datetime.now(UTC).date().isoformat()
    if settings.market_data_mode != "fake":
        return {"demo_research": "disabled"}

    async def go(sessions: SessionFactory) -> dict[str, object]:
        async def work(session: AsyncSession) -> dict[str, object]:
            report = await ingest_research(
                session, DemoResearchSource(), build_embedder(settings.research_embedder)
            )
            return asdict(report)

        outcome = await run_once(sessions, "ingest_research", key, work)
        if outcome.skipped or outcome.value is None:
            return {"skipped": True}
        return outcome.value

    return run_async(go)


# ------------------------------------------------------------------------------ forex (P13)
@celery_app.task(base=JobTask, name="app.worker.tasks.forex_maintenance")
def forex_maintenance_job(day: str | None = None) -> dict[str, object]:
    """Keeps the forex registry and the contract specifications (P13-T07) in step with their
    files and creates the time-series partitions three months ahead (P13-T02.3, DEC-21). Runs
    whether or not forex is switched on: it only prepares reference data and tables, and fetches
    nothing."""
    settings = get_settings()
    key = day or datetime.now(UTC).date().isoformat()

    async def go(sessions: SessionFactory) -> dict[str, object]:
        async def work(session: AsyncSession) -> dict[str, object]:
            report = await sync_forex_instruments(
                session, load_forex_registry(), settings.forex_universe
            )
            specs = await sync_forex_contract_specs(session)
            created: list[str] = []
            for table in FOREX_PARTITIONED:
                created += await ensure_forex_months(
                    session, table, date.fromisoformat(key), FOREX_MONTHS_AHEAD
                )
            return {**asdict(report), "contract_specs": specs, "partitions_created": created}

        outcome = await run_once(sessions, "forex_maintenance", key, work)
        if outcome.skipped or outcome.value is None:
            return {"skipped": True}
        return outcome.value

    return run_async(go)


@celery_app.task(base=JobTask, name="app.worker.tasks.forex_candle_sync")
def forex_candle_sync_job(slot: str | None = None) -> dict[str, object]:
    """Stores the provider's one-minute candles for the active forex pairs (P13-T03). Only when
    the forex module is switched on; the provider is the simulated one (DEC-19)."""
    settings = get_settings()
    if not settings.forex_enabled:
        return {"forex": "disabled"}
    key = slot or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M")

    async def go(sessions: SessionFactory) -> dict[str, object]:
        async def work(session: AsyncSession) -> dict[str, object]:
            codes = [i.code for i in await active_forex_instruments(session)]
            report = await sync_forex_minutes(
                session,
                build_forex_provider(settings),
                codes,
                datetime.now(UTC),
                timedelta(hours=settings.forex_candle_sync_max_hours),
            )
            return {"stored": report.stored, "failed": report.failed}

        outcome = await run_once(sessions, "forex_candle_sync", key, work)
        if outcome.skipped or outcome.value is None:
            return {"skipped": True}
        return outcome.value

    return run_async(go)


@celery_app.task(base=JobTask, name="app.worker.tasks.forex_calendar_ingest")
def forex_calendar_ingest_job(day: str | None = None) -> dict[str, object]:
    """Loads the economic calendar every hour (P13-T04): a week back and 30 days ahead, so released
    values arrive within the hour. Only the synthetic DEMO calendar exists (DEC-19); it runs only
    when forex is switched on. `day` is the run key: an ISO date, optionally with the hour."""
    settings = get_settings()
    if not settings.forex_enabled:
        return {"forex": "disabled"}
    key = day or datetime.now(UTC).strftime("%Y-%m-%dT%H")

    async def go(sessions: SessionFactory) -> dict[str, object]:
        async def work(session: AsyncSession) -> dict[str, object]:
            today = date.fromisoformat(key[:10])
            report = await ingest_forex_calendar(
                session,
                DemoCalendarSource(),
                today - timedelta(days=7),
                today + timedelta(days=30),
                datetime.now(UTC),
            )
            return asdict(report)

        outcome = await run_once(sessions, "forex_calendar_ingest", key, work)
        if outcome.skipped or outcome.value is None:
            return {"skipped": True}
        return outcome.value

    return run_async(go)


@celery_app.task(base=JobTask, name="app.worker.tasks.forex_forecast_train")
def forex_forecast_train_job(slot: str | None = None) -> dict[str, object]:
    """Trains, evaluates and publishes forecasts for every active pair and configured horizon,
    once an hour (P13-T05). Only when forex is switched on. A pair and horizon disabled by drift
    is skipped until retraining is approved; one without enough history publishes nothing."""
    settings = get_settings()
    if not settings.forex_enabled:
        return {"forex": "disabled"}
    key = slot or datetime.now(UTC).strftime("%Y-%m-%dT%H")

    async def go(sessions: SessionFactory) -> dict[str, object]:
        async def work(session: AsyncSession) -> dict[str, object]:
            now = datetime.now(UTC)
            counts: dict[str, object] = {}
            for instrument in [i.code for i in await active_forex_instruments(session)]:
                for horizon in settings.forex_forecast_horizons:
                    outcome = await train_forex_forecast(
                        session, settings, instrument, horizon, now
                    )
                    seen = counts.get(outcome.result, 0)
                    counts[outcome.result] = (seen if isinstance(seen, int) else 0) + 1
            return counts

        outcome = await run_once(sessions, "forex_forecast_train", key, work)
        if outcome.skipped or outcome.value is None:
            return {"skipped": True}
        return outcome.value

    return run_async(go)
