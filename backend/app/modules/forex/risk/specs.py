"""Contract specifications (P13-T07.1, DEC-24): a reviewed, versioned table (migration 0023).

- The specifications live in `contract_specs.json` with a version number and are loaded into
  `forex_contract_specs` by `sync`. A row is never edited in place: a new version supersedes the
  old one, so every calculation can name the specification version it used.
- Until a reviewer records a review (`mark_reviewed`), a version is `unreviewed` and every risk
  calculation says it uses unreviewed defaults.
- `compare_with_provider` checks a specification against a provider's published values when one
  exists. A mismatch is reported, never silently corrected."""

import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    select,
    text,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

SPEC_FILE = Path(__file__).with_name("contract_specs.json")
FIELDS = (
    "contract_size",
    "lot_step",
    "min_lots",
    "max_lots",
    "margin_rate",
    "commission_per_lot_side",
    "slippage_pips",
)


class ForexContractSpec(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "forex_contract_specs"
    __table_args__ = (
        UniqueConstraint(
            "instrument", "version", name="uq_forex_contract_specs_instrument_version"
        ),
        CheckConstraint(
            "contract_size > 0 AND lot_step > 0 AND min_lots > 0 AND max_lots >= min_lots",
            name="sizes",
        ),
        CheckConstraint("margin_rate > 0 AND margin_rate <= 1", name="margin_rate"),
        CheckConstraint("commission_per_lot_side >= 0 AND slippage_pips >= 0", name="costs"),
        CheckConstraint("review_status IN ('unreviewed', 'reviewed')", name="review_status"),
        CheckConstraint("status IN ('active', 'superseded')", name="status"),
        # One active version per pair.
        Index(
            "uq_forex_contract_specs_active",
            "instrument",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )

    instrument: Mapped[str] = mapped_column(
        String(7), ForeignKey("forex_instruments.code", ondelete="RESTRICT")
    )
    version: Mapped[int] = mapped_column(Integer)
    contract_size: Mapped[Decimal] = mapped_column(Numeric(20, 4))  # base units per standard lot
    lot_step: Mapped[Decimal] = mapped_column(Numeric(10, 4))  # in lots
    min_lots: Mapped[Decimal] = mapped_column(Numeric(10, 4))
    max_lots: Mapped[Decimal] = mapped_column(Numeric(10, 4))
    margin_rate: Mapped[Decimal] = mapped_column(Numeric(8, 6))  # initial margin / notional
    commission_per_lot_side: Mapped[Decimal] = mapped_column(Numeric(18, 8))  # quote currency
    slippage_pips: Mapped[Decimal] = mapped_column(Numeric(10, 2))  # assumption per fill
    review_status: Mapped[str] = mapped_column(String(16))
    reviewed_by: Mapped[str | None] = mapped_column(String(200))
    reviewed_at: Mapped[datetime | None] = mapped_column()
    status: Mapped[str] = mapped_column(String(16))


@dataclass(frozen=True)
class SpecValues:
    contract_size: Decimal
    lot_step: Decimal
    min_lots: Decimal
    max_lots: Decimal
    margin_rate: Decimal
    commission_per_lot_side: Decimal
    slippage_pips: Decimal

    def __post_init__(self) -> None:
        if (
            self.contract_size <= 0
            or self.lot_step <= 0
            or self.min_lots <= 0
            or self.max_lots < self.min_lots
        ):
            raise ValueError("sizes must be positive and max_lots at least min_lots")
        if not Decimal(0) < self.margin_rate <= 1:
            raise ValueError("margin_rate must be in (0, 1]")
        if self.commission_per_lot_side < 0 or self.slippage_pips < 0:
            raise ValueError("costs must not be negative")


def load_file(path: Path = SPEC_FILE) -> tuple[int, str, dict[str, SpecValues]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    specs = {
        item["code"]: SpecValues(**{k: Decimal(item[k]) for k in FIELDS})
        for item in raw["instruments"]
    }
    if len(specs) != len(raw["instruments"]):
        raise ValueError("instrument codes must be unique")
    return int(raw["version"]), str(raw["review_status"]), specs


def values_of(row: ForexContractSpec) -> SpecValues:
    return SpecValues(**{k: getattr(row, k) for k in FIELDS})


async def sync(session: AsyncSession, path: Path = SPEC_FILE) -> dict[str, int]:
    """Loads the file's version. A new version supersedes the active one; the same version with
    different values is refused (a change needs a new version). Idempotent."""
    version, review, specs = load_file(path)
    added = 0
    for code, values in specs.items():
        rows = list(
            (
                await session.execute(
                    select(ForexContractSpec).where(ForexContractSpec.instrument == code)
                )
            ).scalars()
        )
        same = next((r for r in rows if r.version == version), None)
        if same is not None:
            if values_of(same) != values:
                raise ValueError(
                    f"{code}: version {version} already exists with other values; bump the version"
                )
            continue
        for r in rows:
            if r.status == "active":
                r.status = "superseded"
        await session.flush()  # before the insert: one active version per pair
        session.add(
            ForexContractSpec(
                instrument=code,
                version=version,
                review_status="reviewed" if review == "reviewed" else "unreviewed",
                status="active",
                **{k: getattr(values, k) for k in FIELDS},
            )
        )
        added += 1
    await session.commit()
    return {"version": version, "added": added}


async def active_spec(session: AsyncSession, instrument: str) -> ForexContractSpec | None:
    return await session.scalar(
        select(ForexContractSpec).where(
            ForexContractSpec.instrument == instrument, ForexContractSpec.status == "active"
        )
    )


async def mark_reviewed(
    session: AsyncSession, instrument: str, version: int, reviewer: str, at: datetime
) -> ForexContractSpec:
    row = await session.scalar(
        select(ForexContractSpec).where(
            ForexContractSpec.instrument == instrument, ForexContractSpec.version == version
        )
    )
    if row is None:
        raise ValueError("no such specification version")
    if not reviewer.strip():
        raise ValueError("a reviewer is required")
    row.review_status, row.reviewed_by, row.reviewed_at = "reviewed", reviewer.strip()[:200], at
    await session.commit()
    return row


def compare_with_provider(spec: SpecValues, provider: dict[str, Decimal]) -> list[str]:
    """Differences between our specification and a provider's published values (only the fields
    the provider publishes). Reported for review; never applied automatically."""
    return [
        f"{k}: ours {getattr(spec, k)}, provider {v}"
        for k, v in sorted(provider.items())
        if k in FIELDS and getattr(spec, k) != v
    ]
