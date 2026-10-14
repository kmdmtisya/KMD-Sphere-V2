"""One training run for a pair and a horizon (P13-T05): features, labels, walk-forward folds,
evaluation of every model against the baselines, calibration, the volatility forecast, drift, and
the forecast to publish for the latest closed bar.

What is published:
- the model with a demonstrated edge and the lowest out-of-sample log loss; or, when no model
  beats the baselines, the **random-walk baseline**, stated as such ("no demonstrated edge");
- the probability recalibrated on the calibration window when recalibration lowered the
  out-of-sample log loss (otherwise the model's own), labelled `calibrated` only when the held-out
  walk-forward check passed and `requires_calibration` otherwise;
- price intervals = last close x exp(return quantile), converted to `Decimal` at the instrument's
  display precision (rounded half-up; a statistical interval, not a guarantee)."""

import hashlib
import json
import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Literal

import numpy as np

from app.modules.forex.forecast import features as feat
from app.modules.forex.forecast import models as mdl
from app.modules.forex.forecast.calibration import Calibration, Calibrator
from app.modules.forex.forecast.drift import DriftReport, check
from app.modules.forex.forecast.evaluation import (
    Evaluation,
    evaluate,
    per_row_losses,
    walk_forward,
)
from app.modules.forex.marketdata.types import Timeframe

CODE_VERSION = "fx-forecast-1"
# Horizon -> (bar timeframe, bars ahead).
HORIZONS: dict[str, tuple[Timeframe, int]] = {
    "15m": (Timeframe.M5, 3),
    "1h": (Timeframe.M15, 4),
    "4h": (Timeframe.H1, 4),
    "24h": (Timeframe.H4, 6),
    "1w": (Timeframe.D1, 5),
}
MIN_ROWS = 400


class InsufficientHistory(ValueError):
    pass


@dataclass(frozen=True)
class Series:
    timestamps: Sequence[datetime]
    close: Sequence[Decimal]
    high: Sequence[Decimal]
    low: Sequence[Decimal]
    event_window: Sequence[bool] | None = None


@dataclass
class Published:
    horizon: str
    timeframe: Timeframe
    bars_ahead: int
    as_of: datetime
    last_close: Decimal
    model: str
    family: str
    edge: bool
    prob_up: float
    prob_up_raw: float
    return_quantiles: list[float]
    expected_volatility: float
    volatility_model: str
    price_quantiles: list[Decimal]
    calibration: Calibration | None


@dataclass
class Run:
    evaluation: Evaluation
    published: Published
    drift: DriftReport
    volatility: dict[str, float]
    feature_set_hash: str
    data_snapshot_hash: str
    code_version: str
    seed: int
    train_rows: int

    @property
    def version(self) -> str:
        chosen = self.evaluation.by_name(self.published.model)
        raw = json.dumps(
            [
                chosen.name,
                chosen.params,
                self.feature_set_hash,
                self.data_snapshot_hash,
                self.code_version,
                self.seed,
            ],
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _factories(seed: int) -> dict[str, Callable[[], mdl.Forecaster]]:
    return {
        "arima": lambda: mdl.Arima(),
        "random_forest": lambda: mdl.TreeModel("random_forest", seed),
        "lightgbm": lambda: mdl.TreeModel("lightgbm", seed),
        "xgboost": lambda: mdl.TreeModel("xgboost", seed),
        "ensemble": lambda: mdl.Ensemble(
            [
                mdl.Arima(),
                mdl.TreeModel("random_forest", seed),
                mdl.TreeModel("lightgbm", seed),
                mdl.TreeModel("xgboost", seed),
            ]
        ),
    }


BASELINE_FACTORIES: dict[str, Callable[[], mdl.Forecaster]] = {
    "no_change": mdl.NoChange,
    "random_walk": mdl.RandomWalk,
    "drift": mdl.Drift,
}


def _final_split(rows: np.ndarray, horizon: int) -> tuple[np.ndarray, np.ndarray]:
    cut = int(len(rows) * 0.8)
    calib = rows[cut:]
    fit = rows[:cut]
    fit = fit[fit + horizon < calib[0]]
    return fit, calib


def _price(last: Decimal, log_return: float, places: int) -> Decimal:
    value = last * Decimal(repr(float(np.exp(log_return))))
    return value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)


