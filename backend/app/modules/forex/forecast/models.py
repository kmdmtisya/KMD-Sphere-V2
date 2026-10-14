"""Forecasters (P13-T05.2 to T05.4, DEC-22). Every forecaster predicts, for a bar t and the
horizon h, the distribution of the forward log return: its mean, five quantiles, a standard
deviation and the probability that it is positive.

Interface: `fit(ctx, fit_idx, calib_idx)` then `predict(ctx, idx)`. `ctx` holds the whole series,
but a forecaster may read, for a prediction at bar t, only features and one-bar returns at bars
0..t, and labels of bars s with s + h <= t (the label of s uses the close at s + h). A future
perturbation test enforces this on every forecaster, and a deliberately leaky forecaster fails it.

Families:
- baselines: `no_change` (zero return, Gaussian spread), `random_walk` (zero-drift empirical
  distribution), `drift` (empirical distribution with its mean);
- statistical: `arima` (SARIMAX on one-bar returns, h-step cumulative mean and variance);
- machine learning: `random_forest`, `lightgbm`, `xgboost` (a classifier for the direction and a
  regressor for the mean; quantiles from residuals on the calibration window);
- `ensemble`: the average of member distributions (quantiles averaged);
- volatility: `ewma` and `har` forecasts of the horizon's return standard deviation.
LSTM, GRU and Transformer models are research-only (DEC-22) and not implemented here."""

import warnings
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

import numpy as np
from numpy.typing import NDArray
from scipy.stats import norm

Floats = NDArray[np.float64]
Ints = NDArray[np.int64]
QUANTILES = (0.1, 0.25, 0.5, 0.75, 0.9)
Z = np.array([norm.ppf(q) for q in QUANTILES])
EPS = 1e-12


@dataclass(frozen=True)
class Context:
    x: Floats  # bars x features
    y: Floats  # forward log return over the horizon (label), NaN where unknown
    r1: Floats  # one-bar log returns
    horizon: int


@dataclass(frozen=True)
class Distribution:
    mean: Floats
    std: Floats
    quantiles: Floats  # rows x len(QUANTILES), non-decreasing
    prob_up: Floats

    def rows(self) -> int:
        return len(self.mean)


def gaussian(mean: Floats, std: Floats) -> Distribution:
    std = np.maximum(std, EPS)
    q = mean[:, None] + std[:, None] * Z[None, :]
    return Distribution(mean, std, q, 1 - norm.cdf(-mean / std))


def empirical(mean: Floats, residuals: Floats, prob_up: Floats | None = None) -> Distribution:
    """mean + residual quantiles; prob_up from the residuals unless given."""
    res = residuals[np.isfinite(residuals)]
    if len(res) < 5:
        raise ValueError("not enough residuals for an empirical distribution")
    qs = np.quantile(res, QUANTILES)
    std = np.full(len(mean), float(np.std(res)) + EPS)
    if prob_up is None:
        prob_up = np.array([float(np.mean(m + res > 0)) for m in mean])
    return Distribution(mean, std, mean[:, None] + qs[None, :], prob_up)


class Forecaster(Protocol):
    name: str
    family: str

    @property
    def params(self) -> dict[str, Any]: ...

    def fit(self, ctx: Context, fit_idx: Ints, calib_idx: Ints) -> None: ...

    def predict(self, ctx: Context, idx: Ints) -> Distribution: ...


def _known_labels(ctx: Context, idx: Ints) -> Floats:
    y = ctx.y[idx]
    return y[np.isfinite(y)]


# ------------------------------------------------------------------------------- baselines
@dataclass
class NoChange:
    """The price stays where it is: zero expected return, Gaussian spread from training labels."""

    name: str = "no_change"
    family: str = "baseline"
    sigma: float = 0.0

    @property
    def params(self) -> dict[str, Any]:
        return {}

    def fit(self, ctx: Context, fit_idx: Ints, calib_idx: Ints) -> None:
        y = _known_labels(ctx, np.concatenate([fit_idx, calib_idx]))
        self.sigma = float(np.std(y)) if len(y) else 0.0

    def predict(self, ctx: Context, idx: Ints) -> Distribution:
        n = len(idx)
        d = gaussian(np.zeros(n), np.full(n, self.sigma))
        return Distribution(d.mean, d.std, d.quantiles, np.full(n, 0.5))


