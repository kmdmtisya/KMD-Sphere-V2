"""Price and FX ingestion (P08-T05).

Fetch from a provider (through the interface only), validate against what we know, and store with
provenance. Everything is idempotent: a row is identified by what it is (asset or pair, provider,
type, `as_of`), inserted with `ON CONFLICT DO NOTHING`, so running a job or a backfill again, or
two overlapping runs, never duplicates data.

Safety rules:
- A price is stored only in the asset's own currency. A provider that answers in another currency
  is a failure, not a conversion (we never guess an FX rate to fix a price).
- A failure for one asset or pair never stops the others; it is returned in the result.
- Nothing is invented: if the provider has no value, nothing is stored."""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.assets.models import Asset, AssetClass
from app.modules.market_data.freshness import is_stale, kind_for_asset_class
from app.modules.market_data.models import FxRate, MarketPrice
from app.modules.market_data.providers.base import MarketDataProvider
from app.modules.market_data.providers.errors import ProviderDataError, ProviderError
from app.modules.market_data.providers.models import AssetKind
from app.modules.portfolio.models import Portfolio

_MESSAGE_LIMIT = 200


@dataclass(frozen=True)
class IngestFailure:
    subject: str
    error_type: str
    message: str


@dataclass
class IngestResult:
    stored: int = 0
    duplicates: int = 0
    failures: list[IngestFailure] = field(default_factory=list)

    def merge(self, other: "IngestResult") -> None:
        self.stored += other.stored
        self.duplicates += other.duplicates
        self.failures.extend(other.failures)

    @property
    def attempted_all_and_failed(self) -> bool:
        """Nothing was stored or already known, and something failed: a likely outage."""
        return self.stored == 0 and self.duplicates == 0 and bool(self.failures)


@dataclass(frozen=True)
class StoredPrice:
    asset_id: uuid.UUID
    price: Decimal
    currency: str
    provider: str
    as_of: datetime
    retrieved_at: datetime
    stale: bool


def _failure(subject: str, error: Exception) -> IngestFailure:
    return IngestFailure(subject, type(error).__name__, str(error)[:_MESSAGE_LIMIT])


async def market_assets(session: AsyncSession) -> list[tuple[Asset, AssetKind]]:
    """Global, active assets valued from prices that have a symbol and a provider kind."""
    rows = await session.execute(
        select(Asset, AssetClass.code)
        .join(AssetClass, Asset.asset_class_id == AssetClass.id)
        .where(
            AssetClass.valuation_mode == "market",
            Asset.is_active.is_(True),
            Asset.owner_user_id.is_(None),
            Asset.symbol.is_not(None),
        )
        .order_by(Asset.symbol)
    )
    result: list[tuple[Asset, AssetKind]] = []
    for asset, code in rows.all():
        kind = kind_for_asset_class(code)
        if kind is not None:
            result.append((asset, kind))
    return result


async def _store_prices(session: AsyncSession, values: list[dict[str, object]]) -> IngestResult:
    if not values:
        return IngestResult()
    stmt = (
        insert(MarketPrice)
        .values(values)
        .on_conflict_do_nothing(constraint="uq_market_prices_asset_provider_type_as_of")
        .returning(MarketPrice.id)
    )
    stored = len((await session.execute(stmt)).all())
    await session.commit()
    return IngestResult(stored=stored, duplicates=len(values) - stored)


def _check_currency(asset: Asset, currency: str) -> None:
    if currency != asset.currency:
        raise ProviderDataError(
            f"provider priced {asset.symbol} in {currency}, the asset is in {asset.currency}"
        )


async def ingest_quote(
    session: AsyncSession, provider: MarketDataProvider, asset: Asset, kind: AssetKind
) -> IngestResult:
    assert asset.symbol is not None  # noqa: S101 (market_assets only returns assets with one)
    try:
        quote = await provider.get_quote(asset.symbol, kind)
        _check_currency(asset, quote.currency)
    except ProviderError as error:
        return IngestResult(failures=[_failure(asset.symbol, error)])
    return await _store_prices(
        session,
        [
            {
                "asset_id": asset.id,
                "price": quote.price,
                "currency": quote.currency,
                "price_type": "quote",
                "provider": quote.provenance.provider,
                "as_of": quote.provenance.as_of,
                "retrieved_at": quote.provenance.retrieved_at,
            }
        ],
    )


async def ingest_quotes(
    session: AsyncSession,
    providers: dict[AssetKind, MarketDataProvider],
) -> IngestResult:
    """The latest quote of every market-valued asset whose kind has a provider."""
    total = IngestResult()
    for asset, kind in await market_assets(session):
        provider = providers.get(kind)
        if provider is None:
            continue
        total.merge(await ingest_quote(session, provider, asset, kind))
    return total


