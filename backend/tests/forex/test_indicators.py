"""Technical indicators against an independent exact oracle (P13-T03, QG-14.1): every indicator
equals the oracle within 1e-18 on seeded random series, hand-checkable cases hold, warm-ups are
exact, undefined ratios are None, and a value never depends on later bars."""

import random
from collections.abc import Callable
from decimal import Decimal
from fractions import Fraction

import pytest

from app.modules.forex.analysis import indicators as ind
from tests.forex import indicator_oracle as oracle

D = Decimal
TOLERANCE = Fraction(1, 10**18)
F1 = Fraction(1)


def close_to(actual: list[Decimal | None], expected: list[Fraction | None]) -> None:
    assert len(actual) == len(expected)
    for i, (a, e) in enumerate(zip(actual, expected, strict=True)):
        if e is None:
            assert a is None, f"index {i}: expected no value, got {a}"
        else:
            assert a is not None, f"index {i}: expected {float(e)}, got None"
            assert abs(Fraction(a) - e) <= TOLERANCE * max(F1, abs(e)), (
                f"index {i}: {a} vs {float(e)}"
            )


def series(seed: int, n: int = 90, start: str = "1.10000", step: str = "0.0030") -> list[Decimal]:
    rng = random.Random(seed)  # noqa: S311 (seeded test data, not security)
    price, out = D(start), []
    for _ in range(n):
        price = max(price + D(rng.randint(-100, 100)) * D(step) / 100, D("0.5"))
        out.append(price.quantize(D("0.00001")))
    return out


def bars(seed: int, n: int = 90) -> tuple[list[Decimal], list[Decimal], list[Decimal]]:
    close = series(seed, n)
    rng = random.Random(seed + 1000)  # noqa: S311 (seeded test data, not security)
    high = [c + D(rng.randint(1, 40)) * D("0.00001") for c in close]
    low = [c - D(rng.randint(1, 40)) * D("0.00001") for c in close]
    return high, low, close


SEEDS = [1, 2, 3, 7, 42]


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("period", [1, 2, 5, 14, 20])
def test_sma_and_ema_equal_the_oracle(seed: int, period: int) -> None:
    x = series(seed)
    close_to(ind.sma(x, period), oracle.sma(oracle.fr(x), period))
    close_to(ind.ema(x, period), oracle.ema(oracle.fr(x), period))


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("params", [(12, 26, 9), (3, 8, 4), (5, 35, 5)])
def test_macd_equals_the_oracle(seed: int, params: tuple[int, int, int]) -> None:
    x = series(seed, 120)
    result = ind.macd(x, *params)
    line, sig, hist = oracle.macd(oracle.fr(x), *params)
    close_to(result.macd, line)
    close_to(result.signal, sig)
    close_to(result.histogram, hist)


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("period", [2, 7, 14])
def test_rsi_equals_the_oracle(seed: int, period: int) -> None:
    x = series(seed)
    close_to(ind.rsi(x, period), oracle.rsi(oracle.fr(x), period))


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("params", [(14, 3, 1), (14, 3, 3), (5, 3, 3), (9, 1, 1)])
def test_stochastic_equals_the_oracle(seed: int, params: tuple[int, int, int]) -> None:
    h, lo, c = bars(seed)
    result = ind.stochastic(h, lo, c, *params)
    k, d = oracle.stochastic(oracle.fr(h), oracle.fr(lo), oracle.fr(c), *params)
    close_to(result.k, k)
    close_to(result.d, d)


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("period", [1, 5, 12])
def test_roc_equals_the_oracle(seed: int, period: int) -> None:
    x = series(seed)
    close_to(ind.roc(x, period), oracle.roc(oracle.fr(x), period))


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("period", [1, 5, 14])
def test_atr_equals_the_oracle(seed: int, period: int) -> None:
    h, lo, c = bars(seed)
    expected = oracle.atr(oracle.fr(h), oracle.fr(lo), oracle.fr(c), period)
    close_to(ind.atr(h, lo, c, period), expected)


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("period", [2, 5, 14])
def test_adx_equals_the_oracle(seed: int, period: int) -> None:
    h, lo, c = bars(seed, 100)
    result = ind.adx(h, lo, c, period)
    plus, minus, adx = oracle.adx(oracle.fr(h), oracle.fr(lo), oracle.fr(c), period)
    close_to(result.plus_di, plus)
    close_to(result.minus_di, minus)
    close_to(result.adx, adx)


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("period", [2, 10, 20])
def test_bollinger_equals_the_oracle(seed: int, period: int) -> None:
    x = series(seed)
    result = ind.bollinger(x, period, D(2))
    mid, var = oracle.bollinger(oracle.fr(x), period)
    close_to(result.middle, mid)
    for i, v in enumerate(var):
        up, lo = result.upper[i], result.lower[i]
        if v is None:
            assert up is None and lo is None and result.bandwidth[i] is None
            continue
        assert up is not None and lo is not None
        sd = (up - lo) / 4  # bands are mid +/- 2 sd
        assert abs(Fraction(sd) ** 2 - v) <= Fraction(1, 10**18)  # the root of the oracle variance


