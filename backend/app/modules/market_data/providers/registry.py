"""Composition point: which provider serves which kind of asset (ADR-0014).

The only module (with the fake and the adapters themselves) that names a vendor. Everything else
asks for `MarketProviders` and uses the interface. Each provider is wrapped with retry and a
circuit breaker; FX is a fallback chain. A provider whose key is not configured is left out, so
the app runs on what is available and reports the rest as unavailable (never invented)."""

from dataclasses import dataclass

from app.core.config import Settings
from app.modules.market_data.providers.base import MarketDataProvider
from app.modules.market_data.providers.coingecko import CoinGeckoProvider
from app.modules.market_data.providers.ecb import EcbProvider
from app.modules.market_data.providers.exchangerate_api import ExchangeRateApiProvider
from app.modules.market_data.providers.fake import FakeProvider
from app.modules.market_data.providers.models import AssetKind
from app.modules.market_data.providers.resilience import FallbackChain, ResilientProvider
from app.modules.market_data.providers.twelvedata import TwelveDataProvider


@dataclass(frozen=True)
class MarketProviders:
    by_kind: dict[AssetKind, MarketDataProvider]
    fx: MarketDataProvider | None
    # The FX providers one by one, in the configured order (P11-T03): the reporting-currency
    # refresh asks each for the pairs the previous ones could not supply.
    fx_sources: tuple[MarketDataProvider, ...] = ()

    @property
    def configured(self) -> bool:
        return bool(self.by_kind) or self.fx is not None


def build_providers(settings: Settings) -> MarketProviders:
    if settings.market_data_mode == "fake":
        fake = FakeProvider()
        return MarketProviders(dict.fromkeys(AssetKind, fake), fake, (fake,))

    by_kind: dict[AssetKind, MarketDataProvider] = {}
    available: dict[str, MarketDataProvider] = {"ecb": ResilientProvider(EcbProvider())}

    twelve_key = settings.twelvedata_api_key
    if twelve_key.get_secret_value():
        twelve = ResilientProvider(TwelveDataProvider(twelve_key))
        for kind in (AssetKind.EQUITY, AssetKind.ETF, AssetKind.INDEX):
            by_kind[kind] = twelve
        available["twelvedata"] = twelve

    rates_key = settings.exchangerate_api_key
    if rates_key.get_secret_value():
        available["exchangerate_api"] = ResilientProvider(ExchangeRateApiProvider(rates_key))

    gecko_key = settings.coingecko_api_key
    if gecko_key.get_secret_value():
        by_kind[AssetKind.CRYPTO] = ResilientProvider(CoinGeckoProvider(gecko_key))

    # The configured order (DEC-25: ECB first, the commercial API for what the ECB lacks).
    fx_sources = tuple(available[n] for n in settings.fx_provider_order if n in available)
    if not fx_sources:
        return MarketProviders(by_kind, None, ())
    fx: MarketDataProvider = (
        fx_sources[0] if len(fx_sources) == 1 else FallbackChain(list(fx_sources))
    )
    return MarketProviders(by_kind, fx, fx_sources)
