"""identity: users, user_profiles, risk_profiles

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("issuer", sa.String(length=255), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("email_verified", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "status", sa.String(length=16), server_default=sa.text("'active'"), nullable=False
        ),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint("status IN ('active', 'disabled')", name=op.f("ck_users_status")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("issuer", "subject", name="uq_users_issuer_subject"),
    )
    op.create_table(
        "risk_profiles",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("risk_tolerance", sa.String(length=16), nullable=False),
        sa.Column("horizon_years", sa.Integer(), nullable=True),
        sa.Column(
            "source",
            sa.String(length=32),
            server_default=sa.text("'self_assessment'"),
            nullable=False,
        ),
        sa.Column(
            "assessed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
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
            "risk_tolerance IN ('conservative', 'balanced', 'growth', 'aggressive')",
            name=op.f("ck_risk_profiles_risk_tolerance"),
        ),
        sa.CheckConstraint(
            "horizon_years IS NULL OR (horizon_years BETWEEN 0 AND 100)",
            name=op.f("ck_risk_profiles_horizon_years"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_risk_profiles_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_risk_profiles")),
    )
    op.create_index(op.f("ix_risk_profiles_user_id"), "risk_profiles", ["user_id"], unique=False)
    op.create_table(
        "user_profiles",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("display_name", sa.String(length=100), nullable=True),
        sa.Column(
            "base_currency", sa.String(length=3), server_default=sa.text("'USD'"), nullable=False
        ),
        sa.Column("locale", sa.String(length=35), server_default=sa.text("'en'"), nullable=False),
        sa.Column(
            "timezone", sa.String(length=64), server_default=sa.text("'UTC'"), nullable=False
        ),
        sa.Column(
            "preferences",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
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
            "base_currency ~ '^[A-Z]{3}$'", name=op.f("ck_user_profiles_base_currency")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_profiles_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_user_profiles")),
    )


def downgrade() -> None:
    op.drop_table("user_profiles")
    op.drop_index(op.f("ix_risk_profiles_user_id"), table_name="risk_profiles")
    op.drop_table("risk_profiles")
    op.drop_table("users")
