"""The feature pipeline (P13-T05.1). Point in time: the features of bar t use bars 0..t only,
and the label of bar t is the forward log return over the horizon, ln(close[t+h] / close[t]).
A test rebuilds the features on every prefix and checks they are unchanged.

Features (all dimensionless):
- `ret_k`: log return over the last k bars (k = 1, 2, 3, 5, 10);
- `vol_n`: standard deviation of the last n one-bar log returns (n = 10, 30);
- `rsi_14`: RSI(14) / 100 (P13-T03, Wilder);
- `macd_hist`: MACD(12, 26, 9) histogram / close;
- `boll_pctb`: position within Bollinger(20, 2): (close - lower) / (upper - lower);
- `atr_ratio`: ATR(14) / close;
- `event_window`: 1 when an economic-event risk window (P13-T04) covers the bar's close, else 0.
Undefined values are NaN; rows with any NaN are not used."""

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

import numpy as np
from numpy.typing import NDArray

from app.modules.forex.analysis import indicators as ind

FEATURES = (
    "ret_1",
    "ret_2",
    "ret_3",
    "ret_5",
    "ret_10",
    "vol_10",
    "vol_30",
    "rsi_14",
    "macd_hist",
    "boll_pctb",
    "atr_ratio",
    "event_window",
)
FEATURE_SET_VERSION = 1
Floats = NDArray[np.float64]


def feature_set_hash() -> str:
    raw = json.dumps({"version": FEATURE_SET_VERSION, "features": FEATURES}, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _f(values: Sequence[Decimal | None]) -> Floats:
    return np.array([np.nan if v is None else float(v) for v in values], dtype=np.float64)


@dataclass(frozen=True)
class Matrix:
    names: tuple[str, ...]
    x: Floats  # bars x features, NaN where undefined
    r1: Floats  # one-bar log returns (NaN for the first bar)


def build(
    close: Sequence[Decimal],
    high: Sequence[Decimal],
    low: Sequence[Decimal],
    event_window: Sequence[bool] | None = None,
) -> Matrix:
    n = len(close)
    if not len(high) == len(low) == n:
        raise ValueError("close, high and low must have the same length")
    if event_window is not None and len(event_window) != n:
        raise ValueError("event_window must have one value per bar")
    c = _f(close)
    logc = np.log(c) if n else c
    r1 = np.full(n, np.nan)
    if n > 1:
        r1[1:] = np.diff(logc)
    cols: list[Floats] = []
    for k in (1, 2, 3, 5, 10):
        col = np.full(n, np.nan)
        if n > k:
            col[k:] = logc[k:] - logc[:-k]
        cols.append(col)
    for w in (10, 30):
        col = np.full(n, np.nan)
        for t in range(w, n):
            col[t] = float(np.std(r1[t - w + 1 : t + 1]))
        cols.append(col)
    cols.append(_f(ind.rsi(close, 14)) / 100)
    cols.append(_f(ind.macd(close).histogram) / c if n else np.array([]))
    bb = ind.bollinger(close, 20)
    upper, lower = _f(bb.upper), _f(bb.lower)
    with np.errstate(divide="ignore", invalid="ignore"):
        width = upper - lower
        pctb = np.where(width > 0, (c - lower) / width, np.nan)
    cols.append(pctb)
    cols.append(_f(ind.atr(high, low, close, 14)) / c if n else np.array([]))
    cols.append(
        np.array([1.0 if e else 0.0 for e in event_window], dtype=np.float64)
        if event_window is not None
        else np.zeros(n)
    )
    x = np.column_stack(cols) if n else np.empty((0, len(FEATURES)))
    return Matrix(FEATURES, x, r1)


def labels(close: Sequence[Decimal], horizon: int) -> Floats:
    """Forward log return over `horizon` bars; NaN where the future is not known yet."""
    if horizon < 1:
        raise ValueError("horizon must be at least 1")
    c = _f(close)
    y = np.full(len(c), np.nan)
    if len(c) > horizon:
        y[:-horizon] = np.log(c[horizon:]) - np.log(c[:-horizon])
    return y


def data_hash(timestamps: Sequence[object], close: Sequence[Decimal]) -> str:
    """Fingerprint of the data a model was trained on (reproducibility)."""
    digest = hashlib.sha256()
    for t, c in zip(timestamps, close, strict=True):
        digest.update(f"{t}|{c}\n".encode())
    return digest.hexdigest()[:16]
