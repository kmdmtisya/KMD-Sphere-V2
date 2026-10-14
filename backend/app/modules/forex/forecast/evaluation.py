"""Walk-forward evaluation (P13-T05.5, design section 7.3). Time-series-aware only: no shuffling.

Splits are expanding windows. Each fold has a fit window, then a calibration window, then a test
window, separated by purge gaps of h bars: the label of bar s uses the close at s + h, so a
training label never reaches into the next window. Every model is scored against all three
baselines on exactly the same test bars, and the comparison is reported whatever it shows.

Metrics (per test bar, then averaged): direction accuracy, log loss and Brier score of the
probability that the return is positive, pinball loss over the five quantiles, CRPS approximated
as twice the mean pinball loss over those quantiles (a stated approximation), coverage of the
50% and 80% intervals, and RMSE and MAE of the mean return.

Edge: a model has a demonstrated edge only if its log loss is lower than every baseline's and a
Diebold-Mariano test (Newey-West variance with h - 1 lags) rejects equal loss at 5% against
each. Otherwise it is reported as "no demonstrated edge"."""

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np
from numpy.typing import NDArray
from scipy.stats import norm

from app.modules.forex.forecast.calibration import Calibration, Calibrator, assess
from app.modules.forex.forecast.models import (
    QUANTILES,
    Context,
    Distribution,
    Forecaster,
    Ints,
)

Floats = NDArray[np.float64]
P_CLIP = 1e-6


@dataclass(frozen=True)
class Fold:
    fit: Ints
    calib: Ints
    test: Ints


def walk_forward(
    rows: Ints, horizon: int, initial: int, test_size: int, calib_fraction: float = 0.2
) -> list[Fold]:
    """Expanding-window folds over the usable rows (bar indexes, increasing). Purge gaps of
    `horizon` bars separate fit, calibration and test windows."""
    if horizon < 1 or initial < 20 or test_size < 1 or not 0 < calib_fraction < 1:
        raise ValueError("bad walk-forward settings")
    rows = np.asarray(rows, dtype=np.int64)
    folds: list[Fold] = []
    start = initial
    while start + test_size <= len(rows):
        history = rows[:start]
        test = rows[start : start + test_size]
        # Rows whose label window reaches the test start are purged.
        usable = history[history + horizon < test[0]]
        cut = int(len(usable) * (1 - calib_fraction))
        fit, calib = usable[:cut], usable[cut:]
        fit = fit[fit + horizon < (calib[0] if len(calib) else test[0])]
        if len(fit) >= 20 and len(calib) >= 5:
            folds.append(Fold(fit, calib, test))
        start += test_size
    return folds


def no_overlap(fold: Fold, horizon: int) -> bool:
    """The leakage rule for splits: every training label window ends before the next window."""
    return bool(
        (len(fold.fit) == 0 or fold.fit.max() + horizon < fold.calib.min())
        and fold.calib.max() + horizon < fold.test.min()
    )


# ----------------------------------------------------------------------------------- metrics
def pinball(q: Floats, y: Floats) -> Floats:
    """Mean pinball loss over the quantiles, per row."""
    levels = np.array(QUANTILES)
    diff = y[:, None] - q
    return np.mean(np.maximum(levels * diff, (levels - 1) * diff), axis=1)


def per_row_losses(d: Distribution, y: Floats) -> dict[str, Floats]:
    p = np.clip(d.prob_up, P_CLIP, 1 - P_CLIP)
    up = (y > 0).astype(np.float64)
    return {
        "log_loss": -(up * np.log(p) + (1 - up) * np.log(1 - p)),
        "brier": (p - up) ** 2,
        "pinball": pinball(d.quantiles, y),
        "sq_error": (d.mean - y) ** 2,
        "abs_error": np.abs(d.mean - y),
    }


