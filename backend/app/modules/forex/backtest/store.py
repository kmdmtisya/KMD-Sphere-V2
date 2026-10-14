"""`forex_backtest_reports` (P13-T08.6, migration 0024): stored reports, reference data shared by
every user. A report is stored once per hash: rerunning the same inputs adds nothing. The
columns repeat the out-of-sample summary so the Opportunity Ranking can read a rule's history
without loading the report."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, Numeric, String, select
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, distinct_on, insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ForexBacktestReport(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "forex_backtest_reports"
    __table_args__ = (
        CheckConstraint("label = 'backtested'", name="label"),
        CheckConstraint("bars > 0 AND oos_trades >= 0", name="counts"),
        Index(
            "ix_forex_backtest_reports_lookup", "instrument", "timeframe", "rule", "generated_at"
        ),
    )

    instrument: Mapped[str] = mapped_column(
        String(7), ForeignKey("forex_instruments.code", ondelete="RESTRICT")
    )
    timeframe: Mapped[str] = mapped_column(String(3))
    rule: Mapped[str] = mapped_column(String(24))
    rule_version: Mapped[int] = mapped_column(Integer)
    engine_version: Mapped[str] = mapped_column(String(24))
    code_version: Mapped[str] = mapped_column(String(64))
    seed: Mapped[int] = mapped_column(Integer)
    data_snapshot_hash: Mapped[str] = mapped_column(String(16))
    report_hash: Mapped[str] = mapped_column(String(64), unique=True)
    label: Mapped[str] = mapped_column(String(16))
    period_start: Mapped[datetime] = mapped_column()
    period_end: Mapped[datetime] = mapped_column()
    bars: Mapped[int] = mapped_column(Integer)
    data_types: Mapped[list[str]] = mapped_column(ARRAY(String(16)))
    oos_trades: Mapped[int] = mapped_column(Integer)
    oos_return: Mapped[Decimal] = mapped_column(Numeric(14, 6))
    oos_profit_factor: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    generated_at: Mapped[datetime] = mapped_column()
    report: Mapped[dict[str, Any]] = mapped_column(JSONB)


def _dec(value: str | None) -> Decimal | None:
    return None if value is None else Decimal(value)


async def save(session: AsyncSession, report: dict[str, Any]) -> bool:
    """Stores a report unless one with the same hash exists. Returns whether it was new. Commits."""
    oos = report["walk_forward"]["out_of_sample"]
    row = {
        "instrument": report["instrument"],
        "timeframe": report["timeframe"],
        "rule": report["rule"],
        "rule_version": report["rule_version"],
        "engine_version": report["engine_version"],
        "code_version": report["code_version"],
        "seed": report["seed"],
        "data_snapshot_hash": report["data"]["snapshot_hash"],
        "report_hash": report["report_hash"],
        "label": report["label"],
        "period_start": datetime.fromisoformat(report["data"]["start"]),
        "period_end": datetime.fromisoformat(report["data"]["end"]),
        "bars": report["data"]["bars"],
        "data_types": report["data"]["data_types"],
        "oos_trades": oos["trades"],
        "oos_return": Decimal(oos["total_return"]),
        "oos_profit_factor": _dec(oos["profit_factor"]),
        "generated_at": datetime.fromisoformat(report["generated_at"]),
        "report": report,
    }
    result = await session.execute(
        insert(ForexBacktestReport)
        .values(**row)
        .on_conflict_do_nothing(index_elements=["report_hash"])
    )
    await session.commit()
    return bool(result.rowcount)  # type: ignore[attr-defined]


async def latest_by_rule(
    session: AsyncSession, instrument: str, timeframe: str
) -> dict[str, ForexBacktestReport]:
    """The newest report of each rule for a pair and timeframe."""
    rows = (
        await session.execute(
            select(ForexBacktestReport)
            .where(
                ForexBacktestReport.instrument == instrument,
                ForexBacktestReport.timeframe == timeframe,
            )
            .order_by(ForexBacktestReport.rule, ForexBacktestReport.generated_at.desc())
            .ext(distinct_on(ForexBacktestReport.rule))
        )
    ).scalars()
    return {r.rule: r for r in rows}
