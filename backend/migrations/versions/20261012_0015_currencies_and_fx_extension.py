"""currencies, reporting-currency preferences, fx_rates extension, conversion audit (P11-T02)

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The launch currencies (ADR-0010). More are added as rows, without a code change.
LAUNCH_CURRENCIES = [
    ("AED", "UAE dirham", "AED", 2),
    ("AUD", "Australian dollar", "A$", 2),
    ("CAD", "Canadian dollar", "CA$", 2),
    ("CHF", "Swiss franc", "CHF", 2),
    ("EUR", "Euro", "€", 2),
    ("GBP", "Pound sterling", "£", 2),
    ("JPY", "Japanese yen", "¥", 0),
    ("KES", "Kenyan shilling", "KSh", 2),
    ("USD", "US dollar", "$", 2),
    ("ZAR", "South African rand", "R", 2),
]

_REJECT_FUNCTION = """
CREATE FUNCTION fx_conversion_audit_reject_change() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'fx_conversion_audit is append-only: % is not allowed', TG_OP
        USING ERRCODE = 'insufficient_privilege';
END;
$$
"""


def _now(name: str) -> sa.Column[sa.DateTime]:
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def upgrade() -> None:
    currencies = op.create_table(
        "currencies",
        sa.Column("code", sa.String(length=3), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("symbol", sa.String(length=8), nullable=False),
        sa.Column("decimal_places", sa.SmallInteger(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        _now("created_at"),
        _now("updated_at"),
        sa.CheckConstraint("code ~ '^[A-Z]{3}$'", name=op.f("ck_currencies_code")),
        sa.CheckConstraint(
            "decimal_places BETWEEN 0 AND 4", name=op.f("ck_currencies_decimal_places")
        ),
        sa.CheckConstraint(
            "length(name) BETWEEN 1 AND 100", name=op.f("ck_currencies_name_length")
        ),
        sa.PrimaryKeyConstraint("code", name=op.f("pk_currencies")),
    )
    op.bulk_insert(
        currencies,
        [
            {"code": c, "name": n, "symbol": s, "decimal_places": d}
            for c, n, s, d in LAUNCH_CURRENCIES
        ],
    )

    op.create_table(
        "user_currency_preferences",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("reporting_currency", sa.String(length=3), nullable=False),
        sa.Column(
            "recent_currencies",
            sa.ARRAY(sa.String(length=3)),
            server_default=sa.text("'{}'::varchar(3)[]"),
            nullable=False,
        ),
        _now("created_at"),
        _now("updated_at"),
        sa.CheckConstraint(
            "cardinality(recent_currencies) <= 5",
            name=op.f("ck_user_currency_preferences_recent_currencies_size"),
        ),
        sa.ForeignKeyConstraint(
            ["reporting_currency"],
            ["currencies.code"],
            name=op.f("fk_user_currency_preferences_reporting_currency_currencies"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_currency_preferences_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_user_currency_preferences")),
    )

    op.add_column(
        "fx_rates",
        sa.Column(
            "rate_type",
            sa.String(length=16),
            server_default=sa.text("'indicative'"),
            nullable=False,
        ),
    )
    op.add_column("fx_rates", sa.Column("rate_path", sa.ARRAY(sa.String(length=3)), nullable=True))
    op.create_check_constraint(
        op.f("ck_fx_rates_rate_type"),
        "fx_rates",
        "rate_type IN ('mid_market', 'indicative', 'delayed')",
    )
    op.create_check_constraint(
        op.f("ck_fx_rates_rate_path"),
        "fx_rates",
        "rate_path IS NULL OR cardinality(rate_path) BETWEEN 3 AND 4",
    )

    op.create_table(
        "fx_conversion_audit",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("source_currency", sa.String(length=3), nullable=False),
        sa.Column("target_currency", sa.String(length=3), nullable=False),
        sa.Column("source_amount", sa.Numeric(precision=28, scale=8), nullable=False),
        sa.Column("converted_amount", sa.Numeric(precision=28, scale=8), nullable=False),
        sa.Column("rate", sa.Numeric(precision=28, scale=12), nullable=False),
        sa.Column("rate_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("snapshot_id", sa.UUID(), nullable=True),
        sa.Column("conversion_type", sa.String(length=16), nullable=False),
        _now("created_at"),
        sa.CheckConstraint(
            "conversion_type IN ('ai_answer', 'report', 'converter')",
            name=op.f("ck_fx_conversion_audit_conversion_type"),
        ),
        sa.CheckConstraint("rate > 0", name=op.f("ck_fx_conversion_audit_rate_positive")),
        sa.CheckConstraint(
            "source_currency ~ '^[A-Z]{3}$'", name=op.f("ck_fx_conversion_audit_source_currency")
        ),
        sa.CheckConstraint(
            "target_currency ~ '^[A-Z]{3}$'", name=op.f("ck_fx_conversion_audit_target_currency")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fx_conversion_audit")),
    )
    op.create_index(
        "ix_fx_conversion_audit_user_id_created_at",
        "fx_conversion_audit",
        ["user_id", "created_at"],
    )
    op.execute(_REJECT_FUNCTION)
    op.execute(
        "CREATE TRIGGER fx_conversion_audit_no_update_delete BEFORE UPDATE OR DELETE "
        "ON fx_conversion_audit FOR EACH ROW EXECUTE FUNCTION fx_conversion_audit_reject_change()"
    )
    op.execute(
        "CREATE TRIGGER fx_conversion_audit_no_truncate BEFORE TRUNCATE ON fx_conversion_audit "
        "FOR EACH STATEMENT EXECUTE FUNCTION fx_conversion_audit_reject_change()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER fx_conversion_audit_no_truncate ON fx_conversion_audit")
    op.execute("DROP TRIGGER fx_conversion_audit_no_update_delete ON fx_conversion_audit")
    op.execute("DROP FUNCTION fx_conversion_audit_reject_change()")
    op.drop_index("ix_fx_conversion_audit_user_id_created_at", table_name="fx_conversion_audit")
    op.drop_table("fx_conversion_audit")
    op.drop_constraint(op.f("ck_fx_rates_rate_path"), "fx_rates", type_="check")
    op.drop_constraint(op.f("ck_fx_rates_rate_type"), "fx_rates", type_="check")
    op.drop_column("fx_rates", "rate_path")
    op.drop_column("fx_rates", "rate_type")
    op.drop_table("user_currency_preferences")
    op.drop_table("currencies")
