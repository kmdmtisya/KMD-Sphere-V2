"""The instrument registry (P13-T02.2): the currency pairs WealthSphere knows and how each is
quoted. The universe is configuration, not code: the pairs live in `universe.json`, and the
`forex_universe` setting chooses which are active. Stored in `forex_instruments` (migration 0020)
so quotes and candles reference a known pair."""

import json
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.forex.instruments.models import ForexInstrument
from app.modules.forex.marketdata.types import DataType, check_instrument

REGISTRY_FILE = Path(__file__).with_name("universe.json")
LiquidityTier = Literal["major", "minor", "exotic"]
TIERS: tuple[LiquidityTier, ...] = ("major", "minor", "exotic")


@dataclass(frozen=True)
class InstrumentSpec:
    code: str
    pip_location: int  # a pip is 10 ** pip_location of the quote currency (-4: 0.0001)
    display_precision: int  # decimals a price is shown and simulated with
    liquidity_tier: LiquidityTier

    def __post_init__(self) -> None:
        check_instrument(self.code)
        if self.base == self.quote:
            raise ValueError(f"{self.code}: base and quote must differ")
        if not -6 <= self.pip_location <= 0:
            raise ValueError(f"{self.code}: pip_location must be between -6 and 0")
        if not -self.pip_location <= self.display_precision <= 8:
            raise ValueError(f"{self.code}: display_precision must show at least a whole pip")
        if self.liquidity_tier not in TIERS:
            raise ValueError(f"{self.code}: unknown liquidity tier")

    @property
    def base(self) -> str:
        return self.code[:3]

    @property
    def quote(self) -> str:
        return self.code[4:]

    @property
    def default_data_type(self) -> DataType:
        """Less liquid pairs are indicative unless the provider says otherwise (design 4.2)."""
        if self.liquidity_tier == "exotic":
            return DataType.INDICATIVE_RATE
        return DataType.TRADABLE_QUOTE


@dataclass(frozen=True)
class Registry:
    spec_version: int
    specs: tuple[InstrumentSpec, ...]

    @cached_property
    def by_code(self) -> dict[str, InstrumentSpec]:
        return {s.code: s for s in self.specs}

    def active(self, universe: list[str]) -> list[InstrumentSpec]:
        """The configured universe (every pair when it is empty). An unknown code is an error,
        not something to skip quietly."""
        if not universe:
            return list(self.specs)
        unknown = sorted(set(universe) - set(self.by_code))
        if unknown:
            raise ValueError(f"forex_universe names unknown instruments: {', '.join(unknown)}")
        return [s for s in self.specs if s.code in universe]


def load_registry(path: Path = REGISTRY_FILE) -> Registry:
    raw = json.loads(path.read_text(encoding="utf-8"))
    specs = tuple(InstrumentSpec(**item) for item in raw["instruments"])
    if len({s.code for s in specs}) != len(specs):
        raise ValueError("instrument codes must be unique")
    version = raw["spec_version"]
    if not isinstance(version, int) or version < 1:
        raise ValueError("spec_version must be a positive integer")
    return Registry(version, specs)


@dataclass(frozen=True)
class SyncReport:
    added: int
    changed: int
    active: int


async def sync(session: AsyncSession, registry: Registry, universe: list[str]) -> SyncReport:
    """Makes `forex_instruments` match the registry. Idempotent. A pair dropped from the file or
    the universe is deactivated, never deleted: stored quotes keep pointing at it."""
    active = {s.code for s in registry.active(universe)}
    rows = {r.code: r for r in (await session.execute(select(ForexInstrument))).scalars()}
    added = changed = 0
    for spec in registry.specs:
        values = {
            "base": spec.base,
            "quote": spec.quote,
            "pip_location": spec.pip_location,
            "display_precision": spec.display_precision,
            "liquidity_tier": spec.liquidity_tier,
            "default_data_type": spec.default_data_type.value,
        }
        row = rows.get(spec.code)
        if row is None:
            session.add(
                ForexInstrument(
                    code=spec.code,
                    spec_version=registry.spec_version,
                    is_active=spec.code in active,
                    **values,
                )
            )
            added += 1
            continue
        if any(getattr(row, k) != v for k, v in values.items()):
            for k, v in values.items():
                setattr(row, k, v)
            row.spec_version = registry.spec_version
            changed += 1
        row.is_active = spec.code in active
    for code, row in rows.items():
        if code not in registry.by_code:
            row.is_active = False
    await session.commit()
    return SyncReport(added, changed, len(active))


async def active_instruments(session: AsyncSession) -> list[ForexInstrument]:
    return list(
        (
            await session.execute(
                select(ForexInstrument)
                .where(ForexInstrument.is_active.is_(True))
                .order_by(ForexInstrument.code)
            )
        ).scalars()
    )
