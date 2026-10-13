"""Compare and Simulate (P12-T07).

**Compare** puts 2 to 5 universe instruments side by side with what is measured or recorded about
them: asset class, geography, currency, risk level, liquidity, fees, past price figures (labelled
past), the explainable score, eligibility for the user, a research horizon and, with a portfolio,
the diversification impact. Income yield is shown as not available: no distribution data is
stored. Nothing about the future appears in a comparison.

**Simulate** runs one instrument through the deterministic forecast engine (P06-T02) under return
assumptions the user states: conservative, base and growth. There is no default return and none
comes from a model. Every result is an illustration under those assumptions, never a forecast of
the instrument, and the response says how the assumptions differ from what is recorded (for
example the instrument's expense ratio)."""

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authz import ResourceNotFoundError
from app.core.errors import InvalidValueError
from app.core.money import format_decimal, round_half_up
from app.modules.compatibility.service import Compatibility, CompatibilityService
from app.modules.forecasting import service as forecasting
from app.modules.forecasting.schemas import ScenarioForecastIn, ScenarioForecastOut
from app.modules.scoring.scoring import Factor
from app.modules.scoring.service import ScoredItem, ScoringService

MAX_COMPARED = 5


@dataclass(frozen=True)
class Compared:
    scored: ScoredItem
    compatibility: Compatibility | None


@dataclass(frozen=True)
class Simulation:
    scored: ScoredItem
    forecast: ScenarioForecastOut
    notes: list[str]
    compatibility: Compatibility | None


class CompareService:
    def __init__(self, session: AsyncSession, weights: dict[Factor, Decimal]) -> None:
        self._scoring = ScoringService(session, weights)
        self._compat = CompatibilityService(session)

    async def _items(
        self, user_id: uuid.UUID, asset_ids: list[uuid.UUID], now: datetime
    ) -> dict[uuid.UUID, ScoredItem]:
        found = {s.item.asset_id: s for s in await self._scoring.universe(user_id, None, now)}
        missing = [a for a in asset_ids if a not in found]
        if missing:
            raise ResourceNotFoundError("instrument")
        return found

    async def compare(
        self,
        user_id: uuid.UUID,
        asset_ids: list[uuid.UUID],
        portfolio_id: uuid.UUID | None,
        amount: Decimal | None,
        currency: str | None,
        now: datetime,
    ) -> list[Compared]:
        if len(set(asset_ids)) != len(asset_ids):
            raise InvalidValueError("Each instrument may be compared once.")
        found = await self._items(user_id, asset_ids, now)
        out = []
        for asset_id in asset_ids:
            compat = None
            if portfolio_id is not None and amount is not None and currency is not None:
                compat = await self._compat.check(
                    user_id, portfolio_id, asset_id, amount, currency, now
                )
            out.append(Compared(found[asset_id], compat))
        return out

    async def simulate(
        self,
        user_id: uuid.UUID,
        asset_id: uuid.UUID,
        assumptions: ScenarioForecastIn,
        portfolio_id: uuid.UUID | None,
        now: datetime,
    ) -> Simulation:
        scored = (await self._items(user_id, [asset_id], now))[asset_id]
        forecast = forecasting.scenarios(assumptions)
        notes = []
        ratio = scored.features.expense_ratio
        if ratio is not None and assumptions.annual_fee_percent != ratio * 100:
            recorded = format_decimal(round_half_up(ratio * 100, 2))
            yours = format_decimal(assumptions.annual_fee_percent)
            notes.append(
                f"The instrument's recorded expense ratio is {recorded}% a year; your "
                f"assumptions use {yours}%."
            )
        if assumptions.currency != scored.item.currency:
            notes.append(
                f"The instrument is priced in {scored.item.currency}; the simulation is in "
                f"{assumptions.currency}, so exchange-rate moves are not modelled."
            )
        notes.append(
            "Returns are your assumptions, not a forecast of this instrument; real returns vary "
            "from year to year and can be negative."
        )
        compat = None
        if portfolio_id is not None:
            amount = assumptions.initial_investment
            if amount.amount > 0:
                compat = await self._compat.check(
                    user_id, portfolio_id, asset_id, amount.amount, amount.currency, now
                )
        return Simulation(scored, forecast, notes, compat)
