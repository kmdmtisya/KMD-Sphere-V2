"""Provider values are validated on construction (P08-T02.3)."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.modules.market_data.providers.errors import ProviderDataError
from app.modules.market_data.providers.models import (
    AssetKind,
    FxQuote,
    PricePoint,
    PriceQuote,
    Provenance,
)

NOW = datetime(2026, 10, 12, 12, tzinfo=UTC)


def prov(as_of: datetime = NOW - timedelta(minutes=5), retrieved: datetime = NOW) -> Provenance:
    return Provenance("fake", as_of, retrieved)


def quote(price: Decimal = Decimal("10.5"), **kw: object) -> PriceQuote:
    args: dict[str, object] = {
        "symbol": "DEMO-GEQ",
        "kind": AssetKind.ETF,
        "price": price,
        "currency": "USD",
        "provenance": prov(),
    }
    args.update(kw)
    return PriceQuote(**args)  # type: ignore[arg-type]


class TestProvenance:
    def test_age_and_staleness(self) -> None:
        p = prov()
        assert p.age(NOW) == timedelta(minutes=5)
        assert not p.is_stale(NOW, timedelta(minutes=5))
        assert p.is_stale(NOW, timedelta(minutes=4))

    def test_age_is_never_negative(self) -> None:
        assert prov().age(NOW - timedelta(hours=1)) == timedelta(0)

    def test_naive_timestamps_are_rejected(self) -> None:
        with pytest.raises(ProviderDataError):
            Provenance("p", datetime(2026, 1, 1), NOW)
        with pytest.raises(ProviderDataError):
            Provenance("p", NOW, datetime(2026, 1, 1))

    def test_a_value_from_the_future_is_rejected(self) -> None:
        with pytest.raises(ProviderDataError):
            Provenance("p", NOW + timedelta(seconds=1), NOW)

    def test_provider_name_is_required(self) -> None:
        with pytest.raises(ProviderDataError):
            Provenance("", NOW, NOW)


class TestPriceQuote:
    def test_valid(self) -> None:
        assert quote().price == Decimal("10.5")

    @pytest.mark.parametrize(
        "bad", [Decimal(0), Decimal("-1"), Decimal("NaN"), Decimal("Infinity")]
    )
    def test_bad_prices_are_rejected(self, bad: Decimal) -> None:
        with pytest.raises(ProviderDataError):
            quote(bad)

    def test_a_float_price_is_rejected(self) -> None:
        with pytest.raises(ProviderDataError):
            quote(10.5)  # type: ignore[arg-type]

    @pytest.mark.parametrize("bad", ["usd", "US", "USDD", "", "12$"])
    def test_bad_currency_is_rejected(self, bad: str) -> None:
        with pytest.raises(ProviderDataError):
            quote(currency=bad)

    @pytest.mark.parametrize("bad", ["", " ", "a b", "x" * 40, "-lead", "semi;colon"])
    def test_bad_symbol_is_rejected(self, bad: str) -> None:
        with pytest.raises(ProviderDataError):
            quote(symbol=bad)


class TestOthers:
    def test_price_point_rejects_a_non_positive_close(self) -> None:
        with pytest.raises(ProviderDataError):
            PricePoint("DEMO-GEQ", NOW.date(), Decimal(0), "USD", prov())

    def test_fx_needs_two_currencies_and_a_positive_rate(self) -> None:
        assert FxQuote("USD", "AED", Decimal("3.67"), prov()).rate == Decimal("3.67")
        with pytest.raises(ProviderDataError):
            FxQuote("USD", "USD", Decimal(1), prov())
        with pytest.raises(ProviderDataError):
            FxQuote("USD", "AED", Decimal(0), prov())
        with pytest.raises(ProviderDataError):
            FxQuote("usd", "AED", Decimal(1), prov())
