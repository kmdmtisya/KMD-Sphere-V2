"""Several FX rates of one base in as few requests as the provider allows (P11-T03.4).

A provider that can answer many quotes at once implements `get_fx_rates(base, quotes)` (the ECB
and ExchangeRate-API do, from one document); for any other provider the rates are asked one by
one. Either way, a quote the provider does not publish is reported as unsupported, so the next
provider can be asked for it; a provider outage propagates, so the caller can fall back."""

from typing import Protocol, runtime_checkable

from app.modules.market_data.providers.base import MarketDataProvider
from app.modules.market_data.providers.errors import SymbolNotFound, UnsupportedKind
from app.modules.market_data.providers.models import FxBatch, FxQuote


@runtime_checkable
class BatchFxProvider(Protocol):
    async def get_fx_rates(self, base: str, quotes: list[str]) -> FxBatch: ...


async def fetch_fx_batch(provider: MarketDataProvider, base: str, quotes: list[str]) -> FxBatch:
    wanted = [q for q in dict.fromkeys(quotes) if q != base]
    if isinstance(provider, BatchFxProvider):
        return await provider.get_fx_rates(base, wanted)
    found: list[FxQuote] = []
    unsupported: list[str] = []
    for quote in wanted:
        try:
            found.append(await provider.get_fx_rate(base, quote))
        except (UnsupportedKind, SymbolNotFound):
            # The provider does not know this pair (the contract allows either error).
            unsupported.append(quote)
    return FxBatch(found, unsupported)