@dataclass
class RandomWalk:
    """Zero drift with the empirical distribution of training returns (centred)."""

    name: str = "random_walk"
    family: str = "baseline"
    residuals: Floats = field(default_factory=lambda: np.zeros(0))

    @property
    def params(self) -> dict[str, Any]:
        return {}

    def fit(self, ctx: Context, fit_idx: Ints, calib_idx: Ints) -> None:
        y = _known_labels(ctx, np.concatenate([fit_idx, calib_idx]))
        self.residuals = y - float(np.mean(y))

    def predict(self, ctx: Context, idx: Ints) -> Distribution:
        return empirical(np.zeros(len(idx)), self.residuals)


@dataclass
class Drift:
    """The training mean return with the empirical distribution around it."""

    name: str = "drift"
    family: str = "baseline"
    mu: float = 0.0
    residuals: Floats = field(default_factory=lambda: np.zeros(0))

    @property
    def params(self) -> dict[str, Any]:
        return {}

    def fit(self, ctx: Context, fit_idx: Ints, calib_idx: Ints) -> None:
        y = _known_labels(ctx, np.concatenate([fit_idx, calib_idx]))
        self.mu = float(np.mean(y))
        self.residuals = y - self.mu

    def predict(self, ctx: Context, idx: Ints) -> Distribution:
        return empirical(np.full(len(idx), self.mu), self.residuals)


BASELINES = ("no_change", "random_walk", "drift")


# ----------------------------------------------------------------------------------- ARIMA
@dataclass
class Arima:
    """ARMA(p, q) with a constant on one-bar returns (statsmodels SARIMAX), fitted on the fit
    window. Predictions use one Kalman filter pass over the series with the fitted parameters (no
    refit): the filtered state at origin t uses returns up to t only. The h-step cumulative mean is
    the sum of the step forecasts; its variance is exact for the ARMA model,
    sigma2 * sum_{j<h} (sum_{i<=j} psi_i)^2 with psi the MA(infinity) weights (parameter
    uncertainty ignored, a stated approximation). Gaussian."""

    order: tuple[int, int] = (1, 1)
    name: str = "arima"
    family: str = "statistical"
    _result: Any = None
    _first: int = 0

    @property
    def params(self) -> dict[str, Any]:
        return {"order": list(self.order), "trend": "c"}

    def fit(self, ctx: Context, fit_idx: Ints, calib_idx: Ints) -> None:
        from statsmodels.tsa.statespace.sarimax import SARIMAX

        last = int(fit_idx.max())
        self._first = int(np.argmax(np.isfinite(ctx.r1)))
        endog = ctx.r1[self._first : last + 1]
        if len(endog) < 50:
            raise ValueError("not enough returns for ARIMA")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model = SARIMAX(endog, order=(self.order[0], 0, self.order[1]), trend="c")
            self._result = model.fit(disp=False)

    def predict(self, ctx: Context, idx: Ints) -> Distribution:
        from statsmodels.tsa.arima_process import arma2ma

        if self._result is None:
            raise RuntimeError("fit first")
        h = ctx.horizon
        upto = int(idx.max())
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            filtered = self._result.apply(ctx.r1[self._first : upto + 1]).filter_results
        z = filtered.design[:, :, 0]
        trans = filtered.transition[:, :, 0]
        d = filtered.obs_intercept[:, 0]
        c = filtered.state_intercept[:, 0]
        # Predicted state for bar t + 1 given returns up to t, for every origin t.
        states = filtered.predicted_state[:, idx - self._first + 1]
        means = np.zeros(len(idx))
        a = states.copy()
        for _ in range(h):
            means += (d[:, None] + z @ a)[0]
            a = c[:, None] + trans @ a
        ar = np.r_[1, -np.asarray(self._result.arparams)]
        ma = np.r_[1, np.asarray(self._result.maparams)]
        psi = arma2ma(ar, ma, lags=h)
        sigma2 = float(self._result.params[-1])
        var = sigma2 * float(np.sum(np.cumsum(psi) ** 2))
        return gaussian(means, np.full(len(idx), np.sqrt(var)))


