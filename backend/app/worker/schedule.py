"""The beat schedule: which job runs when (P08-T04.1). Later tasks add their jobs here (price and
FX ingestion in P08-T05, alert evaluation in P08-T07)."""

from typing import Any

from celery.schedules import crontab

HEARTBEAT_EVERY_SECONDS = 60.0
PRICE_INGEST_EVERY_SECONDS = 900.0
ALERT_EVALUATION_EVERY_SECONDS = 900.0


def build_schedule() -> dict[str, dict[str, Any]]:
    return {
        # Proves the worker and beat are alive: writes a timestamp to Redis.
        "worker-heartbeat": {
            "task": "app.worker.tasks.heartbeat",
            "schedule": HEARTBEAT_EVERY_SECONDS,
        },
        # Latest quotes of market-valued assets. Quotes are stored once per provider timestamp, so
        # a quote that has not changed is not stored again.
        "price-ingest": {
            "task": "app.worker.tasks.ingest_prices",
            "schedule": PRICE_INGEST_EVERY_SECONDS,
        },
        # Alerts are checked on the same cadence, shortly after the quotes arrive. Only fresh data
        # fires an alert.
        "alert-evaluation": {
            "task": "app.worker.tasks.evaluate_alerts",
            "schedule": ALERT_EVALUATION_EVERY_SECONDS,
        },
        # Conversation history past its retention period is deleted once a day.
        "ai-conversation-purge": {
            "task": "app.worker.tasks.purge_ai_conversations",
            "schedule": crontab(hour=3, minute=15),
        },
        # The ECB publishes around 14:15 Central European Time (12:15 or 13:15 UTC).
        "fx-ingest": {
            "task": "app.worker.tasks.ingest_fx",
            "schedule": crontab(hour=16, minute=30),
        },
    }
