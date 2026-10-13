"""Loading the investment universe (P12-T02.2).

A source lists instruments; `ingest` makes each one a public catalogue asset (no owner, referenced
by source and symbol) with its universe attributes. It is idempotent: running it again changes
nothing, and instruments a source no longer lists are deactivated, never deleted (assets may be
referenced by portfolios, prices or research).

Only the synthetic DEMO source exists today (approved for P12: no licensed universe yet). It is
loaded only when market data runs on the fake provider, so fictional symbols never reach a real
provider; with real market data the job deactivates any DEMO instruments instead."""

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.assets.catalogue import INITIAL_CLASSES, validate_metadata
from app.modules.assets.liquidity import LIQUIDITY_BY_CLASS, Liquidity
from app.modules.assets.models import Asset, AssetClass, AssetMetadata
from app.modules.universe.models import UniverseInstrument

DEMO_FILE = Path(__file__).with_name("demo_universe.json")
DEMO_SOURCE = "demo"
_CLASSES = {c.code: c for c in INITIAL_CLASSES}


@dataclass(frozen=True)
class UniverseEntry:
    symbol: str
    name: str
    asset_class: str
    currency: str
    risk_level: int
    jurisdictions: tuple[str, ...]
    country: str | None = None
    sector: str | None = None
    minimum_investment: Decimal | None = None
    # Class metadata (for example a fund's expense_ratio as a decimal string); keys the class
    # does not define are dropped.
    metadata: tuple[tuple[str, str], ...] = ()


class UniverseSource(Protocol):
    name: str
    is_demo: bool
    licence_status: str

    def load(self) -> tuple[datetime, Sequence[UniverseEntry]]:
        """The instruments and the time the list applies to."""
        ...


class DemoUniverseSource:
    """The synthetic, DEMO-labelled universe in demo_universe.json."""

    name = DEMO_SOURCE
    is_demo = True
    licence_status = "demo"

    def __init__(self, path: Path = DEMO_FILE) -> None:
        self._path = path

    def load(self) -> tuple[datetime, Sequence[UniverseEntry]]:
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        entries = [
            UniverseEntry(
                symbol=i["symbol"],
                name=i["name"],
                asset_class=i["asset_class"],
                currency=i["currency"],
                risk_level=int(i["risk_level"]),
                jurisdictions=tuple(i["jurisdictions"]),
                country=i.get("country"),
                sector=i.get("sector"),
                minimum_investment=(
                    Decimal(i["minimum_investment"]) if i.get("minimum_investment") else None
                ),
                metadata=tuple(sorted((i.get("metadata") or {}).items())),
            )
            for i in raw["instruments"]
        ]
        return datetime.fromisoformat(raw["data_as_of"]), entries


@dataclass
class IngestReport:
    source: str
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    deactivated: int = 0
    skipped: list[str] = field(default_factory=list)  # symbols that could not be loaded, with why


def _universe_values(
    source: UniverseSource, entry: UniverseEntry, as_of: datetime
) -> dict[str, object]:
    return {
        "source": source.name,
        "is_demo": source.is_demo,
        "licence_status": source.licence_status,
        "risk_level": entry.risk_level,
        "liquidity": LIQUIDITY_BY_CLASS.get(entry.asset_class, Liquidity.UNKNOWN).value,
        "jurisdictions": sorted(entry.jurisdictions),
        "minimum_investment": entry.minimum_investment,
        "data_as_of": as_of,
        "is_active": True,
    }


async def _store_metadata(
    session: AsyncSession, asset: Asset, entry: UniverseEntry, source: str
) -> bool:
    """Writes the entry's metadata the asset class defines; True when anything changed."""
    schema = _CLASSES[entry.asset_class].metadata_schema
    # A listing has no holding-specific fields (a deposit's maturity date): none is required here,
    # but every value given is checked like any other metadata.
    relaxed = {"fields": {k: f | {"required": False} for k, f in schema["fields"].items()}}
    wanted = dict(entry.metadata) | ({"sector": entry.sector} if entry.sector else {})
    values = validate_metadata(relaxed, {k: v for k, v in wanted.items() if k in relaxed["fields"]})
    stored = {
        m.key: m
        for m in (
            await session.execute(select(AssetMetadata).where(AssetMetadata.asset_id == asset.id))
        ).scalars()
    }
    changed = False
    for key, value in values.items():
        row = stored.get(key)
        if row is None:
            session.add(AssetMetadata(asset_id=asset.id, key=key, value=value, source=source))
            changed = True
        elif row.value != value:
            row.value = value
            changed = True
    return changed


async def ingest(session: AsyncSession, source: UniverseSource) -> IngestReport:
    as_of, entries = source.load()
    report = IngestReport(source.name)
    classes = {c.code: c for c in (await session.execute(select(AssetClass))).scalars()}
    existing = {
        a.external_provider_id: (a, u)
        for a, u in (
            await session.execute(
                select(Asset, UniverseInstrument)
                .outerjoin(UniverseInstrument, UniverseInstrument.asset_id == Asset.id)
                .where(Asset.owner_user_id.is_(None), Asset.external_provider == source.name)
            )
        ).all()
    }
    listed: set[str] = set()
    for entry in entries:
        if (
            entry.asset_class not in _CLASSES
            or entry.asset_class not in classes
            or not (1 <= entry.risk_level <= 5)
        ):
            report.skipped.append(f"{entry.symbol}: unknown class or risk level")
            continue
        listed.add(entry.symbol)
        values = _universe_values(source, entry, as_of)
        asset, row = existing.get(entry.symbol, (None, None))
        if asset is None:
            asset = Asset(
                asset_class_id=classes[entry.asset_class].id,
                owner_user_id=None,
                symbol=entry.symbol,
                name=entry.name,
                currency=entry.currency,
                country=entry.country,
                external_provider=source.name,
                external_provider_id=entry.symbol,
            )
            session.add(asset)
            await session.flush()
        elif asset.currency != entry.currency:
            report.skipped.append(f"{entry.symbol}: currency changed, not updated")
            continue
        changed = await _store_metadata(session, asset, entry, source.name)
        for attr, value in (("name", entry.name), ("country", entry.country), ("is_active", True)):
            if getattr(asset, attr) != value:
                setattr(asset, attr, value)
                changed = True
        if row is None:
            session.add(UniverseInstrument(asset_id=asset.id, **values))
            report.created += 1
            continue
        for attr, new in values.items():
            if getattr(row, attr) != new:
                setattr(row, attr, new)
                changed = True
        if changed:
            report.updated += 1
        else:
            report.unchanged += 1
    for symbol, (asset, row) in existing.items():
        if symbol not in listed and row is not None and row.is_active:
            row.is_active = False
            asset.is_active = False
            report.deactivated += 1
    await session.commit()
    return report


async def deactivate_source(session: AsyncSession, source: str) -> int:
    """Takes a source's instruments out of the universe (and out of price ingestion)."""
    rows = (
        await session.execute(
            select(Asset, UniverseInstrument)
            .join(UniverseInstrument, UniverseInstrument.asset_id == Asset.id)
            .where(UniverseInstrument.source == source, UniverseInstrument.is_active.is_(True))
        )
    ).all()
    for asset, row in rows:
        row.is_active = False
        asset.is_active = False
    await session.commit()
    return len(rows)
