"""Forex time series (P13-T02.3, migration 0020, DEC-21): append-only quotes and candles in
PostgreSQL tables range-partitioned by month on their time column, with BRIN indexes for range
scans. Monthly partitions are created ahead of time by `partitions.ensure_months`; a DEFAULT
partition catches anything outside them, so an insert never fails for want of a partition.

Reference data, not user data: no row belongs to a user. Rows are never updated: a duplicate
(same provider, pair and time) is dropped on insert."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Computed,
    ForeignKey,
    Index,
    Numeric,
    PrimaryKeyConstraint,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

PRICE = Numeric(20, 10)
# (bid + ask) / 2 of two 10-decimal prices is exact at 11 decimals.
MID = Numeric(21, 11)
DATA_TYPES = "('tradable_quote', 'indicative_rate', 'delayed', 'simulated')"


class ForexQuote(Base):
    __tablename__ = "forex_quotes"
    __table_args__ = (
        PrimaryKeyConstraint("provider", "instrument", "ts_provider", name="pk_forex_quotes"),
        CheckConstraint("bid > 0 AND ask > 0", name="positive"),
        CheckConstraint(f"data_type IN {DATA_TYPES}", name="data_type"),
        CheckConstraint("quality IN ('ok', 'suspect', 'stale')", name="quality"),
        CheckConstraint(
            "feed_status IN ('connected', 'degraded', 'disconnected')", name="feed_status"
        ),
        Index("ix_forex_quotes_instrument_ts_provider", "instrument", "ts_provider"),
        Index("ix_forex_quotes_ts_provider_brin", "ts_provider", postgresql_using="brin"),
        {"postgresql_partition_by": "RANGE (ts_provider)"},
    )

    provider: Mapped[str] = mapped_column(String(32))
    instrument: Mapped[str] = mapped_column(
        String(7), ForeignKey("forex_instruments.code", ondelete="RESTRICT")
    )
    ts_provider: Mapped[datetime] = mapped_column()  # the provider's time (UTC)
    ts_received: Mapped[datetime] = mapped_column()  # when WealthSphere received it (UTC)
    bid: Mapped[Decimal] = mapped_column(PRICE)
    ask: Mapped[Decimal] = mapped_column(PRICE)
    # Derived by the database, never written by code or taken from a provider.
    mid: Mapped[Decimal] = mapped_column(MID, Computed("(bid + ask) / 2", persisted=True))
    data_type: Mapped[str] = mapped_column(String(16))
    quality: Mapped[str] = mapped_column(String(8))
    feed_status: Mapped[str] = mapped_column(String(16))  # the feed's status at receipt


class ForexCandle(Base):
    """Complete candles only: a forming candle is never stored, so no row is ever rewritten."""

    __tablename__ = "forex_candles"
    __table_args__ = (
        PrimaryKeyConstraint(
            "provider", "instrument", "timeframe", "price_basis", "ts", name="pk_forex_candles"
        ),
        CheckConstraint("low > 0", name="positive"),
        CheckConstraint(
            "high >= open AND high >= close AND low <= open AND low <= close", name="bounds"
        ),
        CheckConstraint(
            "timeframe IN ('1m', '5m', '15m', '30m', '1H', '4H', '1D', '1W', '1M')",
            name="timeframe",
        ),
        CheckConstraint("price_basis IN ('mid', 'bid', 'ask')", name="price_basis"),
        CheckConstraint(f"data_type IN {DATA_TYPES}", name="data_type"),
        CheckConstraint("volume IS NULL OR volume >= 0", name="volume"),
        Index("ix_forex_candles_ts_brin", "ts", postgresql_using="brin"),
        {"postgresql_partition_by": "RANGE (ts)"},
    )

    provider: Mapped[str] = mapped_column(String(32))
    instrument: Mapped[str] = mapped_column(
        String(7), ForeignKey("forex_instruments.code", ondelete="RESTRICT")
    )
    timeframe: Mapped[str] = mapped_column(String(3))
    price_basis: Mapped[str] = mapped_column(String(3))
    ts: Mapped[datetime] = mapped_column()  # the period's start (UTC)
    open: Mapped[Decimal] = mapped_column(PRICE)
    high: Mapped[Decimal] = mapped_column(PRICE)
    low: Mapped[Decimal] = mapped_column(PRICE)
    close: Mapped[Decimal] = mapped_column(PRICE)
    volume: Mapped[int | None] = mapped_column(BigInteger)  # tick volume, when the provider has it
    data_type: Mapped[str] = mapped_column(String(16))
    ts_received: Mapped[datetime] = mapped_column()
