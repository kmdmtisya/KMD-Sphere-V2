"""Holdings cache and API (ADR-0012). The ledger is the source of truth; `holdings` is rebuilt for
the affected asset in the same database transaction as every posting or reversal."""

import uuid
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authz import require_found
from app.core.money import Money, minor_units, round_half_up
from app.modules.assets.schemas import AssetSummary
from app.modules.assets.service import AssetService
from app.modules.transactions.holdings import compute
from app.modules.transactions.models import Holding
from app.modules.transactions.repository import LedgerRepository
from app.modules.transactions.schemas import HoldingOut


class HoldingsService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = LedgerRepository(session)
        self._assets = AssetService(session)

    async def rebuild_asset(
        self, portfolio_id: uuid.UUID, asset_id: uuid.UUID, currency: str
    ) -> None:
        """Recomputes one asset's position from its full ledger history."""
        positions = compute(await self._repo.entries(portfolio_id, asset_id))
        position = positions.get(asset_id)
        if position is None:  # every entry was reversed
            await self._repo.delete_holding(portfolio_id, asset_id)
        else:
            await self._repo.save_holding(portfolio_id, position, currency)

    async def list(
        self, user_id: uuid.UUID, portfolio_id: uuid.UUID, include_closed: bool
    ) -> list[HoldingOut]:
        require_found(await self._repo.owned_portfolio(user_id, portfolio_id), "portfolio")
        rows = await self._repo.holdings(portfolio_id, include_closed)
        assets = await self._assets.summaries(user_id, [h.asset_id for h in rows])
        out = [_out(h, assets[h.asset_id]) for h in rows if h.asset_id in assets]
        return sorted(out, key=lambda h: (h.asset.name.lower(), str(h.asset.id)))


def _money(amount: Decimal, currency: str) -> Money:
    return Money(amount=round_half_up(amount, minor_units(currency)), currency=currency)


def _out(h: Holding, asset: AssetSummary) -> HoldingOut:
    average = None
    if h.quantity > 0:
        unit = round_half_up(h.cost_basis / h.quantity, 8).normalize()
        average = Money(amount=unit, currency=h.currency)
    return HoldingOut(
        asset=asset,
        quantity=h.quantity,
        average_cost=average,
        cost_basis=_money(h.cost_basis, h.currency),
        realized_pl=_money(h.realized_pl, h.currency),
        income=_money(h.income, h.currency),
        expenses=_money(h.expenses, h.currency),
        last_transaction_at=h.last_transaction_at,
        computed_at=h.computed_at,
    )
