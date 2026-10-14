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
        # Reporting-currency rates (P11-T03): hourly, inside the commercial plan's quota; the
        # refresh window makes a second call in the same window a no-op.
        "fx-refresh": {
            "task": "app.worker.tasks.refresh_fx",
            "schedule": crontab(minute=5),
        },
        # The ECB publishes around 14:15 Central European Time (12:15 or 13:15 UTC).
        "fx-ingest": {
            "task": "app.worker.tasks.ingest_fx",
            "schedule": crontab(hour=16, minute=30),
        },
        # The investment universe (P12-T02): once a day, before markets open in Nairobi and Dubai.
        "universe-ingest": {
            "task": "app.worker.tasks.ingest_universe",
            "schedule": crontab(hour=2, minute=45),
        },
        # Research evidence (P12-T05), after the universe so notes link to its instruments.
        "research-ingest": {
            "task": "app.worker.tasks.ingest_research",
            "schedule": crontab(hour=3, minute=0),
        },
        # Forex registry and monthly partitions three months ahead (P13-T02.3), once a day.
        # One-minute forex candles from the provider (P13-T03), every five minutes.
        "forex-candle-sync": {
            "task": "app.worker.tasks.forex_candle_sync",
            "schedule": crontab(minute="*/5"),
        },
        "forex-maintenance": {
            "task": "app.worker.tasks.forex_maintenance",
            "schedule": crontab(hour=1, minute=15),
        },
    }