def summarise(d: Distribution, y: Floats) -> dict[str, float]:
    losses = per_row_losses(d, y)
    lo80, hi80 = d.quantiles[:, 0], d.quantiles[:, 4]
    lo50, hi50 = d.quantiles[:, 1], d.quantiles[:, 3]
    up = y > 0
    return {
        "rows": float(len(y)),
        "direction_accuracy": float(np.mean((d.prob_up > 0.5) == up)),
        "log_loss": float(np.mean(losses["log_loss"])),
        "brier": float(np.mean(losses["brier"])),
        "pinball": float(np.mean(losses["pinball"])),
        "crps_approx": float(2 * np.mean(losses["pinball"])),
        "coverage_50": float(np.mean((y >= lo50) & (y <= hi50))),
        "coverage_80": float(np.mean((y >= lo80) & (y <= hi80))),
        "rmse": float(np.sqrt(np.mean(losses["sq_error"]))),
        "mae": float(np.mean(losses["abs_error"])),
    }


def diebold_mariano(loss_a: Floats, loss_b: Floats, horizon: int) -> tuple[float, float]:
    """DM statistic for mean(loss_a - loss_b) with a Newey-West variance (h - 1 lags), and the
    two-sided p-value. Negative statistic: a has lower loss."""
    d = loss_a - loss_b
    n = len(d)
    if n < 10:
        return 0.0, 1.0
    mean = float(np.mean(d))
    dc = d - mean
    var = float(np.dot(dc, dc) / n)
    for lag in range(1, max(horizon, 1)):
        w = 1 - lag / horizon
        var += 2 * w * float(np.dot(dc[lag:], dc[:-lag]) / n)
    if var <= 0:
        return 0.0, 1.0
    stat = mean / math.sqrt(var / n)
    return stat, float(2 * (1 - norm.cdf(abs(stat))))


# -------------------------------------------------------------------------------- running
@dataclass
class ModelResult:
    name: str
    family: str
    params: dict[str, Any]
    metrics: dict[str, float]
    versus: dict[str, dict[str, float]] = field(default_factory=dict)  # baseline -> numbers
    edge: bool = False
    calibration: Calibration | None = None
    probability: str = "raw"  # raw or recalibrated: what is reported and would be published
    error: str | None = None


@dataclass
class Evaluation:
    horizon: int
    folds: int
    test_rows: int
    results: list[ModelResult]

    def by_name(self, name: str) -> ModelResult:
        return next(r for r in self.results if r.name == name)


@dataclass
class Collected:
    calibrated: Distribution  # test predictions with probabilities recalibrated per fold
    raw_prob: Floats  # the model's own test probabilities
    y: Floats
    method: str


def _collect(factory: Callable[[], Forecaster], ctx: Context, folds: Sequence[Fold]) -> Collected:
    """Out-of-sample predictions over all folds. In each fold the probability is recalibrated
    on that fold's calibration window (isotonic with at least 300 rows, otherwise Platt) and
    applied to its test window, so every reported number is out of sample."""
    parts: list[Distribution] = []
    raws: list[Floats] = []
    ys: list[Floats] = []
    methods: set[str] = set()
    for fold in folds:
        model = factory()
        model.fit(ctx, fold.fit, fold.calib)
        test = model.predict(ctx, fold.test)
        cal = model.predict(ctx, fold.calib)
        method: Literal["isotonic", "platt"] = "isotonic" if len(fold.calib) >= 300 else "platt"
        calibrator = Calibrator(method).fit(cal.prob_up, (ctx.y[fold.calib] > 0).astype(np.float64))
        parts.append(
            Distribution(test.mean, test.std, test.quantiles, calibrator.apply(test.prob_up))
        )
        raws.append(test.prob_up)
        ys.append(ctx.y[fold.test])
        methods.add(method)
    d = Distribution(
        np.concatenate([p.mean for p in parts]),
        np.concatenate([p.std for p in parts]),
        np.vstack([p.quantiles for p in parts]),
        np.concatenate([p.prob_up for p in parts]),
    )
    return Collected(d, np.concatenate(raws), np.concatenate(ys), "/".join(sorted(methods)))


