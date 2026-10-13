"""research_items: public research evidence with provenance and embeddings (P12-T05)

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "research_items",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("source_id", sa.String(length=200), nullable=False),
        sa.Column("source_url", sa.String(length=500), nullable=True),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("asset_id", sa.UUID(), nullable=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("licence_status", sa.String(length=16), nullable=False),
        sa.Column("is_demo", sa.Boolean(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("embedding_model", sa.String(length=64), nullable=True),
        sa.Column(
            "search",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('english', title || ' ' || summary)", persisted=True),
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
            "licence_status IN ('demo', 'public_domain', 'unconfirmed', 'licensed')",
            name=op.f("ck_research_items_licence_status"),
        ),
        sa.CheckConstraint(
            "length(btrim(title)) BETWEEN 1 AND 300", name=op.f("ck_research_items_title")
        ),
        sa.CheckConstraint(
            "retrieved_at >= published_at",
            name=op.f("ck_research_items_retrieved_after_published"),
        ),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["assets.id"],
            name=op.f("fk_research_items_asset_id_assets"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_research_items")),
        sa.UniqueConstraint("source", "source_id", name=op.f("uq_research_items_source_source_id")),
    )
    # pgvector's type (the extension is created by the baseline migration).
    op.execute("ALTER TABLE research_items ADD COLUMN embedding vector(256)")
    op.create_index(
        "ix_research_items_asset_id_published_at",
        "research_items",
        ["asset_id", "published_at"],
    )
    op.create_index(
        "ix_research_items_search", "research_items", ["search"], postgresql_using="gin"
    )
    op.execute(
        "CREATE INDEX ix_research_items_embedding ON research_items "
        "USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.drop_index("ix_research_items_embedding", table_name="research_items")
    op.drop_index("ix_research_items_search", table_name="research_items")
    op.drop_index("ix_research_items_asset_id_published_at", table_name="research_items")
    op.drop_table("research_items")
