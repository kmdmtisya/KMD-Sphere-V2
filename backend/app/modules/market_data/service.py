"""FX service: rates from `fx_rates` chosen by the rules in `fx.py` (P05-T06)."""

from datetime import UTC, date, datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.money import round_half_up
from app.modules.market_data.fx import (
    HISTORICAL_MAX_AGE,
    FxRateUnavailable,
    Quote,
    StoredRate,
    end_of_day,
)
from app.modules.market_data.fx import (
    select as select_rate,
)
from app.modules.market_data.models import FxRate

# Rates stored on ledger postings have 12 decimals (NUMERIC(28,12), ADR-0006).
POSTING_RATE_DECIMALS = 12


class FxService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def quote(self, base: str, quote: str, at: datetime | None = None) -> Quote:
        """The rate valid at `at` (default: now). Raises FxRateUnavailable."""
        now = datetime.now(UTC)
        when = at or now
        if base == quote:
            return select_rate(base, quote, [], when, now=now)
        result = await self._session.execute(
            select(FxRate).where(
                or_(
                    (FxRate.base_currency == base) & (FxRate.quote_currency == quote),
                    (FxRate.base_currency == quote) & (FxRate.quote_currency == base),
                ),
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
            )
            for r in result.scalars()
        ]
        return select_rate(base, quote, candidates, when, now=now)

    async def rate_for_posting(self, base: str, quote: str, trade_date: date) -> Quote:
        """The historical rate for a posting on `trade_date`, rounded to the 12 decimals the
        ledger stores."""
        q = await self.quote(base, quote, end_of_day(trade_date))
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
