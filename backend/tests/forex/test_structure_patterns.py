"""Market structure and candlestick detectors (P13-T03.4, T03.5): hand-built charts where the
answer is clear by inspection, edge cases, and the no-look-ahead property."""

from decimal import Decimal

import pytest

from app.modules.forex.analysis import patterns as pat
from app.modules.forex.analysis import structure as st

D = Decimal


def ds(values: str) -> list[Decimal]:
    return [D(v) for v in values.split()]


# A zig-zag: highs at index 2 (10), 6 (10), lows at 4 (2), 8 (3).
HIGH = ds("5 8 10 8 5 8 10 8 6 7 9")
LOW = ds("3 5 7 5 2 5 7 5 3 5 6")


def test_swing_points_are_confirmed_by_the_bars_after_them() -> None:
    points = st.swing_points(HIGH, LOW, 2, 2)
    got = [(p.index, p.kind, p.price, p.confirmed) for p in points]
    assert got == [
        (2, "high", D(10), 4),
        (4, "low", D(2), 6),
        (6, "high", D(10), 8),
        (8, "low", D(3), 10),
    ]


def test_a_flat_top_gives_one_swing_the_first() -> None:
    high = ds("1 2 5 5 3 2 1")
    low = ds("0 1 4 4 2 1 0")
    highs = [p for p in st.swing_points(high, low, 2, 2) if p.kind == "high"]
    assert [p.index for p in highs] == [2]


def test_swing_points_look_only_backwards_once_confirmed() -> None:
    """A prefix's swings are exactly the full data's swings that were confirmed by then."""
    full = st.swing_points(HIGH, LOW, 2, 2)
    for m in range(1, len(HIGH) + 1):
        prefix = st.swing_points(HIGH[:m], LOW[:m], 2, 2)
        assert prefix == [p for p in full if p.confirmed <= m - 1]


def test_swing_edge_cases() -> None:
    assert st.swing_points([], [], 2, 2) == []
    assert st.swing_points(ds("1 2 3"), ds("0 1 2")) == []
    with pytest.raises(ValueError):
        st.swing_points(ds("1 2"), ds("1"))
    with pytest.raises(ValueError):
        st.swing_points(ds("1 2 3"), ds("0 1 2"), 0, 2)


def test_levels_cluster_pivots_within_the_tolerance() -> None:
    points = st.swing_points(HIGH, LOW, 2, 2)
    found = st.levels(points, D("0.5"))
    assert [(lv.price, lv.touches, lv.indices) for lv in found] == [(D(10), 2, (2, 6))]
    assert found[0].established == 8 and found[0].first_index == 2 and found[0].last_index == 6
    # A wider tolerance joins the two lows (2 and 3) into a second level.
    wide = st.levels(points, D(1))
    assert [(lv.price, lv.touches) for lv in wide] == [(D("2.5"), 2), (D(10), 2)]
    assert st.levels(points, D("0.5"), min_touches=3) == []
    with pytest.raises(ValueError):
        st.levels(points, D(0))


def test_a_level_is_support_below_the_price_and_resistance_above() -> None:
    level = st.Level(D(10), 2, 0, 1, 2, (0, 1))
    assert st.role(level, D(12)) == "support"
    assert st.role(level, D(8)) == "resistance"
    assert st.role(level, D(10)) == "resistance"


def test_breakouts_need_a_close_beyond_the_level_after_it_was_established() -> None:
    level = st.Level(D(10), 2, 2, 6, 8, (2, 6))
    close = ds("5 8 9 9 8 9 9 9 9 9 11 12 9 8")
    # The first decisive close above 10 is at index 10; the drop back to 9 at 12 is a down break.
    assert st.breakouts(close, [level]) == [
        st.Breakout(10, D(10), "up"),
        st.Breakout(12, D(10), "down"),
    ]
    # A buffer makes a marginal close indecisive.
    assert st.breakouts(ds("9 9 9 9 9 9 9 9 9 9 10.2 12"), [level], D("0.5")) == [
        st.Breakout(11, D(10), "up")
    ]
    # A cross before the level was established is not reported.
    early = st.Level(D(10), 2, 2, 6, 20, (2, 6))
    assert st.breakouts(close, [early]) == []
    with pytest.raises(ValueError):
        st.breakouts(close, [level], D(-1))


