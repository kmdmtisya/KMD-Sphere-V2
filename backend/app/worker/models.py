"""Job bookkeeping tables (P08-T04). Global operational data, no owner: they hold no user
information, only which job ran with which idempotency key and which jobs failed for good."""

from datetime import datetime

from sqlalchemy import CheckConstraint, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

RUN_STATUSES = ("running", "done", "failed")


class JobRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One idempotency key of one job. `done` means the work was completed: running the job again
    with the same key does nothing."""

    __tablename__ = "job_runs"
    __table_args__ = (
        UniqueConstraint("job_name", "idempotency_key", name="uq_job_runs_job_name_key"),
        CheckConstraint("status IN ('running', 'done', 'failed')", name="status"),
        CheckConstraint("attempts >= 0", name="attempts_non_negative"),
    )

    job_name: Mapped[str] = mapped_column(String(100))
    idempotency_key: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(12))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column()
    finished_at: Mapped[datetime | None] = mapped_column()
    last_error: Mapped[str | None] = mapped_column(String(500))


class JobFailure(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A job that failed after all its retries; the message also sits in the dead-letter queue.
    Visible with `python -m app.worker.cli failures`. The error text is truncated and carries no
    arguments."""

    __tablename__ = "job_failures"
    __table_args__ = (
        Index("ix_job_failures_failed_at", "failed_at"),
        CheckConstraint("attempts >= 0", name="attempts_non_negative"),
    )

    task_id: Mapped[str] = mapped_column(String(64))
    job_name: Mapped[str] = mapped_column(String(100))
    error_type: Mapped[str] = mapped_column(String(100))
    error_message: Mapped[str] = mapped_column(String(500))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    failed_at: Mapped[datetime] = mapped_column()
    acknowledged_at: Mapped[datetime | None] = mapped_column()
