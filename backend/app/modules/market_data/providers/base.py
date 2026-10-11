"""The interface every market-data source implements. Feature code depends on this and nothing
else, so a vendor can be replaced without touching it (ADR-0014)."""

from datetime import date
from typing import Protocol, runtime_checkable

from app.modules.market_data.providers.models import AssetKind, FxQuote, PricePoint, PriceQuote


@runtime_checkable
class MarketDataProvider(Protocol):
    """A source of prices, history and FX rates.

    Implementations raise the errors in `errors` (never a vendor exception) and return values
    that already passed validation and carry provenance. They never return a guessed or filled-in
    value: if the vendor has nothing, they raise."""

    @property
    def name(self) -> str:
        """Stable identifier stored with every value (for example `ecb`, `coingecko`)."""
        ...

    @property
    def supported_kinds(self) -> frozenset[AssetKind]: ...

    async def get_quote(self, symbol: str, kind: AssetKind) -> PriceQuote: ...

    async def get_history(
        self, symbol: str, kind: AssetKind, start: date, end: date
    ) -> list[PricePoint]:
        """Daily closes from `start` to `end` inclusive, oldest first. Days without a close (a
        weekend, a holiday) are absent, not filled."""
        ...

    async def get_fx_rate(self, base: str, quote: str) -> FxQuote: ...

    async def get_fx_history(self, base: str, quote: str, start: date, end: date) -> list[FxQuote]:
        """One rate per day from `start` to `end` inclusive, oldest first; days the provider
        published nothing for are absent."""
        ...
