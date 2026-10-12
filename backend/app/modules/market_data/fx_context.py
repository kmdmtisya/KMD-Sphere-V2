"""The rate snapshot of the current request (P11-T06).

A reporting endpoint opens a snapshot for its request (`app.modules.fx.reporting`). While it is
open, every *latest* rate the FX service is asked for comes from that snapshot, so all figures of
one response (portfolio totals, net worth, income, goal values) use the same rates and a total
equals the sum of its converted parts. Historical rates (a date given) and ledger postings never
come from the snapshot. Outside a reporting request nothing changes.

This module only holds the hook; it imports nothing from the FX module, which implements it."""

from contextvars import ContextVar
from typing import Protocol

from app.modules.market_data.fx import Quote


class LatestRates(Protocol):
    def quote(self, base: str, quote: str) -> Quote | None:
        """The snapshot's rate, or None when the snapshot cannot supply this pair (the caller
        then uses the stored rates directly and says so)."""
        ...

    def note_fallback(self, quote: Quote) -> None:
        """Records a rate that came from the stored rates instead of the snapshot."""
        ...


current_rates: ContextVar[LatestRates | None] = ContextVar("current_rates", default=None)
