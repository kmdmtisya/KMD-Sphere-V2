"""The Celery application (P08-T04.1).

Run a worker:   `celery -A app.worker.celery_app worker -l info`
Run the beat:   `celery -A app.worker.celery_app beat -l info`

Reliability settings, and why:
- `task_acks_late` + `reject_on_worker_lost`: a task is acknowledged only after it finishes, so a
  worker that dies mid-task does not lose it (it is redelivered; jobs are idempotent).
- `worker_prefetch_multiplier=1`: a long job does not hold others hostage.
- Queues: `default` is declared with a dead-letter exchange, so a message the broker rejects
  (an unknown task, a poison message) lands in `dead_letter`; a task that fails after its retries
  is also published there by `JobTask.on_failure` (see jobs.py). Nothing is silently dropped.
- JSON only (no pickle): a message cannot carry code."""

from celery import Celery
from celery.signals import setup_logging
from kombu import Exchange, Queue

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.worker.queues import DEAD_LETTER_EXCHANGE, DEAD_LETTER_QUEUE, DEFAULT_QUEUE
from app.worker.schedule import build_schedule


def create_celery_app(settings: Settings | None = None) -> Celery:
    cfg = settings or get_settings()
    app = Celery("wealthsphere", broker=cfg.broker_url, include=["app.worker.tasks"])
    app.conf.update(
        task_default_queue=DEFAULT_QUEUE,
        task_queues=(
            Queue(
                DEFAULT_QUEUE,
                Exchange(DEFAULT_QUEUE),
                routing_key=DEFAULT_QUEUE,
                queue_arguments={
                    "x-dead-letter-exchange": DEAD_LETTER_EXCHANGE,
                    "x-dead-letter-routing-key": DEAD_LETTER_QUEUE,
                },
            ),
            Queue(
                DEAD_LETTER_QUEUE,
                Exchange(DEAD_LETTER_EXCHANGE, type="direct"),
                routing_key=DEAD_LETTER_QUEUE,
            ),
        ),
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1,
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        task_ignore_result=True,
        timezone="UTC",
        enable_utc=True,
        broker_connection_retry_on_startup=True,
        # Celery's own logging would bypass the redacting JSON formatter: use ours.
        worker_hijack_root_logger=False,
        # RabbitMQ 4 refuses the transient, non-exclusive queues of Celery's remote control (pidbox)
        # and events, which makes the worker restart in a loop. Run workers with
        # `--without-mingle --without-gossip` (see docs/design/jobs.md and the Makefile).
        worker_enable_remote_control=False,
        # A hung provider call must not hold a worker for ever.
        task_soft_time_limit=120,
        task_time_limit=180,
        beat_schedule=build_schedule(),
    )
    return app


@setup_logging.connect
def _use_application_logging(**_: object) -> None:
    """Structured, redacted JSON logs for workers and beat, like the API (docs/observability.md)."""
    configure_logging(get_settings().log_level)


celery_app = create_celery_app()
