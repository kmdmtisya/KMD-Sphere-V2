"""Calendar ingestion (P13-T04.2): stores a source's events and policy rates, idempotently.

An event is upserted by (source, source event id): its schedule and expectations may be revised,
and its `actual` appears once released. A published `actual` is never replaced by a missing one,
and `actual_seen_at` records when it was first seen. Policy rates are upserted by (source,
currency, effective date)."""

from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.forex.calendar.models import ForexEconomicEvent, ForexPolicyRate
from app.modules.forex.calendar.sources import CalendarSource


@dataclass(frozen=True)
class IngestReport:
    source: str
    added: int
    updated: int
    released: int  # events whose actual value appeared in this run
    rates: int


async def ingest(
    session: AsyncSession, source: CalendarSource, start: date, end: date, now: datetime
) -> IngestReport:
    batch = source.load(start, end, now)
    ids = [e.source_event_id for e in batch.events]
    existing = (
        {
            r.source_event_id: r
            for r in (
                await session.execute(
                    select(ForexEconomicEvent).where(
                        ForexEconomicEvent.source == source.name,
                        ForexEconomicEvent.source_event_id.in_(ids),
                    )
                )
            ).scalars()
        }
        if ids
        else {}
    )
    added = updated = released = 0
    for e in batch.events:
        row = existing.get(e.source_event_id)
        values = {
            "name": e.name,
            "kind": e.kind,
            "currencies": list(e.currencies),
            "scheduled_at": e.scheduled_at,
            "importance": e.importance,
            "unit": e.unit,
            "forecast": e.forecast,
            "previous": e.previous,
            "commentary": e.commentary,
            "source_url": e.source_url,
        }
        if row is None:
            session.add(
                ForexEconomicEvent(
                    source=source.name,
                    source_event_id=e.source_event_id,
                    is_demo=source.is_demo,
                    licence_status=source.licence_status,
                    retrieved_at=batch.retrieved_at,
                    actual=e.actual,
                    actual_seen_at=batch.retrieved_at if e.actual is not None else None,
                    **values,
                )
            )
            added += 1
            released += e.actual is not None
            continue
        changed = any(getattr(row, k) != v for k, v in values.items())
        for k, v in values.items():
            setattr(row, k, v)
        if e.actual is not None and row.actual != e.actual:
            if row.actual is None:
                row.actual_seen_at = batch.retrieved_at
                released += 1
            row.actual = e.actual
            changed = True
        row.retrieved_at = batch.retrieved_at
        updated += changed
    rates = 0
    for r in batch.rates:
        found = await session.scalar(
            select(ForexPolicyRate).where(
                ForexPolicyRate.source == source.name,
                ForexPolicyRate.currency == r.currency,
                ForexPolicyRate.effective_date == r.effective_date,
            )
        )
        if found is None:
            session.add(
                ForexPolicyRate(
                    source=source.name,
                    currency=r.currency,
                    bank=r.bank,
                    rate=r.rate,
                    effective_date=r.effective_date,
                    decided_at=r.decided_at,
                    source_url=r.source_url,
                    is_demo=source.is_demo,
                    licence_status=source.licence_status,
                    retrieved_at=batch.retrieved_at,
                )
            )
            rates += 1
        else:
            found.bank, found.rate, found.decided_at = r.bank, r.rate, r.decided_at
            found.source_url, found.retrieved_at = r.source_url, batch.retrieved_at
    await session.commit()
    return IngestReport(source.name, added, updated, released, rates)
