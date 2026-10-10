"""Asset catalogue.

One `assets` table plus type-specific metadata rows, rather than a table per asset class
(implementation guide 6.3). A new asset class is a row in `asset_classes`, not a schema change.

An asset is either **global** (`owner_user_id` is null: a listed security, fund, currency pair)
or **user-defined** (`owner_user_id` set: a house, a private business, a SACCO share). User-defined
assets are visible only to their owner (ADR-0011)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AssetClass(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "asset_classes"
    __table_args__ = (
        UniqueConstraint("code", name="uq_asset_classes_code"),
        CheckConstraint("code ~ '^[a-z][a-z0-9_]{1,39}$'", name="code"),
        CheckConstraint("valuation_mode IN ('market', 'manual')", name="valuation_mode"),
    )

    code: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(100))
    # `market`: valued from prices (P08-T05/T06). `manual`: valued from user-entered valuations.
    valuation_mode: Mapped[str] = mapped_column(String(16))
    # Which metadata keys the class uses, for validation by the asset service (P05-T02).
    metadata_schema: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb")
    )
    is_active: Mapped[bool] = mapped_column(server_default=text("true"))


class Asset(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "assets"
    __table_args__ = (
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="currency"),
        CheckConstraint("country IS NULL OR country ~ '^[A-Z]{2}$'", name="country"),
        CheckConstraint("length(btrim(name)) BETWEEN 1 AND 200", name="name"),
        CheckConstraint(
            "(external_provider IS NULL) = (external_provider_id IS NULL)",
            name="external_ref",
        ),
        # A listed instrument appears once per provider reference.
        Index(
            "uq_assets_external_ref",
            "external_provider",
            "external_provider_id",
            unique=True,
            postgresql_where=text("external_provider IS NOT NULL"),
        ),
        Index("ix_assets_symbol", "symbol"),
        Index("ix_assets_asset_class_id", "asset_class_id"),
        Index("ix_assets_owner_user_id", "owner_user_id"),
    )

    asset_class_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("asset_classes.id", ondelete="RESTRICT")
    )
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    symbol: Mapped[str | None] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(200))
    subtype: Mapped[str | None] = mapped_column(String(64))
    # The currency the asset is priced or valued in (its native currency).
    currency: Mapped[str] = mapped_column(String(3))
    country: Mapped[str | None] = mapped_column(String(2))
    external_provider: Mapped[str | None] = mapped_column(String(32))
    external_provider_id: Mapped[str | None] = mapped_column(String(128))
    is_active: Mapped[bool] = mapped_column(server_default=text("true"))


class AssetMetadata(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One typed fact about an asset (a bond's coupon, a REIT's sector, a property's address)."""

    __tablename__ = "asset_metadata"
    __table_args__ = (
        UniqueConstraint("asset_id", "key", name="uq_asset_metadata_asset_id_key"),
        CheckConstraint("key ~ '^[a-z][a-z0-9_]{0,63}$'", name="key"),
    )

    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"))
    key: Mapped[str] = mapped_column(String(64))
    value: Mapped[Any] = mapped_column(JSONB)
    source: Mapped[str | None] = mapped_column(String(64))
    as_of: Mapped[datetime | None] = mapped_column()
