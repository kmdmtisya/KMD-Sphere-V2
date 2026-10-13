"""Scores of the investment universe (P12-T03): features from stored data, then the explainable
score, for every active instrument, with its eligibility for the signed-in user. The score itself
does not depend on the user; eligibility does."""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.assets.repository import AssetRepository
from app.modules.market_data.freshness import kind_for_asset_class
from app.modules.market_data.models import MarketPrice
from app.modules.scoring.features import WINDOW_DAYS, Close, Features, compute
from app.modules.scoring.scoring import Factor, Score, score
from app.modules.universe.service import UniverseItem, UniverseService

FUND_CLASSES = frozenset({"etf", "mutual_fund"})
# Daily closes do not come at weekends: four days old is still the latest close.
CLOSE_FRESH_FOR = timedelta(days=4)


@dataclass(frozen=True)
class ScoredItem:
    item: UniverseItem
    features: Features
    score: Score


async def closes_for(
    session: AsyncSession, asset_ids: list[uuid.UUID], today: date
) -> dict[uuid.UUID, list[Close]]:
    """One close per asset and day over the trailing window: the most recently retrieved one
    when providers overlap (as the prices API does)."""
    if not asset_ids:
        return {}
    start = datetime.combine(today - timedelta(days=WINDOW_DAYS), time.min, UTC)
    end = datetime.combine(today, time.max, UTC)
    rows = (
        await session.execute(
            select(MarketPrice)
            .where(
                MarketPrice.asset_id.in_(asset_ids),
                MarketPrice.price_type == "close",
                MarketPrice.as_of >= start,
                MarketPrice.as_of <= end,
            )
            .order_by(MarketPrice.asset_id, MarketPrice.as_of, MarketPrice.retrieved_at.desc())
        )
    ).scalars()
    return pick_closes(
        [StoredClose(p.asset_id, p.as_of, p.retrieved_at, p.price) for p in rows], today
    )


@dataclass(frozen=True)
class StoredClose:
    asset_id: uuid.UUID
    as_of: datetime
    retrieved_at: datetime
    price: Decimal


def pick_closes(rows: Iterable[StoredClose], today: date) -> dict[uuid.UUID, list[Close]]:
    """Pure: one close per asset and UTC day. When providers disagree, the most recently
    retrieved close is kept; on an exact tie the lower price, so the result never depends on row
    order. Closes dated after `today` are ignored."""
    by_day: dict[uuid.UUID, dict[date, StoredClose]] = {}
    for r in rows:
        day = r.as_of.astimezone(UTC).date()
        if day > today:
            continue
        days = by_day.setdefault(r.asset_id, {})
        kept = days.get(day)
        if kept is None or (r.retrieved_at, -r.price) > (kept.retrieved_at, -kept.price):
            days[day] = r
    return {
        asset: [Close(on, r.price) for on, r in sorted(days.items())]
        for asset, days in by_day.items()
    }


class ScoringService:
    def __init__(self, session: AsyncSession, weights: dict[Factor, Decimal]) -> None:
        self._session = session
        self._weights = weights
        self._universe = UniverseService(session)
        self._assets = AssetRepository(session)

    async def universe(
        self, user_id: uuid.UUID, asset_class: str | None, now: datetime
    ) -> list[ScoredItem]:
        items = (await self._universe.for_user(user_id, asset_class)).items
        ids = [i.asset_id for i in items]
        today = now.date()
        closes = await closes_for(self._session, ids, today)
        ratios = await self._assets.metadata_values(ids, "expense_ratio")
        scored = []
        for item in items:
            features = compute(
                closes.get(item.asset_id, []),
                risk_level=item.risk_level,
                liquidity=item.liquidity,
                priced=kind_for_asset_class(item.asset_class) is not None,
                fund=item.asset_class in FUND_CLASSES,
                expense_ratio=Decimal(str(ratios[item.asset_id]))
                if item.asset_id in ratios
                else None,
                today=today,
                stale_after=CLOSE_FRESH_FOR,
            )
            scored.append(ScoredItem(item, features, score(features, self._weights)))
        # Highest score first; unscored last; ties by symbol, then id.
        return sorted(
            scored,
            key=lambda s: (
                s.score.score is None,
                -(s.score.score or Decimal(0)),
                s.item.symbol or "",
                str(s.item.asset_id),
            ),
        )
