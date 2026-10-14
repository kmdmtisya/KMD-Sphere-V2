"""Drift monitoring (P13-T05.7, design section 7.3).

Checks, comparing the most recent rows with the model's training rows:
- feature drift: the population stability index (PSI, 10 bins from training deciles) and a
  two-sample Kolmogorov-Smirnov test for every feature;
- error drift: the model's mean log loss over the recent rows against the random walk's.
Breach rules. Rolling features (volatility over 30 bars, RSI) are strongly persistent, so a PSI over
a few hundred recent bars is noisy even for an unchanged process. Single-feature drift is therefore
reported, not acted on. A breach needs one of:
- broad feature drift: PSI above `MAX_PSI` on at least half of the features;
- extreme drift on one feature: PSI above `EXTREME_PSI`;
- error drift: a recent log loss worse than the random walk's by more than `MAX_SKILL_LOSS`.
A breach disables the model's forecasts for the pair. They show as unavailable until
retraining is approved (`store.approve_retraining`)."""

from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray
from scipy.stats import ks_2samp

Floats = NDArray[np.float64]
MAX_PSI = 0.25
EXTREME_PSI = 2.0
MAX_SKILL_LOSS = 0.02
MIN_ROWS = 50


def psi(reference: Floats, current: Floats, bins: int = 10) -> float:
    ref = reference[np.isfinite(reference)]
    cur = current[np.isfinite(current)]
    if len(ref) < MIN_ROWS or len(cur) < MIN_ROWS:
        return float("nan")
    edges = np.unique(np.quantile(ref, np.linspace(0, 1, bins + 1)))
    if len(edges) < 3:
        return 0.0  # a constant feature cannot drift by this measure
    edges[0], edges[-1] = -np.inf, np.inf
    r = np.histogram(ref, edges)[0] / len(ref)
    c = np.histogram(cur, edges)[0] / len(cur)
    r, c = np.clip(r, 1e-4, None), np.clip(c, 1e-4, None)
    return float(np.sum((c - r) * np.log(c / r)))


@dataclass
class DriftReport:
    feature_psi: dict[str, float]  # all reported; see the breach rules above
    feature_ks_p: dict[str, float]
    recent_log_loss: float | None
    recent_random_walk_log_loss: float | None
    status: str = "ok"  # ok or breached
    reasons: list[str] = field(default_factory=list)


def check(
    names: Sequence[str],
    reference: Floats,
    current: Floats,
    recent_loss: Floats | None = None,
    recent_random_walk_loss: Floats | None = None,
) -> DriftReport:
    if reference.shape[1] != len(names) or current.shape[1] != len(names):
        raise ValueError("feature matrices must match the names")
    psis: dict[str, float] = {}
    ks: dict[str, float] = {}
    reasons: list[str] = []
    for j, name in enumerate(names):
        value = psi(reference[:, j], current[:, j])
        psis[name] = value
        a, b = reference[:, j], current[:, j]
        a, b = a[np.isfinite(a)], b[np.isfinite(b)]
        ks[name] = (
            float(ks_2samp(a, b).pvalue)
            if len(a) >= MIN_ROWS and len(b) >= MIN_ROWS
            else float("nan")
        )
        if np.isfinite(value) and value > EXTREME_PSI:
            reasons.append(f"extreme feature drift: {name} PSI {value:.3f} > {EXTREME_PSI}")
    drifting = [n for n, v in psis.items() if np.isfinite(v) and v > MAX_PSI]
    if len(drifting) * 2 >= len(names) and drifting:
        reasons.append(
            f"broad feature drift: PSI > {MAX_PSI} on {len(drifting)} of {len(names)} features"
        )
    mine = theirs = None
    if (
        recent_loss is not None
        and recent_random_walk_loss is not None
        and len(recent_loss) >= MIN_ROWS
    ):
        mine, theirs = float(np.mean(recent_loss)), float(np.mean(recent_random_walk_loss))
        if mine - theirs > MAX_SKILL_LOSS:
            reasons.append(
                f"error drift: recent log loss {mine:.4f} is worse than the random walk's "
                f"{theirs:.4f}"
            )
    return DriftReport(psis, ks, mine, theirs, "breached" if reasons else "ok", reasons)
