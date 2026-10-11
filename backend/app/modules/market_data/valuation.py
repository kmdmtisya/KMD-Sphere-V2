"""Valuing positions from market prices with fallback to manual valuations (P08-T06).

Rules (docs/design/valuation-sources.md):
- A position of an asset valued from prices (market class with a provider kind) is worth
  `quantity x latest price`, in the asset's own currency. The price keeps its `as_of`, provider
  and a `stale` flag when older than its kind's freshness window.
- A manual valuation (the user's own figure for the whole position) is the fallback when there is
  no price, and **wins when it is newer than the latest price**: the user's more recent statement
  of value beats an older quote. On a tie the market price wins.
- An asset valued manually (a house, a SACCO share) uses its manual valuation only.
- No price and no valuation: the position is unpriced (reported as such, never guessed).

The result feeds the summary and the holdings list; the FX conversion into the portfolio currency
stays where it was (docs/design/portfolio-summary.md)."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, localcontext
from typing import Literal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.assets.models import Asset, AssetClass
from app.modules.market_data.freshness import is_stale, kind_for_asset_class
from app.modules.market_data.models import MarketPrice
from app.modules.market_data.providers.models import AssetKind
from app.modules.transactions.valuations_service import ValuationService

PRECISION = 50
Source = Literal["price", "valuation"]


@dataclass(frozen=True)
class PriceCandidate:
    price: Decimal
    currency: str
    as_of: datetime
    provider: str


@dataclass(frozen=True)
class ManualCandidate:
    value: Decimal  # the whole position
    currency: str
    as_of: datetime


@dataclass(frozen=True)
class PositionValue:
    """A position's value in its own currency, and where it came from."""

    asset_id: uuid.UUID
    value: Decimal
    currency: str
    as_of: datetime
    source: Source
    stale: bool
    provider: str | None


def choose_value(
    asset_id: uuid.UUID,
    quantity: Decimal,
    kind: AssetKind | None,
    price: PriceCandidate | None,
    manual: ManualCandidate | None,
    now: datetime,
) -> PositionValue | None:
    """The value of a position, or None when it cannot be valued.

    `kind` is None for an asset that is valued manually (or has no provider): its price, if one
    somehow exists, is ignored."""
    use_price = kind is not None and price is not None
    if use_price and manual is not None and price is not None and manual.as_of > price.as_of:
        use_price = False  # the user's newer figure wins
    if use_price and price is not None and kind is not None:
        with localcontext() as ctx:
            ctx.prec = PRECISION
            value = quantity * price.price
        return PositionValue(
            asset_id,
            value,
            price.currency,
            price.as_of,
            "price",
            is_stale(price.as_of, now, kind),
            price.provider,
        )
    if manual is not None:
        return PositionValue(
            asset_id, manual.value, manual.currency, manual.as_of, "valuation", False, None
        )
    return None


class PositionValuer:
    """Loads prices and valuations and applies `choose_value`. The caller has authorised the
    portfolio; prices belong to global assets and carry no user data."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def values(
        self,
        portfolio_id: uuid.UUID,
        quantities: dict[uuid.UUID, Decimal],
        now: datetime | None = None,
    ) -> dict[uuid.UUID, PositionValue]:
        """Values for the open positions in `quantities` (asset id -> units held). Closed
        positions (zero units) and unpriced ones are absent. Manual valuations of assets that
        are not in `quantities` are ignored here (the summary reports them separately)."""
        moment = now or datetime.now(UTC)
        manual = {
            v.asset_id: ManualCandidate(v.value, v.currency, v.as_of)
            for v in await ValuationService(self._session).latest_rows(portfolio_id, moment)
        }
        open_ids = {a for a, q in quantities.items() if q != 0}
        kinds = await self._kinds(open_ids | set(manual))
        prices = await self._latest_prices(
            {a for a in open_ids if kinds.get(a) is not None}, moment
        )
        out: dict[uuid.UUID, PositionValue] = {}
        for asset_id in sorted(open_ids | {a for a in manual if a not in quantities}, key=str):
            quantity = quantities.get(asset_id, Decimal(0))
            if asset_id in quantities and quantity == 0:
                continue
            chosen = choose_value(
                asset_id,
                quantity,
                kinds.get(asset_id),
                prices.get(asset_id),
                manual.get(asset_id),
                moment,
            )
            if chosen is not None:
                out[asset_id] = chosen
        return out

    async def _kinds(self, asset_ids: set[uuid.UUID]) -> dict[uuid.UUID, AssetKind | None]:
        if not asset_ids:
            return {}
        rows = await self._session.execute(
            select(Asset.id, AssetClass.code, AssetClass.valuation_mode)
            .join(AssetClass, Asset.asset_class_id == AssetClass.id)
            .where(Asset.id.in_(asset_ids))
        )
        return {
            asset_id: kind_for_asset_class(code) if mode == "market" else None
            for asset_id, code, mode in rows.all()
        }

    async def _latest_prices(
        self, asset_ids: set[uuid.UUID], moment: datetime
    ) -> dict[uuid.UUID, PriceCandidate]:
        if not asset_ids:
            return {}
        rows = await self._session.execute(
            select(MarketPrice)
            .where(MarketPrice.asset_id.in_(asset_ids), MarketPrice.as_of <= moment)
            .ext(distinct_on(MarketPrice.asset_id))
            .order_by(
                MarketPrice.asset_id,
                MarketPrice.as_of.desc(),
                MarketPrice.retrieved_at.desc(),
                MarketPrice.provider,
            )
        )
        return {
            p.asset_id: PriceCandidate(p.price, p.currency, p.as_of, p.provider)
            for p in rows.scalars()
        }