def test_trendlines_through_the_last_two_swings_and_their_validity() -> None:
    # Rising lows at 1 and 4: 10 then 13 -> slope 1 per bar; rising highs 20 and 24.
    high = ds("12 20 15 14 24 18 17 16")
    low = ds("11 15 12 10 18 13 14 14")
    points = [
        st.SwingPoint(1, "high", D(20), 3),
        st.SwingPoint(4, "high", D(24), 6),
        st.SwingPoint(3, "low", D(10), 5),
        st.SwingPoint(6, "low", D(13), 8),
    ]
    close = ds("12 18 13 12 22 15 16 15")
    lines = {ln.kind: ln for ln in st.trendlines(points, close, D(0))}
    support = lines["support"]
    assert support.slope == D(1) and support.value_at(8) == D(15) and support.value_at_last == D(14)
    assert support.intact is True  # close[7] = 15 is above the line value at 7 (14)
    broken = st.trendlines(points, ds("12 18 13 12 22 15 16 12"), D(0))
    assert {ln.kind: ln.intact for ln in broken}["support"] is False  # 12 < 14
    assert {ln.kind: ln.intact for ln in broken}["resistance"] is True
    resistance = lines["resistance"]
    assert resistance.slope == D(4) / D(3) and resistance.first.index == 1
    assert st.trendlines(points[:1], close) == []
    assert st.trendlines(points, []) == []
    channel = st.channel(support, high, low)
    assert channel.lower_at_last == support.value_at_last
    assert channel.offset == max(high[i] - support.value_at(i) for i in range(3, 8))
    assert channel.upper_at_last == support.value_at_last + channel.offset
    down = st.channel(resistance, high, low)
    assert down.upper_at_last == resistance.value_at_last and down.offset <= 0
    with pytest.raises(ValueError):
        st.channel(support, [], [])


# ------------------------------------------------------------------------- price action
def ohlc(rows: list[tuple[str, str, str, str]]) -> pat.Ohlc:
    return pat.Ohlc(
        [D(r[0]) for r in rows],
        [D(r[1]) for r in rows],
        [D(r[2]) for r in rows],
        [D(r[3]) for r in rows],
    )


FALL = [
    ("20", "20.5", "19.5", "19.8"),
    ("19.8", "20", "18.8", "19"),
    ("19", "19.2", "18", "18.2"),
    ("18.2", "18.4", "17.2", "17.4"),
    ("17.4", "17.6", "16.4", "16.6"),
]
RISE = [
    ("10", "10.5", "9.8", "10.4"),
    ("10.4", "11.2", "10.3", "11"),
    ("11", "12", "10.9", "11.8"),
    ("11.8", "12.8", "11.7", "12.6"),
    ("12.6", "13.6", "12.5", "13.4"),
]


def rules(hits: list[pat.PatternHit]) -> list[str]:
    return [h.rule for h in hits]


def test_doji_and_marubozu() -> None:
    assert rules(pat.single_candle(ohlc([("10", "12", "8", "10.1")]))) == ["doji"]
    [hit] = pat.single_candle(ohlc([("10", "14", "10", "14")]))
    assert (hit.rule, hit.bias, hit.category) == ("marubozu", "bullish", "continuation")
    [hit] = pat.single_candle(ohlc([("14", "14", "10", "10")]))
    assert hit.bias == "bearish"
    assert pat.single_candle(ohlc([("10", "10", "10", "10")])) == []  # no range: nothing to measure


