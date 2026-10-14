"""forex_contract_specs: the reviewed, versioned contract specifications (P13-T07, DEC-24)

Revision ID: 0023
Revises: 0022
Create Date: 2026-10-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "forex_contract_specs",
        sa.Column("instrument", sa.String(length=7), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("contract_size", sa.Numeric(precision=20, scale=4), nullable=False),
        sa.Column("lot_step", sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column("min_lots", sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column("max_lots", sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column("margin_rate", sa.Numeric(precision=8, scale=6), nullable=False),
        sa.Column("commission_per_lot_side", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("slippage_pips", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("review_status", sa.String(length=16), nullable=False),
        sa.Column("reviewed_by", sa.String(length=200), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
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
            "contract_size > 0 AND lot_step > 0 AND min_lots > 0 AND max_lots >= min_lots",
            name=op.f("ck_forex_contract_specs_sizes"),
        ),
        sa.CheckConstraint(
            "margin_rate > 0 AND margin_rate <= 1", name=op.f("ck_forex_contract_specs_margin_rate")
        ),
        sa.CheckConstraint(
            "commission_per_lot_side >= 0 AND slippage_pips >= 0",
            name=op.f("ck_forex_contract_specs_costs"),
        ),
        sa.CheckConstraint(
            "review_status IN ('unreviewed', 'reviewed')",
            name=op.f("ck_forex_contract_specs_review_status"),
        ),
        sa.CheckConstraint(
            "status IN ('active', 'superseded')", name=op.f("ck_forex_contract_specs_status")
        ),
        sa.ForeignKeyConstraint(
            ["instrument"],
            ["forex_instruments.code"],
            name=op.f("fk_forex_contract_specs_instrument_forex_instruments"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_forex_contract_specs")),
        sa.UniqueConstraint(
            "instrument", "version", name="uq_forex_contract_specs_instrument_version"
        ),
    )
    op.create_index(
        "uq_forex_contract_specs_active",
        "forex_contract_specs",
        ["instrument"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )


def downgrade() -> None:
    op.drop_table("forex_contract_specs")
