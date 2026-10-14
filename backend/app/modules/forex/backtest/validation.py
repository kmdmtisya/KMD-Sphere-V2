"""Walk-forward validation, benchmarks and cost sensitivity (P13-T08.2, T08.4, T08.5).

**Walk-forward.** The tradable bars are cut into `folds + 1` equal windows. For each k, every
parameter set in the grid is run on window k (in-sample) and the one with the best net return
(ties: the first in grid order) is run once on window k + 1 (out-of-sample). Positions never
cross a window edge. In-sample and out-of-sample results are reported separately; the
out-of-sample windows are compounded into one series. Stability = the share of consecutive folds
that chose the same parameters.

**Benchmarks,** over the same out-of-sample bars:
- no trade: a return of 0;
- buy and hold: one long position of the starting equity's notional (no leverage), from the first
  open to the last close, with the same costs;
- random entry: `runs` seeded runs that enter at random bars with the strategy's trade frequency,
  a random side, the strategy's median stop distance and a 2R target, under the same engine,
  costs and holding limit. Reported: the mean and median return, and the share of random runs
  the strategy beat.

**Cost sensitivity.** The full-period run is repeated with the spread and commission, and the
slippage, multiplied (x2, x3). Costs are never removed: every scenario includes them."""

import random
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal, localcontext
from itertools import pairwise
from statistics import median

from app.modules.forex.backtest import metrics as mt
from app.modules.forex.backtest.engine import ONE_PERCENT, Costs, Params, Run, simulate
from app.modules.forex.backtest.strategy import Decision, Side
from app.modules.forex.risk.specs import SpecValues
from app.modules.forex.signals import setups as su

D = Decimal
ZERO = D(0)
GRID = tuple(
    Params(max_hold=h, reward_multiple=m) for h in (24, 48, 96) for m in (None, D("1.5"), D(3))
)
SCENARIOS = (
    ("base", D(1), D(1)),
    ("spread and commission x2", D(2), D(1)),
    ("slippage x2", D(1), D(2)),
    ("slippage x3", D(1), D(3)),
    ("all costs x2", D(2), D(2)),
    ("all costs x3", D(3), D(3)),
)


def windows(start: int, end: int, folds: int) -> list[tuple[int, int]]:
    if folds < 1:
        raise ValueError("at least one fold is needed")
    size = (end - start) // (folds + 1)
    if size < 2:
        raise ValueError("too few bars for the folds")
    edges = [start + size * k for k in range(folds + 1)] + [end]
    return list(pairwise(edges))


@dataclass(frozen=True)
class Fold:
    index: int
    in_sample: tuple[int, int]
    out_of_sample: tuple[int, int]
    chosen: Params
    in_sample_metrics: mt.Metrics
    out_of_sample_metrics: mt.Metrics
    out_of_sample_run: Run


@dataclass(frozen=True)
class WalkForward:
    folds: list[Fold]
    out_of_sample: mt.Metrics  # the compounded out-of-sample series
    stability: Decimal | None
    span: tuple[int, int]


def walk_forward(
    bars: su.Bars,
    decisions: Sequence[Decision | None],
    spec: SpecValues,
    costs: Costs,
    start: int,
    end: int,
    folds: int,
    timeframe: str,
    risk_percent: Decimal = ONE_PERCENT,
    grid: Sequence[Params] = GRID,
) -> WalkForward:
    grid = [Params(p.max_hold, p.reward_multiple, risk_percent) for p in grid]
    edges = windows(start, end, folds)
    out: list[Fold] = []
    for k in range(folds):
        (a, b), (c, d) = edges[k], edges[k + 1]
        best: tuple[Params, mt.Metrics] | None = None
        for p in grid:
            m = mt.compute(simulate(bars, decisions, spec, costs, p, a, b), timeframe)
            if best is None or m.total_return > best[1].total_return:
                best = (p, m)
        if best is None:
            raise ValueError("the parameter grid is empty")
        oos = simulate(bars, decisions, spec, costs, best[0], c, d)
        out.append(Fold(k, (a, b), (c, d), best[0], best[1], mt.compute(oos, timeframe), oos))
    return WalkForward(out, _chain(out, timeframe), _stability(out), (edges[1][0], end))


