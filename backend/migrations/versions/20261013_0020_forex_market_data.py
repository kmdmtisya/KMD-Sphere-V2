"""forex_instruments, and forex_quotes and forex_candles partitioned by month (P13-T02.3, DEC-21)

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-13

The parents are range-partitioned on their time column. Only the DEFAULT partitions are created
here (a migration must not depend on today's date); the monthly partitions are created ahead of
time by `app.modules.forex.marketdata.partitions.ensure_months` (worker job `forex_partitions`).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DATA_TYPES = "('tradable_quote', 'indicative_rate', 'delayed', 'simulated')"


def upgrade() -> None:
    op.create_table(
        "forex_instruments",
        sa.Column("code", sa.String(length=7), nullable=False),
        sa.Column("base", sa.String(length=3), nullable=False),
        sa.Column("quote", sa.String(length=3), nullable=False),
        sa.Column("pip_location", sa.SmallInteger(), nullable=False),
        sa.Column("display_precision", sa.SmallInteger(), nullable=False),
        sa.Column("liquidity_tier", sa.String(length=8), nullable=False),
        sa.Column("default_data_type", sa.String(length=16), nullable=False),
        sa.Column("spec_version", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
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
        sa.CheckConstraint("code ~ '^[A-Z]{3}_[A-Z]{3}$'", name=op.f("ck_forex_instruments_code")),
        sa.CheckConstraint(
            "pip_location BETWEEN -6 AND 0", name=op.f("ck_forex_instruments_pip_location")
        ),
        sa.CheckConstraint(
            "display_precision BETWEEN -pip_location AND 8",
            name=op.f("ck_forex_instruments_display_precision"),
        ),
        sa.CheckConstraint(
            "liquidity_tier IN ('major', 'minor', 'exotic')",
            name=op.f("ck_forex_instruments_liquidity_tier"),
        ),
        sa.CheckConstraint(
            "default_data_type IN ('tradable_quote', 'indicative_rate')",
            name=op.f("ck_forex_instruments_default_data_type"),
        ),
        sa.CheckConstraint("spec_version >= 1", name=op.f("ck_forex_instruments_spec_version")),
        sa.PrimaryKeyConstraint("code", name=op.f("pk_forex_instruments")),
    )
    op.create_table(
        "forex_quotes",
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("instrument", sa.String(length=7), nullable=False),
        sa.Column("ts_provider", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ts_received", sa.DateTime(timezone=True), nullable=False),
        sa.Column("bid", sa.Numeric(precision=20, scale=10), nullable=False),
        sa.Column("ask", sa.Numeric(precision=20, scale=10), nullable=False),
        sa.Column(
            "mid",
            sa.Numeric(precision=21, scale=11),
            sa.Computed("(bid + ask) / 2", persisted=True),
            nullable=False,
        ),
        sa.Column("data_type", sa.String(length=16), nullable=False),
        sa.Column("quality", sa.String(length=8), nullable=False),
        sa.Column("feed_status", sa.String(length=16), nullable=False),
        sa.CheckConstraint("bid > 0 AND ask > 0", name=op.f("ck_forex_quotes_positive")),
        sa.CheckConstraint(f"data_type IN {DATA_TYPES}", name=op.f("ck_forex_quotes_data_type")),
        sa.CheckConstraint(
            "quality IN ('ok', 'suspect', 'stale')", name=op.f("ck_forex_quotes_quality")
        ),
        sa.CheckConstraint(
            "feed_status IN ('connected', 'degraded', 'disconnected')",
            name=op.f("ck_forex_quotes_feed_status"),
        ),
        sa.ForeignKeyConstraint(
            ["instrument"],
            ["forex_instruments.code"],
            name=op.f("fk_forex_quotes_instrument_forex_instruments"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("provider", "instrument", "ts_provider", name="pk_forex_quotes"),
        postgresql_partition_by="RANGE (ts_provider)",
    )
    op.create_index(
        "ix_forex_quotes_instrument_ts_provider", "forex_quotes", ["instrument", "ts_provider"]
    )
    op.create_index(
        "ix_forex_quotes_ts_provider_brin",
        "forex_quotes",
        ["ts_provider"],
        postgresql_using="brin",
    )
    op.execute("CREATE TABLE forex_quotes_default PARTITION OF forex_quotes DEFAULT")

    op.create_table(
        "forex_candles",
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("instrument", sa.String(length=7), nullable=False),
        sa.Column("timeframe", sa.String(length=3), nullable=False),
        sa.Column("price_basis", sa.String(length=3), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open", sa.Numeric(precision=20, scale=10), nullable=False),
        sa.Column("high", sa.Numeric(precision=20, scale=10), nullable=False),
        sa.Column("low", sa.Numeric(precision=20, scale=10), nullable=False),
        sa.Column("close", sa.Numeric(precision=20, scale=10), nullable=False),
        sa.Column("volume", sa.BigInteger(), nullable=True),
        sa.Column("data_type", sa.String(length=16), nullable=False),
        sa.Column("ts_received", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("low > 0", name=op.f("ck_forex_candles_positive")),
        sa.CheckConstraint(
            "high >= open AND high >= close AND low <= open AND low <= close",
            name=op.f("ck_forex_candles_bounds"),
        ),
        sa.CheckConstraint(
            "timeframe IN ('1m', '5m', '15m', '30m', '1H', '4H', '1D', '1W', '1M')",
            name=op.f("ck_forex_candles_timeframe"),
        ),
        sa.CheckConstraint(
            "price_basis IN ('mid', 'bid', 'ask')", name=op.f("ck_forex_candles_price_basis")
        ),
        sa.CheckConstraint(f"data_type IN {DATA_TYPES}", name=op.f("ck_forex_candles_data_type")),
        sa.CheckConstraint("volume IS NULL OR volume >= 0", name=op.f("ck_forex_candles_volume")),
        sa.ForeignKeyConstraint(
            ["instrument"],
            ["forex_instruments.code"],
            name=op.f("fk_forex_candles_instrument_forex_instruments"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "provider", "instrument", "timeframe", "price_basis", "ts", name="pk_forex_candles"
        ),
        postgresql_partition_by="RANGE (ts)",
    )
    op.create_index("ix_forex_candles_ts_brin", "forex_candles", ["ts"], postgresql_using="brin")
    op.execute("CREATE TABLE forex_candles_default PARTITION OF forex_candles DEFAULT")


def downgrade() -> None:
    # Dropping a partitioned parent drops all its partitions, including those made by the job.
    op.drop_table("forex_candles")
    op.drop_table("forex_quotes")
    op.drop_table("forex_instruments")
