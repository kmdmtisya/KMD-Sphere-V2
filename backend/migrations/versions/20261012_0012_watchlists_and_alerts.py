"""watchlist_items, alert_preferences, alerts, alert_events (P08-T07)

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid_pk() -> sa.Column:  # type: ignore[type-arg]
    return sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False)


def _timestamps() -> list[sa.Column]:  # type: ignore[type-arg]
    return [
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


def upgrade() -> None:
    op.create_table(
        "watchlist_items",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("asset_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        _uuid_pk(),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_watchlist_items_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["assets.id"],
            name=op.f("fk_watchlist_items_asset_id_assets"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_watchlist_items")),
        sa.UniqueConstraint("user_id", "asset_id", name="uq_watchlist_items_user_id_asset_id"),
    )
    op.create_index("ix_watchlist_items_user_id", "watchlist_items", ["user_id"], unique=False)

    op.create_table(
        "alert_preferences",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("alerts_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "price_alerts_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column(
            "allocation_alerts_enabled",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_alert_preferences_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_alert_preferences")),
    )

    op.create_table(
        "alerts",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("alert_type", sa.String(length=20), nullable=False),
        sa.Column(
            "status", sa.String(length=12), server_default=sa.text("'active'"), nullable=False
        ),
        sa.Column("threshold", sa.Numeric(precision=28, scale=12), nullable=False),
        sa.Column("asset_id", sa.UUID(), nullable=True),
        sa.Column("portfolio_id", sa.UUID(), nullable=True),
        sa.Column("asset_class", sa.String(length=40), nullable=True),
        sa.Column("note", sa.String(length=200), nullable=True),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=True),
        _uuid_pk(),
        *_timestamps(),
        sa.CheckConstraint(
            "alert_type IN ('price_above', 'price_below', 'allocation_above')",
            name=op.f("ck_alerts_alert_type"),
        ),
        sa.CheckConstraint(
            "status IN ('active', 'triggered', 'paused')", name=op.f("ck_alerts_status")
        ),
        sa.CheckConstraint("threshold > 0", name=op.f("ck_alerts_threshold_positive")),
        sa.CheckConstraint(
            "(alert_type IN ('price_above', 'price_below') AND asset_id IS NOT NULL "
            "AND portfolio_id IS NULL AND asset_class IS NULL) OR "
            "(alert_type = 'allocation_above' AND asset_id IS NULL AND portfolio_id IS NOT NULL "
            "AND asset_class IS NOT NULL AND threshold <= 100)",
            name=op.f("ck_alerts_shape"),
        ),
        sa.CheckConstraint(
            "note IS NULL OR length(btrim(note)) BETWEEN 1 AND 200", name=op.f("ck_alerts_note")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_alerts_user_id_users"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["asset_id"], ["assets.id"], name=op.f("fk_alerts_asset_id_assets"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["portfolio_id"],
            ["portfolios.id"],
            name=op.f("fk_alerts_portfolio_id_portfolios"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_alerts")),
    )
    op.create_index("ix_alerts_user_id_status", "alerts", ["user_id", "status"], unique=False)
    op.create_index("ix_alerts_status", "alerts", ["status"], unique=False)

    op.create_table(
        "alert_events",
        sa.Column("alert_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("trigger_key", sa.String(length=100), nullable=False),
        sa.Column("observed_value", sa.Numeric(precision=28, scale=12), nullable=False),
        sa.Column("observed_as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "triggered_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("seen_at", sa.DateTime(timezone=True), nullable=True),
        _uuid_pk(),
        sa.ForeignKeyConstraint(
            ["alert_id"],
            ["alerts.id"],
            name=op.f("fk_alert_events_alert_id_alerts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_alert_events_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_alert_events")),
        sa.UniqueConstraint("alert_id", "trigger_key", name="uq_alert_events_alert_id_trigger_key"),
    )
    op.create_index(
        "ix_alert_events_user_id_triggered_at",
        "alert_events",
        ["user_id", "triggered_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_alert_events_user_id_triggered_at", table_name="alert_events")
    op.drop_table("alert_events")
    op.drop_index("ix_alerts_status", table_name="alerts")
    op.drop_index("ix_alerts_user_id_status", table_name="alerts")
    op.drop_table("alerts")
    op.drop_table("alert_preferences")
    op.drop_index("ix_watchlist_items_user_id", table_name="watchlist_items")
    op.drop_table("watchlist_items")
