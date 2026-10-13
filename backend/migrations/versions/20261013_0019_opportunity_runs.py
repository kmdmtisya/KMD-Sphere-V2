"""opportunity_runs and opportunities: the opportunity pipeline's runs, kept unchanged (P12-T06)

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_REJECT = """
CREATE FUNCTION opportunities_reject_update() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION '% rows are kept as they were: UPDATE is not allowed', TG_TABLE_NAME
        USING ERRCODE = 'insufficient_privilege';
END;
$$
"""


def upgrade() -> None:
    op.create_table(
        "opportunity_runs",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("portfolio_id", sa.UUID(), nullable=True),
        sa.Column("amount", sa.Numeric(precision=20, scale=4), nullable=True),
        sa.Column("amount_currency", sa.String(length=3), nullable=True),
        sa.Column("asset_class", sa.String(length=40), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("explanation_source", sa.String(length=16), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=True),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("problems", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("weights", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("investor", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("excluded", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint(
            "explanation_source IN ('model', 'template')",
            name=op.f("ck_opportunity_runs_explanation_source"),
        ),
        sa.CheckConstraint(
            "(amount IS NULL) = (amount_currency IS NULL)",
            name=op.f("ck_opportunity_runs_amount_with_currency"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_opportunity_runs_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_opportunity_runs")),
    )
    op.create_index(
        "ix_opportunity_runs_user_id_created_at", "opportunity_runs", ["user_id", "created_at"]
    )
    op.create_table(
        "opportunities",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("rank", sa.SmallInteger(), nullable=False),
        sa.Column("asset_id", sa.UUID(), nullable=False),
        sa.Column("is_demo", sa.Boolean(), nullable=False),
        sa.Column("facts", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("explanation", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("explanation_source", sa.String(length=16), nullable=False),
        sa.CheckConstraint("rank >= 1", name=op.f("ck_opportunities_rank")),
        sa.CheckConstraint(
            "explanation_source IN ('model', 'template')",
            name=op.f("ck_opportunities_explanation_source"),
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["opportunity_runs.id"],
            name=op.f("fk_opportunities_run_id_opportunity_runs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["assets.id"],
            name=op.f("fk_opportunities_asset_id_assets"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_opportunities")),
    )
    op.create_index(
        "ix_opportunities_run_id_rank", "opportunities", ["run_id", "rank"], unique=True
    )
    op.execute(_REJECT)
    for table in ("opportunity_runs", "opportunities"):
        op.execute(
            f"CREATE TRIGGER {table}_no_update BEFORE UPDATE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION opportunities_reject_update()"
        )


def downgrade() -> None:
    for table in ("opportunities", "opportunity_runs"):
        op.execute(f"DROP TRIGGER {table}_no_update ON {table}")
    op.execute("DROP FUNCTION opportunities_reject_update()")
    op.drop_index("ix_opportunities_run_id_rank", table_name="opportunities")
    op.drop_table("opportunities")
    op.drop_index("ix_opportunity_runs_user_id_created_at", table_name="opportunity_runs")
    op.drop_table("opportunity_runs")
