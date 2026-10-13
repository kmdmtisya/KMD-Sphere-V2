"""The investment universe (P12-T02): instruments that opportunity analysis may consider, each a
public catalogue asset with the attributes eligibility needs. Reference data, not user data: no
row belongs to a user. Schema: migration 0017."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    ARRAY,
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class UniverseInstrument(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "universe_instruments"
    __table_args__ = (
        UniqueConstraint("asset_id", name="uq_universe_instruments_asset_id"),
        CheckConstraint("risk_level BETWEEN 1 AND 5", name="risk_level"),
        CheckConstraint(
            "liquidity IN ('immediate', 'market', 'term', 'illiquid', 'unknown')",
            name="liquidity",
        ),
        CheckConstraint(
            "licence_status IN ('demo', 'unconfirmed', 'licensed')", name="licence_status"
        ),
        CheckConstraint(
            "minimum_investment IS NULL OR minimum_investment >= 0", name="minimum_investment"
        ),
        Index("ix_universe_instruments_source_active", "source", "is_active"),
    )

    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assets.id", ondelete="RESTRICT"))
    # Where the instrument list came from ("demo" for the synthetic fixture).
    source: Mapped[str] = mapped_column(String(32))
    # Synthetic instruments are always labelled DEMO and never presented as live.
    is_demo: Mapped[bool] = mapped_column()
    # demo: synthetic; unconfirmed: real data whose licence is not yet confirmed; licensed.
    licence_status: Mapped[str] = mapped_column(String(16))
    # The source's risk classification, 1 (lowest) to 5 (highest).
    risk_level: Mapped[int] = mapped_column(SmallInteger)
    liquidity: Mapped[str] = mapped_column(String(16))
    # Countries (ISO 3166-1 alpha-2) where the source says the instrument is offered.
    jurisdictions: Mapped[list[str]] = mapped_column(ARRAY(String(2)))
    # In the asset's currency; None when there is no stated minimum.
    minimum_investment: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    data_as_of: Mapped[datetime] = mapped_column()
    is_active: Mapped[bool] = mapped_column(server_default=text("true"))
