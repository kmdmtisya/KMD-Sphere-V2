"""Strategies and the look-ahead controls (P13-T08.1, T08.7).

A strategy sees only closed bars: at bar i it is given the bars up to and including i (the last
`window` of them) and may return a decision. The engine fills a decision at the **next** bar's
open, never at the bar the decision was made on.

The rule strategy uses the live setup rules (P13-T06) with the live window (200 bars), so a
backtest tests what the Opportunity Ranking shows.

`leakage_audit` catches a strategy that reads the future through any channel: the decisions
made before a cut must not change when every bar after the cut is altered (mirrored, and
stretched). A strategy built
from the series (a factory) is rebuilt on the altered series, so one that peeks through a
closure fails the audit."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, Protocol

from app.modules.forex.signals import setups as su

Side = Literal["long", "short"]
WINDOW = 200  # bars a decision sees: the live ranking's window (signals.service.BARS)


@dataclass(frozen=True)
class Decision:
    side: Side
    stop: Decimal  # price level
    target: Decimal  # price level
    rule: str


class Strategy(Protocol):
    def decide(self, history: su.Bars) -> Decision | None: ...


def history(bars: su.Bars, i: int, window: int = WINDOW) -> su.Bars:
    """The closed bars a decision at bar i may see: copies, so nothing later is reachable."""
    lo = max(0, i + 1 - window)
    return su.Bars(
        list(bars.ts[lo : i + 1]),
        list(bars.open[lo : i + 1]),
        list(bars.high[lo : i + 1]),
        list(bars.low[lo : i + 1]),
        list(bars.close[lo : i + 1]),
    )


def from_setup(s: su.Setup) -> Decision:
    return Decision("long" if s.direction == "bullish" else "short", s.stop, s.target, s.rule)


@dataclass(frozen=True)
class RuleStrategy:
    rule: str

    def decide(self, history: su.Bars) -> Decision | None:
        if len(history) < su.MIN_BARS:
            return None
        found = next((s for s in su.detect(su.context(history)) if s.rule == self.rule), None)
        return from_setup(found) if found is not None else None


def setups_by_bar(
    bars: su.Bars, start: int, end: int, window: int = WINDOW
) -> list[list[su.Setup]]:
    """Every setup on every bar in [start, end), computed once and shared by all six rules.
    Entry i holds the setups of bar i (empty before there are enough bars)."""
    out: list[list[su.Setup]] = [[] for _ in range(len(bars))]
    for i in range(max(start, su.MIN_BARS - 1), min(end, len(bars))):
        out[i] = su.detect(su.context(history(bars, i, window)))
    return out


def rule_decisions(by_bar: Sequence[Sequence[su.Setup]], rule: str) -> list[Decision | None]:
    return [next((from_setup(s) for s in setups if s.rule == rule), None) for setups in by_bar]


def decisions(
    strategy: Strategy, bars: su.Bars, start: int, end: int, window: int = WINDOW
) -> list[Decision | None]:
    out: list[Decision | None] = [None] * len(bars)
    for i in range(start, min(end, len(bars))):
        out[i] = strategy.decide(history(bars, i, window))
    return out


Alteration = Literal["mirror", "stretch"]
ALTERATIONS: tuple[Alteration, ...] = ("mirror", "stretch")


def altered_after(bars: su.Bars, cut: int, how: Alteration = "mirror") -> su.Bars:
    """The same bars up to `cut`, and a different future around the close at the cut:
    `mirror` reverses the direction of every later move, `stretch` doubles its size. Together
    they change any use of the future, whether of its direction or of its size."""
    pivot = bars.close[cut]

    def move(v: Decimal) -> Decimal:
        return 2 * pivot - v if how == "mirror" else pivot + 2 * (v - pivot)

    def future(head: Sequence[Decimal], tail: Sequence[Decimal]) -> list[Decimal]:
        return list(head[: cut + 1]) + [move(v) for v in tail[cut + 1 :]]

    swap = how == "mirror"  # mirroring turns highs into lows
    return su.Bars(
        list(bars.ts),
        future(bars.open, bars.open),
        future(bars.high, bars.low if swap else bars.high),
        future(bars.low, bars.high if swap else bars.low),
        future(bars.close, bars.close),
    )


@dataclass(frozen=True)
class Audit:
    passed: bool
    cuts: list[int]
    checked: int  # decisions compared
    first_difference: int | None  # bar index of the first decision that changed


def leakage_audit(
    factory: Callable[[su.Bars], Strategy],
    bars: su.Bars,
    cuts: Sequence[int],
    lookback: int = 20,
    window: int = WINDOW,
) -> Audit:
    """For each cut, the decisions on the `lookback` bars up to the cut are made on the real
    series and on each altered future (the strategy is rebuilt from each series). Any
    difference is look-ahead."""
    checked = 0
    for cut in cuts:
        if not 0 <= cut < len(bars) - 1:
            raise ValueError("each cut must leave at least one later bar")
        start = max(0, cut + 1 - lookback)
        real = decisions(factory(bars), bars, start, cut + 1, window)
        for how in ALTERATIONS:
            other_bars = altered_after(bars, cut, how)
            other = decisions(factory(other_bars), other_bars, start, cut + 1, window)
            for i in range(start, cut + 1):
                checked += 1
                if real[i] != other[i]:
                    return Audit(False, list(cuts), checked, i)
    return Audit(True, list(cuts), checked, None)
