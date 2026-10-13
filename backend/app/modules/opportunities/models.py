"""Opportunity runs (P12-T06): every run of the pipeline and what it produced, kept as it was
(the database refuses updates; a run is deleted only with its user). Schema: migration 0019."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, Numeric, SmallInteger, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin


class OpportunityRun(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "opportunity_runs"
    __table_args__ = (
        CheckConstraint("explanation_source IN ('model', 'template')", name="explanation_source"),
        CheckConstraint(
            "(amount IS NULL) = (amount_currency IS NULL)", name="amount_with_currency"
        ),
        Index("ix_opportunity_runs_user_id_created_at", "user_id", "created_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    # The portfolio the run checked compatibility against, as it was (no foreign key: a run is
    # never updated, so it outlives an archived or deleted portfolio).
    portfolio_id: Mapped[uuid.UUID | None] = mapped_column()
    amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    amount_currency: Mapped[str | None] = mapped_column(String(3))
    asset_class: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column()
    explanation_source: Mapped[str] = mapped_column(String(16))
    provider: Mapped[str | None] = mapped_column(String(32))
    model: Mapped[str | None] = mapped_column(String(100))
    # Problem codes of rejected model replies (never the replies themselves).
    problems: Mapped[list[str]] = mapped_column(JSONB)
    weights: Mapped[dict[str, Any]] = mapped_column(JSONB)
    investor: Mapped[dict[str, Any]] = mapped_column(JSONB)  # the facts eligibility used
    excluded: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)  # candidates left out, why


class Opportunity(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "opportunities"
    __table_args__ = (
        CheckConstraint("rank >= 1", name="rank"),
        CheckConstraint("explanation_source IN ('model', 'template')", name="explanation_source"),
        Index("ix_opportunities_run_id_rank", "run_id", "rank", unique=True),
    )

    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("opportunity_runs.id", ondelete="CASCADE"))
    rank: Mapped[int] = mapped_column(SmallInteger)
    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assets.id", ondelete="RESTRICT"))
    is_demo: Mapped[bool] = mapped_column()
    # The facts at run time: instrument, score block, compatibility, evidence, data times.
    facts: Mapped[dict[str, Any]] = mapped_column(JSONB)
    explanation: Mapped[dict[str, Any]] = mapped_column(JSONB)
    explanation_source: Mapped[str] = mapped_column(String(16))
