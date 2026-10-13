"""Monthly partitions of the forex time series (P13-T02.3, DEC-21).

`ensure_months` creates the partitions for a run of months ahead of time. It is idempotent and
safe to run from several workers (an advisory lock serialises it). If rows for a month already
landed in the DEFAULT partition (the job had not run), they are moved into the new partition in
the same transaction, unchanged, so nothing is lost or rewritten."""

from datetime import UTC, date, datetime, time

from sqlalchemy import Table, insert, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.forex.marketdata.models import ForexCandle, ForexQuote

# Table -> (ORM table, partition column). Names are fixed here, never taken from input.
PARTITIONED: dict[str, tuple[Table, str]] = {
    "forex_quotes": (ForexQuote.__table__, "ts_provider"),  # type: ignore[dict-item]
    "forex_candles": (ForexCandle.__table__, "ts"),  # type: ignore[dict-item]
}


def add_months(day: date, months: int) -> date:
    index = day.year * 12 + day.month - 1 + months
    return date(index // 12, index % 12 + 1, 1)


def partition_name(table: str, month: date) -> str:
    return f"{table}_p{month:%Y%m}"


async def ensure_months(session: AsyncSession, table: str, first: date, count: int) -> list[str]:
    """Creates the missing monthly partitions of `table` for `count` months from `first`'s month.
    Returns the names created. Commits."""
    if count < 1:
        raise ValueError("count must be at least 1")
    model, column = PARTITIONED[table]
    columns = [c.name for c in model.columns if c.computed is None]
    listed = ", ".join(columns)
    await session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:t))"), {"t": table})
    created: list[str] = []
    for i in range(count):
        start = add_months(first.replace(day=1), i)
        end = add_months(start, 1)
        name = partition_name(table, start)
        if await session.scalar(text("SELECT to_regclass(:n) IS NOT NULL"), {"n": name}):
            continue
        lo, hi = f"{start.isoformat()} 00:00:00+00", f"{end.isoformat()} 00:00:00+00"
        # Names come from PARTITIONED and the model, never from input; values are bound.
        move = (
            f"DELETE FROM {table}_default WHERE {column} >= :lo "  # noqa: S608
            f"AND {column} < :hi RETURNING {listed}"
        )
        bounds = {
            "lo": datetime.combine(start, time.min, UTC),
            "hi": datetime.combine(end, time.min, UTC),
        }
        moved = (await session.execute(text(move), bounds)).mappings().all()
        await session.execute(
            text(f"CREATE TABLE {name} PARTITION OF {table} FOR VALUES FROM ('{lo}') TO ('{hi}')")
        )
        if moved:
            await session.execute(insert(model), [dict(row) for row in moved])
        created.append(name)
    await session.commit()
    return created
