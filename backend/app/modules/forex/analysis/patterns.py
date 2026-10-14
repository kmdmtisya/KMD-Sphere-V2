"""Candlestick and price-action detectors (P13-T03.5). Pure rules over open, high, low and close
in `Decimal`. Every hit names its rule and the candle indexes it used, so the UI and the AI can
cite exactly what was seen.

A pattern's `bias` describes the shape (a hammer is a "bullish" shape) and is never a forecast or
a probability. Context rules (a prior fall or rise) use the close `lookback` bars earlier."""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from app.modules.forex.analysis.structure import Breakout

Category = Literal["reversal", "continuation", "indecision", "consolidation", "breakout"]
Bias = Literal["bullish", "bearish", "neutral"]
D = Decimal
THREE = Decimal(3)


@dataclass(frozen=True)
class PatternHit:
    rule: str
    category: Category
    bias: Bias
    indices: tuple[int, ...]  # the candles involved, oldest first

    @property
    def end(self) -> int:
        return self.indices[-1]


@dataclass(frozen=True)
class Ohlc:
    open: Sequence[Decimal]
    high: Sequence[Decimal]
    low: Sequence[Decimal]
    close: Sequence[Decimal]

    def __post_init__(self) -> None:
        if not len(self.open) == len(self.high) == len(self.low) == len(self.close):
            raise ValueError("open, high, low and close must have the same length")

    def __len__(self) -> int:
        return len(self.close)

    def body(self, i: int) -> Decimal:
        return abs(self.close[i] - self.open[i])

    def range(self, i: int) -> Decimal:
        return self.high[i] - self.low[i]

    def upper(self, i: int) -> Decimal:
        return self.high[i] - max(self.open[i], self.close[i])

    def lower(self, i: int) -> Decimal:
        return min(self.open[i], self.close[i]) - self.low[i]

    def up(self, i: int) -> bool:
        return self.close[i] > self.open[i]

    def down(self, i: int) -> bool:
        return self.close[i] < self.open[i]


def _after_fall(c: Ohlc, i: int, lookback: int) -> bool:
    return i >= lookback and c.close[i - lookback] > c.close[i - 1]


def _after_rise(c: Ohlc, i: int, lookback: int) -> bool:
    return i >= lookback and c.close[i - lookback] < c.close[i - 1]


def single_candle(c: Ohlc, lookback: int = 5) -> list[PatternHit]:
    """doji, marubozu, hammer, inverted hammer, hanging man and shooting star.

    - doji: body at most 10% of the range.
    - marubozu: body at least 90% of the range (continuation in the candle's direction).
    - hammer / hanging man: lower shadow at least twice the body, upper shadow at most 10% of the
      range, body at most 35% of the range; a hammer after a fall, a hanging man after a rise.
    - inverted hammer / shooting star: the mirror (upper shadow long); after a fall / after a
      rise."""
    out: list[PatternHit] = []
    for i in range(len(c)):
        rng = c.range(i)
        if rng <= 0:
            continue
        body = c.body(i)
        if body <= rng * D("0.1"):
            out.append(PatternHit("doji", "indecision", "neutral", (i,)))
        if body >= rng * D("0.9"):
            out.append(
                PatternHit("marubozu", "continuation", "bullish" if c.up(i) else "bearish", (i,))
            )
        small = body <= rng * D("0.35")
        if small and c.lower(i) >= 2 * body and c.upper(i) <= rng * D("0.1") and body > 0:
            if _after_fall(c, i, lookback):
                out.append(PatternHit("hammer", "reversal", "bullish", (i,)))
            elif _after_rise(c, i, lookback):
                out.append(PatternHit("hanging_man", "reversal", "bearish", (i,)))
        if small and c.upper(i) >= 2 * body and c.lower(i) <= rng * D("0.1") and body > 0:
            if _after_rise(c, i, lookback):
                out.append(PatternHit("shooting_star", "reversal", "bearish", (i,)))
            elif _after_fall(c, i, lookback):
                out.append(PatternHit("inverted_hammer", "reversal", "bullish", (i,)))
    return out


def two_candle(c: Ohlc, lookback: int = 5) -> list[PatternHit]:
    """Engulfing, harami and inside bar.

    - engulfing: the candle's body covers the previous body, opposite colours; bullish after a
      fall, bearish after a rise.
    - harami: the candle's body lies inside the previous body, opposite colours, previous body at
      least 50% of its range; bullish after a fall, bearish after a rise.
    - inside bar: high below the previous high and low above the previous low (consolidation)."""
    out: list[PatternHit] = []
    for i in range(1, len(c)):
        p = i - 1
        hi_now, lo_now = max(c.open[i], c.close[i]), min(c.open[i], c.close[i])
        hi_prev, lo_prev = max(c.open[p], c.close[p]), min(c.open[p], c.close[p])
        opposite = (c.up(i) and c.down(p)) or (c.down(i) and c.up(p))
        if opposite and c.body(p) > 0:
            if hi_now >= hi_prev and lo_now <= lo_prev and (hi_now > hi_prev or lo_now < lo_prev):
                if c.up(i) and _after_fall(c, p, lookback):
                    out.append(PatternHit("bullish_engulfing", "reversal", "bullish", (p, i)))
                if c.down(i) and _after_rise(c, p, lookback):
                    out.append(PatternHit("bearish_engulfing", "reversal", "bearish", (p, i)))
            elif (
                hi_now <= hi_prev
                and lo_now >= lo_prev
                and c.range(p) > 0
                and c.body(p) >= c.range(p) / 2
            ):
                if c.up(i) and _after_fall(c, p, lookback):
                    out.append(PatternHit("bullish_harami", "reversal", "bullish", (p, i)))
                if c.down(i) and _after_rise(c, p, lookback):
                    out.append(PatternHit("bearish_harami", "reversal", "bearish", (p, i)))
        if c.high[i] < c.high[p] and c.low[i] > c.low[p]:
            out.append(PatternHit("inside_bar", "consolidation", "neutral", (p, i)))
    return out


