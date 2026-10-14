"""Market structure (P13-T03.4): swing points, support and resistance, breakouts, trendlines and
channels. Pure functions over highs, lows and closes in `Decimal`; positions are bar indexes.

No look-ahead: a swing point is only reported once `right` further bars confirm it
(`confirmed` = index + right), so the result for a prefix of the data equals what was known at
that time. Everything here describes the past shape of the chart; none of it is a forecast."""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

ZERO = Decimal(0)


@dataclass(frozen=True)
class SwingPoint:
    index: int
    kind: Literal["high", "low"]
    price: Decimal
    confirmed: int  # the first bar at which the point is known


def swing_points(
    high: Sequence[Decimal], low: Sequence[Decimal], left: int = 2, right: int = 2
) -> list[SwingPoint]:
    """Swing highs and lows. A swing high is a bar whose high is strictly above the `left` bars
    before it and at least as high as the `right` bars after it (so a flat top gives one swing,
    the first); a swing low mirrors that. Ordered by index."""
    if len(high) != len(low):
        raise ValueError("high and low must have the same length")
    if left < 1 or right < 1:
        raise ValueError("left and right must be at least 1")
    out: list[SwingPoint] = []
    for i in range(left, len(high) - right):
        if all(high[i] > high[j] for j in range(i - left, i)) and all(
            high[i] >= high[j] for j in range(i + 1, i + right + 1)
        ):
            out.append(SwingPoint(i, "high", high[i], i + right))
        if all(low[i] < low[j] for j in range(i - left, i)) and all(
            low[i] <= low[j] for j in range(i + 1, i + right + 1)
        ):
            out.append(SwingPoint(i, "low", low[i], i + right))
    return sorted(out, key=lambda p: (p.index, p.kind))


@dataclass(frozen=True)
class Level:
    price: Decimal  # mean of the pivots in the cluster
    touches: int
    first_index: int
    last_index: int
    established: int  # confirmation index of the latest pivot in the cluster
    indices: tuple[int, ...]


def levels(points: Sequence[SwingPoint], tolerance: Decimal, min_touches: int = 2) -> list[Level]:
    """Support/resistance levels: swing prices (highs and lows together) sorted by price and
    grouped greedily; a pivot joins the open group while it is within `tolerance` of the group's
    first price. Groups with at least `min_touches` pivots are levels, ordered by price."""
    if tolerance <= 0:
        raise ValueError("tolerance must be positive")
    ordered = sorted(points, key=lambda p: (p.price, p.index))
    groups: list[list[SwingPoint]] = []
    for p in ordered:
        if groups and p.price - groups[-1][0].price <= tolerance:
            groups[-1].append(p)
        else:
            groups.append([p])
    out = []
    for g in groups:
        if len(g) < min_touches:
            continue
        idx = sorted(p.index for p in g)
        out.append(
            Level(
                price=sum((p.price for p in g), ZERO) / len(g),
                touches=len(g),
                first_index=idx[0],
                last_index=idx[-1],
                established=max(p.confirmed for p in g),
                indices=tuple(idx),
            )
        )
    return out


def role(level: Level, price: Decimal) -> Literal["support", "resistance"]:
    """A level below the price is support, otherwise resistance."""
    return "support" if level.price < price else "resistance"


@dataclass(frozen=True)
class Breakout:
    index: int
    level_price: Decimal
    direction: Literal["up", "down"]


def breakouts(
    close: Sequence[Decimal], found: Sequence[Level], buffer: Decimal = ZERO
) -> list[Breakout]:
    """Closes that cross a level after it was established: up when a close is above level +
    buffer after the last decisive close was below level - buffer, down for the mirror. Closes
    within the buffer band do not change the side. Ordered by index."""
    if buffer < 0:
        raise ValueError("buffer must not be negative")
    out: list[Breakout] = []
    for lv in found:
        side: str | None = None
        for i in range(len(close)):
            now = (
                "above"
                if close[i] > lv.price + buffer
                else "below"
                if close[i] < lv.price - buffer
                else side
            )
            if i > lv.established and side is not None and now != side and now is not None:
                out.append(Breakout(i, lv.price, "up" if now == "above" else "down"))
            if now is not None:
                side = now
    return sorted(out, key=lambda b: (b.index, b.level_price))


@dataclass(frozen=True)
class Trendline:
    kind: Literal["support", "resistance"]
    first: SwingPoint
    second: SwingPoint
    slope: Decimal  # price change per bar
    value_at_last: Decimal  # the line at the last bar
    intact: bool  # no close beyond the line (by more than the tolerance) since the second point

    def value_at(self, index: int) -> Decimal:
        return self.first.price + self.slope * (index - self.first.index)


def trendlines(
    points: Sequence[SwingPoint], close: Sequence[Decimal], tolerance: Decimal = ZERO
) -> list[Trendline]:
    """A support line through the last two swing lows and a resistance line through the last two
    swing highs (when each exists). `intact` says whether any close since the second point went
    beyond the line by more than `tolerance`."""
    if not close:
        return []
    last = len(close) - 1
    out: list[Trendline] = []
    for kind, swing in (("support", "low"), ("resistance", "high")):
        pts = [p for p in points if p.kind == swing]
        if len(pts) < 2:
            continue
        a, b = pts[-2], pts[-1]
        slope = (b.price - a.price) / (b.index - a.index)
        line = Trendline(kind, a, b, slope, Decimal(0), True)  # type: ignore[arg-type]
        broken = any(
            (close[i] < line.value_at(i) - tolerance)
            if kind == "support"
            else (close[i] > line.value_at(i) + tolerance)
            for i in range(b.index + 1, last + 1)
        )
        out.append(Trendline(kind, a, b, slope, line.value_at(last), not broken))  # type: ignore[arg-type]
    return out


@dataclass(frozen=True)
class Channel:
    base: Trendline
    offset: Decimal  # signed distance from the base line to the parallel line at the far extreme
    upper_at_last: Decimal
    lower_at_last: Decimal


def channel(line: Trendline, high: Sequence[Decimal], low: Sequence[Decimal]) -> Channel:
    """A channel from a trendline: a parallel line through the furthest opposite extreme between
    the line's first point and the last bar (the highest high above a support line, the lowest low
    below a resistance line)."""
    if len(high) != len(low) or not high:
        raise ValueError("high and low must be the same non-zero length")
    span = range(line.first.index, len(high))
    if line.kind == "support":
        offset = max(high[i] - line.value_at(i) for i in span)
        upper, lower = line.value_at_last + offset, line.value_at_last
    else:
        offset = min(low[i] - line.value_at(i) for i in span)
        upper, lower = line.value_at_last, line.value_at_last + offset
    return Channel(line, offset, upper, lower)
