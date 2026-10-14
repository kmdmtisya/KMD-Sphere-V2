"""Probability calibration (P13-T05.6, design section 7.3).

A model's probability that the return is positive is recalibrated on the separate calibration
window of each walk-forward fold (isotonic regression with at least 300 calibration rows,
otherwise Platt scaling) and judged on that fold's held-out test rows. The status is
`calibrated` only when, on those held-out rows:
- there are at least `MIN_TEST_ROWS` rows;
- the expected calibration error (10 equal-width bins) is at most `MAX_ECE`;
- no bin with at least 20 rows is off by more than `MAX_BIN_GAP`.
Otherwise the status is `requires_calibration`, and the probability must be labelled so. A
probability is never described as a success rate."""

from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
from numpy.typing import NDArray

Floats = NDArray[np.float64]
MIN_TEST_ROWS = 300
MAX_ECE = 0.05
MAX_BIN_GAP = 0.10
BINS = 10
Status = Literal["calibrated", "requires_calibration"]


@dataclass(frozen=True)
class Bin:
    low: float
    high: float
    count: int
    mean_probability: float
    observed_frequency: float


def reliability(prob: Floats, outcome: Floats, bins: int = BINS) -> list[Bin]:
    edges = np.linspace(0.0, 1.0, bins + 1)
    out = []
    for k in range(bins):
        lo, hi = edges[k], edges[k + 1]
        mask = (prob >= lo) & ((prob < hi) if k < bins - 1 else (prob <= hi))
        n = int(mask.sum())
        out.append(
            Bin(
                float(lo),
                float(hi),
                n,
                float(prob[mask].mean()) if n else float("nan"),
                float(outcome[mask].mean()) if n else float("nan"),
            )
        )
    return out


def ece(prob: Floats, outcome: Floats, bins: int = BINS) -> float:
    n = len(prob)
    if n == 0:
        return float("nan")
    return float(
        sum(
            b.count / n * abs(b.mean_probability - b.observed_frequency)
            for b in reliability(prob, outcome, bins)
            if b.count
        )
    )


class Calibrator:
    """Isotonic regression or Platt scaling fitted on calibration-window probabilities."""

    def __init__(self, method: Literal["isotonic", "platt"]) -> None:
        self.method = method
        self._model: Any = None

    def fit(self, prob: Floats, outcome: Floats) -> "Calibrator":
        if len(set(outcome.tolist())) < 2:
            self._model = None  # one class only: leave probabilities unchanged
            return self
        if self.method == "isotonic":
            from sklearn.isotonic import IsotonicRegression

            self._model = IsotonicRegression(y_min=0.001, y_max=0.999, out_of_bounds="clip").fit(
                prob, outcome
            )
        else:
            from sklearn.linear_model import LogisticRegression

            self._model = LogisticRegression().fit(_logit(prob)[:, None], outcome.astype(np.int64))
        return self

    def apply(self, prob: Floats) -> Floats:
        if self._model is None:
            return prob
        if self.method == "isotonic":
            return np.asarray(self._model.predict(prob), dtype=np.float64)
        return np.asarray(self._model.predict_proba(_logit(prob)[:, None])[:, 1], dtype=np.float64)


def _logit(p: Floats) -> Floats:
    q = np.clip(p, 1e-6, 1 - 1e-6)
    return np.asarray(np.log(q / (1 - q)), dtype=np.float64)


@dataclass(frozen=True)
class Calibration:
    method: str
    test_rows: int
    ece_raw: float
    ece_calibrated: float
    worst_bin_gap: float
    status: Status
    bins: list[Bin]


def assess(raw: Floats, calibrated: Floats, outcome: Floats, method: str) -> Calibration:
    """Judge the out-of-sample probabilities that would be published (recalibrated on separate
    calibration windows, or the model's own when recalibration did not help: `method` "none")."""
    bins = reliability(calibrated, outcome)
    gaps = [abs(b.mean_probability - b.observed_frequency) for b in bins if b.count >= 20]
    worst = max(gaps) if gaps else float("nan")
    after = ece(calibrated, outcome)
    ok = (
        len(calibrated) >= MIN_TEST_ROWS
        and after <= MAX_ECE
        and bool(gaps)
        and worst <= MAX_BIN_GAP
    )
    return Calibration(
        method=method,
        test_rows=len(calibrated),
        ece_raw=ece(raw, outcome),
        ece_calibrated=after,
        worst_bin_gap=worst,
        status="calibrated" if ok else "requires_calibration",
        bins=bins,
    )