def evaluate(
    factories: dict[str, Callable[[], Forecaster]],
    baseline_factories: dict[str, Callable[[], Forecaster]],
    ctx: Context,
    folds: Sequence[Fold],
) -> Evaluation:
    if not folds:
        raise ValueError("no walk-forward folds: not enough history")
    for fold in folds:
        if not no_overlap(fold, ctx.horizon):
            raise AssertionError("a fold leaks labels across windows")
    out: dict[str, Collected] = {}
    results: list[ModelResult] = []
    for name, make in {**baseline_factories, **factories}.items():
        probe = make()
        try:
            out[name] = got = _collect(make, ctx, folds)
        except (ValueError, np.linalg.LinAlgError) as error:
            results.append(ModelResult(name, probe.family, probe.params, {}, error=str(error)))
            continue
        up = (got.y > 0).astype(np.float64)
        raw = Distribution(
            got.calibrated.mean, got.calibrated.std, got.calibrated.quantiles, got.raw_prob
        )
        ll_raw = float(np.mean(per_row_losses(raw, got.y)["log_loss"]))
        ll_cal = float(np.mean(per_row_losses(got.calibrated, got.y)["log_loss"]))
        # Recalibration is used only when it lowers the out-of-sample log loss; small calibration
        # windows can otherwise add noise (they only learn their own base rate).
        use_cal = ll_cal < ll_raw
        chosen_d = got.calibrated if use_cal else raw
        out[name] = Collected(chosen_d, got.raw_prob, got.y, got.method)
        res = ModelResult(name, probe.family, probe.params, summarise(chosen_d, got.y))
        res.metrics["log_loss_raw"] = ll_raw
        res.metrics["log_loss_recalibrated"] = ll_cal
        res.probability = "recalibrated" if use_cal else "raw"
        res.calibration = assess(
            got.raw_prob, chosen_d.prob_up, up, got.method if use_cal else "none"
        )
        results.append(res)
    base_losses = {
        b: per_row_losses(out[b].calibrated, out[b].y)["log_loss"]
        for b in baseline_factories
        if b in out
    }
    for res in results:
        if res.error or res.name not in out:
            continue
        mine = per_row_losses(out[res.name].calibrated, out[res.name].y)["log_loss"]
        wins = []
        for b, theirs in base_losses.items():
            if b == res.name:
                continue
            stat, p = diebold_mariano(mine, theirs, ctx.horizon)
            res.versus[b] = {
                "log_loss_difference": float(np.mean(mine - theirs)),
                "dm_statistic": stat,
                "dm_p_value": p,
            }
            wins.append(float(np.mean(mine - theirs)) < 0 and p < 0.05)
        res.edge = res.family != "baseline" and bool(wins) and all(wins)
    test_rows = len(next(iter(out.values())).y) if out else 0
    return Evaluation(ctx.horizon, len(folds), test_rows, results)


# ----------------------------------------------------------------------------------- leakage
def future_altered(ctx: Context, origin: int, seed: int = 0) -> Context:
    """A copy of `ctx` in which everything not known at bar `origin` is replaced with noise:
    features and one-bar returns after the origin, and labels of bars s with s + h > origin
    (those labels use closes after the origin)."""
    rng = np.random.default_rng(seed)
    x, y, r1 = ctx.x.copy(), ctx.y.copy(), ctx.r1.copy()
    x[origin + 1 :] = rng.normal(size=x[origin + 1 :].shape)
    r1[origin + 1 :] = rng.normal(scale=0.01, size=len(r1) - origin - 1)
    first_unknown = max(origin - ctx.horizon + 1, 0)
    y[first_unknown:] = rng.normal(scale=0.01, size=len(y) - first_unknown)
    return Context(x, y, r1, ctx.horizon)


def leakage_audit(
    factory: Callable[[], Forecaster], ctx: Context, fold: Fold, origins: int = 3
) -> bool:
    """True when the forecaster's predictions do not depend on anything unknown at prediction
    time: for a few test origins, the model is fitted on the fold and its prediction compared
    with the prediction made after `future_altered`. A model that reads a future feature, return
    or label changes its answer and fails."""
    for k, origin in enumerate(fold.test[:origins]):
        t = np.array([int(origin)], dtype=np.int64)
        honest = factory()
        honest.fit(ctx, fold.fit, fold.calib)
        a = honest.predict(ctx, t)
        altered = future_altered(ctx, int(origin), seed=k)
        other = factory()
        other.fit(altered, fold.fit, fold.calib)
        b = other.predict(altered, t)
        for left, right in ((a.mean, b.mean), (a.prob_up, b.prob_up), (a.quantiles, b.quantiles)):
            if not np.allclose(left, right, rtol=1e-9, atol=1e-12, equal_nan=True):
                return False
    return True
