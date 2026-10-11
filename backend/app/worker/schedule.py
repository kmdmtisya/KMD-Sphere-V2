"""The beat schedule: which job runs when (P08-T04.1). Later tasks add their jobs here (price and
FX ingestion in P08-T05, alert evaluation in P08-T07)."""

from typing import Any

HEARTBEAT_EVERY_SECONDS = 60.0


def build_schedule() -> dict[str, dict[str, Any]]:
    return {
        # Proves the worker and beat are alive: writes a timestamp to Redis.
        "worker-heartbeat": {
            "task": "app.worker.tasks.heartbeat",
            "schedule": HEARTBEAT_EVERY_SECONDS,
        },
    }
