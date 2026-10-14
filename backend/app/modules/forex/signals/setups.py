"""Setup rules (P13-T06.1, design section 8.1). Each rule is named and versioned, reads only
closed bars (no look-ahead), and returns a direction with **illustrative levels**: the entry is
the last close, the stop is the invalidation level (where the setup no longer holds), and the
target is set by the rule. Levels come only from the stored bars and the rule definitions, with
the time of the bar they are based on. They are scenarios for study, not orders or advice.

Rules (bullish shown; bearish is the mirror):
- `trend_continuation`: EMA(20) > EMA(50), close > EMA(20), ADX(14) >= 25 and +DI > -DI. Stop: the
  lower of the last swing low and close - 1.5 ATR. Target: 2 x risk.
- `breakout`: a close broke up through a support/resistance level in the last 3 bars. Stop: the
  level - 0.5 ATR. Target: 2 x risk.
- `reversal`: a bullish reversal candle pattern in the last 2 bars with its low within 0.5 ATR of
  a level. Stop: the pattern's low - 0.25 ATR. Target: the next level above, else 2 x risk.
- `range`: ADX < 20 and Bollinger %b < 0.1. Stop: the lower band - 0.5 ATR. Target: the middle
  band.
- `momentum`: MACD histogram positive and rising for 3 bars, RSI(14) from 55 to 70 (bearish: 30 to
  45). Stop: close - 1.5 ATR. Target: 2 x risk.
- `mean_reversion`: RSI(14) < 30 and close below the lower Bollinger band. Stop: the bar's low -
  0.5 ATR. Target: the middle band.
A setup whose stop or target falls on the wrong side of the entry is not reported."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Literal

from app.modules.forex.analysis import indicators as ind
from app.modules.forex.analysis import patterns as pat
from app.modules.forex.analysis import structure as st

Direction = Literal["bullish", "bearish"]
SetupType = Literal[
    "trend_continuation", "breakout", "reversal", "range", "momentum", "mean_reversion"
]
RULE_VERSION = 1
MIN_BARS = 60
D = Decimal
REVERSAL_RULES: dict[Direction, set[str]] = {
    "bullish": {"hammer", "bullish_engulfing", "morning_star", "inverted_hammer", "bullish_harami"},
    "bearish": {
        "shooting_star",
        "bearish_engulfing",
        "evening_star",
        "hanging_man",
        "bearish_harami",
    },
}


@dataclass(frozen=True)
class Bars:
    ts: Sequence[datetime]
    open: Sequence[Decimal]
    high: Sequence[Decimal]
    low: Sequence[Decimal]
    close: Sequence[Decimal]

    def __len__(self) -> int:
        return len(self.close)


@dataclass(frozen=True)
class Setup:
    rule: SetupType
    version: int
    direction: Direction
    as_of: datetime  # the bar the levels are based on
    entry: Decimal
    stop: Decimal
    target: Decimal
    evidence: list[str] = field(default_factory=list)

    @property
    def risk(self) -> Decimal:
        return abs(self.entry - self.stop)

    @property
    def reward(self) -> Decimal:
        return abs(self.target - self.entry)

    @property
    def risk_reward(self) -> Decimal | None:
        return None if self.risk == 0 else self.reward / self.risk


@dataclass(frozen=True)
class Context:
    """Indicators and structure computed once per pair, shared by every rule and the score."""

    bars: Bars
    ema20: list[Decimal | None]
    ema50: list[Decimal | None]
    rsi: list[Decimal | None]
    atr: list[Decimal | None]
    adx: ind.Adx
    macd: ind.Macd
    bollinger: ind.Bollinger
    swings: list[st.SwingPoint]
    levels: list[st.Level]
    breakouts: list[st.Breakout]
    patterns: list[pat.PatternHit]


def context(bars: Bars) -> Context:
    if len(bars) < MIN_BARS:
        raise ValueError(f"at least {MIN_BARS} bars are needed")
    c, h, lo = list(bars.close), list(bars.high), list(bars.low)
    atr = ind.atr(h, lo, c, 14)
    last_atr = next((a for a in reversed(atr) if a is not None), None)
    swings = st.swing_points(h, lo)
    levels = st.levels(swings, (last_atr or D("0.0001")) / 2)
    return Context(
        bars=bars,
        ema20=ind.ema(c, 20),
        ema50=ind.ema(c, 50),
        rsi=ind.rsi(c, 14),
        atr=atr,
        adx=ind.adx(h, lo, c, 14),
        macd=ind.macd(c),
        bollinger=ind.bollinger(c, 20),
        swings=swings,
        levels=levels,
        breakouts=st.breakouts(c, levels),
        patterns=pat.detect(pat.Ohlc(list(bars.open), h, lo, c)),
    )


def _make(
    rule: SetupType,
    direction: Direction,
    ctx: Context,
    stop: Decimal,
    target: Decimal | None,
    evidence: list[str],
) -> Setup | None:
    entry = ctx.bars.close[-1]
    risk = entry - stop if direction == "bullish" else stop - entry
    if risk <= 0:
        return None  # an invalidation level on the wrong side means the setup does not hold
    if target is None:
        target = entry + 2 * risk if direction == "bullish" else entry - 2 * risk
    if (direction == "bullish" and target <= entry) or (direction == "bearish" and target >= entry):
        return None
    return Setup(rule, RULE_VERSION, direction, ctx.bars.ts[-1], entry, stop, target, evidence)


def trend_continuation(ctx: Context) -> Setup | None:
    c, e20, e50, atr = ctx.bars.close[-1], ctx.ema20[-1], ctx.ema50[-1], ctx.atr[-1]
    adx, pdi, mdi = ctx.adx.adx[-1], ctx.adx.plus_di[-1], ctx.adx.minus_di[-1]
    if e20 is None or e50 is None or atr is None or adx is None or pdi is None or mdi is None:
        return None
    n = len(ctx.bars)
    lows = [p.price for p in ctx.swings if p.kind == "low" and p.confirmed < n]
    highs = [p.price for p in ctx.swings if p.kind == "high" and p.confirmed < n]
    evidence = [
        f"EMA(20) {e20:.5f} vs EMA(50) {e50:.5f}",
        f"ADX {adx:.1f}",
        f"+DI {pdi:.1f}, -DI {mdi:.1f}",
    ]
    if e20 > e50 and c > e20 and adx >= 25 and pdi > mdi:
        stop = min([c - D("1.5") * atr, *lows[-1:]])
        return _make("trend_continuation", "bullish", ctx, stop, None, evidence)
    if e20 < e50 and c < e20 and adx >= 25 and mdi > pdi:
        stop = max([c + D("1.5") * atr, *highs[-1:]])
        return _make("trend_continuation", "bearish", ctx, stop, None, evidence)
    return None


def breakout(ctx: Context) -> Setup | None:
    atr = ctx.atr[-1]
    recent = [b for b in ctx.breakouts if b.index >= len(ctx.bars) - 3]
    if atr is None or not recent:
        return None
    b = recent[-1]
    evidence = [f"a close broke {b.direction} through the level {b.level_price:.5f}"]
    if b.direction == "up":
        return _make("breakout", "bullish", ctx, b.level_price - atr / 2, None, evidence)
    return _make("breakout", "bearish", ctx, b.level_price + atr / 2, None, evidence)


def reversal(ctx: Context) -> Setup | None:
    atr = ctx.atr[-1]
    if atr is None or not ctx.levels:
        return None
    n, close = len(ctx.bars), ctx.bars.close[-1]
    for direction in ("bullish", "bearish"):
        hits = [h for h in ctx.patterns if h.rule in REVERSAL_RULES[direction] and h.end >= n - 2]
        if not hits:
            continue
        hit = hits[-1]
        span = range(hit.indices[0], hit.end + 1)
        if direction == "bullish":
            low = min(ctx.bars.low[i] for i in span)
            near = [lv for lv in ctx.levels if abs(lv.price - low) <= atr / 2]
            above = sorted(lv.price for lv in ctx.levels if lv.price > close)
            if near:
                evidence = [f"{hit.rule} near the level {near[0].price:.5f}"]
                target = above[0] if above else None
                return _make("reversal", "bullish", ctx, low - atr / 4, target, evidence)
        else:
            high = max(ctx.bars.high[i] for i in span)
            near = [lv for lv in ctx.levels if abs(lv.price - high) <= atr / 2]
            below = sorted((lv.price for lv in ctx.levels if lv.price < close), reverse=True)
            if near:
                evidence = [f"{hit.rule} near the level {near[0].price:.5f}"]
                target = below[0] if below else None
                return _make("reversal", "bearish", ctx, high + atr / 4, target, evidence)
    return None


def range_setup(ctx: Context) -> Setup | None:
    adx, atr = ctx.adx.adx[-1], ctx.atr[-1]
    mid, up, lo = ctx.bollinger.middle[-1], ctx.bollinger.upper[-1], ctx.bollinger.lower[-1]
    if adx is None or atr is None or mid is None or up is None or lo is None or up == lo:
        return None
    if adx >= 20:
        return None
    pctb = (ctx.bars.close[-1] - lo) / (up - lo)
    evidence = [f"ADX {adx:.1f} (no trend)", f"Bollinger %b {pctb:.2f}"]
    if pctb < D("0.1"):
        return _make("range", "bullish", ctx, lo - atr / 2, mid, evidence)
    if pctb > D("0.9"):
        return _make("range", "bearish", ctx, up + atr / 2, mid, evidence)
    return None


def momentum(ctx: Context) -> Setup | None:
    rsi, atr = ctx.rsi[-1], ctx.atr[-1]
    hist = [x for x in ctx.macd.histogram[-3:] if x is not None]
    if len(hist) < 3 or rsi is None or atr is None:
        return None
    c = ctx.bars.close[-1]
    evidence = [f"MACD histogram {hist[0]:.6f} to {hist[2]:.6f}", f"RSI {rsi:.1f}"]
    if all(x > 0 for x in hist) and hist[0] < hist[1] < hist[2] and D(55) <= rsi <= D(70):
        return _make("momentum", "bullish", ctx, c - D("1.5") * atr, None, evidence)
    if all(x < 0 for x in hist) and hist[0] > hist[1] > hist[2] and D(30) <= rsi <= D(45):
        return _make("momentum", "bearish", ctx, c + D("1.5") * atr, None, evidence)
    return None


def mean_reversion(ctx: Context) -> Setup | None:
    rsi, atr = ctx.rsi[-1], ctx.atr[-1]
    mid, up, lo = ctx.bollinger.middle[-1], ctx.bollinger.upper[-1], ctx.bollinger.lower[-1]
    if rsi is None or atr is None or mid is None or up is None or lo is None:
        return None
    c = ctx.bars.close[-1]
    evidence = [f"RSI {rsi:.1f}", f"close {c} against the bands {lo:.5f} and {up:.5f}"]
    if rsi < 30 and c < lo:
        return _make("mean_reversion", "bullish", ctx, ctx.bars.low[-1] - atr / 2, mid, evidence)
    if rsi > 70 and c > up:
        return _make("mean_reversion", "bearish", ctx, ctx.bars.high[-1] + atr / 2, mid, evidence)
    return None


RULES = (trend_continuation, breakout, reversal, range_setup, momentum, mean_reversion)


def detect(ctx: Context) -> list[Setup]:
    """Every rule that holds on the last closed bar."""
    return [s for rule in RULES if (s := rule(ctx)) is not None]
