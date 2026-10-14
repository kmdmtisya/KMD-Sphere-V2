"""Paper fills and triggers (P13-T09.2, T09.3, design section 11). Pure and Decimal-only.
PAPER TRADING: nothing here reaches a broker.

**Fills are at the feed's bid or ask, never the mid,** with the contract specification's slippage
against the trader on every market fill, and commission per lot per side:
- a market buy (opening a long, or closing a short) fills at ask + slippage;
- a market sell (opening a short, or closing a long) fills at bid - slippage;
- a limit order fills at its limit price once the quote reaches it (ask <= limit to buy, bid >=
  limit to sell), with no slippage;
- a stop is a market order: once the closing side of the quote reaches the stop (bid <= stop for
  a long, ask >= stop for a short) it fills at that quote with slippage, so a gap fills beyond the
  stop;
- a target is a limit order: it fills at the target price once the closing side reaches it.
Quotes are taken strictly in time order. When one quote reaches both the stop and the target the
stop is taken (it cannot happen with a valid stop and target, and is the conservative order).

**Money.** P/L is earned in the quote currency and converted into the account currency at the
rate of the closing quote's time (risk.conversion, from stored quotes):
    realised = side x units x (exit - entry) x rate_exit - entry commission - exit commission
Margin = units x entry x rate_entry x margin rate. Account amounts are kept to 4 places and shown
in the currency's minor units."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal

from app.modules.forex.risk.specs import SpecValues

D = Decimal
Side = Literal["long", "short"]
ExitReason = Literal["stop", "target", "manual"]


@dataclass(frozen=True)
class Tick:
    at: datetime
    bid: Decimal
    ask: Decimal
    data_type: str = "simulated"

    @property
    def mid(self) -> Decimal:
        return (self.bid + self.ask) / 2


def sign(side: Side) -> Decimal:
    return D(1) if side == "long" else D(-1)


def slippage(spec: SpecValues, pip_location: int) -> Decimal:
    return spec.slippage_pips * D(1).scaleb(pip_location)


def market_entry(side: Side, tick: Tick, slip: Decimal) -> Decimal:
    return tick.ask + slip if side == "long" else tick.bid - slip


def market_exit(side: Side, tick: Tick, slip: Decimal) -> Decimal:
    return tick.bid - slip if side == "long" else tick.ask + slip


def closing_price(side: Side, tick: Tick) -> Decimal:
    """The side of the quote a position closes on (marking, before slippage)."""
    return tick.bid if side == "long" else tick.ask


def units_for(lots: Decimal, spec: SpecValues) -> Decimal:
    """Lots to units; the lots must be a multiple of the lot step within the size limits."""
    if lots <= 0 or lots % spec.lot_step != 0:
        raise ValueError(f"lots must be a positive multiple of {spec.lot_step}")
    if not spec.min_lots <= lots <= spec.max_lots:
        raise ValueError(f"lots must be from {spec.min_lots} to {spec.max_lots}")
    return lots * spec.contract_size


def commission(units: Decimal, spec: SpecValues) -> Decimal:
    """Per side, in the quote currency."""
    return units / spec.contract_size * spec.commission_per_lot_side


def check_levels(side: Side, reference: Decimal, stop: Decimal, target: Decimal | None) -> None:
    """The stop on the losing side of the reference price, the target on the winning side."""
    if side == "long" and not stop < reference:
        raise ValueError("for a long position the stop must be below the entry price")
    if side == "short" and not stop > reference:
        raise ValueError("for a short position the stop must be above the entry price")
    if target is not None and (
        (side == "long" and not target > reference) or (side == "short" and not target < reference)
    ):
        raise ValueError("the target must be on the profit side of the entry price")


def limit_fill(side: Side, limit: Decimal, ticks: Iterable[Tick]) -> Tick | None:
    """The first quote at which a pending limit order fills."""
    for t in ticks:
        if (side == "long" and t.ask <= limit) or (side == "short" and t.bid >= limit):
            return t
    return None


@dataclass(frozen=True)
class Exit:
    tick: Tick
    price: Decimal
    reason: ExitReason


def exit_for(
    side: Side, stop: Decimal, target: Decimal | None, ticks: Iterable[Tick], slip: Decimal
) -> Exit | None:
    """The first quote that triggers the stop or the target, and the fill."""
    for t in ticks:
        close = closing_price(side, t)
        if (side == "long" and close <= stop) or (side == "short" and close >= stop):
            return Exit(t, market_exit(side, t, slip), "stop")
        if target is not None and (
            (side == "long" and close >= target) or (side == "short" and close <= target)
        ):
            return Exit(t, target, "target")
    return None


def pnl_quote(side: Side, units: Decimal, entry: Decimal, exit_: Decimal) -> Decimal:
    """Gross P/L in the quote currency, before commission."""
    return sign(side) * units * (exit_ - entry)


def spread_and_slippage(units: Decimal, fill: Decimal, mid: Decimal) -> Decimal:
    """What a fill paid against the mid, in the quote currency."""
    return units * abs(fill - mid)
