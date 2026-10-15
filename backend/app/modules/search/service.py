"""Search over the signed-in user's own records only. Every query starts from the user's
ownership (ADR-0011): portfolios, goals and liabilities by their `user_id`; assets only when the
user's own portfolios hold them, the user's watchlist lists them, or the user created them."""

import uuid
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authz import owned_by
from app.modules.alerts.models import WatchlistItem
from app.modules.assets.models import Asset
from app.modules.goals.models import Goal
from app.modules.networth.models import Liability
from app.modules.portfolio.models import Portfolio
from app.modules.transactions.models import Transaction

Kind = Literal["portfolio", "goal", "liability", "asset"]
PER_KIND = 5
MAX_QUERY = 80
ESCAPE = chr(92)  # a single backslash, the LIKE escape character


class SearchHit(BaseModel):
    kind: Kind
    id: uuid.UUID
    title: str
    subtitle: str | None = Field(default=None, description="Type, symbol or currency, for display")


class SearchOut(BaseModel):
    query: str
    results: list[SearchHit]


def like_pattern(query: str) -> str:
    """A case-insensitive 'contains' pattern with the LIKE wildcards in the text escaped."""
    escaped = (
        query.replace(ESCAPE, ESCAPE * 2).replace("%", ESCAPE + "%").replace("_", ESCAPE + "_")
    )
    return f"%{escaped}%"


class SearchService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def search(self, user_id: uuid.UUID, query: str) -> SearchOut:
        q = query.strip()[:MAX_QUERY]
        if not q:
            return SearchOut(query="", results=[])
        pattern = like_pattern(q)
        hits: list[SearchHit] = []

        portfolios = await self._session.execute(
            owned_by(Portfolio, user_id)
            .where(Portfolio.archived_at.is_(None), Portfolio.name.ilike(pattern, escape=ESCAPE))
            .order_by(Portfolio.name)
            .limit(PER_KIND)
        )
        hits += [
            SearchHit(kind="portfolio", id=p.id, title=p.name, subtitle=p.base_currency)
            for p in portfolios.scalars()
        ]

        goals = await self._session.execute(
            owned_by(Goal, user_id)
            .where(Goal.name.ilike(pattern, escape=ESCAPE))
            .order_by(Goal.name)
            .limit(PER_KIND)
        )
        hits += [
            SearchHit(kind="goal", id=g.id, title=g.name, subtitle=g.goal_type)
            for g in goals.scalars()
        ]

        liabilities = await self._session.execute(
            owned_by(Liability, user_id)
            .where(Liability.name.ilike(pattern, escape=ESCAPE))
            .order_by(Liability.name)
            .limit(PER_KIND)
        )
        hits += [
            SearchHit(kind="liability", id=item.id, title=item.name, subtitle=item.liability_type)
            for item in liabilities.scalars()
        ]

        held = (
            select(Transaction.asset_id)
            .join(Portfolio, Portfolio.id == Transaction.portfolio_id)
            .where(Portfolio.user_id == user_id, Transaction.asset_id.is_not(None))
        )
        watched = select(WatchlistItem.asset_id).where(WatchlistItem.user_id == user_id)
        assets = await self._session.execute(
            select(Asset)
            .where(
                or_(Asset.id.in_(held), Asset.id.in_(watched), Asset.owner_user_id == user_id),
                or_(
                    Asset.name.ilike(pattern, escape=ESCAPE),
                    Asset.symbol.ilike(pattern, escape=ESCAPE),
                ),
            )
            .order_by(Asset.name)
            .limit(PER_KIND)
        )
        hits += [
            SearchHit(kind="asset", id=a.id, title=a.name, subtitle=a.symbol or a.currency)
            for a in assets.scalars()
        ]
        return SearchOut(query=q, results=hits)
