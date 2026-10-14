"""Forecasting without a database (P13-T05, QG-15): point-in-time features and labels, purged
walk-forward splits, the leakage audit over every model (a leaky model fails it), metrics,
calibration, drift, ARIMA's forecasts, and honest reporting: on a random walk no model shows an
edge and the random-walk baseline is published; on a predictable process the edge is found."""

import warnings
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from itertools import pairwise
from typing import Any

import numpy as np
import pytest

from app.modules.forex.forecast import calibration as cal
from app.modules.forex.forecast import drift, pipeline
from app.modules.forex.forecast import features as feat
from app.modules.forex.forecast import models as mdl
from app.modules.forex.forecast.evaluation import (
    diebold_mariano,
    evaluate,
    leakage_audit,
    no_overlap,
    pinball,
    summarise,
    walk_forward,
)

D = Decimal


def returns(n: int, phi: float = 0.0, seed: int = 3, scale: float = 1e-3) -> np.ndarray:
    rng = np.random.default_rng(seed)
    r = np.zeros(n)
    for t in range(1, n):
        r[t] = phi * r[t - 1] + rng.normal(0, scale)
    return r


def series(n: int = 1200, phi: float = 0.0, seed: int = 3) -> pipeline.Series:
    c = 1.1 * np.exp(np.cumsum(returns(n, phi, seed)))
    ts = [datetime(2026, 1, 5, tzinfo=UTC) + timedelta(hours=k) for k in range(n)]
    return pipeline.Series(
        ts,
        [D(f"{v:.5f}") for v in c],
        [D(f"{v * 1.0004:.5f}") for v in c],
        [D(f"{v * 0.9996:.5f}") for v in c],
    )


def ctx_from(s: pipeline.Series, h: int) -> mdl.Context:
    m = feat.build(s.close, s.high, s.low)
    return mdl.Context(m.x, feat.labels(s.close, h), m.r1, h)


def usable(ctx: mdl.Context) -> np.ndarray:
    return np.flatnonzero(np.isfinite(ctx.x).all(axis=1) & np.isfinite(ctx.y)).astype(np.int64)


# --------------------------------------------------------------------------- features (T05.1)
def test_features_are_point_in_time() -> None:
    """Features of bar t are identical whether computed on bars 0..t or on the whole series."""
    s = series(300)
    full = feat.build(s.close, s.high, s.low)
    for t in (40, 120, 250, 299):
        prefix = feat.build(s.close[: t + 1], s.high[: t + 1], s.low[: t + 1])
        np.testing.assert_array_equal(prefix.x[t], full.x[t])
        np.testing.assert_array_equal(prefix.r1[t], full.r1[t])


def test_labels_are_forward_returns_and_unknown_at_the_end() -> None:
    close = [D("1.0"), D("1.1"), D("1.21"), D("1.331")]
    y = feat.labels(close, 2)
    assert y[0] == pytest.approx(np.log(1.21)) and y[1] == pytest.approx(np.log(1.331 / 1.1))
    assert np.isnan(y[2]) and np.isnan(y[3])
    with pytest.raises(ValueError):
        feat.labels(close, 0)


def test_feature_names_hash_and_bad_input() -> None:
    m = feat.build(series(60).close, series(60).high, series(60).low, [False] * 59 + [True])
    assert m.names == feat.FEATURES and m.x.shape == (60, len(feat.FEATURES))
    assert m.x[-1, feat.FEATURES.index("event_window")] == 1.0
    assert np.isnan(m.x[5, feat.FEATURES.index("vol_30")])  # warm-up stays undefined
    assert feat.feature_set_hash() == feat.feature_set_hash() and len(feat.feature_set_hash()) == 16
    with pytest.raises(ValueError):
        feat.build([D(1)], [D(1), D(1)], [D(1)])
    with pytest.raises(ValueError):
        feat.build([D(1)], [D(1)], [D(1)], [True, False])
    assert feat.build([], [], []).x.shape == (0, len(feat.FEATURES))


# ------------------------------------------------------------------------- splits (T05.5)
def test_walk_forward_folds_are_expanding_and_purged() -> None:
    rows = np.arange(30, 1030, dtype=np.int64)
    folds = walk_forward(rows, horizon=6, initial=500, test_size=100)
    assert len(folds) == 5
    for a, b in pairwise(folds):
        assert b.fit.min() == a.fit.min() and len(b.fit) > len(a.fit)  # expanding
        assert b.test.min() > a.test.max()
    for f in folds:
        assert no_overlap(f, 6)
        assert f.fit.max() + 6 < f.calib.min() and f.calib.max() + 6 < f.test.min()
    with pytest.raises(ValueError):
        walk_forward(rows, 0, 500, 100)
    assert walk_forward(rows[:100], 6, 500, 100) == []


