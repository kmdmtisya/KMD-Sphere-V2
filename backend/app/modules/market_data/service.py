"""FX service: rates from `fx_rates` chosen by the rules in `fx.py` (P05-T06)."""

from datetime import UTC, date, datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.money import round_half_up
from app.modules.market_data.fx import (
    HISTORICAL_MAX_AGE,
    FxRateUnavailable,
    Quote,
    StoredRate,
    end_of_day,
    select_via,
)
from app.modules.market_data.fx import (
    select as select_rate,
)
from app.modules.market_data.models import FxRate

# Rates stored on ledger postings have 12 decimals (NUMERIC(28,12), ADR-0006).
POSTING_RATE_DECIMALS = 12


class FxService:
    def __init__(self, session: AsyncSession, pivot: str | None = None) -> None:
        self._session = session
        # Cross rates go through the pivot currency (DEC-27, P11-T04).
        self._pivot = pivot or get_settings().fx_pivot_currency

    async def quote(
        self, base: str, quote: str, at: datetime | None = None, *, cross: bool = True
    ) -> Quote:
        """The rate valid at `at` (default: now): direct, inverted, or (with `cross`) through the
        pivot when neither direction is stored. Raises FxRateUnavailable."""
        now = datetime.now(UTC)
        when = at or now
        if base == quote:
            return select_rate(base, quote, [], when, now=now)
        currencies = {base, quote} | ({self._pivot} if cross else set())
        result = await self._session.execute(
            select(FxRate).where(
                FxRate.base_currency.in_(currencies),
                FxRate.quote_currency.in_(currencies),
                FxRate.rate_timestamp <= when,
                FxRate.rate_timestamp >= when - HISTORICAL_MAX_AGE,
            )
        )
        candidates = [
            StoredRate(
                r.base_currency,
                r.quote_currency,
                r.rate,
                r.provider,
                r.rate_timestamp,
                r.retrieved_at,
                tuple(r.rate_path) if r.rate_path else None,
            )
            for r in result.scalars()
        ]
        return select_via(
            base, quote, candidates, when, now=now, pivot=self._pivot if cross else None
        )

    async def history(
        self, currencies: set[str], quote: str, start: datetime, end: datetime
    ) -> list[StoredRate]:
        """Every stored rate between each of `currencies` and `quote` (either direction) that
        the historical rule could choose for a moment in [start, end] (for value series)."""
        others = sorted(currencies - {quote})
        if not others:
            return []
        result = await self._session.execute(
            select(FxRate).where(
                or_(
                    (FxRate.base_currency.in_(others)) & (FxRate.quote_currency == quote),
                    (FxRate.base_currency == quote) & (FxRate.quote_currency.in_(others)),
                ),
                FxRate.rate_timestamp <= end,
                FxRate.rate_timestamp >= start - HISTORICAL_MAX_AGE,
            )
        )
        return [
            StoredRate(
                r.base_currency,
                r.quote_currency,
                r.rate,
                r.provider,
                r.rate_timestamp,
                r.retrieved_at,
            )
            for r in result.scalars()
        ]

    async def rate_for_posting(self, base: str, quote: str, trade_date: date) -> Quote:
        """The historical rate for a posting on `trade_date`, rounded to the 12 decimals the
        ledger stores."""
        # A posting keeps the rate of the pair itself (direct or inverted): ledger rates are
        # never derived through a third currency.
        q = await self.quote(base, quote, end_of_day(trade_date), cross=False)
        rounded = round_half_up(q.rate, POSTING_RATE_DECIMALS)
        if rounded <= 0:
            raise FxRateUnavailable(f"{base}/{quote} rate rounds to zero")
        return Quote(
            q.base_currency,
            q.quote_currency,
            rounded,
            q.as_of,
            q.provider,
            inverted=q.inverted,
            stale=q.stale,
        )
