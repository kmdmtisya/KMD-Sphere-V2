"""forex_paper_*: paper-trading accounts, orders, positions and journal (P13-T09)

PAPER TRADING only. No foreign key into portfolios, holdings, transactions or net-worth tables,
and none from them: paper money never enters real-money views.

Revision ID: 0025
Revises: 0024
Create Date: 2026-10-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PRICE = sa.Numeric(precision=20, scale=10)
MONEY = sa.Numeric(precision=20, scale=4)
LOTS = sa.Numeric(precision=10, scale=4)


def _base() -> list[sa.Column]:  # type: ignore[type-arg]
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


def _user(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["user_id"], ["users.id"], name=op.f(f"fk_{table}_user_id_users"), ondelete="CASCADE"
    )


def _account(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["account_id"],
        ["forex_paper_accounts.id"],
        name=op.f(f"fk_{table}_account_id_forex_paper_accounts"),
        ondelete="CASCADE",
    )


def _instrument(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["instrument"],
        ["forex_instruments.code"],
        name=op.f(f"fk_{table}_instrument_forex_instruments"),
        ondelete="RESTRICT",
    )


def upgrade() -> None:
    t = "forex_paper_accounts"
    op.create_table(
        t,
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("starting_balance", MONEY, nullable=False),
        sa.Column("starting_balance_is_default", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        *_base(),
        sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name=op.f(f"ck_{t}_currency")),
        sa.CheckConstraint("starting_balance > 0", name=op.f(f"ck_{t}_starting_balance")),
        sa.CheckConstraint("status IN ('active', 'closed')", name=op.f(f"ck_{t}_status")),
        sa.CheckConstraint("length(btrim(name)) BETWEEN 1 AND 100", name=op.f(f"ck_{t}_name")),
        _user(t),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{t}")),
    )
    op.create_index(f"ix_{t}_user_id", t, ["user_id"])

    t = "forex_paper_orders"
    op.create_table(
        t,
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("instrument", sa.String(length=7), nullable=False),
        sa.Column("side", sa.String(length=5), nullable=False),
        sa.Column("order_type", sa.String(length=6), nullable=False),
        sa.Column("lots", LOTS, nullable=False),
        sa.Column("units", MONEY, nullable=False),
        sa.Column("limit_price", PRICE, nullable=True),
        sa.Column("stop", PRICE, nullable=False),
        sa.Column("target", PRICE, nullable=True),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("reject_reason", sa.String(length=200), nullable=True),
        sa.Column("strategy_tag", sa.String(length=40), nullable=True),
        sa.Column("spec_version", sa.Integer(), nullable=False),
        sa.Column("checked_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("filled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        *_base(),
        sa.CheckConstraint("side IN ('long', 'short')", name=op.f(f"ck_{t}_side")),
        sa.CheckConstraint("order_type IN ('market', 'limit')", name=op.f(f"ck_{t}_order_type")),
        sa.CheckConstraint(
            "status IN ('pending', 'filled', 'cancelled', 'rejected')", name=op.f(f"ck_{t}_status")
        ),
        sa.CheckConstraint("units > 0", name=op.f(f"ck_{t}_units")),
        sa.CheckConstraint(
            "(order_type = 'limit') = (limit_price IS NOT NULL)", name=op.f(f"ck_{t}_limit_price")
        ),
        _account(t),
        _user(t),
        _instrument(t),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{t}")),
    )
    op.create_index(f"ix_{t}_account_id_status", t, ["account_id", "status"])
    op.create_index(f"ix_{t}_user_id", t, ["user_id"])

    t = "forex_paper_positions"
    op.create_table(
        t,
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("order_id", sa.UUID(), nullable=False),
        sa.Column("instrument", sa.String(length=7), nullable=False),
        sa.Column("side", sa.String(length=5), nullable=False),
        sa.Column("lots", LOTS, nullable=False),
        sa.Column("units", MONEY, nullable=False),
        sa.Column("entry_price", PRICE, nullable=False),
        sa.Column("entry_mid", PRICE, nullable=False),
        sa.Column("entry_quote_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data_type", sa.String(length=16), nullable=False),
        sa.Column("stop", PRICE, nullable=False),
        sa.Column("target", PRICE, nullable=True),
        sa.Column("margin", MONEY, nullable=False),
        sa.Column("entry_commission", MONEY, nullable=False),
        sa.Column("strategy_tag", sa.String(length=40), nullable=True),
        sa.Column("status", sa.String(length=6), nullable=False),
        sa.Column("checked_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("exit_price", PRICE, nullable=True),
        sa.Column("exit_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("exit_reason", sa.String(length=12), nullable=True),
        sa.Column("exit_rate", sa.Numeric(precision=30, scale=15), nullable=True),
        sa.Column("exit_rate_path", sa.String(length=80), nullable=True),
        sa.Column("realised_pnl", MONEY, nullable=True),
        sa.Column("costs", MONEY, nullable=True),
        *_base(),
        sa.CheckConstraint("side IN ('long', 'short')", name=op.f(f"ck_{t}_side")),
        sa.CheckConstraint("status IN ('open', 'closed')", name=op.f(f"ck_{t}_status")),
        sa.CheckConstraint("units > 0", name=op.f(f"ck_{t}_units")),
        sa.CheckConstraint(
            "exit_reason IS NULL OR exit_reason IN ('stop', 'target', 'manual')",
            name=op.f(f"ck_{t}_exit_reason"),
        ),
        sa.CheckConstraint(
            "(status = 'closed') = (exit_at IS NOT NULL AND exit_price IS NOT NULL "
            "AND realised_pnl IS NOT NULL)",
            name=op.f(f"ck_{t}_closed_fields"),
        ),
        _account(t),
        _user(t),
        _instrument(t),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["forex_paper_orders.id"],
            name=op.f(f"fk_{t}_order_id_forex_paper_orders"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{t}")),
        sa.UniqueConstraint("order_id", name=op.f(f"uq_{t}_order_id")),
    )
    op.create_index(f"ix_{t}_account_id_status", t, ["account_id", "status"])
    op.create_index(f"ix_{t}_user_id", t, ["user_id"])

    t = "forex_paper_journal"
    op.create_table(
        t,
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("position_id", sa.UUID(), nullable=True),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("tags", postgresql.ARRAY(sa.String(length=40)), nullable=False),
        *_base(),
        sa.CheckConstraint("length(btrim(note)) BETWEEN 1 AND 4000", name=op.f(f"ck_{t}_note")),
        sa.CheckConstraint("cardinality(tags) <= 10", name=op.f(f"ck_{t}_tags")),
        _account(t),
        _user(t),
        sa.ForeignKeyConstraint(
            ["position_id"],
            ["forex_paper_positions.id"],
            name=op.f(f"fk_{t}_position_id_forex_paper_positions"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{t}")),
    )
    op.create_index(f"ix_{t}_account_id_created_at", t, ["account_id", "created_at"])
    op.create_index(f"ix_{t}_user_id", t, ["user_id"])


def downgrade() -> None:
    op.drop_table("forex_paper_journal")
    op.drop_table("forex_paper_positions")
    op.drop_table("forex_paper_orders")
    op.drop_table("forex_paper_accounts")