def _chain(folds: Sequence[Fold], timeframe: str) -> mt.Metrics:
    """The out-of-sample windows compounded: each starts with the equity the previous ended on."""
    with localcontext() as ctx:
        ctx.prec = 50
        capital, equity, trades, in_market, bars = D(1), [], [], 0, 0
        initial = folds[0].out_of_sample_run.initial
        for f in folds:
            run = f.out_of_sample_run
            equity += [initial * capital * e / run.initial for e in run.equity]
            trades += run.trades
            in_market += run.in_market
            bars += run.end - run.start
            capital *= run.final / run.initial
        return mt.summarise(trades, initial, equity, in_market, bars, timeframe)


def _stability(folds: Sequence[Fold]) -> Decimal | None:
    if len(folds) < 2:
        return None
    same = sum(1 for a, b in pairwise(folds) if a.chosen == b.chosen)
    return D(same) / (len(folds) - 1)


@dataclass(frozen=True)
class Benchmarks:
    no_trade: Decimal
    buy_and_hold: Decimal
    random_mean: Decimal | None
    random_median: Decimal | None
    random_runs: int
    strategy_beat_share: Decimal | None  # of random runs with a lower return than the strategy
    note: str


def buy_and_hold(bars: su.Bars, costs: Costs, start: int, end: int, initial: Decimal) -> Decimal:
    with localcontext() as ctx:
        ctx.prec = 50
        against = costs.spread / 2 + costs.slippage
        entry = bars.open[start] + against
        units = initial / entry
        exit_ = bars.close[end - 1] - against
        pnl = units * (exit_ - entry) - 2 * units * costs.commission
        return pnl / initial


def random_entry(
    bars: su.Bars,
    spec: SpecValues,
    costs: Costs,
    params: Params,
    start: int,
    end: int,
    trades: int,
    stop_distance: Decimal,
    seed: int,
    runs: int = 20,
) -> list[Decimal]:
    returns = []
    p = trades / max(end - start, 1)
    for r in range(runs):
        rng = random.Random(f"fx-backtest-random:{seed}:{r}")  # noqa: S311 (a seeded benchmark, not security)
        decisions: list[Decision | None] = [None] * len(bars)
        for i in range(start, end):
            if rng.random() < p:
                side: Side = "long" if rng.random() < 0.5 else "short"
                c = bars.close[i]
                s = D(1) if side == "long" else D(-1)
                decisions[i] = Decision(
                    side, c - s * stop_distance, c + s * 2 * stop_distance, "random"
                )
        run = simulate(bars, decisions, spec, costs, params, start, end)
        returns.append(run.final / run.initial - 1)
    return returns


def benchmarks(
    bars: su.Bars,
    spec: SpecValues,
    costs: Costs,
    wf: WalkForward,
    seed: int,
    runs: int = 20,
) -> Benchmarks:
    start, end = wf.span
    oos = wf.out_of_sample
    hold = buy_and_hold(bars, costs, start, end, wf.folds[0].out_of_sample_run.initial)
    trades = [t for f in wf.folds for t in f.out_of_sample_run.trades]
    if not trades:
        return Benchmarks(
            ZERO, hold, None, None, 0, None, "no out-of-sample trades: random entry not run"
        )
    distance = D(median([abs(t.entry_price - t.stop) for t in trades]))
    params = wf.folds[-1].chosen
    rets = random_entry(bars, spec, costs, params, start, end, len(trades), distance, seed, runs)
    beat = sum(1 for r in rets if r < oos.total_return)
    return Benchmarks(
        no_trade=ZERO,
        buy_and_hold=hold,
        random_mean=sum(rets, ZERO) / len(rets),
        random_median=D(median(rets)),
        random_runs=len(rets),
        strategy_beat_share=D(beat) / len(rets),
        note="random entry: the strategy's trade frequency and median stop distance, 2R target, "
        "the last fold's parameters",
    )


@dataclass(frozen=True)
class Scenario:
    name: str
    spread_and_commission: Decimal
    slippage: Decimal
    metrics: mt.Metrics


def sensitivity(
    bars: su.Bars,
    decisions: Sequence[Decision | None],
    spec: SpecValues,
    costs: Costs,
    params: Params,
    start: int,
    end: int,
    timeframe: str,
) -> list[Scenario]:
    return [
        Scenario(
            name,
            a,
            b,
            mt.compute(
                simulate(bars, decisions, spec, costs.scaled(a, b), params, start, end), timeframe
            ),
        )
        for name, a, b in SCENARIOS
    ]
