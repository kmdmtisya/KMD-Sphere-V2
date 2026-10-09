"""Declarative base, naming conventions and shared column types.

Conventions (ADR-0004, ADR-0006):
- UUID primary keys (`gen_random_uuid()` server default).
- Money, quantities and rates are NUMERIC, never floating point.
- Every table carries timezone-aware created_at / updated_at.
- Constraint and index names are deterministic so migrations are stable and reviewable.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, MetaData, Numeric, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# Monetary amounts: 20 integer digits, 8 fractional digits. Rounding to a currency's minor
# units happens only at the boundaries defined in ADR-0006.
AMOUNT = Numeric(28, 8)
# Quantities (units, shares, crypto): up to 12 fractional digits.
QUANTITY = Numeric(28, 12)
# Rates, percentages and FX: at least 12 fractional digits, stored unrounded.
RATE = Numeric(28, 12)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {  # noqa: RUF012 (SQLAlchemy documented declarative pattern)
        uuid.UUID: PG_UUID(as_uuid=True),
        datetime: DateTime(timezone=True),
        Decimal: AMOUNT,
    }


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(
        server_default=text("now()"), onupdate=text("now()")
    )
