"""Holdings cache and API (ADR-0012). The ledger is the source of truth; `holdings` is rebuilt for
the affected asset in the same database transaction as every posting or reversal."""

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authz import require_found
from app.core.money import Money, minor_units, round_half_up
from app.modules.assets.schemas import AssetSummary
from app.modules.assets.service import AssetService
from app.modules.market_data.fx import FxRateUnavailable
from app.modules.market_data.service import FxService
from app.modules.transactions.holdings import Entry, compute
from app.modules.transactions.models import Holding
from app.modules.transactions.repository import LedgerRepository
from app.modules.transactions.schemas import HoldingOut


@dataclass(frozen=True)
class _Value:
    native: Money
    converted: Money | None
    as_of: datetime


class HoldingsService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
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

    async def positions(self, portfolio_id: uuid.UUID) -> list[Holding]:
        """Every holding row, closed ones included. The caller has authorised the portfolio."""
        return await self._repo.holdings(portfolio_id, include_closed=True)

    async def entries(self, portfolio_id: uuid.UUID) -> list[Entry]:
        """Every ledger entry (with reversals). The caller has authorised the portfolio."""
        return await self._repo.all_entries(portfolio_id)

    async def list(
        self, user_id: uuid.UUID, portfolio_id: uuid.UUID, include_closed: bool
    ) -> list[HoldingOut]:
        portfolio = require_found(
            await self._repo.owned_portfolio(user_id, portfolio_id), "portfolio"
        )
        rows = await self._repo.holdings(portfolio_id, include_closed)
        assets = await self._assets.summaries(user_id, [h.asset_id for h in rows])
        values = await self._values(portfolio_id, portfolio.base_currency)
        out = [
            _out(h, assets[h.asset_id], values.get(h.asset_id) if h.quantity > 0 else None)
            for h in rows
            if h.asset_id in assets
        ]
        return sorted(out, key=lambda h: (h.asset.name.lower(), str(h.asset.id)))

    async def _values(self, portfolio_id: uuid.UUID, base: str) -> dict[uuid.UUID, _Value]:
        """Latest valuation per asset, converted to the portfolio currency at the latest rate
        (the same rules as the summary, docs/design/portfolio-summary.md)."""
        from app.modules.transactions.valuations_service import ValuationService

        out: dict[uuid.UUID, _Value] = {}
        rates: dict[str, Decimal | None] = {}
        for v in await ValuationService(self._session).latest_rows(portfolio_id, None):
            if v.currency not in rates:
                try:
                    rates[v.currency] = (
                        await FxService(self._session).quote(v.currency, base)
                    ).rate
                except FxRateUnavailable:
                    rates[v.currency] = None
            rate = rates[v.currency]
            out[v.asset_id] = _Value(
                native=Money(
                    amount=round_half_up(v.value, minor_units(v.currency)), currency=v.currency
                ),
                converted=_money(v.value * rate, base) if rate is not None else None,
                as_of=v.as_of,
            )
        return out


def _money(amount: Decimal, currency: str) -> Money:
    return Money(amount=round_half_up(amount, minor_units(currency)), currency=currency)


def _out(h: Holding, asset: AssetSummary, value: _Value | None) -> HoldingOut:
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
        value=value.converted if value else None,
        native_value=value.native if value else None,
        value_as_of=value.as_of if value else None,
        value_source="valuation" if value else None,
    )