# ------------------------------------------------------------- hand-checkable cases
def test_sma_and_ema_by_hand() -> None:
    x = [D(v) for v in (1, 2, 3, 4, 5)]
    assert ind.sma(x, 3) == [None, None, D(2), D(3), D(4)]
    # alpha = 2/4 = 0.5, seed = (1+2+3)/3 = 2: 2 -> 2 + 0.5(4-2) = 3 -> 3 + 0.5(5-3) = 4
    assert ind.ema(x, 3) == [None, None, D(2), D(3), D(4)]
    assert ind.ema([D(2), D(2), D(2), D(10)], 3) == [None, None, D(2), D(2) + D("0.5") * 8]


def test_rsi_by_hand() -> None:
    # period 2: gains 1, 1 then a loss of 1. Seed: average gain 1, average loss 0 -> RSI 100.
    # Next: gain (1*1+0)/2 = 0.5, loss (0*1+1)/2 = 0.5 -> RSI 50.
    result = ind.rsi([D(10), D(11), D(12), D(11)], 2)
    assert result == [None, None, D(100), D(50)]


def test_roc_and_atr_by_hand() -> None:
    assert ind.roc([D(100), D(110), D(121)], 1) == [None, D(10), D(10)]
    h, lo, c = [D(11), D(12), D(13)], [D(9), D(10), D(11)], [D(10), D(11), D(12)]
    assert ind.true_range(h, lo, c) == [D(2), D(2), D(2)]
    assert ind.atr(h, lo, c, 3) == [None, None, D(2)]


def test_true_range_uses_the_gap_to_the_previous_close() -> None:
    # The second bar gaps up: |high - previous close| = 7 exceeds high - low = 2.
    assert ind.true_range([D(11), D(14)], [D(9), D(12)], [D(10), D(13)]) == [D(2), D(4)]
    assert ind.true_range([D(11), D(18)], [D(9), D(16)], [D(10), D(17)]) == [D(2), D(8)]


def test_bollinger_by_hand() -> None:
    result = ind.bollinger([D(2), D(4), D(4), D(4), D(5), D(5), D(7), D(9)], 8, D(2))
    # The textbook sample: mean 5, population standard deviation exactly 2.
    assert result.middle[-1] == D(5)
    assert result.upper[-1] == D(9) and result.lower[-1] == D(1)
    assert result.bandwidth[-1] == D("1.6")


def test_macd_histogram_is_the_difference() -> None:
    r = ind.macd(series(5, 80))
    for m, s, h in zip(r.macd, r.signal, r.histogram, strict=True):
        assert (h is None) == (m is None or s is None)
        if h is not None and m is not None and s is not None:
            assert h == m - s


