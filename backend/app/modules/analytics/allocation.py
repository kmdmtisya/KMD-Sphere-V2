"""Allocation and concentration (P06-T04). Pure and deterministic (Decimal only, no I/O).
Methods: docs/design/allocation.md."""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal, localcontext
from enum import StrEnum

from app.core.money import percentages

ZERO = Decimal(0)
ONE = Decimal(1)
PRECISION = 50
TOP = (1, 3, 5)
CASH_CLASS = "cash"


class Dimension(StrEnum):
    ASSET_CLASS = "asset_class"
    CURRENCY = "currency"
    COUNTRY = "country"
    SECTOR = "sector"


@dataclass(frozen=True)
class Part:
    """A part of the portfolio's value, in its base currency: a position or a cash balance."""

    key: str  # asset id, or cash:<currency>
    value: Decimal
    asset_class: str
    currency: str
    country: str | None = None
    sector: str | None = None

    def classify(self, dimension: Dimension) -> str | None:
        return {
            Dimension.ASSET_CLASS: self.asset_class,
            Dimension.CURRENCY: self.currency,
            Dimension.COUNTRY: self.country,
            Dimension.SECTOR: self.sector,
        }[dimension]


def cash(currency: str, value: Decimal) -> Part:
    return Part(f"cash:{currency}", value, CASH_CLASS, currency)


@dataclass(frozen=True)
class Slice:
    key: str | None  # None: unclassified
    value: Decimal
    weight_percent: Decimal | None  # 2 decimals, adding up to 100.00; None when undefined
    parts: int


@dataclass(frozen=True)
class Allocation:
    dimension: Dimension
    total: Decimal
    slices: tuple[Slice, ...]
    hhi: Decimal | None  # concentration of the slices


@dataclass(frozen=True)
class Concentration:
    positions: int
    hhi: Decimal | None
    effective_positions: Decimal | None
    top: dict[int, Decimal | None]  # n -> share (fraction) held by the largest n
    largest: str | None


def allocate(parts: Iterable[Part], dimension: Dimension) -> Allocation:
    parts = list(parts)
    sums: dict[str | None, Decimal] = {}
    counts: dict[str | None, int] = {}
    with localcontext() as ctx:
        ctx.prec = PRECISION
        for p in parts:
            key = p.classify(dimension)
            sums[key] = sums.get(key, ZERO) + p.value
            counts[key] = counts.get(key, 0) + 1
        total = sum((p.value for p in parts), ZERO)
    keys = sorted(sums, key=lambda k: (-sums[k], k is None, k or ""))
    values = [sums[k] for k in keys]
    # A negative part (cash) makes every share meaningless, even inside a positive slice.
    measurable = _measurable([p.value for p in parts])
    weights = percentages(values) if measurable else None
    return Allocation(
        dimension=dimension,
        total=total,
        slices=tuple(
            Slice(k, sums[k], weights[i] if weights else None, counts[k])
            for i, k in enumerate(keys)
        ),
        hhi=herfindahl(values) if measurable else None,
    )


def concentration(parts: Iterable[Part]) -> Concentration:
    parts = sorted(parts, key=lambda p: (-p.value, p.key))
    values = [p.value for p in parts]
    if not _measurable(values):
        return Concentration(len(parts), None, None, dict.fromkeys(TOP), None)
    with localcontext() as ctx:
        ctx.prec = PRECISION
        total = sum(values, ZERO)
        hhi = _hhi(values, total)
        return Concentration(
            positions=len(parts),
            hhi=hhi,
            effective_positions=ONE / hhi,
            top={n: sum(values[:n], ZERO) / total for n in TOP},
            largest=parts[0].key,
        )


def herfindahl(values: Sequence[Decimal]) -> Decimal | None:
    """Sum of squared shares (fractions); None when the total is not positive or a value is
    negative."""
    if not _measurable(values):
        return None
    return _hhi(values, sum(values, ZERO))


def _hhi(values: Sequence[Decimal], total: Decimal) -> Decimal:
    with localcontext() as ctx:
        ctx.prec = PRECISION
        return sum(((v / total) ** 2 for v in values), ZERO)


def _measurable(values: Sequence[Decimal]) -> bool:
    return bool(values) and all(v >= 0 for v in values) and sum(values, ZERO) > 0
