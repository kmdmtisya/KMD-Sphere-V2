"""forex_economic_events and forex_policy_rates: the economic calendar and policy rates (P13-T04)

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LICENCES = "('demo', 'public_domain', 'unconfirmed', 'licensed')"


def _common() -> list[sa.Column]:
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


def upgrade() -> None:
    op.create_table(
        "forex_economic_events",
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("source_event_id", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("currencies", postgresql.ARRAY(sa.String(length=3)), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("importance", sa.String(length=8), nullable=False),
        sa.Column("unit", sa.String(length=20), nullable=True),
        sa.Column("actual", sa.Numeric(precision=28, scale=8), nullable=True),
        sa.Column("previous", sa.Numeric(precision=28, scale=8), nullable=True),
        sa.Column("forecast", sa.Numeric(precision=28, scale=8), nullable=True),
        sa.Column("commentary", sa.Text(), nullable=True),
        sa.Column("source_url", sa.String(length=500), nullable=True),
        sa.Column("is_demo", sa.Boolean(), nullable=False),
        sa.Column("licence_status", sa.String(length=16), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actual_seen_at", sa.DateTime(timezone=True), nullable=True),
        *_common(),
        sa.CheckConstraint(
            "kind IN ('indicator', 'central_bank_decision', 'speech', 'other')",
            name=op.f("ck_forex_economic_events_kind"),
        ),
        sa.CheckConstraint(
            "importance IN ('low', 'medium', 'high')",
            name=op.f("ck_forex_economic_events_importance"),
        ),
        sa.CheckConstraint(
            f"licence_status IN {LICENCES}", name=op.f("ck_forex_economic_events_licence_status")
        ),
        sa.CheckConstraint(
            "cardinality(currencies) >= 1", name=op.f("ck_forex_economic_events_currencies")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_forex_economic_events")),
        sa.UniqueConstraint(
            "source", "source_event_id", name="uq_forex_economic_events_source_event"
        ),
    )
    op.create_index(
        "ix_forex_economic_events_scheduled_at", "forex_economic_events", ["scheduled_at"]
    )
    op.create_table(
        "forex_policy_rates",
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("bank", sa.String(length=100), nullable=False),
        sa.Column("rate", sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_url", sa.String(length=500), nullable=True),
        sa.Column("is_demo", sa.Boolean(), nullable=False),
        sa.Column("licence_status", sa.String(length=16), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        *_common(),
        sa.CheckConstraint("rate BETWEEN -10 AND 100", name=op.f("ck_forex_policy_rates_rate")),
        sa.CheckConstraint(
            f"licence_status IN {LICENCES}", name=op.f("ck_forex_policy_rates_licence_status")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_forex_policy_rates")),
        sa.UniqueConstraint(
            "source",
            "currency",
            "effective_date",
            name="uq_forex_policy_rates_source_currency_date",
        ),
    )
    op.create_index(
        "ix_forex_policy_rates_currency_effective_date",
        "forex_policy_rates",
        ["currency", "effective_date"],
    )


def downgrade() -> None:
    op.drop_table("forex_policy_rates")
    op.drop_table("forex_economic_events")
