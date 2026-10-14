"""An independent oracle for the technical indicators (P13-T03, QG-14.1).

Written from the indicator definitions, in exact rational arithmetic (`fractions.Fraction`), and
by different algorithms from the application's: moving averages are closed-form weighted sums of
the whole history instead of running updates, every window is recomputed from scratch, and
Wilder smoothing is expanded into its geometric weights. `None` is returned where the definition
has no value (warm-up or an undefined ratio)."""

from collections.abc import Sequence
from fractions import Fraction as F

Opt = list[F | None]
Triple = tuple[Opt, Opt, Opt]


def fr(values: Sequence[object]) -> list[F]:
    return [F(str(v)) for v in values]


def sma(x: list[F], n: int) -> list[F | None]:
    return [sum(x[i - n + 1 : i + 1], F(0)) / n if i >= n - 1 else None for i in range(len(x))]


def ema(x: list[F], n: int) -> list[F | None]:
    """Closed form: EMA_t = (1-a)^(t-n+1) SMA_n + a sum_{k=0}^{t-n} (1-a)^k x_{t-k}."""
    a = F(2, n + 1)
    out: list[F | None] = [None] * len(x)
    for t in range(n - 1, len(x)):
        seed = sum(x[:n], F(0)) / n
        out[t] = (1 - a) ** (t - n + 1) * seed + a * sum(
            ((1 - a) ** k * x[t - k] for k in range(t - n + 1)), F(0)
        )
    return out


def wilder(seed: F, inputs: list[F], n: int) -> list[F]:
    """Wilder average after each input: v_k = ((n-1) v_{k-1} + input_k) / n, as weights."""
    out = []
    for k in range(1, len(inputs) + 1):
        w = F(n - 1, n)
        out.append(
            w**k * seed + sum((w ** (k - j) * inputs[j - 1] / n for j in range(1, k + 1)), F(0))
        )
    return out


def macd(x: list[F], fast: int, slow: int, signal: int) -> Triple:
    f, s = ema(x, fast), ema(x, slow)
    line = [a - b if a is not None and b is not None else None for a, b in zip(f, s, strict=True)]
    valid = [v for v in line if v is not None]
    sig_valid = ema(valid, signal)
    sig: Opt = [*([None] * (len(x) - len(valid))), *sig_valid]
    hist = [
        a - b if a is not None and b is not None else None for a, b in zip(line, sig, strict=True)
    ]
    return line, sig, hist


def rsi(x: list[F], n: int) -> list[F | None]:
    gains = [max(x[i] - x[i - 1], F(0)) for i in range(1, len(x))]
    losses = [max(x[i - 1] - x[i], F(0)) for i in range(1, len(x))]
    out: list[F | None] = [None] * len(x)
    if len(x) <= n:
        return out
    g = [sum(gains[:n], F(0)) / n, *wilder(sum(gains[:n], F(0)) / n, gains[n:], n)]
    l_ = [sum(losses[:n], F(0)) / n, *wilder(sum(losses[:n], F(0)) / n, losses[n:], n)]
    for k, (ag, al) in enumerate(zip(g, l_, strict=True)):
        if al == 0:
            out[n + k] = F(100) if ag > 0 else None
        else:
            out[n + k] = 100 - 100 / (1 + ag / al)
    return out


def true_range(h: list[F], lo: list[F], c: list[F]) -> list[F]:
    return [
        h[0] - lo[0],
        *[max(h[i] - lo[i], abs(h[i] - c[i - 1]), abs(lo[i] - c[i - 1])) for i in range(1, len(c))],
    ]


def atr(h: list[F], lo: list[F], c: list[F], n: int) -> list[F | None]:
    tr = true_range(h, lo, c)
    out: list[F | None] = [None] * len(c)
    if len(c) < n:
        return out
    seed = sum(tr[:n], F(0)) / n
    out[n - 1] = seed
    for k, v in enumerate(wilder(seed, tr[n:], n), start=1):
        out[n - 1 + k] = v
    return out


def stochastic(
    h: list[F], lo: list[F], c: list[F], k_n: int, d_n: int, smooth: int
) -> tuple[Opt, Opt]:
    raw: list[F | None] = [None] * len(c)
    for i in range(k_n - 1, len(c)):
        hh, ll = max(h[i - k_n + 1 : i + 1]), min(lo[i - k_n + 1 : i + 1])
        raw[i] = None if hh == ll else 100 * (c[i] - ll) / (hh - ll)

    def smooth_of(v: list[F | None], n: int) -> list[F | None]:
        res: list[F | None] = [None] * len(v)
        for i in range(n - 1, len(v)):
            w = v[i - n + 1 : i + 1]
            res[i] = (
                None
                if any(e is None for e in w)
                else sum((e for e in w if e is not None), F(0)) / n
            )
        return res

    k = smooth_of(raw, smooth)
    return k, smooth_of(k, d_n)


def roc(x: list[F], n: int) -> list[F | None]:
    return [
        None if i < n or x[i - n] == 0 else 100 * (x[i] - x[i - n]) / x[i - n]
        for i in range(len(x))
    ]


def adx(h: list[F], lo: list[F], c: list[F], n: int) -> Triple:
    """Wilder's directional system by an explicit sum over past values (no running recursion)."""
    size = len(c)
    tr = true_range(h, lo, c)
    pdm, mdm = [F(0)] * size, [F(0)] * size
    for i in range(1, size):
        up, down = h[i] - h[i - 1], lo[i - 1] - lo[i]
        pdm[i] = up if up > down and up > 0 else F(0)
        mdm[i] = down if down > up and down > 0 else F(0)

    def smoothed(v: list[F], t: int) -> F:
        # S_n = sum v[1..n] and S_t = S_{t-1} - S_{t-1}/n + v_t give, in closed form,
        # S_t = (1-1/n)^(t-n) S_n + sum_{j>n} (1-1/n)^(t-j) v_j
        w = F(n - 1, n)
        return w ** (t - n) * sum(v[1 : n + 1], F(0)) + sum(
            (w ** (t - j) * v[j] for j in range(n + 1, t + 1)), F(0)
        )

    plus: list[F | None] = [None] * size
    minus: list[F | None] = [None] * size
    dx: dict[int, F] = {}
    for t in range(n, size):
        s_tr, s_p, s_m = smoothed(tr, t), smoothed(pdm, t), smoothed(mdm, t)
        p = F(0) if s_tr == 0 else 100 * s_p / s_tr
        m = F(0) if s_tr == 0 else 100 * s_m / s_tr
        plus[t], minus[t] = p, m
        dx[t] = F(0) if p + m == 0 else 100 * abs(p - m) / (p + m)
    out: list[F | None] = [None] * size
    first = 2 * n - 1
    if size > first:
        seed = sum((dx[t] for t in range(n, 2 * n)), F(0)) / n
        out[first] = seed
        for k, v in enumerate(wilder(seed, [dx[t] for t in range(2 * n, size)], n), start=1):
            out[first + k] = v
    return plus, minus, out


def bollinger(x: list[F], n: int) -> tuple[Opt, Opt]:
    """Returns (middle, variance) per index; the standard deviation is the root of the variance."""
    mid = sma(x, n)
    var: list[F | None] = [None] * len(x)
    for i in range(n - 1, len(x)):
        m = mid[i]
        assert m is not None
        var[i] = sum(((v - m) ** 2 for v in x[i - n + 1 : i + 1]), F(0)) / n
    return mid, var
