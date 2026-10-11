"""Which assets get prices from which kind of provider, and when a price is stale (P08-T05).

Staleness is a flag on a stored price, never a reason to hide it or to invent a newer one: a
holding valued from a stale price shows the price's `as_of` and the flag (P08-T06). The windows
are provisional until DEC-26 (refresh cadence and staleness, P11-T01)."""

from datetime import datetime, timedelta

from app.modules.market_data.providers.models import AssetKind

# Asset class code (assets.asset_classes) -> the kind of provider that serves it. A class that is
# valued from prices but has no entry here (bonds, commodities) has no automatic provider yet and
# keeps using manual valuations.
KIND_BY_ASSET_CLASS: dict[str, AssetKind] = {
    "stock": AssetKind.EQUITY,
    "reit": AssetKind.EQUITY,
    "etf": AssetKind.ETF,
    "mutual_fund": AssetKind.ETF,
    "cryptocurrency": AssetKind.CRYPTO,
}

# How old a quote may be and still count as fresh. Exchanges close for weekends and holidays, so
# listed assets get a longer window than crypto, which trades every day.
FRESH_FOR: dict[AssetKind, timedelta] = {
    AssetKind.EQUITY: timedelta(days=4),
    AssetKind.ETF: timedelta(days=4),
    AssetKind.BOND: timedelta(days=4),
    AssetKind.INDEX: timedelta(days=4),
    AssetKind.CRYPTO: timedelta(hours=6),
}


def kind_for_asset_class(code: str) -> AssetKind | None:
    return KIND_BY_ASSET_CLASS.get(code)


def is_stale(as_of: datetime, now: datetime, kind: AssetKind) -> bool:
    """True when a price valid at `as_of` is older than its kind's freshness window at `now`."""
    return now - as_of > FRESH_FOR[kind]