def shapes(hits: list[pat.PatternHit]) -> list[tuple[str, str]]:
    """(rule, bias) of the hits, leaving out the plain shape descriptions that a candle can also
    satisfy (a long-shadowed small body is also a doji; a harami is also an inside bar)."""
    return [(h.rule, h.bias) for h in hits if h.rule not in ("doji", "inside_bar")]


def test_hammer_needs_a_prior_fall_and_the_same_shape_after_a_rise_is_a_hanging_man() -> None:
    candle = ("16.5", "16.7", "14.5", "16.6")  # small body at the top, long lower shadow
    hits = pat.single_candle(ohlc([*FALL, candle]), 3)
    assert shapes(hits) == [("hammer", "bullish")]
    assert [h.indices for h in hits if h.rule == "hammer"] == [(5,)]
    up = pat.single_candle(ohlc([*RISE, ("13.5", "13.7", "11.5", "13.6")]), 3)
    assert shapes(up) == [("hanging_man", "bearish")]
    assert shapes(pat.single_candle(ohlc([candle]), 3)) == []  # no context, no pattern


def test_shooting_star_and_inverted_hammer() -> None:
    star = ("13.5", "15.7", "13.4", "13.6")
    assert shapes(pat.single_candle(ohlc([*RISE, star]), 3)) == [("shooting_star", "bearish")]
    inverted = ("16.5", "18.7", "16.4", "16.6")
    assert shapes(pat.single_candle(ohlc([*FALL, inverted]), 3)) == [("inverted_hammer", "bullish")]


def test_context_is_the_close_lookback_bars_earlier() -> None:
    candle = ("16.5", "16.7", "14.5", "16.6")
    assert shapes(pat.single_candle(ohlc([*FALL, candle]), 5)) == [("hammer", "bullish")]
    assert shapes(pat.single_candle(ohlc([*FALL, candle]), 6)) == []  # not enough history


def test_engulfing_and_harami() -> None:
    bull = pat.two_candle(ohlc([*FALL, ("16.4", "18", "16.3", "17.8")]), 3)
    assert [(h.rule, h.indices) for h in bull] == [("bullish_engulfing", (4, 5))]
    bear = pat.two_candle(ohlc([*RISE, ("13.6", "13.7", "12.2", "12.3")]), 3)
    assert shapes(bear) == [("bearish_engulfing", "bearish")]
    harami = pat.two_candle(ohlc([*FALL, ("16.9", "17.1", "16.8", "17")]), 3)
    assert shapes(harami) == [("bullish_harami", "bullish")]
    assert {h.rule for h in harami} == {"bullish_harami", "inside_bar"}
    # The same engulfing shape without a prior fall is not reported as a reversal.
    assert pat.two_candle(ohlc([*FALL, ("16.4", "18", "16.3", "17.8")]), 5) == []


def test_inside_bar() -> None:
    hits = pat.two_candle(ohlc([("10", "12", "8", "11"), ("10.5", "11", "9", "10.8")]))
    assert [(h.rule, h.category, h.bias) for h in hits] == [
        ("inside_bar", "consolidation", "neutral")
    ]


def test_morning_and_evening_star() -> None:
    morning = [
        *FALL[:4],
        ("17.4", "17.5", "15.0", "15.2"),
        ("15.1", "15.3", "14.9", "15.15"),
        ("15.3", "17.0", "15.2", "16.8"),
    ]
    hits = pat.three_candle(ohlc(morning), 3)
    assert [(h.rule, h.indices) for h in hits] == [("morning_star", (4, 5, 6))]
    evening = [
        *RISE[:4],
        ("12.6", "14.9", "12.5", "14.8"),
        ("14.85", "15.0", "14.75", "14.9"),
        ("14.7", "14.8", "12.9", "13.0"),
    ]
    assert [h.rule for h in pat.three_candle(ohlc(evening), 3)] == ["evening_star"]


