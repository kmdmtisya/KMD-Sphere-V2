"""goals and goal_scenarios (P06-T06)

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "goals",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("portfolio_id", sa.UUID(), nullable=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column(
            "goal_type", sa.String(length=24), server_default=sa.text("'wealth'"), nullable=False
        ),
        sa.Column("target_amount", sa.Numeric(precision=28, scale=8), nullable=False),
        sa.Column("target_currency", sa.String(length=3), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=False),
        sa.Column(
            "target_in_todays_money", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "contribution",
            sa.Numeric(precision=28, scale=8),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "contribution_frequency",
            sa.String(length=16),
            server_default=sa.text("'monthly'"),
            nullable=False,
        ),
        sa.Column(
            "contribution_growth_percent",
            sa.Numeric(precision=9, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "inflation_percent",
            sa.Numeric(precision=9, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "annual_fee_percent",
            sa.Numeric(precision=9, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "compounding_frequency",
            sa.String(length=16),
            server_default=sa.text("'monthly'"),
            nullable=False,
        ),
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
            "compounding_frequency IN ('monthly', 'quarterly', 'yearly')",
            name=op.f("ck_goals_compounding_frequency"),
        ),
        sa.CheckConstraint(
            "contribution_frequency IN ('monthly', 'quarterly', 'yearly')",
            name=op.f("ck_goals_contribution_frequency"),
        ),
        sa.CheckConstraint(
            "goal_type IN ('wealth', 'retirement', 'education', 'house_deposit', 'business_capital', 'custom')",
            name=op.f("ck_goals_goal_type"),
        ),
        sa.CheckConstraint("target_currency ~ '^[A-Z]{3}$'", name=op.f("ck_goals_target_currency")),
        sa.CheckConstraint("contribution >= 0", name=op.f("ck_goals_contribution_non_negative")),
        sa.CheckConstraint(
            "contribution_growth_percent >= 0 AND inflation_percent >= 0 AND annual_fee_percent >= 0",
            name=op.f("ck_goals_percents_non_negative"),
        ),
        sa.CheckConstraint("length(btrim(name)) BETWEEN 1 AND 100", name=op.f("ck_goals_name")),
        sa.CheckConstraint("target_amount > 0", name=op.f("ck_goals_target_amount_positive")),
        sa.ForeignKeyConstraint(
            ["portfolio_id"],
            ["portfolios.id"],
            name=op.f("fk_goals_portfolio_id_portfolios"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_goals_user_id_users"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_goals")),
        sa.UniqueConstraint("user_id", "name", name="uq_goals_user_id_name"),
    )
    op.create_index("ix_goals_portfolio_id", "goals", ["portfolio_id"], unique=False)
    op.create_table(
        "goal_scenarios",
        sa.Column("goal_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("annual_return_percent", sa.Numeric(precision=9, scale=4), nullable=False),
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
            "kind IN ('conservative', 'base', 'growth')", name=op.f("ck_goal_scenarios_kind")
        ),
        sa.ForeignKeyConstraint(
            ["goal_id"],
            ["goals.id"],
            name=op.f("fk_goal_scenarios_goal_id_goals"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_goal_scenarios")),
        sa.UniqueConstraint("goal_id", "kind", name="uq_goal_scenarios_goal_id_kind"),
    )


def downgrade() -> None:
    op.drop_table("goal_scenarios")
    op.drop_index("ix_goals_portfolio_id", table_name="goals")
    op.drop_table("goals")
