"""investment universe and residence country (P12-T02)

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LIQUIDITY = "('immediate', 'market', 'term', 'illiquid', 'unknown')"


def upgrade() -> None:
    op.add_column("user_profiles", sa.Column("residence_country", sa.String(length=2)))
    op.create_check_constraint(
        op.f("ck_user_profiles_residence_country"),
        "user_profiles",
        "residence_country IS NULL OR residence_country ~ '^[A-Z]{2}$'",
    )
    op.create_table(
        "universe_instruments",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("asset_id", sa.UUID(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("is_demo", sa.Boolean(), nullable=False),
        sa.Column("licence_status", sa.String(length=16), nullable=False),
        sa.Column("risk_level", sa.SmallInteger(), nullable=False),
        sa.Column("liquidity", sa.String(length=16), nullable=False),
        sa.Column("jurisdictions", postgresql.ARRAY(sa.String(length=2)), nullable=False),
        sa.Column("minimum_investment", sa.Numeric(precision=20, scale=4)),
        sa.Column("data_as_of", sa.DateTime(timezone=True), nullable=False),
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
        sa.CheckConstraint(
            "risk_level BETWEEN 1 AND 5", name=op.f("ck_universe_instruments_risk_level")
        ),
        sa.CheckConstraint(
            f"liquidity IN {LIQUIDITY}", name=op.f("ck_universe_instruments_liquidity")
        ),
        sa.CheckConstraint(
            "licence_status IN ('demo', 'unconfirmed', 'licensed')",
            name=op.f("ck_universe_instruments_licence_status"),
        ),
        sa.CheckConstraint(
            "minimum_investment IS NULL OR minimum_investment >= 0",
            name=op.f("ck_universe_instruments_minimum_investment"),
        ),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["assets.id"],
            name=op.f("fk_universe_instruments_asset_id_assets"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_universe_instruments")),
        sa.UniqueConstraint("asset_id", name=op.f("uq_universe_instruments_asset_id")),
    )
    op.create_index(
        "ix_universe_instruments_source_active", "universe_instruments", ["source", "is_active"]
    )


def downgrade() -> None:
    op.drop_index("ix_universe_instruments_source_active", table_name="universe_instruments")
    op.drop_table("universe_instruments")
    op.drop_constraint(op.f("ck_user_profiles_residence_country"), "user_profiles", type_="check")
    op.drop_column("user_profiles", "residence_country")
