"""Compatibility of a universe instrument with one of the user's portfolios (P12-T04). Gathers the
portfolio's Doctor inputs (owner-scoped), the instrument and its eligibility for the user, and the
rate to check its minimum investment; the assessment itself is pure (impact.py)."""

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authz import ResourceNotFoundError
from app.core.errors import InvalidValueError
from app.modules.assets.service import AssetService
from app.modules.compatibility.impact import Assessment, Candidate, assess
from app.modules.doctor.service import DoctorService
from app.modules.market_data.fx import FxRateUnavailable
from app.modules.market_data.service import FxService
from app.modules.universe.service import UniverseItem, UniverseService


@dataclass(frozen=True)
class Compatibility:
    portfolio_id: uuid.UUID
    currency: str  # the portfolio's base currency
    amount: Decimal
    item: UniverseItem
    amount_in_instrument_currency: Decimal | None
    assessment: Assessment


class CompatibilityService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._doctor = DoctorService(session)
        self._universe = UniverseService(session)
        self._assets = AssetService(session)

    async def check(
        self,
        user_id: uuid.UUID,
        portfolio_id: uuid.UUID,
        asset_id: uuid.UUID,
        amount: Decimal,
        currency: str,
        now: datetime,
    ) -> Compatibility:
        """Raises ResourceNotFoundError for another user's portfolio or an instrument that is not
        in the universe, and InvalidValueError for an amount not in the portfolio's currency."""
        inputs = await self._doctor.inputs(user_id, portfolio_id, now)  # the ownership check
        if currency != inputs.currency:
            raise InvalidValueError(
                f"The amount must be in the portfolio's base currency ({inputs.currency})."
            )
        if amount <= 0:
            raise InvalidValueError("The amount must be greater than zero.")
        item = next(
            (i for i in (await self._universe.for_user(user_id)).items if i.asset_id == asset_id),
            None,
        )
        if item is None:
            raise ResourceNotFoundError("instrument")
        cls = (await self._assets.classifications([asset_id]))[asset_id]
        candidate = Candidate(asset_id, item.asset_class, item.currency, cls.country, cls.sector)
        converted: Decimal | None = amount
        if item.currency != inputs.currency:
            try:
                rate = (await FxService(self._session).quote(inputs.currency, item.currency)).rate
                converted = amount * rate
            except FxRateUnavailable:
                converted = None
        assessment = assess(
            inputs,
            candidate,
            amount,
            item.eligibility,
            minimum=item.minimum_investment,
            amount_in_instrument_currency=converted,
        )
        return Compatibility(portfolio_id, inputs.currency, amount, item, converted, assessment)
