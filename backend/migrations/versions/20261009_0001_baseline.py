"""baseline: required PostgreSQL extensions

Revision ID: 0001
Revises:
Create Date: 2026-10-09
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # pgcrypto: gen_random_uuid() for UUID primary keys. vector: embeddings for AI retrieval.
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    # Extensions are shared database infrastructure and may be used outside this migration
    # chain, so the baseline downgrade intentionally leaves them installed.
    pass
