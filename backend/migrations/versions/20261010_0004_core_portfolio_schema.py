"""core portfolio schema (P05-T01)

Portfolios, members, asset catalogue, ledger, holdings, valuations and FX rates.

The ledger (`transactions`) is append-only: UPDATE, DELETE and TRUNCATE are rejected by triggers.
Corrections are reversal entries (P05-T04).

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_REJECT_FUNCTION = """
CREATE FUNCTION transactions_reject_change() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'transactions is append-only: % is not allowed (post a reversal)', TG_OP
        USING ERRCODE = 'insufficient_privilege';
END;
$$
"""


def upgrade() -> None:
    op.create_table(
        "asset_classes",
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("valuation_mode", sa.String(length=16), nullable=False),
        sa.Column(
            "metadata_schema",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
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
        sa.CheckConstraint("code ~ '^[a-z][a-z0-9_]{1,39}$'", name=op.f("ck_asset_classes_code")),
        sa.CheckConstraint(
            "valuation_mode IN ('market', 'manual')", name=op.f("ck_asset_classes_valuation_mode")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_asset_classes")),
        sa.UniqueConstraint("code", name="uq_asset_classes_code"),
    )
    op.create_table(
        "fx_rates",
        sa.Column("base_currency", sa.String(length=3), nullable=False),
        sa.Column("quote_currency", sa.String(length=3), nullable=False),
        sa.Column("rate", sa.Numeric(precision=28, scale=12), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("rate_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
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
        sa.CheckConstraint("base_currency ~ '^[A-Z]{3}$'", name=op.f("ck_fx_rates_base_currency")),
        sa.CheckConstraint(
            "quote_currency ~ '^[A-Z]{3}$'", name=op.f("ck_fx_rates_quote_currency")
        ),
        sa.CheckConstraint(
            "base_currency <> quote_currency", name=op.f("ck_fx_rates_distinct_currencies")
        ),
        sa.CheckConstraint("rate > 0", name=op.f("ck_fx_rates_rate_positive")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fx_rates")),
        sa.UniqueConstraint(
            "base_currency",
            "quote_currency",
            "provider",
            "rate_timestamp",
            name="uq_fx_rates_pair_provider_timestamp",
        ),
    )
    op.create_index(
        "ix_fx_rates_pair_rate_timestamp",
        "fx_rates",
        ["base_currency", "quote_currency", "rate_timestamp"],
        unique=False,
    )
    op.create_table(
        "assets",
        sa.Column("asset_class_id", sa.UUID(), nullable=False),
        sa.Column("owner_user_id", sa.UUID(), nullable=True),
        sa.Column("symbol", sa.String(length=32), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("subtype", sa.String(length=64), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("country", sa.String(length=2), nullable=True),
        sa.Column("external_provider", sa.String(length=32), nullable=True),
        sa.Column("external_provider_id", sa.String(length=128), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
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
            "country IS NULL OR country ~ '^[A-Z]{2}$'", name=op.f("ck_assets_country")
        ),
        sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name=op.f("ck_assets_currency")),
        sa.CheckConstraint(
            "(external_provider IS NULL) = (external_provider_id IS NULL)",
            name=op.f("ck_assets_external_ref"),
        ),
        sa.CheckConstraint("length(btrim(name)) BETWEEN 1 AND 200", name=op.f("ck_assets_name")),
        sa.ForeignKeyConstraint(
            ["asset_class_id"],
            ["asset_classes.id"],
            name=op.f("fk_assets_asset_class_id_asset_classes"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["users.id"],
            name=op.f("fk_assets_owner_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assets")),
    )
    op.create_index("ix_assets_asset_class_id", "assets", ["asset_class_id"], unique=False)
    op.create_index("ix_assets_owner_user_id", "assets", ["owner_user_id"], unique=False)
    op.create_index("ix_assets_symbol", "assets", ["symbol"], unique=False)
    op.create_index(
        "uq_assets_external_ref",
        "assets",
        ["external_provider", "external_provider_id"],
        unique=True,
        postgresql_where=sa.text("external_provider IS NOT NULL"),
    )
    op.create_table(
        "portfolios",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("base_currency", sa.String(length=3), nullable=False),
        sa.Column(
            "portfolio_type",
            sa.String(length=16),
            server_default=sa.text("'personal'"),
            nullable=False,
        ),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
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
            "base_currency ~ '^[A-Z]{3}$'", name=op.f("ck_portfolios_base_currency")
        ),
        sa.CheckConstraint(
            "portfolio_type IN ('personal', 'family', 'retirement', 'geographic', 'strategy')",
            name=op.f("ck_portfolios_portfolio_type"),
        ),
        sa.CheckConstraint(
            "length(btrim(name)) BETWEEN 1 AND 100", name=op.f("ck_portfolios_name")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_portfolios_user_id_users"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_portfolios")),
        sa.UniqueConstraint("user_id", "name", name="uq_portfolios_user_id_name"),
    )
    op.create_index(
        "ix_portfolios_user_id_archived_at", "portfolios", ["user_id", "archived_at"], unique=False
    )
    op.create_table(
        "asset_metadata",
        sa.Column("asset_id", sa.UUID(), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=True),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint("key ~ '^[a-z][a-z0-9_]{0,63}$'", name=op.f("ck_asset_metadata_key")),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["assets.id"],
            name=op.f("fk_asset_metadata_asset_id_assets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_asset_metadata")),
        sa.UniqueConstraint("asset_id", "key", name="uq_asset_metadata_asset_id_key"),
    )
    op.create_table(
        "holdings",
        sa.Column("portfolio_id", sa.UUID(), nullable=False),
        sa.Column("asset_id", sa.UUID(), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=28, scale=12), nullable=False),
        sa.Column("cost_basis", sa.Numeric(precision=28, scale=8), nullable=False),
        sa.Column(
            "realized_pl",
            sa.Numeric(precision=28, scale=8),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("last_transaction_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "computed_at",
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
        sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name=op.f("ck_holdings_currency")),
        sa.CheckConstraint("quantity >= 0", name=op.f("ck_holdings_quantity_non_negative")),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["assets.id"],
            name=op.f("fk_holdings_asset_id_assets"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["portfolio_id"],
            ["portfolios.id"],
            name=op.f("fk_holdings_portfolio_id_portfolios"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_holdings")),
        sa.UniqueConstraint("portfolio_id", "asset_id", name="uq_holdings_portfolio_id_asset_id"),
    )
    op.create_index("ix_holdings_asset_id", "holdings", ["asset_id"], unique=False)
    op.create_table(
        "portfolio_members",
        sa.Column("portfolio_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("role", sa.String(length=16), server_default=sa.text("'viewer'"), nullable=False),
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
        sa.CheckConstraint("role IN ('viewer', 'editor')", name=op.f("ck_portfolio_members_role")),
        sa.ForeignKeyConstraint(
            ["portfolio_id"],
            ["portfolios.id"],
            name=op.f("fk_portfolio_members_portfolio_id_portfolios"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_portfolio_members_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_portfolio_members")),
        sa.UniqueConstraint(
            "portfolio_id", "user_id", name="uq_portfolio_members_portfolio_id_user_id"
        ),
    )
    op.create_index("ix_portfolio_members_user_id", "portfolio_members", ["user_id"], unique=False)
    op.create_table(
        "transactions",
        sa.Column("portfolio_id", sa.UUID(), nullable=False),
        sa.Column("asset_id", sa.UUID(), nullable=True),
        sa.Column("transaction_type", sa.String(length=24), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("settlement_date", sa.Date(), nullable=True),
        sa.Column("quantity", sa.Numeric(precision=28, scale=12), nullable=True),
        sa.Column("unit_price", sa.Numeric(precision=28, scale=8), nullable=True),
        sa.Column("gross_amount", sa.Numeric(precision=28, scale=8), nullable=False),
        sa.Column(
            "fees", sa.Numeric(precision=28, scale=8), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "taxes", sa.Numeric(precision=28, scale=8), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column(
            "fx_rate_to_portfolio_currency",
            sa.Numeric(precision=28, scale=12),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column("fx_rate_as_of", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fx_rate_source", sa.String(length=32), nullable=True),
        sa.Column(
            "source", sa.String(length=16), server_default=sa.text("'manual'"), nullable=False
        ),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("reverses_transaction_id", sa.UUID(), nullable=True),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("created_by_user_id", sa.UUID(), nullable=False),
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
        sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name=op.f("ck_transactions_currency")),
        sa.CheckConstraint(
            "source IN ('manual', 'import', 'system')", name=op.f("ck_transactions_source")
        ),
        sa.CheckConstraint(
            "transaction_type = 'VALUATION_ADJUSTMENT' OR gross_amount >= 0",
            name=op.f("ck_transactions_gross_amount_non_negative"),
        ),
        sa.CheckConstraint(
            "transaction_type IN ('BUY', 'SELL', 'DEPOSIT', 'WITHDRAWAL', 'DIVIDEND', 'INTEREST', 'COUPON', 'RENT', 'DISTRIBUTION', 'FEE', 'TAX', 'TRANSFER_IN', 'TRANSFER_OUT', 'VALUATION_ADJUSTMENT')",
            name=op.f("ck_transactions_transaction_type"),
        ),
        sa.CheckConstraint(
            "transaction_type NOT IN ('BUY', 'SELL') OR (asset_id IS NOT NULL AND quantity > 0 AND unit_price IS NOT NULL)",
            name=op.f("ck_transactions_trade_has_asset_quantity_price"),
        ),
        sa.CheckConstraint(
            "fees >= 0 AND taxes >= 0", name=op.f("ck_transactions_fees_taxes_non_negative")
        ),
        sa.CheckConstraint(
            "fx_rate_to_portfolio_currency > 0", name=op.f("ck_transactions_fx_rate_positive")
        ),
        sa.CheckConstraint(
            "idempotency_key IS NULL OR length(idempotency_key) BETWEEN 1 AND 128",
            name=op.f("ck_transactions_idempotency_key_length"),
        ),
        sa.CheckConstraint(
            "quantity IS NULL OR quantity >= 0", name=op.f("ck_transactions_quantity_non_negative")
        ),
        sa.CheckConstraint(
            "reverses_transaction_id IS NULL OR reverses_transaction_id <> id",
            name=op.f("ck_transactions_not_self_reversal"),
        ),
        sa.CheckConstraint(
            "settlement_date IS NULL OR settlement_date >= trade_date",
            name=op.f("ck_transactions_settlement_after_trade"),
        ),
        sa.CheckConstraint(
            "unit_price IS NULL OR unit_price >= 0",
            name=op.f("ck_transactions_unit_price_non_negative"),
        ),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["assets.id"],
            name=op.f("fk_transactions_asset_id_assets"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_transactions_created_by_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["portfolio_id", "reverses_transaction_id"],
            ["transactions.portfolio_id", "transactions.id"],
            name="fk_transactions_reversal_same_portfolio",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["portfolio_id"],
            ["portfolios.id"],
            name=op.f("fk_transactions_portfolio_id_portfolios"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_transactions")),
        sa.UniqueConstraint("portfolio_id", "id", name="uq_transactions_portfolio_id_id"),
        sa.UniqueConstraint(
            "portfolio_id", "idempotency_key", name="uq_transactions_portfolio_id_idempotency_key"
        ),
        sa.UniqueConstraint(
            "reverses_transaction_id", name="uq_transactions_reverses_transaction_id"
        ),
    )
    op.create_index("ix_transactions_asset_id", "transactions", ["asset_id"], unique=False)
    op.create_index(
        "ix_transactions_portfolio_id_trade_date",
        "transactions",
        ["portfolio_id", "trade_date", "id"],
        unique=False,
    )
    op.create_table(
        "valuations",
        sa.Column("portfolio_id", sa.UUID(), nullable=False),
        sa.Column("asset_id", sa.UUID(), nullable=False),
        sa.Column("value", sa.Numeric(precision=28, scale=8), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("created_by_user_id", sa.UUID(), nullable=False),
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
        sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name=op.f("ck_valuations_currency")),
        sa.CheckConstraint(
            "length(btrim(source)) BETWEEN 1 AND 64", name=op.f("ck_valuations_source")
        ),
        sa.CheckConstraint("value >= 0", name=op.f("ck_valuations_value_non_negative")),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["assets.id"],
            name=op.f("fk_valuations_asset_id_assets"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_valuations_created_by_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["portfolio_id"],
            ["portfolios.id"],
            name=op.f("fk_valuations_portfolio_id_portfolios"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_valuations")),
        sa.UniqueConstraint(
            "portfolio_id", "asset_id", "as_of", name="uq_valuations_portfolio_id_asset_id_as_of"
        ),
    )
    op.execute(_REJECT_FUNCTION)
    op.execute(
        "CREATE TRIGGER transactions_no_update_delete BEFORE UPDATE OR DELETE ON transactions "
        "FOR EACH ROW EXECUTE FUNCTION transactions_reject_change()"
    )
    op.execute(
        "CREATE TRIGGER transactions_no_truncate BEFORE TRUNCATE ON transactions "
        "FOR EACH STATEMENT EXECUTE FUNCTION transactions_reject_change()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER transactions_no_truncate ON transactions")
    op.execute("DROP TRIGGER transactions_no_update_delete ON transactions")
    op.execute("DROP FUNCTION transactions_reject_change()")
    op.drop_table("valuations")
    op.drop_index("ix_transactions_portfolio_id_trade_date", table_name="transactions")
    op.drop_index("ix_transactions_asset_id", table_name="transactions")
    op.drop_table("transactions")
    op.drop_index("ix_portfolio_members_user_id", table_name="portfolio_members")
    op.drop_table("portfolio_members")
    op.drop_index("ix_holdings_asset_id", table_name="holdings")
    op.drop_table("holdings")
    op.drop_table("asset_metadata")
    op.drop_index("ix_portfolios_user_id_archived_at", table_name="portfolios")
    op.drop_table("portfolios")
    op.drop_index(
        "uq_assets_external_ref",
        table_name="assets",
        postgresql_where=sa.text("external_provider IS NOT NULL"),
    )
    op.drop_index("ix_assets_symbol", table_name="assets")
    op.drop_index("ix_assets_owner_user_id", table_name="assets")
    op.drop_index("ix_assets_asset_class_id", table_name="assets")
    op.drop_table("assets")
    op.drop_index("ix_fx_rates_pair_rate_timestamp", table_name="fx_rates")
    op.drop_table("fx_rates")
    op.drop_table("asset_classes")
