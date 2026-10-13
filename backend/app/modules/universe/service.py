"""The investment universe for a user (P12-T02.3): every instrument with the outcome of each
eligibility rule for that user. The universe is public reference data; only the investor facts
(country of residence, latest risk profile) are the user's own."""

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.assets.liquidity import Liquidity
from app.modules.assets.models import Asset, AssetClass
from app.modules.identity.repository import IdentityRepository
from app.modules.universe.eligibility import Eligibility, Instrument, Investor, evaluate
from app.modules.universe.models import UniverseInstrument


@dataclass(frozen=True)
class UniverseItem:
    asset_id: uuid.UUID
    symbol: str | None
    name: str
    asset_class: str
    currency: str
    country: str | None
    risk_level: int
    liquidity: Liquidity
    jurisdictions: list[str]
    minimum_investment: Decimal | None
    is_demo: bool
    licence_status: str
    data_as_of: datetime
    eligibility: Eligibility


@dataclass(frozen=True)
class UserUniverse:
    investor: Investor
    items: list[UniverseItem]


class UniverseService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._identity = IdentityRepository(session)

    async def investor(self, user_id: uuid.UUID) -> Investor:
        profile = await self._identity.get_profile(user_id)
        latest = next(iter(await self._identity.list_risk_profiles(user_id)), None)
        return Investor(
            residence_country=profile.residence_country,
            risk_tolerance=latest.risk_tolerance if latest is not None else None,
            horizon_years=latest.horizon_years if latest is not None else None,
        )

    async def for_user(
        self, user_id: uuid.UUID, asset_class: str | None = None, *, active_only: bool = True
    ) -> UserUniverse:
        investor = await self.investor(user_id)
        query = (
            select(UniverseInstrument, Asset, AssetClass.code)
            .join(Asset, Asset.id == UniverseInstrument.asset_id)
            .join(AssetClass, AssetClass.id == Asset.asset_class_id)
            .order_by(AssetClass.code, Asset.symbol, Asset.id)
        )
        if active_only:
            query = query.where(UniverseInstrument.is_active.is_(True))
        if asset_class is not None:
            query = query.where(AssetClass.code == asset_class)
        items = []
        for row, asset, code in (await self._session.execute(query)).all():
            liquidity = Liquidity(row.liquidity)
            instrument = Instrument(
                code, row.risk_level, liquidity, row.jurisdictions, row.is_active
            )
            items.append(
                UniverseItem(
                    asset_id=asset.id,
                    symbol=asset.symbol,
                    name=asset.name,
                    asset_class=code,
                    currency=asset.currency,
                    country=asset.country,
                    risk_level=row.risk_level,
                    liquidity=liquidity,
                    jurisdictions=list(row.jurisdictions),
                    minimum_investment=row.minimum_investment,
                    is_demo=row.is_demo,
                    licence_status=row.licence_status,
                    data_as_of=row.data_as_of,
                    eligibility=evaluate(investor, instrument),
                )
            )
        return UserUniverse(investor, items)
