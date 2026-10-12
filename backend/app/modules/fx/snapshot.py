"""Rate snapshots and the reporting-conversion engine (P11-T04).

A snapshot is the set of rates one view, report or AI answer uses: the latest stored rate of every
active currency against the pivot, frozen. Every conversion in that view goes through the same
snapshot, so a total always equals the sum of its converted parts.

- **Content-addressed and immutable.** The id is derived from the rates, so the same rates give
  the same snapshot (one row, however many requests), and a stored snapshot never changes
  (database triggers refuse UPDATE and DELETE). A report keeps its snapshot id.
- **Rates inside a snapshot.** The newest stored rate of every pair among the active currencies
  (within 7 days). A rate is the stored pair, else the opposite pair inverted, else the cross
  rate through the pivot (A->pivot->B, path stated); each states the stored rates it came from.
- **Conversion.** converted = round_half_up(amount x rate, decimal places of the target), once, at
  the end (ADR-0006). The places come from the `currencies` table. Original amounts are never
  touched: conversions are read-only views.
- **Status** (DEC-26) is computed per read from the clock, never frozen into the snapshot."""

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, localcontext
from typing import Any

from sqlalchemy import String, event, select, text
from sqlalchemy.dialects.postgresql import JSONB, distinct_on, insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, Mapper, mapped_column

from app.core.authz import ResourceNotFoundError
from app.core.errors import InvalidValueError
from app.core.money import round_half_up
from app.db.base import Base
from app.modules.fx.models import Currency
from app.modules.fx.status import RateStatus, StatusPolicy
from app.modules.market_data.fx import HISTORICAL_MAX_AGE, FxRateUnavailable
from app.modules.market_data.models import FxRate

PRECISION = 50
_NAMESPACE = uuid.UUID("6f1d1f4e-1a0b-4d3e-9a51-6e6f0d1c0a10")
_STATUS_ORDER = [RateStatus.CURRENT, RateStatus.CACHED, RateStatus.STALE]


class FxSnapshot(Base):
    __tablename__ = "fx_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    pivot: Mapped[str] = mapped_column(String(3))
    rates: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


class SnapshotImmutableError(RuntimeError):
    pass


@event.listens_for(FxSnapshot, "before_update")
def _refuse_update(_mapper: Mapper[Any], _connection: Any, _target: FxSnapshot) -> None:
    raise SnapshotImmutableError("fx snapshots are immutable")


@event.listens_for(FxSnapshot, "before_delete")
def _refuse_delete(_mapper: Mapper[Any], _connection: Any, _target: FxSnapshot) -> None:
    raise SnapshotImmutableError("fx snapshots are immutable")


class UnsupportedCurrency(InvalidValueError):
    """A currency that is not in the active `currencies` table (HTTP 422)."""


@dataclass(frozen=True)
class Leg:
    """One stored rate in a snapshot: 1 `base` = `rate` `quote`."""

    base: str
    quote: str
    rate: Decimal
    provider: str
    rate_type: str
    rate_timestamp: datetime
    retrieved_at: datetime


@dataclass(frozen=True)
class ResolvedRate:
    base: str
    quote: str
    rate: Decimal
    path: tuple[str, ...] | None
    legs: tuple[Leg, ...]

    @property
    def rate_timestamp(self) -> datetime | None:
        """As old as the oldest stored rate it used (None for the identity)."""
        return min((leg.rate_timestamp for leg in self.legs), default=None)

    @property
    def providers(self) -> list[str]:
        return list(dict.fromkeys(leg.provider for leg in self.legs))

    def status(self, policy: StatusPolicy, now: datetime) -> RateStatus:
        """The worst status of the stored rates it used."""
        statuses = [policy.status(leg.provider, leg.rate_timestamp, now) for leg in self.legs]
        return max(statuses, key=_STATUS_ORDER.index, default=RateStatus.CURRENT)