def test_three_white_soldiers_and_black_crows() -> None:
    soldiers = [
        ("10", "10.2", "9.9", "10.1"),
        ("10", "11", "9.95", "10.9"),
        ("10.5", "11.8", "10.4", "11.7"),
        ("11.2", "12.6", "11.1", "12.5"),
    ]
    assert [h.rule for h in pat.three_candle(ohlc(soldiers))] == ["three_white_soldiers"]
    crows = [
        ("12", "12.1", "11.8", "11.9"),
        ("12", "12.05", "11", "11.1"),
        ("11.5", "11.6", "10.2", "10.3"),
        ("10.8", "10.9", "9.4", "9.5"),
    ]
    assert [h.rule for h in pat.three_candle(ohlc(crows))] == ["three_black_crows"]
    # Opens outside the previous body: not soldiers.
    gappy = [
        ("10", "10.2", "9.9", "10.1"),
        ("10", "11", "9.95", "10.9"),
        ("11.5", "12.5", "11.4", "12.4"),
        ("12.6", "13.5", "12.5", "13.4"),
    ]
    assert pat.three_candle(ohlc(gappy)) == []


def test_range_consolidation_reports_each_run_once() -> None:
    rows = (
        [("10", "10.5", "9.5", "10.1")] * 12
        + [("10", "14", "9", "13")] * 2
        + [("10", "10.4", "9.6", "10")] * 6
    )
    atr = [D("1")] * len(rows)
    hits = pat.range_consolidation(ohlc(rows), atr, bars=5, max_atr_multiple=D(2))
    # Each run is reported once, as the window ending at its last qualifying bar.
    assert [(h.indices[0], h.indices[-1]) for h in hits] == [(7, 11), (15, 19)]
    assert all(h.rule == "range_consolidation" and h.category == "consolidation" for h in hits)
    assert pat.range_consolidation(ohlc(rows), [None] * len(rows), bars=5) == []
    with pytest.raises(ValueError):
        pat.range_consolidation(ohlc(rows), [D(1)], bars=5)
    with pytest.raises(ValueError):
        pat.range_consolidation(ohlc(rows), atr, bars=1)


def test_breakout_and_retest() -> None:
    rows = [
        ("9", "9.5", "8.8", "9.2"),
        ("9.2", "9.8", "9", "9.6"),
        ("9.6", "10.9", "9.5", "10.8"),
        ("10.8", "11.5", "10.7", "11.3"),
        ("11.3", "11.4", "10.05", "10.4"),
        ("10.4", "11", "10.3", "10.9"),
    ]
    found = [st.Breakout(2, D(10), "up")]
    hits = pat.breakout_retest(ohlc(rows), found, D("0.1"), window=4)
    assert [(h.rule, h.bias, h.indices) for h in hits] == [("breakout_retest", "bullish", (2, 4))]
    assert (
        pat.breakout_retest(ohlc(rows), found, D("0.01"), window=4) == []
    )  # never came back that close
    down_rows = [
        ("11", "11.1", "10.5", "10.6"),
        ("10.6", "10.7", "9.1", "9.2"),
        ("9.2", "9.95", "9.0", "9.5"),
    ]
    hits = pat.breakout_retest(ohlc(down_rows), [st.Breakout(1, D(10), "down")], D("0.1"))
    assert [(h.bias, h.indices) for h in hits] == [("bearish", (1, 2))]


def test_detect_orders_hits_and_every_hit_cites_real_candles() -> None:
    rows = [*FALL, ("16.4", "18", "16.3", "17.8"), ("17.8", "18.4", "17.7", "18.3")]
    c = ohlc(rows)
    hits = pat.detect(c)
    assert hits == sorted(hits, key=lambda h: (h.end, h.rule))
    for h in hits:
        assert h.rule and h.indices == tuple(sorted(h.indices))
        assert all(0 <= i < len(c) for i in h.indices)


def test_inputs_must_line_up() -> None:
    with pytest.raises(ValueError):
        pat.Ohlc([D(1)], [D(1), D(2)], [D(1)], [D(1)])
    assert pat.detect(ohlc([])) == []
