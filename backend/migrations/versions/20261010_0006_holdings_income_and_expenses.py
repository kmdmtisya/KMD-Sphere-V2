"""holdings: income and expenses per asset (P05-T05, ADR-0012)

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "holdings",
        sa.Column(
            "income", sa.Numeric(precision=28, scale=8), server_default=sa.text("0"), nullable=False
        ),
    )
    op.add_column(
        "holdings",
        sa.Column(
            "expenses",
            sa.Numeric(precision=28, scale=8),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("holdings", "expenses")
    op.drop_column("holdings", "income")
