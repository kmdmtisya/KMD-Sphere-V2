"""liabilities (P06-T07)

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "liabilities",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("liability_type", sa.String(length=24), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("balance", sa.Numeric(precision=28, scale=8), nullable=False),
        sa.Column("balance_as_of", sa.Date(), nullable=False),
        sa.Column("interest_rate_percent", sa.Numeric(precision=9, scale=4), nullable=True),
        sa.Column("asset_id", sa.UUID(), nullable=True),
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
        sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name=op.f("ck_liabilities_currency")),
        sa.CheckConstraint(
            "liability_type IN ('mortgage', 'personal_loan', 'car_loan', 'student_loan', 'business_loan', 'credit_card', 'other')",
            name=op.f("ck_liabilities_liability_type"),
        ),
        sa.CheckConstraint("balance >= 0", name=op.f("ck_liabilities_balance_non_negative")),
        sa.CheckConstraint(
            "interest_rate_percent IS NULL OR interest_rate_percent >= 0",
            name=op.f("ck_liabilities_interest_rate_non_negative"),
        ),
        sa.CheckConstraint(
            "length(btrim(name)) BETWEEN 1 AND 100", name=op.f("ck_liabilities_name")
        ),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["assets.id"],
            name=op.f("fk_liabilities_asset_id_assets"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_liabilities_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_liabilities")),
        sa.UniqueConstraint("user_id", "name", name="uq_liabilities_user_id_name"),
    )
    op.create_index("ix_liabilities_asset_id", "liabilities", ["asset_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_liabilities_asset_id", table_name="liabilities")
    op.drop_table("liabilities")
