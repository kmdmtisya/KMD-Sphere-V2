"""Technical indicators (P13-T03.1, T03.2, design section 5). Pure functions over price series.

Conventions, stated once and tested against an independent exact-arithmetic oracle:
- Input and output are `Decimal`. Arithmetic runs at the default 28 significant digits; the API
  rounds half-up to 8 decimals for display only.
- Every output list has the same length as its input. Position i is `None` until the indicator has
  enough history (the warm-up); nothing is guessed or back-filled.
- A ratio whose denominator is zero is `None` (undefined), except where the limit is exact and
  stated (RSI with no losses is 100; a flat range gives directional index 0).
- Smoothing: SMA is the plain mean. EMA uses alpha = 2 / (n + 1), seeded with the SMA of the first
  n values. RSI, ATR and ADX use Wilder smoothing (alpha = 1 / n), seeded with the plain mean (or,
  for the ADX components, the sum) of the first n values.
- Bollinger Bands use the population standard deviation of the window.
- Indicators look only backwards: value i depends on values 0..i. A test checks this.
No indicator is computed by, or editable by, a language model."""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

Series = list[Decimal | None]
ZERO = Decimal(0)
ONE = Decimal(1)
HUNDRED = Decimal(100)


def _check(period: int, size: int, minimum: int = 1) -> None:
    if period < minimum:
        raise ValueError(f"period must be at least {minimum}")
    if size < 0:  # pragma: no cover - sizes are never negative
        raise ValueError("size")


def sma(values: Sequence[Decimal], period: int) -> Series:
    """Simple moving average of the last `period` values; first value at index period - 1."""
    _check(period, len(values))
    out: Series = [None] * len(values)
    total = ZERO
    for i, v in enumerate(values):
        total += v
        if i >= period:
            total -= values[i - period]
        if i >= period - 1:
            out[i] = total / period
    return out


def ema(values: Sequence[Decimal], period: int) -> Series:
    """Exponential moving average, alpha = 2 / (period + 1), seeded with the SMA of the first
    `period` values; first value at index period - 1."""
    _check(period, len(values))
    out: Series = [None] * len(values)
    if len(values) < period:
        return out
    alpha = Decimal(2) / (period + 1)
    prev = sum(values[:period], ZERO) / period
    out[period - 1] = prev
    for i in range(period, len(values)):
        prev = prev + alpha * (values[i] - prev)
        out[i] = prev
    return out


@dataclass(frozen=True)
class Macd:
    macd: Series
    signal: Series
    histogram: Series


def macd(values: Sequence[Decimal], fast: int = 12, slow: int = 26, signal: int = 9) -> Macd:
    """MACD line = EMA(fast) - EMA(slow), first at index slow - 1. The signal line is the EMA of
    the MACD line seeded with the SMA of its first `signal` values; histogram = macd - signal."""
    _check(fast, len(values))
    _check(signal, len(values))
    if fast >= slow:
        raise ValueError("fast period must be shorter than slow period")
    f, s = ema(values, fast), ema(values, slow)
    line: Series = [
        a - b if a is not None and b is not None else None for a, b in zip(f, s, strict=True)
    ]
    first = slow - 1
    valid = [v for v in line[first:] if v is not None]
    sig_valid = ema(valid, signal)
    sig: Series = [None] * len(values)
    for k, v in enumerate(sig_valid):
        sig[first + k] = v
    hist: Series = [
        a - b if a is not None and b is not None else None for a, b in zip(line, sig, strict=True)
    ]
    return Macd(line, sig, hist)


def rsi(values: Sequence[Decimal], period: int = 14) -> Series:
    """Relative Strength Index with Wilder smoothing; first value at index `period`.
    100 when there are gains and no losses; `None` while there is neither gain nor loss."""
    _check(period, len(values))
    out: Series = [None] * len(values)
    if len(values) <= period:
        return out
    gains = [max(values[i] - values[i - 1], ZERO) for i in range(1, len(values))]
    losses = [max(values[i - 1] - values[i], ZERO) for i in range(1, len(values))]
    avg_gain = sum(gains[:period], ZERO) / period
    avg_loss = sum(losses[:period], ZERO) / period

    def value(g: Decimal, loss: Decimal) -> Decimal | None:
        if loss == 0:
            return HUNDRED if g > 0 else None
        return HUNDRED - HUNDRED / (ONE + g / loss)

    out[period] = value(avg_gain, avg_loss)
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        out[i + 1] = value(avg_gain, avg_loss)
    return out


@dataclass(frozen=True)
class Stochastic:
    k: Series
    d: Series


def stochastic(
    high: Sequence[Decimal],
    low: Sequence[Decimal],
    close: Sequence[Decimal],
    k_period: int = 14,
    d_period: int = 3,
    smooth: int = 1,
) -> Stochastic:
    """%K = 100 (close - lowest low) / (highest high - lowest low) over `k_period` bars (`None`
    for a flat range), smoothed by an SMA of `smooth` (1 = fast, 3 = slow); %D = SMA of %K over
    `d_period`. An SMA window containing `None` is `None`."""
    n = len(close)
    if not len(high) == len(low) == n:
        raise ValueError("high, low and close must have the same length")
    _check(k_period, n)
    _check(d_period, n)
    _check(smooth, n)
    raw: Series = [None] * n
    for i in range(k_period - 1, n):
        hh = max(high[i - k_period + 1 : i + 1])
        ll = min(low[i - k_period + 1 : i + 1])
        raw[i] = None if hh == ll else HUNDRED * (close[i] - ll) / (hh - ll)
    k = _sma_opt(raw, smooth)
    return Stochastic(k, _sma_opt(k, d_period))


