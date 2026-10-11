"""Contract every `MarketDataProvider` must satisfy (P08-T02.4).

Subclass `ProviderContract`, implement `make_provider` and name a known instrument; the adapters
(P08-T03) reuse it against recorded fixtures, so a vendor cannot break the guarantees the rest of
the platform relies on: provenance on every value, validated numbers, loud failure for unknown
symbols, history oldest-first with no filled gaps."""

from abc import ABC, abstractmethod
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from app.modules.market_data.providers.base import MarketDataProvider
from app.modules.market_data.providers.errors import SymbolNotFound, UnsupportedKind
from app.modules.market_data.providers.models import AssetKind


class ProviderContract(ABC):
    """Mix into a test class (not collected on its own: the name does not start with `Test`)."""

    kind: AssetKind
    symbol: str
    unknown_symbol: str = "NOPE-NOT-REAL"
    history_start: date
    history_end: date
    fx_pair: tuple[str, str] | None = None

    @abstractmethod
    def make_provider(self) -> MarketDataProvider: ...

    async def test_is_a_provider(self) -> None:
        p = self.make_provider()
        assert isinstance(p, MarketDataProvider)
        assert p.name
        assert self.kind in p.supported_kinds

    async def test_quote_is_validated_and_has_provenance(self) -> None:
        q = await self.make_provider().get_quote(self.symbol, self.kind)
        assert q.symbol == self.symbol
        assert isinstance(q.price, Decimal)
        assert q.price > 0
        assert len(q.currency) == 3
        prov = q.provenance
        assert prov.provider
        assert prov.as_of.tzinfo is not None
        assert prov.retrieved_at.tzinfo is not None
        assert prov.as_of <= prov.retrieved_at
        assert prov.retrieved_at <= datetime.now(UTC) + timedelta(minutes=1)

    async def test_unknown_symbol_raises(self) -> None:
        with pytest.raises(SymbolNotFound):
            await self.make_provider().get_quote(self.unknown_symbol, self.kind)

    async def test_history_is_ascending_in_range_and_has_provenance(self) -> None:
        points = await self.make_provider().get_history(
            self.symbol, self.kind, self.history_start, self.history_end
        )
        assert points, "the contract's range must contain at least one trading day"
        days = [pt.day for pt in points]
        assert days == sorted(days)
        assert len(set(days)) == len(days), "one close per day"
        assert all(self.history_start <= d <= self.history_end for d in days)
        for pt in points:
            assert pt.close > 0
            assert pt.provenance.provider
            assert pt.provenance.as_of.tzinfo is not None

    async def test_history_unknown_symbol_raises(self) -> None:
        with pytest.raises(SymbolNotFound):
            await self.make_provider().get_history(
                self.unknown_symbol, self.kind, self.history_start, self.history_end
            )

    async def test_unsupported_kind_raises(self) -> None:
        p = self.make_provider()
        missing = [k for k in AssetKind if k not in p.supported_kinds]
        if not missing:
            pytest.skip("this provider serves every kind")
        with pytest.raises(UnsupportedKind):
            await p.get_quote(self.symbol, missing[0])

    async def test_fx_rate_is_positive_and_has_provenance(self) -> None:
        if self.fx_pair is None:
            pytest.skip("this provider has no FX")
        base, quote = self.fx_pair
        r = await self.make_provider().get_fx_rate(base, quote)
        assert (r.base, r.quote) == (base, quote)
        assert r.rate > 0
        assert r.provenance.provider
        assert r.provenance.as_of <= r.provenance.retrieved_at
