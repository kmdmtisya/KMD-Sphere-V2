"""Liability table (P06-T07). A liability is something a user owes (a mortgage, a loan, a card
balance), entered by the user with the date its balance applied. Net worth subtracts the
liabilities from the value of the user's portfolios (docs/design/net-worth.md)."""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Index, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import AMOUNT, Base, TimestampMixin, UUIDPrimaryKeyMixin

LIABILITY_TYPES = (
    "mortgage",
    "personal_loan",
    "car_loan",
    "student_loan",
    "business_loan",
    "credit_card",
    "other",
)
_TYPES_SQL = ", ".join(f"'{t}'" for t in LIABILITY_TYPES)


class Liability(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "liabilities"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_liabilities_user_id_name"),
        CheckConstraint("length(btrim(name)) BETWEEN 1 AND 100", name="name"),
        CheckConstraint(f"liability_type IN ({_TYPES_SQL})", name="liability_type"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="currency"),
        CheckConstraint("balance >= 0", name="balance_non_negative"),
        CheckConstraint(
            "interest_rate_percent IS NULL OR interest_rate_percent >= 0",
            name="interest_rate_non_negative",
        ),
        Index("ix_liabilities_asset_id", "asset_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    name: Mapped[str] = mapped_column(String(100))
    liability_type: Mapped[str] = mapped_column(String(24))
    currency: Mapped[str] = mapped_column(String(3))
    balance: Mapped[Decimal] = mapped_column(AMOUNT)  # outstanding, in `currency`
    balance_as_of: Mapped[date] = mapped_column()  # when the user's figure applied
    interest_rate_percent: Mapped[Decimal | None] = mapped_column(Numeric(9, 4))
    # The asset securing the liability (a mortgaged house), when there is one.
    asset_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("assets.id", ondelete="RESTRICT"))
