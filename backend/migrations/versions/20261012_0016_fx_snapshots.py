"""fx_snapshots: immutable, content-addressed rate sets (P11-T04)

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_REJECT_FUNCTION = """
CREATE FUNCTION fx_snapshots_reject_change() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'fx_snapshots is immutable: % is not allowed', TG_OP
        USING ERRCODE = 'insufficient_privilege';
END;
$$
"""


def upgrade() -> None:
    op.create_table(
        "fx_snapshots",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("pivot", sa.String(length=3), nullable=False),
        sa.Column("rates", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fx_snapshots")),
    )
    op.execute(_REJECT_FUNCTION)
    op.execute(
        "CREATE TRIGGER fx_snapshots_no_update_delete BEFORE UPDATE OR DELETE ON fx_snapshots "
        "FOR EACH ROW EXECUTE FUNCTION fx_snapshots_reject_change()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER fx_snapshots_no_update_delete ON fx_snapshots")
    op.execute("DROP FUNCTION fx_snapshots_reject_change()")
    op.drop_table("fx_snapshots")
