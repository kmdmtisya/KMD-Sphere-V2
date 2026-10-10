"""Portfolio summaries (P05-T08): gathers the inputs and publishes the figures computed by
`summary.py`. Formulas: docs/design/portfolio-summary.md."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authz import require_found
from app.core.money import Money, minor_units, percentages, round_half_up
from app.modules.assets.service import AssetService
from app.modules.identity.service import IdentityService
from app.modules.market_data.fx import FxRateUnavailable
from app.modules.market_data.service import FxService
from app.modules.portfolio.models import Portfolio
from app.modules.portfolio.repository import PortfolioRepository
from app.modules.portfolio.summary import (
    HoldingInput,
    Rate,
    Summary,
    ValuationInput,
    compute_summary,
    consolidate,
)
from app.modules.portfolio.summary_schemas import CurrencyShare, Freshness, SummaryOut
from app.modules.transactions.holdings_service import HoldingsService
from app.modules.transactions.valuations_service import ValuationService


class SummaryService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._portfolios = PortfolioRepository(session)
        self._holdings = HoldingsService(session)
        self._valuations = ValuationService(session)
        self._fx = FxService(session)
        self._assets = AssetService(session)

    async def portfolio(self, user_id: uuid.UUID, portfolio_id: uuid.UUID) -> SummaryOut:
        portfolio = require_found(await self._portfolios.get(user_id, portfolio_id), "portfolio")
        now = datetime.now(UTC)
        summary = await self._compute(portfolio)
        return await self._out(user_id, [portfolio.id], summary, now)

    async def consolidated(self, user_id: uuid.UUID, currency: str | None) -> SummaryOut:
        reporting = currency or (await IdentityService(self._session).me(user_id)).base_currency
        portfolios = await self._portfolios.list(user_id, include_archived=False)
        now = datetime.now(UTC)
        parts = [await self._compute(p) for p in portfolios]
        rates = await self._rates({p.base_currency for p in portfolios}, reporting)
        summary = consolidate(reporting, parts, rates)
        return await self._out(user_id, [p.id for p in portfolios], summary, now)

    async def _compute(self, portfolio: Portfolio) -> Summary:
        holdings = [
            HoldingInput(h.asset_id, h.quantity, h.cost_basis, h.realized_pl, h.income, h.expenses)
            for h in await self._holdings.positions(portfolio.id)
        ]
        valuations = [
            ValuationInput(v.asset_id, v.value, v.currency, v.as_of)
            for v in await self._valuations.latest_rows(portfolio.id, None)
        ]
        entries = await self._holdings.entries(portfolio.id)
        currencies = {v.currency for v in valuations} | {e.currency for e in entries}
        rates = await self._rates(currencies, portfolio.base_currency)
        return compute_summary(portfolio.base_currency, holdings, valuations, entries, rates)

    async def _rates(self, currencies: set[str], target: str) -> dict[str, Rate]:
        """Latest rates into `target`. A missing rate is left out (the figures report it)."""
        rates: dict[str, Rate] = {}
        for currency in sorted(currencies - {target}):
            try:
                q = await self._fx.quote(currency, target)
            except FxRateUnavailable:
                continue
            rates[currency] = Rate(currency, q.rate, q.as_of, q.stale)
        return rates

    async def _out(
        self, user_id: uuid.UUID, ids: list[uuid.UUID], s: Summary, now: datetime
    ) -> SummaryOut:
        ccy = s.currency
        rows = sorted(s.converted)
        shares = percentages([s.converted[c] for c in rows])
        unpriced = await self._assets.summaries(user_id, sorted(set(s.unpriced_assets)))
        return SummaryOut(
            portfolio_ids=ids,
            currency=ccy,
            total_value=_m(s.total_value, ccy),
            holdings_value=_m(s.holdings_value, ccy),
            cash=_m(s.cash, ccy),
            cost_basis=_m(s.cost_basis, ccy),
            unrealized_pl=_m(s.unrealized_pl, ccy),
            realized_pl=_m(s.realized_pl, ccy),
            income=_m(s.income, ccy),
            expenses=_m(s.expenses, ccy),
            net_contributions=_m(s.net_contributions, ccy),
            valued_positions=s.valued_positions,
            currencies=[
                CurrencyShare(
                    currency=c,
                    native=_m(s.native[c], c),
                    value=_m(s.converted[c], ccy),
                    share_percent=shares[i] if shares else None,
                )
                for i, c in enumerate(rows)
            ],
            unpriced_assets=[unpriced[a] for a in sorted(unpriced, key=str)],
            freshness=Freshness(
                computed_at=now,
                data_as_of=s.data_as_of(now),
                stale_fx=sorted(s.stale_fx),
                unconverted_currencies=sorted(s.unconverted_currencies),
                complete=s.complete,
            ),
        )


def _m(amount: Decimal, currency: str) -> Money:
    return Money(amount=round_half_up(amount, minor_units(currency)), currency=currency)