# ------------------------------------------------------------------------ leakage (QG-15.2)
@dataclass
class Leaky:
    """Deliberately leaky: predicts with the label of the bar itself (the future)."""

    name: str = "leaky"
    family: str = "test"
    params: dict[str, Any] = field(default_factory=dict)

    def fit(self, ctx: mdl.Context, fit_idx: np.ndarray, calib_idx: np.ndarray) -> None:
        return None

    def predict(self, ctx: mdl.Context, idx: np.ndarray) -> mdl.Distribution:
        return mdl.gaussian(np.nan_to_num(ctx.y[idx]), np.full(len(idx), 1e-3))


@dataclass
class PeeksAtNextFeature(Leaky):
    """Deliberately leaky in a subtler way: uses the next bar's one-bar return."""

    name: str = "peeks"

    def predict(self, ctx: mdl.Context, idx: np.ndarray) -> mdl.Distribution:
        nxt = np.array([ctx.r1[min(int(i) + 1, len(ctx.r1) - 1)] for i in idx])
        return mdl.gaussian(nxt, np.full(len(idx), 1e-3))


FACTORIES: dict[str, Callable[[], mdl.Forecaster]] = {
    "no_change": mdl.NoChange,
    "random_walk": mdl.RandomWalk,
    "drift": mdl.Drift,
    "arima": mdl.Arima,
    "random_forest": lambda: mdl.TreeModel("random_forest", 7),
    "lightgbm": lambda: mdl.TreeModel("lightgbm", 7),
    "xgboost": lambda: mdl.TreeModel("xgboost", 7),
    "ensemble": lambda: mdl.Ensemble([mdl.Arima(), mdl.TreeModel("lightgbm", 7)]),
}


@pytest.fixture(scope="module")
def leak_setup() -> tuple[mdl.Context, Any]:
    ctx = ctx_from(series(900, phi=0.3), 4)
    folds = walk_forward(usable(ctx), 4, initial=500, test_size=100)
    return ctx, folds[0]


@pytest.mark.parametrize("name", list(FACTORIES))
def test_no_model_uses_anything_unknown_at_prediction_time(
    name: str, leak_setup: tuple[mdl.Context, Any]
) -> None:
    ctx, fold = leak_setup
    assert leakage_audit(FACTORIES[name], ctx, fold), name


@pytest.mark.parametrize("leaky", [Leaky, PeeksAtNextFeature])
def test_a_deliberately_leaky_model_fails_the_audit(
    leaky: Callable[[], mdl.Forecaster], leak_setup: tuple[mdl.Context, Any]
) -> None:
    ctx, fold = leak_setup
    assert leakage_audit(leaky, ctx, fold) is False


def test_the_evaluation_refuses_folds_that_leak() -> None:
    ctx = ctx_from(series(700), 4)
    folds = walk_forward(usable(ctx), 4, initial=400, test_size=100)
    bad = folds[0].__class__(folds[0].fit, folds[0].calib, folds[0].calib[-10:])
    with pytest.raises(AssertionError):
        evaluate({}, {"random_walk": mdl.RandomWalk}, ctx, [bad])


# --------------------------------------------------------------------------------- metrics
def test_metrics_by_hand() -> None:
    q = np.array([[-2.0, -1.0, 0.0, 1.0, 2.0]])
    assert pinball(q, np.array([0.0]))[0] == pytest.approx(np.mean([0.2, 0.25, 0.0, 0.25, 0.2]))
    d = mdl.Distribution(np.zeros(4), np.ones(4), np.tile(q, (4, 1)), np.full(4, 0.5))
    m = summarise(d, np.array([0.5, -0.5, 3.0, -1.5]))
    assert m["log_loss"] == pytest.approx(np.log(2)) and m["brier"] == pytest.approx(0.25)
    assert m["coverage_80"] == pytest.approx(0.75) and m["coverage_50"] == pytest.approx(0.5)
    assert m["rmse"] == pytest.approx(np.sqrt(np.mean([0.25, 0.25, 9, 2.25])))


def test_diebold_mariano() -> None:
    rng = np.random.default_rng(0)
    a = rng.normal(1.0, 0.1, 500)
    stat, p = diebold_mariano(a + rng.normal(0, 0.05, 500) - 0.05, a + rng.normal(0, 0.05, 500), 1)
    assert stat < 0 and p < 1e-6  # a clear improvement is highly significant
    # A difference with no variance has no defined statistic: no edge is claimed.
    assert diebold_mariano(a - 0.05, a, 1) == (0.0, 1.0)
    _, p_same = diebold_mariano(a, a + rng.normal(0, 0.1, 500), 4)
    assert p_same > 0.01
    assert diebold_mariano(a[:5], a[:5], 1) == (0.0, 1.0)


