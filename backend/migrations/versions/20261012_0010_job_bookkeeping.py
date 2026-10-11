"""job_runs and job_failures (P08-T04)

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _common() -> list[sa.Column]:  # type: ignore[type-arg]
    return [
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "job_runs",
        sa.Column("job_name", sa.String(length=100), nullable=False),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        *_common(),
        sa.CheckConstraint(
            "status IN ('running', 'done', 'failed')", name=op.f("ck_job_runs_status")
        ),
        sa.CheckConstraint("attempts >= 0", name=op.f("ck_job_runs_attempts_non_negative")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_job_runs")),
        sa.UniqueConstraint("job_name", "idempotency_key", name="uq_job_runs_job_name_key"),
    )
    op.create_table(
        "job_failures",
        sa.Column("task_id", sa.String(length=64), nullable=False),
        sa.Column("job_name", sa.String(length=100), nullable=False),
        sa.Column("error_type", sa.String(length=100), nullable=False),
        sa.Column("error_message", sa.String(length=500), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        *_common(),
        sa.CheckConstraint("attempts >= 0", name=op.f("ck_job_failures_attempts_non_negative")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_job_failures")),
    )
    op.create_index("ix_job_failures_failed_at", "job_failures", ["failed_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_job_failures_failed_at", table_name="job_failures")
    op.drop_table("job_failures")
    op.drop_table("job_runs")
