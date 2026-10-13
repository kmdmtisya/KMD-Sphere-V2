"""Research evidence (P12-T05): public research items with provenance, licence status and
timestamps, embedded for retrieval. Reference data, not user data: no row belongs to a user, and
retrieval never reads user data. Schema: migration 0018."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Computed,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import UserDefinedType

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.modules.research.embedding import DIMENSIONS

LICENCE_STATUSES = ("demo", "public_domain", "unconfirmed", "licensed")


class Vector(UserDefinedType[list[float]]):
    """pgvector's `vector(n)` (the extension is created by the baseline migration)."""

    cache_ok = True

    def __init__(self, dimensions: int) -> None:
        self.dimensions = dimensions

    def get_col_spec(self, **kw: Any) -> str:
        return f"vector({self.dimensions})"

    def bind_processor(self, dialect: Any) -> Any:
        def process(value: list[float] | None) -> str | None:
            return None if value is None else "[" + ",".join(repr(float(v)) for v in value) + "]"

        return process

    def result_processor(self, dialect: Any, coltype: Any) -> Any:
        def process(value: str | None) -> list[float] | None:
            return None if value is None else [float(v) for v in value.strip("[]").split(",")]

        return process


class ResearchItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "research_items"
    __table_args__ = (
        UniqueConstraint("source", "source_id", name="uq_research_items_source_source_id"),
        CheckConstraint(
            "licence_status IN ('demo', 'public_domain', 'unconfirmed', 'licensed')",
            name="licence_status",
        ),
        CheckConstraint("length(btrim(title)) BETWEEN 1 AND 300", name="title"),
        CheckConstraint("retrieved_at >= published_at", name="retrieved_after_published"),
        Index("ix_research_items_asset_id_published_at", "asset_id", "published_at"),
        Index("ix_research_items_search", "search", postgresql_using="gin"),
        Index(
            "ix_research_items_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    # Where the item came from and its id there ("demo", "sec_edgar", ...).
    source: Mapped[str] = mapped_column(String(32))
    source_id: Mapped[str] = mapped_column(String(200))
    # The page the source publishes it at: provenance only, never fetched by the app or the AI.
    source_url: Mapped[str | None] = mapped_column(String(500))
    title: Mapped[str] = mapped_column(String(300))
    summary: Mapped[str] = mapped_column(Text)
    # The instrument it is about, when it is about one.
    asset_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("assets.id", ondelete="RESTRICT"))
    kind: Mapped[str] = mapped_column(String(32))  # note, filing, ...
    licence_status: Mapped[str] = mapped_column(String(16))
    is_demo: Mapped[bool] = mapped_column()
    published_at: Mapped[datetime] = mapped_column()  # the source's own time (as-of)
    retrieved_at: Mapped[datetime] = mapped_column()  # when we obtained it
    embedding: Mapped[list[float] | None] = mapped_column(Vector(DIMENSIONS))
    embedding_model: Mapped[str | None] = mapped_column(String(64))
    search: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('english', title || ' ' || summary)", persisted=True),
    )
