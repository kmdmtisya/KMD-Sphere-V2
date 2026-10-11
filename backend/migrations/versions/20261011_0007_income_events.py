"""income_events: one row per income entry of the ledger (P06-T05)

Existing income entries that are not reversed are copied in, so the table matches the ledger from
the start.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "income_events",
        sa.Column("transaction_id", sa.UUID(), nullable=False),
        sa.Column("portfolio_id", sa.UUID(), nullable=False),
        sa.Column("asset_id", sa.UUID(), nullable=True),
        sa.Column("income_type", sa.String(length=24), nullable=False),
        sa.Column("paid_on", sa.Date(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("gross", sa.Numeric(precision=28, scale=8), nullable=False),
        sa.Column(
            "fees", sa.Numeric(precision=28, scale=8), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "taxes", sa.Numeric(precision=28, scale=8), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("fx_rate", sa.Numeric(precision=28, scale=12), nullable=False),
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
        sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name=op.f("ck_income_events_currency")),
        sa.CheckConstraint(
            "income_type IN ('DIVIDEND', 'INTEREST', 'COUPON', 'RENT', 'DISTRIBUTION')",
            name=op.f("ck_income_events_income_type"),
        ),
        sa.CheckConstraint("fx_rate > 0", name=op.f("ck_income_events_fx_rate_positive")),
        sa.CheckConstraint(
            "gross >= 0 AND fees >= 0 AND taxes >= 0",
            name=op.f("ck_income_events_amounts_non_negative"),
        ),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["assets.id"],
            name=op.f("fk_income_events_asset_id_assets"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["portfolio_id"],
            ["portfolios.id"],
            name=op.f("fk_income_events_portfolio_id_portfolios"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["transaction_id"],
            ["transactions.id"],
            name=op.f("fk_income_events_transaction_id_transactions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_income_events")),
        sa.UniqueConstraint("transaction_id", name="uq_income_events_transaction_id"),
    )
    op.create_index("ix_income_events_asset_id", "income_events", ["asset_id"], unique=False)
    op.create_index(
        "ix_income_events_portfolio_id_paid_on",
        "income_events",
        ["portfolio_id", "paid_on"],
        unique=False,
    )
    op.execute(
        """
        INSERT INTO income_events (
            transaction_id, portfolio_id, asset_id, income_type, paid_on, currency,
            gross, fees, taxes, fx_rate
        )
        SELECT t.id, t.portfolio_id, t.asset_id, t.transaction_type, t.trade_date, t.currency,
               t.gross_amount, t.fees, t.taxes, t.fx_rate_to_portfolio_currency
        FROM transactions t
        WHERE t.transaction_type IN ('DIVIDEND', 'INTEREST', 'COUPON', 'RENT', 'DISTRIBUTION')
          AND t.reverses_transaction_id IS NULL
          AND NOT EXISTS (SELECT 1 FROM transactions r WHERE r.reverses_transaction_id = t.id)
        """
    )


def downgrade() -> None:
    op.drop_index("ix_income_events_portfolio_id_paid_on", table_name="income_events")
    op.drop_index("ix_income_events_asset_id", table_name="income_events")
    op.drop_table("income_events")
