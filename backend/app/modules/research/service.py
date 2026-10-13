"""Research ingestion and retrieval (P12-T05.2, T05.3).

Ingestion is idempotent: one row per (source, source id), updated in place when its text
changes, and re-embedded when the text or the model changes. An entry about an instrument is
linked to the public catalogue asset with that universe symbol; an unknown symbol leaves it
unlinked (and says so in the report).

Retrieval reads public research only: no user data is used to rank or filter, and the same query
gives every user the same answer. A query is ranked by the mean of its embedding similarity and
its full-text rank, ties by publication time (newest first) and id; an asset's research is listed
newest first. Every result carries its source, licence status and times."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Float, cast, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.assets.models import Asset
from app.modules.research.embedding import Embedder
from app.modules.research.models import ResearchItem, Vector
from app.modules.research.sources import ResearchEntry, ResearchSource

MAX_RESULTS = 20


@dataclass
class ResearchIngestReport:
    source: str
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    unlinked: list[str] = field(default_factory=list)  # symbols not in the catalogue


def _text(entry: ResearchEntry) -> str:
    return f"{entry.title}\n{entry.summary}"


async def ingest_research(
    session: AsyncSession, source: ResearchSource, embedder: Embedder
) -> ResearchIngestReport:
    retrieved_at, entries = source.load()
    report = ResearchIngestReport(source.name)
    symbols = {e.symbol for e in entries if e.symbol}
    assets = dict(
        (
            await session.execute(
                select(Asset.symbol, Asset.id).where(
                    Asset.owner_user_id.is_(None), Asset.symbol.in_(symbols)
                )
            )
        ).all()
    )
    existing = {
        r.source_id: r
        for r in (
            await session.execute(select(ResearchItem).where(ResearchItem.source == source.name))
        ).scalars()
    }
    vectors = embedder.embed([_text(e) for e in entries])
    for entry, vector in zip(entries, vectors, strict=True):
        if entry.symbol and entry.symbol not in assets:
            report.unlinked.append(entry.symbol)
        embedding = vector if any(vector) else None  # an empty text has no direction
        values = {
            "source_url": entry.source_url,
            "title": entry.title.strip(),
            "summary": entry.summary.strip(),
            "asset_id": assets.get(entry.symbol) if entry.symbol else None,
            "kind": entry.kind,
            "licence_status": source.licence_status,
            "is_demo": source.is_demo,
            "published_at": entry.published_at,
            "retrieved_at": max(retrieved_at, entry.published_at),
            "embedding": embedding,
            "embedding_model": embedder.name if embedding is not None else None,
        }
        row = existing.get(entry.source_id)
        if row is None:
            session.add(ResearchItem(source=source.name, source_id=entry.source_id, **values))
            report.created += 1
            continue
        if row.title == values["title"] and row.summary == values["summary"]:
            values.pop("retrieved_at")  # the same text: keep when we first had it
            if row.embedding_model == values["embedding_model"]:
                values.pop("embedding")
        changed = False
        for attr, new in values.items():
            if getattr(row, attr) != new:
                setattr(row, attr, new)
                changed = True
        if changed:
            report.updated += 1
        else:
            report.unchanged += 1
    await session.commit()
    return report


@dataclass(frozen=True)
class Evidence:
    id: uuid.UUID
    title: str
    summary: str
    kind: str
    source: str
    source_url: str | None
    licence_status: str
    is_demo: bool
    published_at: datetime
    retrieved_at: datetime
    asset_id: uuid.UUID | None
    symbol: str | None
    relevance: Decimal | None  # 0-1 for a query; None when listing an asset's research


class ResearchService:
    def __init__(self, session: AsyncSession, embedder: Embedder) -> None:
        self._session = session
        self._embedder = embedder

    @staticmethod
    def _evidence(row: ResearchItem, symbol: str | None, relevance: Decimal | None) -> Evidence:
        return Evidence(
            row.id,
            row.title,
            row.summary,
            row.kind,
            row.source,
            row.source_url,
            row.licence_status,
            row.is_demo,
            row.published_at,
            row.retrieved_at,
            row.asset_id,
            symbol,
            relevance,
        )

    async def for_asset(self, asset_id: uuid.UUID, limit: int = MAX_RESULTS) -> list[Evidence]:
        rows = (
            await self._session.execute(
                select(ResearchItem, Asset.symbol)
                .outerjoin(Asset, Asset.id == ResearchItem.asset_id)
                .where(ResearchItem.asset_id == asset_id)
                .order_by(ResearchItem.published_at.desc(), ResearchItem.id)
                .limit(min(limit, MAX_RESULTS))
            )
        ).all()
        return [self._evidence(r, s, None) for r, s in rows]

    async def search(
        self, query: str, asset_id: uuid.UUID | None = None, limit: int = MAX_RESULTS
    ) -> list[Evidence]:
        vector = self._embedder.embed([query])[0]
        tsquery = func.websearch_to_tsquery("english", query)
        text_rank = func.least(func.ts_rank_cd(ResearchItem.search, tsquery), 1.0)
        if any(vector):
            similarity = 1 - cast(
                ResearchItem.embedding.op("<=>")(literal(vector, Vector(len(vector)))),
                Float,
            )
            similarity = func.coalesce(func.greatest(similarity, 0.0), 0.0)
        else:
            similarity = literal(0.0)
        relevance = ((similarity + text_rank) / 2).label("relevance")
        stmt = (
            select(ResearchItem, Asset.symbol, relevance)
            .outerjoin(Asset, Asset.id == ResearchItem.asset_id)
            .order_by(relevance.desc(), ResearchItem.published_at.desc(), ResearchItem.id)
            .limit(min(limit, MAX_RESULTS))
        )
        if asset_id is not None:
            stmt = stmt.where(ResearchItem.asset_id == asset_id)
        rows = (await self._session.execute(stmt)).all()
        return [
            self._evidence(r, s, Decimal(str(round(rel, 4))))
            for r, s, rel in rows
            if rel is not None and rel > 0
        ]
