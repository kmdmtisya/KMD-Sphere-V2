"""The base class of every job (P08-T04.3).

A job that raises a transient error (a provider outage, a timeout) is retried with exponential
backoff and jitter, up to `max_retries`. A job that still fails, or fails with an error that is not
worth retrying, is a **dead letter**: it is recorded in `job_failures`, published to the
`dead_letter` queue with its arguments (for replay) and counted in the
`worker_job_failures_total` metric. Logs carry the job name, id and error type only, never
arguments or error text that might hold data."""

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from celery import Task
from kombu import Exchange, Queue

from app.modules.market_data.providers.errors import ProviderUnavailable
from app.worker.db import SessionFactory, run_async
from app.worker.metrics import JOB_FAILURES
from app.worker.models import JobFailure
from app.worker.queues import DEAD_LETTER_EXCHANGE, DEAD_LETTER_QUEUE

logger = logging.getLogger(__name__)

_ERROR_LIMIT = 500


def _record_failure(
    task_id: str, job: str, error: BaseException, attempts: int, failed_at: datetime
) -> None:
    async def work(sessions: SessionFactory) -> None:
        async with sessions() as session:
            session.add(
                JobFailure(
                    task_id=task_id,
                    job_name=job,
                    error_type=type(error).__name__,
                    error_message=str(error)[:_ERROR_LIMIT],
                    attempts=attempts,
                    failed_at=failed_at,
                )
            )
            await session.commit()

    run_async(work)


# The stubs make `Task` generic; at run time it is a plain class.
if TYPE_CHECKING:
    _TaskBase = Task[..., Any]
else:
    _TaskBase = Task


class JobTask(_TaskBase):
    """Retries transient failures; sends the rest to the dead-letter queue."""

    autoretry_for = (ProviderUnavailable, ConnectionError, TimeoutError)
    retry_backoff = True
    retry_backoff_max = 300
    retry_jitter = True
    max_retries = 5

    def on_failure(
        self,
        exc: BaseException,
        task_id: str,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        einfo: Any,
    ) -> None:
        job = self.name or "unknown"
        attempts = int(getattr(self.request, "retries", 0)) + 1
        failed_at = datetime.now(UTC)
        JOB_FAILURES.labels(job=job).inc()
        # Never log arguments or the error text: they may carry data.
        logger.error("job failed for good: %s id=%s error=%s", job, task_id, type(exc).__name__)
        # Recording must never raise: a broken database must not hide the original failure.
        try:
            _record_failure(task_id, job, exc, attempts, failed_at)
        except Exception:
            logger.exception("could not record the failure of %s id=%s", job, task_id)
        try:
            self._publish_dead_letter(task_id, job, exc, args, kwargs, failed_at)
        except Exception:
            logger.exception("could not dead-letter %s id=%s", job, task_id)

    def _publish_dead_letter(
        self,
        task_id: str,
        job: str,
        exc: BaseException,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        failed_at: datetime,
    ) -> None:
        queue = Queue(
            DEAD_LETTER_QUEUE,
            Exchange(DEAD_LETTER_EXCHANGE, type="direct"),
            routing_key=DEAD_LETTER_QUEUE,
        )
        with self.app.producer_or_acquire() as producer:
            producer.publish(
                {
                    "task": job,
                    "id": task_id,
                    "args": list(args),
                    "kwargs": kwargs,
                    "error_type": type(exc).__name__,
                    "failed_at": failed_at.isoformat(),
                },
                exchange=queue.exchange,
                routing_key=DEAD_LETTER_QUEUE,
                declare=[queue],
                serializer="json",
                retry=True,
            )