# ------------------------------------------------------------- honest outcomes (QG-15.1, 15.3)
def test_on_a_random_walk_no_model_shows_an_edge_and_the_baseline_is_published() -> None:
    run = pipeline.run(series(1200, seed=3), "4h", 5)
    ev = run.evaluation
    assert ev.folds >= 3 and ev.test_rows >= 300  # out-of-sample testing done
    names = [r.name for r in ev.results]
    assert names[:3] == ["no_change", "random_walk", "drift"]
    assert set(names) >= {"arima", "random_forest", "lightgbm", "xgboost", "ensemble"}
    for r in ev.results:
        assert not r.error, r.name
        assert r.edge is False, r.name
        if r.family != "baseline":
            # The comparison with every baseline is reported even though the baselines win.
            assert set(r.versus) == {"no_change", "random_walk", "drift"}
            assert all({"log_loss_difference", "dm_p_value"} <= set(v) for v in r.versus.values())
    pub = run.published
    assert (pub.model, pub.edge) == ("random_walk", False)
    report = pipeline.summary(ev)
    assert {e["statement"] for e in report if e["family"] != "baseline"} == {"no demonstrated edge"}


def test_on_a_predictable_process_the_edge_is_found() -> None:
    r = returns(1500, phi=0.5, seed=5)
    h = 1
    y = np.full(len(r), np.nan)
    y[:-h] = r[1:]
    r1 = r.copy()
    r1[0] = np.nan
    ctx = mdl.Context(r[:, None], y, r1, h)
    folds = walk_forward(np.arange(1, len(r) - h, dtype=np.int64), h, initial=700, test_size=200)
    ev = evaluate(
        {"arima": mdl.Arima, "lightgbm": FACTORIES["lightgbm"]},
        pipeline.BASELINE_FACTORIES,
        ctx,
        folds,
    )
    assert ev.by_name("arima").edge is True
    assert ev.by_name("lightgbm").edge is True
    assert ev.by_name("arima").metrics["direction_accuracy"] > 0.6


def test_runs_are_reproducible_and_carry_their_provenance() -> None:
    a, b = pipeline.run(series(900, seed=4), "1h", 5), pipeline.run(series(900, seed=4), "1h", 5)
    assert a.version == b.version and a.published.prob_up == b.published.prob_up
    assert (
        a.data_snapshot_hash == b.data_snapshot_hash
        and a.feature_set_hash == feat.feature_set_hash()
    )
    other = pipeline.run(series(900, seed=9), "1h", 5)
    assert other.data_snapshot_hash != a.data_snapshot_hash and other.version != a.version


def test_published_outputs_are_complete_ordered_and_decimal() -> None:
    pub = pipeline.run(series(900, seed=4), "1h", 5).published
    assert pub.horizon == "1h" and pub.bars_ahead == 4 and pub.timeframe.value == "15m"
    assert 0 <= pub.prob_up <= 1 and 0 <= pub.prob_up_raw <= 1
    assert pub.return_quantiles == sorted(pub.return_quantiles)
    assert all(isinstance(p, Decimal) and p.as_tuple().exponent == -5 for p in pub.price_quantiles)
    assert pub.price_quantiles == sorted(pub.price_quantiles)
    assert pub.price_quantiles[0] < pub.last_close * D("1.05") and pub.expected_volatility > 0
    assert pub.volatility_model in ("ewma", "har") and pub.calibration is not None


def test_short_history_and_unknown_horizons_publish_nothing() -> None:
    with pytest.raises(pipeline.InsufficientHistory):
        pipeline.run(series(200), "1h", 5)
    with pytest.raises(ValueError):
        pipeline.run(series(900), "2h", 5)


# ----------------------------------------------------------------- calibration (QG-15.4)
def test_calibrated_probabilities_pass_and_overconfident_ones_do_not() -> None:
    rng = np.random.default_rng(1)
    p = rng.uniform(0.2, 0.8, 4000)
    outcome = (rng.uniform(size=4000) < p).astype(np.float64)
    good = cal.assess(p, p, outcome, "none")
    assert good.status == "calibrated" and good.ece_calibrated < 0.03
    over = np.where(p > 0.5, 0.95, 0.05)
    bad = cal.assess(over, over, outcome, "none")
    assert bad.status == "requires_calibration" and bad.ece_calibrated > 0.1
    few = cal.assess(p[:100], p[:100], outcome[:100], "none")
    assert few.status == "requires_calibration"  # too few held-out rows to establish calibration
    assert sum(b.count for b in good.bins) == 4000