def run(
    series: Series,
    horizon: str,
    display_precision: int,
    seed: int = 7,
    factories: dict[str, Callable[[], mdl.Forecaster]] | None = None,
) -> Run:
    if horizon not in HORIZONS:
        raise ValueError("unknown horizon")
    timeframe, h = HORIZONS[horizon]
    m = feat.build(series.close, series.high, series.low, series.event_window)
    y = feat.labels(series.close, h)
    ctx = mdl.Context(m.x, y, m.r1, h)
    rows = np.flatnonzero(np.isfinite(m.x).all(axis=1) & np.isfinite(y)).astype(np.int64)
    if len(rows) < MIN_ROWS:
        raise InsufficientHistory(f"{len(rows)} usable bars; at least {MIN_ROWS} are needed")
    test_size = max(50, len(rows) // 8)
    folds = walk_forward(rows, h, initial=len(rows) // 2, test_size=test_size)
    chosen_factories = factories if factories is not None else _factories(seed)
    evaluation = evaluate(chosen_factories, BASELINE_FACTORIES, ctx, folds)

    with_edge = [r for r in evaluation.results if r.edge and not r.error]
    chosen = (
        min(with_edge, key=lambda r: r.metrics["log_loss"])
        if with_edge
        else evaluation.by_name("random_walk")
    )
    make = {**BASELINE_FACTORIES, **chosen_factories}[chosen.name]

    fit, calib = _final_split(rows, h)
    model = make()
    model.fit(ctx, fit, calib)
    last = len(series.close) - 1
    if not np.isfinite(m.x[last]).all():
        raise InsufficientHistory("the latest bar has undefined features")
    latest = model.predict(ctx, np.array([last], dtype=np.int64))
    raw_prob = float(latest.prob_up[0])
    prob = raw_prob
    # Recalibrated on the final calibration window only when recalibration helped out of sample;
    # the label (calibrated or requires calibration) comes from the held-out walk-forward check.
    if chosen.probability == "recalibrated":
        method: Literal["isotonic", "platt"] = "isotonic" if len(calib) >= 300 else "platt"
        cal_pred = model.predict(ctx, calib).prob_up
        calibrator = Calibrator(method).fit(cal_pred, (y[calib] > 0).astype(np.float64))
        prob = float(calibrator.apply(np.array([raw_prob]))[0])

    # Volatility: HAR when it can be fitted, otherwise EWMA; both scored on the test folds.
    vol_scores: dict[str, float] = {}
    realised = np.sqrt(np.maximum(mdl.Har(h).target(m.r1), 0))
    ewma = mdl.ewma_vol(m.r1, h)
    test_rows = np.concatenate([f.test for f in folds])
    ok = np.isfinite(realised[test_rows]) & np.isfinite(ewma[test_rows])
    vol_scores["ewma_rmse"] = float(
        np.sqrt(np.mean((ewma[test_rows][ok] - realised[test_rows][ok]) ** 2))
    )
    vol_model, vol_value = "ewma", float(ewma[last])
    try:
        har_pred = np.full(len(m.r1), np.nan)
        for fold in folds:
            har = mdl.Har(h)
            har.fit(m.r1, fold.fit)
            har_pred[fold.test] = har.predict(m.r1, fold.test)
        okh = np.isfinite(realised[test_rows]) & np.isfinite(har_pred[test_rows])
        vol_scores["har_rmse"] = float(
            np.sqrt(np.mean((har_pred[test_rows][okh] - realised[test_rows][okh]) ** 2))
        )
        if vol_scores["har_rmse"] < vol_scores["ewma_rmse"]:
            final_har = mdl.Har(h)
            final_har.fit(m.r1, fit)
            vol_model, vol_value = (
                "har",
                float(final_har.predict(m.r1, np.array([last], dtype=np.int64))[0]),
            )
    except (ValueError, np.linalg.LinAlgError):
        pass

    # Drift: training features against the most recent rows; recent loss against the random walk.
    last_fold = folds[-1]
    recent_model, recent_rw = make(), mdl.RandomWalk()
    recent_model.fit(ctx, last_fold.fit, last_fold.calib)
    recent_rw.fit(ctx, last_fold.fit, last_fold.calib)
    yt = y[last_fold.test]
    drift = check(
        m.names,
        m.x[fit],
        m.x[rows[-min(200, len(rows)) :]],
        per_row_losses(recent_model.predict(ctx, last_fold.test), yt)["log_loss"],
        per_row_losses(recent_rw.predict(ctx, last_fold.test), yt)["log_loss"],
    )

    last_close = series.close[last]
    published = Published(
        horizon=horizon,
        timeframe=timeframe,
        bars_ahead=h,
        as_of=series.timestamps[last],
        last_close=last_close,
        model=chosen.name,
        family=chosen.family,
        edge=chosen.edge,
        prob_up=prob,
        prob_up_raw=raw_prob,
        return_quantiles=[float(v) for v in latest.quantiles[0]],
        expected_volatility=vol_value,
        volatility_model=vol_model,
        price_quantiles=[
            _price(last_close, float(v), display_precision) for v in latest.quantiles[0]
        ],
        calibration=chosen.calibration,
    )
    return Run(
        evaluation=evaluation,
        published=published,
        drift=drift,
        volatility=vol_scores,
        feature_set_hash=feat.feature_set_hash(),
        data_snapshot_hash=feat.data_hash(series.timestamps, series.close),
        code_version=os.environ.get("GIT_SHA", CODE_VERSION),
        seed=seed,
        train_rows=len(fit),
    )


def summary(evaluation: Evaluation) -> list[dict[str, Any]]:
    """A JSON-friendly report of every model and baseline, whatever the outcome."""
    out = []
    for r in evaluation.results:
        out.append(
            {
                "name": r.name,
                "family": r.family,
                "params": r.params,
                "metrics": r.metrics,
                "versus_baselines": r.versus,
                "edge": r.edge,
                "probability": r.probability,
                "statement": "demonstrated edge"
                if r.edge
                else ("baseline" if r.family == "baseline" else "no demonstrated edge"),
                "calibration": None
                if r.calibration is None
                else {
                    "method": r.calibration.method,
                    "status": r.calibration.status,
                    "ece_raw": r.calibration.ece_raw,
                    "ece_calibrated": r.calibration.ece_calibrated,
                    "worst_bin_gap": r.calibration.worst_bin_gap,
                    "test_rows": r.calibration.test_rows,
                },
                "error": r.error,
            }
        )
    return out