def _sma_opt(values: Series, period: int) -> Series:
    out: Series = [None] * len(values)
    for i in range(period - 1, len(values)):
        window = values[i - period + 1 : i + 1]
        if all(v is not None for v in window):
            out[i] = sum((v for v in window if v is not None), ZERO) / period
    return out


def roc(values: Sequence[Decimal], period: int = 12) -> Series:
    """Rate of change in percent: 100 (v[i] / v[i - period] - 1); first value at index `period`."""
    _check(period, len(values))
    out: Series = [None] * len(values)
    for i in range(period, len(values)):
        base = values[i - period]
        out[i] = None if base == 0 else HUNDRED * (values[i] / base - ONE)
    return out


def true_range(
    high: Sequence[Decimal], low: Sequence[Decimal], close: Sequence[Decimal]
) -> list[Decimal]:
    """True range: high - low for the first bar, then the largest of high - low, |high - previous
    close| and |low - previous close|."""
    if not len(high) == len(low) == len(close):
        raise ValueError("high, low and close must have the same length")
    out = []
    for i in range(len(close)):
        rng = high[i] - low[i]
        if i:
            rng = max(rng, abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
        out.append(rng)
    return out


def atr(
    high: Sequence[Decimal], low: Sequence[Decimal], close: Sequence[Decimal], period: int = 14
) -> Series:
    """Average True Range with Wilder smoothing, seeded with the mean of the first `period` true
    ranges; first value at index period - 1."""
    _check(period, len(close))
    tr = true_range(high, low, close)
    out: Series = [None] * len(tr)
    if len(tr) < period:
        return out
    prev = sum(tr[:period], ZERO) / period
    out[period - 1] = prev
    for i in range(period, len(tr)):
        prev = (prev * (period - 1) + tr[i]) / period
        out[i] = prev
    return out


@dataclass(frozen=True)
class Adx:
    plus_di: Series
    minus_di: Series
    adx: Series


def adx(
    high: Sequence[Decimal], low: Sequence[Decimal], close: Sequence[Decimal], period: int = 14
) -> Adx:
    """Average Directional Index (Wilder). Directional movement and true range are smoothed by
    Wilder's running sum (seeded with the sum of the first `period` values from bar 1); +DI and
    -DI are 100 x smoothed movement / smoothed true range (0 when the range is 0); DX is
    100 |+DI - -DI| / (+DI + -DI) (0 when both are 0). First +DI/-DI at index `period`; ADX is the
    Wilder average of DX, seeded with the mean of the first `period` DX values, first at index
    2 * period - 1."""
    n = len(close)
    _check(period, n)
    tr = true_range(high, low, close)
    plus: Series = [None] * n
    minus: Series = [None] * n
    result: Series = [None] * n
    if n <= period:
        return Adx(plus, minus, result)
    pdm, mdm = [ZERO] * n, [ZERO] * n
    for i in range(1, n):
        up, down = high[i] - high[i - 1], low[i - 1] - low[i]
        pdm[i] = up if up > down and up > 0 else ZERO
        mdm[i] = down if down > up and down > 0 else ZERO
    s_tr = sum(tr[1 : period + 1], ZERO)
    s_p = sum(pdm[1 : period + 1], ZERO)
    s_m = sum(mdm[1 : period + 1], ZERO)
    dx: list[Decimal] = []
    for i in range(period, n):
        if i > period:
            s_tr = s_tr - s_tr / period + tr[i]
            s_p = s_p - s_p / period + pdm[i]
            s_m = s_m - s_m / period + mdm[i]
        p = ZERO if s_tr == 0 else HUNDRED * s_p / s_tr
        m = ZERO if s_tr == 0 else HUNDRED * s_m / s_tr
        plus[i], minus[i] = p, m
        dx.append(ZERO if p + m == 0 else HUNDRED * abs(p - m) / (p + m))
    if len(dx) >= period:
        prev = sum(dx[:period], ZERO) / period
        result[2 * period - 1] = prev
        for k in range(period, len(dx)):
            prev = (prev * (period - 1) + dx[k]) / period
            result[period + k] = prev
    return Adx(plus, minus, result)


@dataclass(frozen=True)
class Bollinger:
    upper: Series
    middle: Series
    lower: Series
    bandwidth: Series


def bollinger(
    values: Sequence[Decimal], period: int = 20, deviations: Decimal = Decimal(2)
) -> Bollinger:
    """Bollinger Bands: middle = SMA; bands = middle +/- `deviations` x the population standard
    deviation of the window; bandwidth = (upper - lower) / middle (`None` if middle is 0)."""
    _check(period, len(values))
    if deviations <= 0:
        raise ValueError("deviations must be positive")
    mid = sma(values, period)
    upper: Series = [None] * len(values)
    lower: Series = [None] * len(values)
    width: Series = [None] * len(values)
    for i, m in enumerate(mid):
        if m is None:
            continue
        window = values[i - period + 1 : i + 1]
        sd = (sum(((x - m) ** 2 for x in window), ZERO) / period).sqrt()
        upper[i], lower[i] = m + deviations * sd, m - deviations * sd
        width[i] = None if m == 0 else (upper[i] - lower[i]) / m  # type: ignore[operator]
    return Bollinger(upper, mid, lower, width)
