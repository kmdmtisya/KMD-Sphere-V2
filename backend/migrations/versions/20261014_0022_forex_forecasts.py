"""forex_model_versions and forex_forecasts: the forecasting registry and its outputs (P13-T05)

Revision ID: 0022
Revises: 0021
Create Date: 2026-10-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    jsonb = postgresql.JSONB(astext_type=sa.Text())
    op.create_table(
        "forex_model_versions",
        sa.Column("instrument", sa.String(length=7), nullable=False),
        sa.Column("horizon", sa.String(length=4), nullable=False),
        sa.Column("timeframe", sa.String(length=3), nullable=False),
        sa.Column("bars_ahead", sa.Integer(), nullable=False),
        sa.Column("model_name", sa.String(length=40), nullable=False),
        sa.Column("family", sa.String(length=20), nullable=False),
        sa.Column("version", sa.String(length=16), nullable=False),
        sa.Column("params", jsonb, nullable=False),
        sa.Column("feature_set_hash", sa.String(length=16), nullable=False),
        sa.Column("data_snapshot_hash", sa.String(length=16), nullable=False),
        sa.Column("code_version", sa.String(length=64), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=False),
        sa.Column("trained_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("train_rows", sa.Integer(), nullable=False),
        sa.Column("test_rows", sa.Integer(), nullable=False),
        sa.Column("folds", sa.Integer(), nullable=False),
        sa.Column("evaluation", jsonb, nullable=False),
        sa.Column("volatility", jsonb, nullable=False),
        sa.Column("calibration_status", sa.String(length=24), nullable=False),
        sa.Column("probability_source", sa.String(length=16), nullable=False),
        sa.Column("edge", sa.Boolean(), nullable=False),
        sa.Column("drift", jsonb, nullable=False),
        sa.Column("drift_status", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("data_types", postgresql.ARRAY(sa.String(length=16)), nullable=False),
        sa.Column("retraining_approved_by", sa.String(length=200), nullable=True),
        sa.Column("retraining_approved_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "horizon IN ('15m', '1h', '4h', '24h', '1w')",
            name=op.f("ck_forex_model_versions_horizon"),
        ),
        sa.CheckConstraint(
            "status IN ('active', 'superseded', 'disabled')",
            name=op.f("ck_forex_model_versions_status"),
        ),
        sa.CheckConstraint(
            "calibration_status IN ('calibrated', 'requires_calibration')",
            name=op.f("ck_forex_model_versions_calibration_status"),
        ),
        sa.CheckConstraint(
            "drift_status IN ('ok', 'breached')", name=op.f("ck_forex_model_versions_drift_status")
        ),
        sa.CheckConstraint(
            "probability_source IN ('raw', 'recalibrated')",
            name=op.f("ck_forex_model_versions_probability_source"),
        ),
        sa.ForeignKeyConstraint(
            ["instrument"],
            ["forex_instruments.code"],
            name=op.f("fk_forex_model_versions_instrument_forex_instruments"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_forex_model_versions")),
    )
    op.create_index(
        "ix_forex_model_versions_instrument_horizon_trained_at",
        "forex_model_versions",
        ["instrument", "horizon", "trained_at"],
    )
    op.create_table(
        "forex_forecasts",
        sa.Column("model_version_id", sa.UUID(), nullable=False),
        sa.Column("instrument", sa.String(length=7), nullable=False),
        sa.Column("horizon", sa.String(length=4), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_close", sa.Numeric(precision=20, scale=10), nullable=False),
        sa.Column("prob_up", sa.Numeric(precision=8, scale=6), nullable=False),
        sa.Column("prob_up_raw", sa.Numeric(precision=8, scale=6), nullable=False),
        sa.Column("return_quantiles", jsonb, nullable=False),
        sa.Column("price_quantiles", jsonb, nullable=False),
        sa.Column("expected_volatility", sa.Numeric(precision=20, scale=12), nullable=False),
        sa.Column("volatility_model", sa.String(length=8), nullable=False),
        sa.Column("data_types", postgresql.ARRAY(sa.String(length=16)), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint(
            "prob_up BETWEEN 0 AND 1 AND prob_up_raw BETWEEN 0 AND 1",
            name=op.f("ck_forex_forecasts_probability"),
        ),
        sa.ForeignKeyConstraint(
            ["model_version_id"],
            ["forex_model_versions.id"],
            name=op.f("fk_forex_forecasts_model_version_id_forex_model_versions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_forex_forecasts")),
    )
    op.create_index(
        "ix_forex_forecasts_instrument_horizon_generated_at",
        "forex_forecasts",
        ["instrument", "horizon", "generated_at"],
    )


def downgrade() -> None:
    op.drop_table("forex_forecasts")
    op.drop_table("forex_model_versions")
