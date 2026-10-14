"""forex_backtest_reports: stored, reproducible backtest reports (P13-T08)

Revision ID: 0024
Revises: 0023
Create Date: 2026-10-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "forex_backtest_reports",
        sa.Column("instrument", sa.String(length=7), nullable=False),
        sa.Column("timeframe", sa.String(length=3), nullable=False),
        sa.Column("rule", sa.String(length=24), nullable=False),
        sa.Column("rule_version", sa.Integer(), nullable=False),
        sa.Column("engine_version", sa.String(length=24), nullable=False),
        sa.Column("code_version", sa.String(length=64), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=False),
        sa.Column("data_snapshot_hash", sa.String(length=16), nullable=False),
        sa.Column("report_hash", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=16), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("bars", sa.Integer(), nullable=False),
        sa.Column("data_types", postgresql.ARRAY(sa.String(length=16)), nullable=False),
        sa.Column("oos_trades", sa.Integer(), nullable=False),
        sa.Column("oos_return", sa.Numeric(precision=14, scale=6), nullable=False),
        sa.Column("oos_profit_factor", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("report", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
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
        sa.CheckConstraint("label = 'backtested'", name=op.f("ck_forex_backtest_reports_label")),
        sa.CheckConstraint(
            "bars > 0 AND oos_trades >= 0", name=op.f("ck_forex_backtest_reports_counts")
        ),
        sa.ForeignKeyConstraint(
            ["instrument"],
            ["forex_instruments.code"],
            name=op.f("fk_forex_backtest_reports_instrument_forex_instruments"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_forex_backtest_reports")),
        sa.UniqueConstraint("report_hash", name=op.f("uq_forex_backtest_reports_report_hash")),
    )
    op.create_index(
        "ix_forex_backtest_reports_lookup",
        "forex_backtest_reports",
        ["instrument", "timeframe", "rule", "generated_at"],
    )


def downgrade() -> None:
    op.drop_table("forex_backtest_reports")
