"""`forex_instruments` (P13-T02.2, migration 0020): reference data, not user data. Rows are
deactivated, never deleted, so stored quotes and candles always point at a known pair."""

from sqlalchemy import CheckConstraint, Integer, SmallInteger, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class ForexInstrument(TimestampMixin, Base):
    __tablename__ = "forex_instruments"
    __table_args__ = (
        CheckConstraint("code ~ '^[A-Z]{3}_[A-Z]{3}$'", name="code"),
        CheckConstraint("pip_location BETWEEN -6 AND 0", name="pip_location"),
        CheckConstraint("display_precision BETWEEN -pip_location AND 8", name="display_precision"),
        CheckConstraint("liquidity_tier IN ('major', 'minor', 'exotic')", name="liquidity_tier"),
        CheckConstraint(
            "default_data_type IN ('tradable_quote', 'indicative_rate')", name="default_data_type"
        ),
        CheckConstraint("spec_version >= 1", name="spec_version"),
    )

    code: Mapped[str] = mapped_column(String(7), primary_key=True)  # EUR_USD
    base: Mapped[str] = mapped_column(String(3))
    quote: Mapped[str] = mapped_column(String(3))
    pip_location: Mapped[int] = mapped_column(SmallInteger)
    display_precision: Mapped[int] = mapped_column(SmallInteger)
    liquidity_tier: Mapped[str] = mapped_column(String(8))
    default_data_type: Mapped[str] = mapped_column(String(16))
    # The registry file's version when this row's quoting conventions last changed.
    spec_version: Mapped[int] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(server_default=text("true"))