# --------------------------------------------------------------------------- tree models
def _clean(ctx: Context, idx: Ints) -> Ints:
    rows = idx[np.isfinite(ctx.x[idx]).all(axis=1) & np.isfinite(ctx.y[idx])]
    return rows


@dataclass
class TreeModel:
    """A classifier for the direction and a regressor for the mean, fitted on the fit window.
    Quantiles come from residuals on the separate calibration window, so they are out of sample."""

    kind: str  # random_forest, lightgbm, xgboost
    seed: int = 7
    name: str = ""
    family: str = "machine_learning"
    _clf: Any = None
    _reg: Any = None
    _residuals: Floats = field(default_factory=lambda: np.zeros(0))

    def __post_init__(self) -> None:
        if self.kind not in ("random_forest", "lightgbm", "xgboost"):
            raise ValueError("unknown tree model")
        self.name = self.name or self.kind

    @property
    def params(self) -> dict[str, Any]:
        return {**_TREE_PARAMS[self.kind], "seed": self.seed}

    def _models(self) -> tuple[Any, Any]:
        p = _TREE_PARAMS[self.kind]
        if self.kind == "random_forest":
            from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor

            return (
                RandomForestClassifier(**p, random_state=self.seed, n_jobs=1),
                RandomForestRegressor(**p, random_state=self.seed, n_jobs=1),
            )
        if self.kind == "lightgbm":
            from lightgbm import LGBMClassifier, LGBMRegressor

            extra: dict[str, Any] = {
                "random_state": self.seed,
                "n_jobs": 1,
                "verbosity": -1,
                "deterministic": True,
                "force_row_wise": True,
            }
            return LGBMClassifier(**p, **extra), LGBMRegressor(**p, **extra)
        from xgboost import XGBClassifier, XGBRegressor

        xgb: dict[str, Any] = {
            "random_state": self.seed,
            "n_jobs": 1,
            "tree_method": "hist",
            "verbosity": 0,
        }
        return XGBClassifier(**p, **xgb), XGBRegressor(**p, **xgb)

    def fit(self, ctx: Context, fit_idx: Ints, calib_idx: Ints) -> None:
        rows = _clean(ctx, fit_idx)
        if len(rows) < 50:
            raise ValueError("not enough training rows")
        up = (ctx.y[rows] > 0).astype(np.int64)
        if len(set(up.tolist())) < 2:
            raise ValueError("training rows have only one direction")
        self._clf, self._reg = self._models()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self._clf.fit(ctx.x[rows], up)
            self._reg.fit(ctx.x[rows], ctx.y[rows])
        cal = _clean(ctx, calib_idx)
        if len(cal) < 5:
            raise ValueError("not enough calibration rows")
        self._residuals = ctx.y[cal] - np.asarray(self._reg.predict(ctx.x[cal]), dtype=np.float64)

    def predict(self, ctx: Context, idx: Ints) -> Distribution:
        x = ctx.x[idx]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            mean = np.asarray(self._reg.predict(x), dtype=np.float64)
            prob = np.asarray(self._clf.predict_proba(x)[:, 1], dtype=np.float64)
        return empirical(mean, self._residuals, prob)


# Small, strongly regularised models: the signal in returns is weak and overfitting is the main
# risk. Fixed seeds and one thread make every run reproducible.
_TREE_PARAMS: dict[str, dict[str, Any]] = {
    "random_forest": {"n_estimators": 150, "max_depth": 3, "min_samples_leaf": 50},
    "lightgbm": {
        "n_estimators": 100,
        "learning_rate": 0.03,
        "num_leaves": 7,
        "min_child_samples": 50,
        "subsample": 0.8,
        "subsample_freq": 1,
        "colsample_bytree": 0.8,
        "reg_lambda": 5.0,
    },
    "xgboost": {
        "n_estimators": 100,
        "learning_rate": 0.03,
        "max_depth": 2,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "min_child_weight": 20,
        "reg_lambda": 5.0,
    },
}