# --------------------------------------------------------------- warm-up and edge cases
def test_warmups_are_exact() -> None:
    x = series(9)
    h, lo, c = bars(9)
    assert ind.sma(x, 10).index(next(v for v in ind.sma(x, 10) if v is not None)) == 9
    assert next(i for i, v in enumerate(ind.ema(x, 10)) if v is not None) == 9
    assert next(i for i, v in enumerate(ind.rsi(x, 14)) if v is not None) == 14
    assert next(i for i, v in enumerate(ind.atr(h, lo, c, 14)) if v is not None) == 13
    r = ind.macd(x, 12, 26, 9)
    assert next(i for i, v in enumerate(r.macd) if v is not None) == 25
    assert next(i for i, v in enumerate(r.signal) if v is not None) == 33
    a = ind.adx(h, lo, c, 14)
    assert next(i for i, v in enumerate(a.plus_di) if v is not None) == 14
    assert next(i for i, v in enumerate(a.adx) if v is not None) == 27
    assert next(i for i, v in enumerate(ind.roc(x, 12)) if v is not None) == 12
    assert next(i for i, v in enumerate(ind.bollinger(x, 20).upper) if v is not None) == 19
    s = ind.stochastic(h, lo, c, 14, 3, 3)
    assert next(i for i, v in enumerate(s.k) if v is not None) == 15
    assert next(i for i, v in enumerate(s.d) if v is not None) == 17


@pytest.mark.parametrize(
    "fn",
    [
        lambda x: ind.sma(x, 5),
        lambda x: ind.ema(x, 5),
        lambda x: ind.rsi(x, 5),
        lambda x: ind.roc(x, 5),
    ],
)
def test_series_shorter_than_the_warmup_have_no_values(
    fn: Callable[[list[Decimal]], list[Decimal | None]],
) -> None:
    assert fn([D(1), D(2), D(3)]) == [None, None, None]
    assert fn([]) == []


def test_undefined_ratios_are_none_not_zero() -> None:
    flat = [D("1.1")] * 30
    assert all(v is None for v in ind.rsi(flat, 14))
    s = ind.stochastic(flat, flat, flat)
    assert all(v is None for v in s.k) and all(v is None for v in s.d)
    assert all(v is None for v in ind.roc([D(0)] * 5 + [D(1)], 5))
    # A strictly rising series has no losses: RSI is exactly 100.
    assert ind.rsi([D(i) for i in range(1, 20)], 14)[-1] == D(100)
    # A flat range has no directional movement: +DI, -DI and ADX are 0, not undefined.
    a = ind.adx(flat, flat, flat, 5)
    assert a.plus_di[5] == 0 and a.minus_di[5] == 0 and a.adx[9] == 0


def test_stochastic_is_bounded_and_extremes_are_exact() -> None:
    h, lo, c = bars(4)
    for v in ind.stochastic(h, lo, c).k:
        assert v is None or 0 <= v <= 100
    rising = [D(i) for i in range(1, 30)]
    s = ind.stochastic(rising, rising, rising, 5, 3, 1)
    assert s.k[-1] == 100


def test_rsi_adx_and_stochastic_stay_in_range() -> None:
    h, lo, c = bars(11, 200)
    assert all(v is None or 0 <= v <= 100 for v in ind.rsi(c, 14))
    a = ind.adx(h, lo, c, 14)
    for s in (a.plus_di, a.minus_di, a.adx):
        assert all(v is None or 0 <= v <= 100 for v in s)


def test_bad_parameters_are_refused() -> None:
    x = series(1, 30)
    with pytest.raises(ValueError):
        ind.sma(x, 0)
    with pytest.raises(ValueError):
        ind.macd(x, 26, 12)
    with pytest.raises(ValueError):
        ind.bollinger(x, 5, D(0))
    with pytest.raises(ValueError):
        ind.stochastic([D(1)], [D(1), D(2)], [D(1)])
    with pytest.raises(ValueError):
        ind.true_range([D(1)], [D(1)], [])


def test_outputs_are_decimal_and_inputs_are_not_changed() -> None:
    x = series(2)
    before = list(x)
    out = ind.rsi(x) + ind.ema(x, 10) + ind.sma(x, 10)
    assert x == before
    assert all(v is None or isinstance(v, Decimal) for v in out)