@pytest.mark.parametrize("method", ["isotonic", "platt"])
def test_recalibration_repairs_overconfidence(method: str) -> None:
    rng = np.random.default_rng(2)
    p = rng.uniform(0.3, 0.7, 6000)
    outcome = (rng.uniform(size=6000) < p).astype(np.float64)
    over = np.clip(0.5 + (p - 0.5) * 3, 0.01, 0.99)
    c = cal.Calibrator(method).fit(over[:3000], outcome[:3000])  # type: ignore[arg-type]
    after = c.apply(over[3000:])
    assert cal.ece(after, outcome[3000:]) < cal.ece(over[3000:], outcome[3000:]) / 2
    one_class = cal.Calibrator(method).fit(over[:10], np.ones(10))  # type: ignore[arg-type]
    assert np.array_equal(one_class.apply(over[:5]), over[:5])


# ------------------------------------------------------------------- intervals (QG-15.5)
def test_arima_forecasts_equal_statsmodels_and_intervals_cover_their_level() -> None:
    r = returns(1600, phi=0.4, seed=11)
    h = 4
    y = np.full(len(r), np.nan)
    y[:-h] = [r[t + 1 : t + 1 + h].sum() for t in range(len(r) - h)]
    r1 = r.copy()
    r1[0] = np.nan
    ctx = mdl.Context(r[:, None], y, r1, h)
    model = mdl.Arima()
    model.fit(ctx, np.arange(1, 800, dtype=np.int64), np.arange(800, 900, dtype=np.int64))
    origins = np.arange(900, 1590, dtype=np.int64)
    d = model.predict(ctx, origins)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for t in (900, 1200, 1589):
            ref = model._result.apply(r1[1 : t + 1]).get_forecast(steps=h)
            assert d.mean[t - 900] == pytest.approx(
                float(np.sum(ref.predicted_mean)), rel=1e-9, abs=1e-15
            )
    inside80 = np.mean((y[origins] >= d.quantiles[:, 0]) & (y[origins] <= d.quantiles[:, 4]))
    inside50 = np.mean((y[origins] >= d.quantiles[:, 1]) & (y[origins] <= d.quantiles[:, 3]))
    assert 0.74 <= inside80 <= 0.86 and 0.43 <= inside50 <= 0.57


def test_volatility_models() -> None:
    r = returns(800, seed=6)
    r1 = r.copy()
    r1[0] = np.nan
    ewma = mdl.ewma_vol(r1, 4)
    assert np.isnan(ewma[0]) and np.all(ewma[1:] > 0)
    prefix = mdl.ewma_vol(r1[:400], 4)
    assert ewma[399] == pytest.approx(prefix[399])  # causal
    har = mdl.Har(4)
    har.fit(r1, np.arange(30, 600, dtype=np.int64))
    pred = har.predict(r1, np.arange(600, 790, dtype=np.int64))
    assert np.all(pred > 0) and abs(np.median(pred) - 1e-3 * 2) < 1e-3  # sqrt(4) x 0.001
    with pytest.raises(ValueError):
        mdl.Har(4).fit(r1, np.arange(30, 40, dtype=np.int64))


# -------------------------------------------------------------------------- drift (QG-15.6)
def test_no_drift_on_a_stationary_process_and_a_breach_on_a_regime_change() -> None:
    s = series(1500, seed=8)
    m = feat.build(s.close, s.high, s.low)
    ok = drift.check(m.names, m.x[100:1100], m.x[1300:])
    assert ok.status == "ok", ok.reasons
    calm = returns(1500, seed=8)
    wild = np.r_[calm[:1100], calm[1100:] * 4]
    c = 1.1 * np.exp(np.cumsum(wild))
    close = [D(f"{v:.6f}") for v in c]
    m2 = feat.build(close, [x * D("1.0004") for x in close], [x * D("0.9996") for x in close])
    shifted = drift.check(m2.names, m2.x[100:1000], m2.x[1300:])
    assert shifted.status == "breached" and any("broad feature drift" in r for r in shifted.reasons)


def test_error_drift_breaches_and_small_samples_are_not_judged() -> None:
    x = np.random.default_rng(0).normal(size=(400, 2))
    worse = drift.check(["a", "b"], x[:200], x[200:], np.full(100, 0.75), np.full(100, 0.69))
    assert worse.status == "breached" and "error drift" in worse.reasons[0]
    same = drift.check(["a", "b"], x[:200], x[200:], np.full(100, 0.70), np.full(100, 0.69))
    assert same.status == "ok"
    assert np.isnan(drift.psi(x[:10, 0], x[10:20, 0]))
    assert drift.psi(np.ones(100), np.ones(100)) == 0.0
    with pytest.raises(ValueError):
        drift.check(["a"], x[:200], x[200:])