async def backfill_prices(
    session: AsyncSession,
    provider: MarketDataProvider,
    asset: Asset,
    kind: AssetKind,
    start: date,
    end: date,
) -> IngestResult:
    """Daily closes from `start` to `end`. Safe to run again over the same or an overlapping
    range."""
    assert asset.symbol is not None  # noqa: S101
    try:
        points = await provider.get_history(asset.symbol, kind, start, end)
        for point in points:
            _check_currency(asset, point.currency)
    except ProviderError as error:
        return IngestResult(failures=[_failure(asset.symbol, error)])
    return await _store_prices(
        session,
        [
            {
                "asset_id": asset.id,
                "price": p.close,
                "currency": p.currency,
                "price_type": "close",
                "provider": p.provenance.provider,
                "as_of": p.provenance.as_of,
                "retrieved_at": p.provenance.retrieved_at,
            }
            for p in points
        ],
    )


async def _store_fx(session: AsyncSession, values: list[dict[str, object]]) -> IngestResult:
    if not values:
        return IngestResult()
    stmt = (
        insert(FxRate)
        .values(values)
        .on_conflict_do_nothing(constraint="uq_fx_rates_pair_provider_timestamp")
        .returning(FxRate.id)
    )
    stored = len((await session.execute(stmt)).all())
    await session.commit()
    return IngestResult(stored=stored, duplicates=len(values) - stored)


async def ingest_fx(
    session: AsyncSession, provider: MarketDataProvider, pairs: list[tuple[str, str]]
) -> IngestResult:
    """The latest rate of each (base, quote) pair. A failing pair does not stop the others."""
    total = IngestResult()
    for base, quote in pairs:
        try:
            rate = await provider.get_fx_rate(base, quote)
        except ProviderError as error:
            total.failures.append(_failure(f"{base}/{quote}", error))
            continue
        total.merge(
            await _store_fx(
                session,
                [
                    {
                        "base_currency": rate.base,
                        "quote_currency": rate.quote,
                        "rate": rate.rate,
                        "provider": rate.provenance.provider,
                        "rate_timestamp": rate.provenance.as_of,
                        "retrieved_at": rate.provenance.retrieved_at,
                        "rate_type": rate.rate_type,
                        "rate_path": list(rate.path) if rate.path else None,
                    }
                ],
            )
        )
    return total


async def backfill_fx(
    session: AsyncSession,
    provider: MarketDataProvider,
    base: str,
    quote: str,
    start: date,
    end: date,
) -> IngestResult:
    try:
        rates = await provider.get_fx_history(base, quote, start, end)
    except ProviderError as error:
        return IngestResult(failures=[_failure(f"{base}/{quote}", error)])
    return await _store_fx(
        session,
        [
            {
                "base_currency": r.base,
                "quote_currency": r.quote,
                "rate": r.rate,
                "provider": r.provenance.provider,
                "rate_timestamp": r.provenance.as_of,
                "retrieved_at": r.provenance.retrieved_at,
                "rate_type": r.rate_type,
                "rate_path": list(r.path) if r.path else None,
            }
            for r in rates
        ],
    )


async def latest_price(
    session: AsyncSession, asset_id: uuid.UUID, kind: AssetKind, now: datetime | None = None
) -> StoredPrice | None:
    """The most recent stored price of an asset, flagged stale when it is older than its kind's
    freshness window. None when nothing is stored (the caller falls back to manual valuations)."""
    moment = now or datetime.now(UTC)
    row = (
        await session.execute(
            select(MarketPrice)
            .where(MarketPrice.asset_id == asset_id, MarketPrice.as_of <= moment)
            .order_by(
                MarketPrice.as_of.desc(), MarketPrice.retrieved_at.desc(), MarketPrice.provider
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    return StoredPrice(
        asset_id=row.asset_id,
        price=row.price,
        currency=row.currency,
        provider=row.provider,
        as_of=row.as_of,
        retrieved_at=row.retrieved_at,
        stale=is_stale(row.as_of, moment, kind),
    )


async def fx_pairs_needed(session: AsyncSession) -> list[tuple[str, str]]:
    """(currency, portfolio base currency) for every currency in use that differs from a base.

    Currencies in use are those of the assets and of the portfolios themselves. This is what
    valuing a holding in its portfolio's currency needs; the reporting-currency pairs of P11
    extend it."""
    asset_currencies = {
        c for (c,) in (await session.execute(select(Asset.currency).distinct())).all()
    }
    bases = {
        b
        for (b,) in (
            await session.execute(
                select(Portfolio.base_currency).where(Portfolio.archived_at.is_(None)).distinct()
            )
        ).all()
    }
    return sorted((c, b) for b in bases for c in asset_currencies | bases if c != b)
