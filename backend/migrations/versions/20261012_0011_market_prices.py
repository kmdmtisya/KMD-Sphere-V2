"""market_prices (P08-T05)

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "market_prices",
        sa.Column("asset_id", sa.UUID(), nullable=False),
        sa.Column("price", sa.Numeric(precision=28, scale=12), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("price_type", sa.String(length=8), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint("price > 0", name=op.f("ck_market_prices_price_positive")),
        sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name=op.f("ck_market_prices_currency")),
        sa.CheckConstraint(
            "price_type IN ('quote', 'close')", name=op.f("ck_market_prices_price_type")
        ),
        sa.CheckConstraint(
            "retrieved_at >= as_of", name=op.f("ck_market_prices_retrieved_after_as_of")
        ),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["assets.id"],
            name=op.f("fk_market_prices_asset_id_assets"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_market_prices")),
        sa.UniqueConstraint(
            "asset_id",
            "provider",
            "price_type",
            "as_of",
            name="uq_market_prices_asset_provider_type_as_of",
        ),
    )
    op.create_index(
        "ix_market_prices_asset_id_as_of", "market_prices", ["asset_id", "as_of"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_market_prices_asset_id_as_of", table_name="market_prices")
    op.drop_table("market_prices")
