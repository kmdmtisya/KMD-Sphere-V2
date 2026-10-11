"""One portfolio's allocation and concentration (P06-T04): the analytics maths applied to its
summary and the classification of its assets. Methods: docs/design/allocation.md. Published by
the analytics API (P06-T09)."""

import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.analytics.allocation import (
    Allocation,
    Concentration,
    Dimension,
    Part,
    allocate,
    cash,
    concentration,
)
from app.modules.assets.service import AssetService, Classification
from app.modules.portfolio.summary import Summary
from app.modules.portfolio.summary_service import SummaryService


@dataclass(frozen=True)
class PortfolioAllocation:
    """Unrounded figures in the portfolio's base currency."""

    currency: str
    total: Decimal
    by: dict[Dimension, Allocation]
    concentration: Concentration
    complete: bool  # false when assets are unpriced or currencies unconverted
    unpriced_assets: tuple[uuid.UUID, ...]


class AllocationService:
    def __init__(self, session: AsyncSession) -> None:
        self._summaries = SummaryService(session)
        self._assets = AssetService(session)

    async def portfolio(self, user_id: uuid.UUID, portfolio_id: uuid.UUID) -> PortfolioAllocation:
        """Raises ResourceNotFoundError (404) unless the portfolio is the user's."""
        return await self.of(await self._summaries.figures(user_id, portfolio_id))

    async def of(self, summary: Summary) -> PortfolioAllocation:
        """The allocation of a summary the caller has authorised (one portfolio or a
        consolidated one, for net worth)."""
        classes = await self._assets.classifications(sorted(summary.positions))
        return measure(summary, classes)


def measure(summary: Summary, classes: dict[uuid.UUID, Classification]) -> PortfolioAllocation:
    """Pure: the allocation of a summary's valued positions and cash balances."""
    parts = [
        Part(
            key=str(asset_id),
            value=value,
            asset_class=classes[asset_id].asset_class,
            currency=summary.position_currencies[asset_id],
            country=classes[asset_id].country,
            sector=classes[asset_id].sector,
        )
        for asset_id, value in sorted(summary.positions.items())
    ] + [cash(currency, value) for currency, value in sorted(summary.cash_balances.items())]
    return PortfolioAllocation(
        currency=summary.currency,
        total=summary.total_value,
        by={d: allocate(parts, d) for d in Dimension},
        concentration=concentration(parts),
        complete=summary.complete,
        unpriced_assets=tuple(summary.unpriced_assets),
    )