def three_candle(c: Ohlc, lookback: int = 5) -> list[PatternHit]:
    """Morning and evening star, three white soldiers and three black crows.

    - morning star: a long down candle (body at least 60% of its range), a small candle (body at
      most 30% of the first body) and an up candle closing above the first body's midpoint;
      evening star is the mirror. Each needs a prior fall / rise.
    - three white soldiers: three up candles, each body at least 50% of its range, each close
      above the previous close and each open inside the previous body; three black crows mirror."""
    out: list[PatternHit] = []
    for i in range(2, len(c)):
        a, b = i - 2, i - 1
        if c.range(a) > 0:
            long_a = c.body(a) >= c.range(a) * D("0.6")
            small_b = c.body(b) <= c.body(a) * D("0.3")
            mid_a = (c.open[a] + c.close[a]) / 2
            if (
                long_a
                and small_b
                and c.down(a)
                and c.up(i)
                and c.close[i] > mid_a
                and _after_fall(c, a, lookback)
            ):
                out.append(PatternHit("morning_star", "reversal", "bullish", (a, b, i)))
            if (
                long_a
                and small_b
                and c.up(a)
                and c.down(i)
                and c.close[i] < mid_a
                and _after_rise(c, a, lookback)
            ):
                out.append(PatternHit("evening_star", "reversal", "bearish", (a, b, i)))
        trio = (a, b, i)
        if not all(c.range(k) > 0 and c.body(k) >= c.range(k) / 2 for k in trio):
            continue
        pairs = ((a, b), (b, i))
        rising = c.close[b] > c.close[a] and c.close[i] > c.close[b]
        falling = c.close[b] < c.close[a] and c.close[i] < c.close[b]
        inside_up = all(c.open[m] < c.open[n] < c.close[m] for m, n in pairs)
        inside_down = all(c.close[m] < c.open[n] < c.open[m] for m, n in pairs)
        if rising and inside_up and all(c.up(k) for k in trio):
            out.append(PatternHit("three_white_soldiers", "continuation", "bullish", trio))
        if falling and inside_down and all(c.down(k) for k in trio):
            out.append(PatternHit("three_black_crows", "continuation", "bearish", trio))
    return out


def range_consolidation(
    c: Ohlc, atr: Sequence[Decimal | None], bars: int = 10, max_atr_multiple: Decimal = THREE
) -> list[PatternHit]:
    """A window of `bars` candles whose total range (highest high - lowest low) is at most
    `max_atr_multiple` times the ATR at the window's last bar. Windows that overlap are reported
    once, as the longest run (the window ending at the last qualifying bar of a run)."""
    if len(atr) != len(c):
        raise ValueError("atr must have the same length as the candles")
    if bars < 2:
        raise ValueError("bars must be at least 2")
    out: list[PatternHit] = []
    run_end: int | None = None
    for i in range(bars - 1, len(c)):
        a = atr[i]
        ok = (
            a is not None
            and max(c.high[i - bars + 1 : i + 1]) - min(c.low[i - bars + 1 : i + 1])
            <= a * max_atr_multiple
        )
        if ok:
            run_end = i
        elif run_end is not None:
            out.append(
                PatternHit(
                    "range_consolidation",
                    "consolidation",
                    "neutral",
                    tuple(range(run_end - bars + 1, run_end + 1)),
                )
            )
            run_end = None
    if run_end is not None:
        out.append(
            PatternHit(
                "range_consolidation",
                "consolidation",
                "neutral",
                tuple(range(run_end - bars + 1, run_end + 1)),
            )
        )
    return out


def breakout_retest(
    c: Ohlc, found: Sequence[Breakout], tolerance: Decimal, window: int = 8
) -> list[PatternHit]:
    """A breakout followed, within `window` bars, by a return to the broken level (an up breakout:
    a low at or below level + tolerance; a down breakout: a high at or above level - tolerance)
    with the close still on the breakout side. Indexes are (breakout bar, retest bar)."""
    out: list[PatternHit] = []
    for b in found:
        for j in range(b.index + 1, min(len(c), b.index + window + 1)):
            if b.direction == "up" and c.low[j] <= b.level_price + tolerance:
                if c.close[j] >= b.level_price:
                    out.append(PatternHit("breakout_retest", "breakout", "bullish", (b.index, j)))
                break
            if b.direction == "down" and c.high[j] >= b.level_price - tolerance:
                if c.close[j] <= b.level_price:
                    out.append(PatternHit("breakout_retest", "breakout", "bearish", (b.index, j)))
                break
    return out


def detect(c: Ohlc, lookback: int = 5) -> list[PatternHit]:
    """All candlestick rules, ordered by the last candle then the rule name."""
    hits = [*single_candle(c, lookback), *two_candle(c, lookback), *three_candle(c, lookback)]
    return sorted(hits, key=lambda h: (h.end, h.rule))