# ------------------------------------------------------------------------------- ensemble
@dataclass
class Ensemble:
    members: Sequence[Forecaster]
    name: str = "ensemble"
    family: str = "ensemble"

    @property
    def params(self) -> dict[str, Any]:
        return {"members": [m.name for m in self.members]}

    def fit(self, ctx: Context, fit_idx: Ints, calib_idx: Ints) -> None:
        for m in self.members:
            m.fit(ctx, fit_idx, calib_idx)

    def predict(self, ctx: Context, idx: Ints) -> Distribution:
        parts = [m.predict(ctx, idx) for m in self.members]
        mean = np.mean([p.mean for p in parts], axis=0)
        q = np.sort(np.mean([p.quantiles for p in parts], axis=0), axis=1)
        std = np.sqrt(np.mean([p.std**2 for p in parts], axis=0))
        prob = np.mean([p.prob_up for p in parts], axis=0)
        return Distribution(mean, std, q, prob)


# ----------------------------------------------------------------------------- volatility
def ewma_vol(r1: Floats, horizon: int, lam: float = 0.94) -> Floats:
    """RiskMetrics EWMA of squared one-bar returns, scaled to the horizon: sqrt(h * var).
    Value t uses returns up to t; NaN before the first return."""
    out = np.full(len(r1), np.nan)
    var: float | None = None
    for t, r in enumerate(r1):
        if not np.isfinite(r):
            continue
        var = r * r if var is None else lam * var + (1 - lam) * r * r
        out[t] = np.sqrt(horizon * var)
    return out


@dataclass
class Har:
    """Heterogeneous autoregressive realised variance: the next-h realised variance regressed
    (OLS) on the mean squared return of the last 1, 5 and 22 bars. Returns the horizon std."""

    horizon: int
    coef: Floats = field(default_factory=lambda: np.zeros(4))

    @staticmethod
    def regressors(r1: Floats) -> Floats:
        sq = np.where(np.isfinite(r1), r1 * r1, np.nan)
        out = np.full((len(r1), 4), np.nan)
        out[:, 0] = 1.0
        for j, w in enumerate((1, 5, 22), start=1):
            for t in range(w, len(r1)):
                out[t, j] = float(np.mean(sq[t - w + 1 : t + 1]))
        return out

    def target(self, r1: Floats) -> Floats:
        sq = np.where(np.isfinite(r1), r1 * r1, np.nan)
        out = np.full(len(r1), np.nan)
        for t in range(len(r1) - self.horizon):
            out[t] = float(np.sum(sq[t + 1 : t + 1 + self.horizon]))
        return out

    def fit(self, r1: Floats, idx: Ints) -> None:
        x, y = self.regressors(r1)[idx], self.target(r1)[idx]
        ok = np.isfinite(x).all(axis=1) & np.isfinite(y)
        if ok.sum() < 30:
            raise ValueError("not enough rows for the HAR model")
        self.coef = np.linalg.lstsq(x[ok], y[ok], rcond=None)[0]

    def predict(self, r1: Floats, idx: Ints) -> Floats:
        var = self.regressors(r1)[idx] @ self.coef
        return np.sqrt(np.maximum(var, EPS))


def default_models(seed: int = 7) -> list[Forecaster]:
    rf, lgb, xgb = (
        TreeModel("random_forest", seed),
        TreeModel("lightgbm", seed),
        TreeModel("xgboost", seed),
    )
    return [
        Arima(),
        rf,
        lgb,
        xgb,
        Ensemble(
            [
                Arima(),
                TreeModel("random_forest", seed),
                TreeModel("lightgbm", seed),
                TreeModel("xgboost", seed),
            ]
        ),
    ]


def baselines() -> list[Forecaster]:
    return [NoChange(), RandomWalk(), Drift()]