# ----------------------------------------------------------------------------- properties
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_no_indicator_depends_on_later_bars(seed: int) -> None:
    """Value i computed on the first i + 1 bars equals value i computed on all bars."""
    h, lo, c = bars(seed, 70)
    full = {
        "sma": ind.sma(c, 10),
        "ema": ind.ema(c, 10),
        "rsi": ind.rsi(c, 14),
        "roc": ind.roc(c, 5),
        "atr": ind.atr(h, lo, c, 14),
        "adx": ind.adx(h, lo, c, 14).adx,
        "macd": ind.macd(c, 5, 12, 4).signal,
        "stoch_d": ind.stochastic(h, lo, c, 9, 3, 3).d,
        "boll": ind.bollinger(c, 10).upper,
    }
    for i in range(0, 70, 7):
        cut = {
            "sma": ind.sma(c[: i + 1], 10),
            "ema": ind.ema(c[: i + 1], 10),
            "rsi": ind.rsi(c[: i + 1], 14),
            "roc": ind.roc(c[: i + 1], 5),
            "atr": ind.atr(h[: i + 1], lo[: i + 1], c[: i + 1], 14),
            "adx": ind.adx(h[: i + 1], lo[: i + 1], c[: i + 1], 14).adx,
            "macd": ind.macd(c[: i + 1], 5, 12, 4).signal,
            "stoch_d": ind.stochastic(h[: i + 1], lo[: i + 1], c[: i + 1], 9, 3, 3).d,
            "boll": ind.bollinger(c[: i + 1], 10).upper,
        }
        for name, values in cut.items():
            assert values[i] == full[name][i], (name, i)


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_scaling_and_shifting_properties(seed: int) -> None:
    x = series(seed)
    scaled = [v * 3 for v in x]
    for a, b in zip(ind.sma(x, 8), ind.sma(scaled, 8), strict=True):
        assert (a is None and b is None) or (
            a is not None and b is not None and abs(a * 3 - b) < D("1e-20")
        )
    for a, b in zip(ind.rsi(x, 14), ind.rsi(scaled, 14), strict=True):  # RSI is scale-free
        assert (a is None and b is None) or (
            a is not None and b is not None and abs(a - b) < D("1e-18")
        )
    shifted = [v + 5 for v in x]
    for a, b in zip(ind.macd(x).macd, ind.macd(shifted).macd, strict=True):  # MACD is shift-free
        assert (a is None and b is None) or (
            a is not None and b is not None and abs(a - b) < D("1e-18")
        )
    for u, m, lo in zip(
        *(getattr(ind.bollinger(x, 10), k) for k in ("upper", "middle", "lower")), strict=True
    ):
        assert (u is None) == (m is None) == (lo is None)
        if u is not None and m is not None and lo is not None:
            assert lo <= m <= u


def test_rsi_matches_the_published_worked_example() -> None:
    """The widely published RSI(14) worked example (Wilder's method; StockCharts ChartSchool, RSI),
    using its 4-decimal closes: the first eight values are 70.53, 66.32, 66.55, 69.41, 66.36,
    57.97, 62.93 and 63.26."""
    closes = [
        "44.3389",
        "44.0902",
        "44.1497",
        "43.6124",
        "44.3278",
        "44.8264",
        "45.0955",
        "45.4245",
        "45.8433",
        "46.0826",
        "45.8931",
        "46.0328",
        "45.6140",
        "46.2820",
        "46.2820",
        "46.0028",
        "46.0328",
        "46.4116",
        "46.2222",
        "45.6439",
        "46.2122",
        "46.2521",
        "45.7137",
        "46.4515",
        "45.7835",
        "45.3548",
        "44.0288",
        "44.1783",
        "44.2181",
        "44.5672",
        "43.4205",
        "42.6628",
        "43.1314",
    ]
    values = [v for v in ind.rsi([D(c) for c in closes], 14) if v is not None]
    published = ["70.53", "66.32", "66.55", "69.41", "66.36", "57.97", "62.93", "63.26"]
    assert [format(v.quantize(D("0.01")), "f") for v in values[:8]] == published


def test_no_floats_in_the_indicator_modules() -> None:
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "app" / "modules" / "forex" / "analysis"
    for name in ("indicators.py", "structure.py", "patterns.py"):
        tree = ast.parse((root / name).read_text(encoding="utf-8"))
        floats = [
            n for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, float)
        ]
        names = [n for n in ast.walk(tree) if isinstance(n, ast.Name) and n.id == "float"]
        assert not floats and not names, name