@dataclass(frozen=True)
class Snapshot:
    """Every stored pair among the active currencies, latest first, frozen. A rate is the
    stored pair, else the opposite pair inverted, else the cross rate through the pivot (the same
    order as the FX service)."""

    id: uuid.UUID
    pivot: str
    created_at: datetime
    legs: dict[tuple[str, str], Leg]

    def rate(self, base: str, quote: str) -> ResolvedRate:
        """1 base = rate quote, from this snapshot only. Raises FxRateUnavailable."""
        if base == quote:
            return ResolvedRate(base, quote, Decimal(1), None, ())
        with localcontext() as ctx:
            ctx.prec = PRECISION
            pair = self._pair(base, quote)
            if pair is not None:
                return ResolvedRate(base, quote, pair[0], None, (pair[1],))
            pivot = self.pivot
            first = self._pair(base, pivot) if base != pivot else None
            second = self._pair(pivot, quote) if quote != pivot else None
            if first is None or second is None:
                raise FxRateUnavailable(f"no {base}/{quote} rate in this snapshot")
            return ResolvedRate(
                base, quote, first[0] * second[0], (base, pivot, quote), (first[1], second[1])
            )

    def _pair(self, base: str, quote: str) -> tuple[Decimal, Leg] | None:
        """The stored pair, or the opposite pair inverted (direction checked by the key)."""
        direct = self.legs.get((base, quote))
        if direct is not None:
            return direct.rate, direct
        opposite = self.legs.get((quote, base))
        if opposite is not None:
            return Decimal(1) / opposite.rate, opposite
        return None


def convert(amount: Decimal, rate: Decimal, decimal_places: int) -> Decimal:
    """amount x rate at full precision, rounded half-up once to `decimal_places`."""
    with localcontext() as ctx:
        ctx.prec = PRECISION
        exact = amount * rate
    return round_half_up(exact, decimal_places)


def _canonical(legs: list[Leg]) -> list[dict[str, Any]]:
    return [
        {
            "base": leg.base,
            "quote": leg.quote,
            "rate": str(leg.rate),
            "provider": leg.provider,
            "rate_type": leg.rate_type,
            "rate_timestamp": leg.rate_timestamp.isoformat(),
            "retrieved_at": leg.retrieved_at.isoformat(),
        }
        for leg in sorted(legs, key=lambda x: (x.base, x.quote))
    ]


def _legs(rows: list[dict[str, Any]]) -> dict[tuple[str, str], Leg]:
    return {
        (r["base"], r["quote"]): Leg(
            r["base"],
            r["quote"],
            Decimal(r["rate"]),
            r["provider"],
            r["rate_type"],
            datetime.fromisoformat(r["rate_timestamp"]),
            datetime.fromisoformat(r["retrieved_at"]),
        )
        for r in rows
    }


class SnapshotService:
    def __init__(self, session: AsyncSession, pivot: str) -> None:
        self._session = session
        self._pivot = pivot

    async def currencies(self) -> dict[str, int]:
        """Active currency codes and their decimal places."""
        rows = await self._session.execute(
            select(Currency.code, Currency.decimal_places).where(Currency.is_active.is_(True))
        )
        return {str(row[0]): int(row[1]) for row in rows.all()}

    async def decimal_places(self, code: str) -> int:
        places = (await self.currencies()).get(code)
        if places is None:
            raise UnsupportedCurrency(f"{code} is not a supported currency")
        return places

    async def current(self) -> Snapshot:
        """The snapshot of the latest stored rates (stored once per distinct rate set): for every
        pair among the active currencies, the newest rate of the last 7 days (older rates are not
        used for conversion, as in the FX service)."""
        active = sorted(set(await self.currencies()) | {self._pivot})
        now = datetime.now(UTC)
        rows = await self._session.execute(
            select(FxRate)
            .where(
                FxRate.base_currency.in_(active),
                FxRate.quote_currency.in_(active),
                FxRate.rate_timestamp <= now,
                FxRate.rate_timestamp >= now - HISTORICAL_MAX_AGE,
            )
            .ext(distinct_on(FxRate.base_currency, FxRate.quote_currency))
            .order_by(
                FxRate.base_currency,
                FxRate.quote_currency,
                FxRate.rate_timestamp.desc(),
                FxRate.retrieved_at.desc(),
                FxRate.provider,
            )
        )
        legs = [
            Leg(
                r.base_currency,
                r.quote_currency,
                r.rate,
                r.provider,
                r.rate_type,
                r.rate_timestamp,
                r.retrieved_at,
            )
            for r in rows.scalars()
        ]
        canonical = _canonical(legs)
        digest = hashlib.sha256(
            json.dumps({"pivot": self._pivot, "rates": canonical}, sort_keys=True).encode()
        ).hexdigest()
        snapshot_id = uuid.uuid5(_NAMESPACE, digest)
        await self._session.execute(
            insert(FxSnapshot)
            .values(id=snapshot_id, pivot=self._pivot, rates=canonical)
            .on_conflict_do_nothing(index_elements=["id"])
        )
        await self._session.commit()
        return await self.get(snapshot_id)

    async def get(self, snapshot_id: uuid.UUID) -> Snapshot:
        row = await self._session.get(FxSnapshot, snapshot_id)
        if row is None:
            raise ResourceNotFoundError("fx snapshot")
        return Snapshot(row.id, row.pivot, row.created_at, _legs(row.rates))
