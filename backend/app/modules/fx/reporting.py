"""The reporting currency across the app (P11-T06, ADR-0010).

- **Preference.** One global setting per user, stored on the server (`user_currency_preferences`)
  so every device shows the same currency. Until the user chooses, it is the profile's base
  currency when that is supported, else the pivot.
- **One snapshot per response.** A reporting endpoint opens the current snapshot for its request
  (`reporting_scope`); every latest rate any service asks for in that request comes from it, and
  the response says which snapshot and which rates it used. A pair the snapshot cannot supply
  falls back to the stored rates and is marked `from_snapshot: false`; it is never guessed.
- **Presentation only.** Nothing here writes balances, transactions, portfolio base currencies,
  goal targets or forecast inputs; switching the reporting currency only changes what is shown."""

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.money import CURRENCY_PATTERN, Money
from app.db.session import get_session
from app.modules.fx.models import MAX_RECENT_CURRENCIES, UserCurrencyPreference
from app.modules.fx.schemas import ReportingOut, ReportingRateOut
from app.modules.fx.snapshot import Snapshot, SnapshotService, UnsupportedCurrency, convert
from app.modules.fx.status import RateStatus, StatusPolicy
from app.modules.identity.service import IdentityService
from app.modules.market_data.fx import FxRateUnavailable, Quote
from app.modules.market_data.fx_context import current_rates


# ----------------------------------------------------------------------------------- preference
class CurrencyPreferencesOut(BaseModel):
    reporting_currency: str
    recent_currencies: list[str] = Field(description="Most recent first, at most 5")
    is_default: bool = Field(description="True until the user chooses a reporting currency")
    updated_at: datetime | None = None


class CurrencyPreferencesUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reporting_currency: str = Field(pattern=CURRENCY_PATTERN)


class CurrencyPreferenceService:
    def __init__(self, session: AsyncSession, pivot: str) -> None:
        self._session = session
        self._pivot = pivot

    async def get(self, user_id: uuid.UUID) -> CurrencyPreferencesOut:
        row = await self._session.get(UserCurrencyPreference, user_id)
        if row is not None:
            return CurrencyPreferencesOut(
                reporting_currency=row.reporting_currency,
                recent_currencies=list(row.recent_currencies),
                is_default=False,
                updated_at=row.updated_at,
            )
        active = await SnapshotService(self._session, self._pivot).currencies()
        base = (await IdentityService(self._session).me(user_id)).base_currency
        return CurrencyPreferencesOut(
            reporting_currency=base if base in active else self._pivot,
            recent_currencies=[],
            is_default=True,
        )

    async def reporting_currency(self, user_id: uuid.UUID) -> str:
        return (await self.get(user_id)).reporting_currency

    async def set(self, user_id: uuid.UUID, currency: str) -> CurrencyPreferencesOut:
        active = await SnapshotService(self._session, self._pivot).currencies()
        if currency not in active:
            raise UnsupportedCurrency(f"{currency} is not a supported currency")
        row = await self._session.get(UserCurrencyPreference, user_id)
        if row is None:
            row = UserCurrencyPreference(
                user_id=user_id, reporting_currency=currency, recent_currencies=[]
            )
            self._session.add(row)
        elif row.reporting_currency != currency:
            previous = row.reporting_currency
            recent = [
                previous,
                *(c for c in row.recent_currencies if c not in (previous, currency)),
            ]
            row.recent_currencies = recent[:MAX_RECENT_CURRENCIES]
            row.reporting_currency = currency
            row.updated_at = datetime.now(UTC)
        await self._session.commit()
        await self._session.refresh(row)
        return await self.get(user_id)


# ------------------------------------------------------------------------------------ snapshot
@dataclass
class ReportingContext:
    """Implements the FX service's `LatestRates` hook for one request and records what it used."""

    snapshot: Snapshot
    policy: StatusPolicy
    used: dict[tuple[str, str], ReportingRateOut] = field(default_factory=dict)

    def quote(self, base: str, quote: str) -> Quote | None:
        now = datetime.now(UTC)
        try:
            resolved = self.snapshot.rate(base, quote)
        except FxRateUnavailable:
            return None
        status = resolved.status(self.policy, now)
        stamp = resolved.rate_timestamp or self.snapshot.created_at
        provider = "+".join(resolved.providers) or "identity"
        self.used[(base, quote)] = ReportingRateOut(
            base=base,
            quote=quote,
            rate=resolved.rate,
            path=list(resolved.path) if resolved.path else None,
            rate_timestamp=stamp,
            provider=provider,
            status=status.value,
            from_snapshot=True,
        )
        return Quote(
            base,
            quote,
            resolved.rate,
            stamp,
            provider,
            inverted=len(resolved.legs) == 1
            and (resolved.legs[0].base, resolved.legs[0].quote) == (quote, base),
            stale=status is not RateStatus.CURRENT,
            path=resolved.path,
        )

    def note_fallback(self, quote: Quote) -> None:
        self.used[(quote.base_currency, quote.quote_currency)] = ReportingRateOut(
            base=quote.base_currency,
            quote=quote.quote_currency,
            rate=quote.rate,
            path=list(quote.path) if quote.path else None,
            rate_timestamp=quote.as_of,
            provider=quote.provider,
            status="stale" if quote.stale else "current",
            from_snapshot=False,
        )

    def out(self, currency: str) -> ReportingOut:
        rates = sorted(self.used.values(), key=lambda r: (r.base, r.quote))
        return ReportingOut(currency=currency, snapshot_id=self.snapshot.id, rates=rates)


async def reporting_scope(
    request: Request, session: Annotated[AsyncSession, Depends(get_session)]
) -> AsyncIterator[ReportingContext]:
    """FastAPI dependency: opens the current snapshot for this request."""
    settings: Settings = request.app.state.settings
    snapshot = await SnapshotService(session, settings.fx_pivot_currency).current()
    context = ReportingContext(snapshot, StatusPolicy.from_settings(settings))
    token = current_rates.set(context)
    try:
        yield context
    finally:
        current_rates.reset(token)


ReportingDep = Annotated[ReportingContext, Depends(reporting_scope)]


def translate(context: ReportingContext, money: Money, to: str, places: int) -> Money | None:
    """`money` shown in `to` at the request snapshot's rate; None when the snapshot has no rate
    (the caller shows the original amount only)."""
    if money.currency == to:
        return money
    q = context.quote(money.currency, to)
    if q is None:
        return None
    return Money(amount=convert(money.amount, q.rate, places), currency=to)
