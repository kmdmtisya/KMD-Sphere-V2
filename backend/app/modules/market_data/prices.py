"""An asset's stored market prices for the app (P09-T07): the latest price with its freshness, and
daily closes over a period. Only assets the user may see; nothing is interpolated or estimated."""

import uuid
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authz import ResourceNotFoundError
from app.modules.assets.models import Asset, AssetClass
from app.modules.assets.service import AssetService
from app.modules.market_data.freshness import kind_for_asset_class
from app.modules.market_data.ingestion import latest_price
from app.modules.market_data.models import MarketPrice
from app.modules.market_data.schemas import AssetPricesOut, PricePointOut, UnitPriceOut

DEFAULT_DAYS = 365


class AssetPriceService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def prices(
        self,
        user_id: uuid.UUID,
        asset_id: uuid.UUID,
        start: date | None,
        end: date | None,
        now: datetime | None = None,
    ) -> AssetPricesOut:
        if not await AssetService(self._session).is_visible(user_id, asset_id):
            raise ResourceNotFoundError("asset")
        moment = now or datetime.now(UTC)
        row = (
            await self._session.execute(
                select(Asset.currency, AssetClass.code)
                .join(AssetClass, AssetClass.id == Asset.asset_class_id)
                .where(Asset.id == asset_id)
            )
        ).one()
        currency, class_code = row
        kind = kind_for_asset_class(class_code)
        if kind is None:  # valued manually: there is no market price to show
            return AssetPricesOut(asset_id=asset_id, currency=currency, latest=None, points=[])
        last = end or moment.date()
        first = start or last - timedelta(days=DEFAULT_DAYS)
        stored = await latest_price(self._session, asset_id, kind, moment)
        rows = (
            await self._session.execute(
                select(MarketPrice)
                .where(
                    MarketPrice.asset_id == asset_id,
                    MarketPrice.price_type == "close",
                    MarketPrice.as_of >= datetime.combine(first, time.min, UTC),
                    MarketPrice.as_of <= datetime.combine(last, time.max, UTC),
                )
                .order_by(MarketPrice.as_of, MarketPrice.retrieved_at.desc())
            )
        ).scalars()
        by_day: dict[date, MarketPrice] = {}
        for p in rows:
            # One close per day: the most recently retrieved one when providers overlap.
            by_day.setdefault(p.as_of.astimezone(UTC).date(), p)
        return AssetPricesOut(
            asset_id=asset_id,
            currency=currency,
            latest=None
            if stored is None
            else UnitPriceOut(
                price=stored.price,
                currency=stored.currency,
                as_of=stored.as_of,
                provider=stored.provider,
                stale=stored.stale,
            ),
            points=[
                PricePointOut(on=day, close=p.price, provider=p.provider)
                for day, p in sorted(by_day.items())
            ],
        )
