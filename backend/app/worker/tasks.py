"""Registered jobs. Later tasks add theirs here (price and FX ingestion, alert evaluation)."""

from datetime import UTC, datetime

import redis

from app.core.config import get_settings
from app.worker.celery_app import celery_app
from app.worker.jobs import JobTask

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
