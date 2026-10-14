"""Backtesting without a database (P13-T08, QG-17): the clock (fills at the next open, nothing
reads later bars), fills with costs (worked by hand), exits (stop before target in one bar, gaps,
time, end), sizing within the risk, metrics (worked by hand), walk-forward windows that never
overlap, benchmarks, cost sensitivity, reproducible report hashes, and the leakage audit: it
fails on a deliberately leaky strategy and passes on the real one."""

import random
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal, localcontext
from fractions import Fraction
from itertools import pairwise

import pytest

from app.ai.orchestrator.guards import guarantee_problems
from app.modules.forex.backtest import engine as en
from app.modules.forex.backtest import metrics as mt
from app.modules.forex.backtest import report as rp
from app.modules.forex.backtest import runner
from app.modules.forex.backtest import strategy as stg
from app.modules.forex.backtest import validation as va
from app.modules.forex.risk.specs import SpecValues, load_file
from app.modules.forex.signals import setups as su

D = Decimal
T0 = datetime(2026, 1, 5, tzinfo=UTC)
PLAIN = SpecValues(D(100000), D("0.01"), D("0.01"), D(100), D("0.0333"), D(0), D(0))
SPREAD_ONLY = en.Costs(D("0.0001"), D(0), D(0))
DEFAULT = en.Params()


def bars_of(rows: list[tuple[str, str, str, str]]) -> su.Bars:
    """(open, high, low, close) per hour."""
    return su.Bars(
        [T0 + timedelta(hours=k) for k in range(len(rows))],
        [D(r[0]) for r in rows],
        [D(r[1]) for r in rows],
        [D(r[2]) for r in rows],
        [D(r[3]) for r in rows],
    )


FLAT = ("1.1000", "1.1005", "1.0995", "1.1000")


def long_at(
    i: int, n: int, stop: str = "1.0950", target: str = "1.1100"
) -> list[stg.Decision | None]:
    out: list[stg.Decision | None] = [None] * n
    out[i] = stg.Decision("long", D(stop), D(target), "test")
    return out


def synthetic(n: int, seed: int = 3) -> su.Bars:
    """Alternating trends with noise, gaps on every 120th bar."""
    rng = random.Random(seed)  # noqa: S311 (test data)
    close = [D("1.1")]
    for k in range(n - 1):
        drift = D("0.0004") if (k // 150) % 2 == 0 else D("-0.0004")
        shock = D(str(round(rng.gauss(0, 0.0012), 6)))
        close.append((close[-1] * (1 + drift + shock)).quantize(D("0.00001")))
    opens = [close[0]] + [
        c + (D("0.003") if k % 120 == 119 else 0) for k, c in enumerate(close[:-1])
    ]
    high = [max(o, c) + D("0.0004") for o, c in zip(opens, close, strict=True)]
    low = [min(o, c) - D("0.0004") for o, c in zip(opens, close, strict=True)]
    return su.Bars([T0 + timedelta(hours=k) for k in range(n)], opens, high, low, close)


# --------------------------------------------------------------------------- clock and fills
def test_a_decision_fills_at_the_next_open_with_costs_and_stays_within_the_risk() -> None:
    rows = [FLAT, FLAT, ("1.1000", "1.1004", "1.0940", "1.0960"), FLAT]
    run = en.simulate(bars_of(rows), long_at(0, 4), PLAIN, SPREAD_ONLY, DEFAULT, 0, 4)
    (t,) = run.trades
    assert t.decided_at == T0 and t.entry_at == T0 + timedelta(hours=1)
    assert t.entry_price == D("1.10005")  # open + half the spread
    # risk 1% of 100,000; per unit 0.005 stop + 0.0001 round trip: 196,078 -> 196,000 units
    assert t.units == D(196000) and t.risk_amount == D("999.6")
    assert t.reason == "stop" and t.exit_price == D("1.09495")
    assert t.pnl == D("-999.60") and -t.pnl <= D(1000)
    assert t.costs == D("19.6") and t.r_multiple == -1
    assert run.final == D("99000.40")


def test_a_decision_on_the_last_bar_is_not_filled() -> None:
    run = en.simulate(bars_of([FLAT, FLAT]), long_at(1, 2), PLAIN, SPREAD_ONLY, DEFAULT, 0, 2)
    assert run.trades == [] and run.final == en.INITIAL_EQUITY


def test_a_bar_touching_both_levels_takes_the_stop_first() -> None:
    rows = [FLAT, FLAT, ("1.1000", "1.1200", "1.0900", "1.1000"), FLAT]
    (t,) = en.simulate(bars_of(rows), long_at(0, 4), PLAIN, SPREAD_ONLY, DEFAULT, 0, 4).trades
    assert t.reason == "stop"


def test_targets_gaps_time_and_the_end() -> None:
    target = [FLAT, FLAT, ("1.1000", "1.1150", "1.0990", "1.1120"), FLAT]
    (t,) = en.simulate(bars_of(target), long_at(0, 4), PLAIN, SPREAD_ONLY, DEFAULT, 0, 4).trades
    assert t.reason == "target" and t.exit_price == D("1.10995") and t.pnl > 0
    gap = [FLAT, FLAT, ("1.0900", "1.0910", "1.0880", "1.0900"), FLAT]
    (g,) = en.simulate(bars_of(gap), long_at(0, 4), PLAIN, SPREAD_ONLY, DEFAULT, 0, 4).trades
    assert g.reason == "gap_stop" and g.exit_price == D("1.08995")  # worse than the stop
    assert -g.pnl > g.risk_amount  # a gap can lose more than the planned risk
    up = [FLAT, FLAT, ("1.1200", "1.1210", "1.1190", "1.1200"), FLAT]
    (u,) = en.simulate(bars_of(up), long_at(0, 4), PLAIN, SPREAD_ONLY, DEFAULT, 0, 4).trades
    assert u.reason == "gap_target" and u.exit_price == D("1.11995")
    timed = en.simulate(
        bars_of([FLAT] * 6), long_at(0, 6), PLAIN, SPREAD_ONLY, en.Params(max_hold=3), 0, 6
    )
    assert timed.trades[0].reason == "time" and timed.trades[0].bars_held == 3
    end = en.simulate(bars_of([FLAT] * 4), long_at(0, 4), PLAIN, SPREAD_ONLY, DEFAULT, 0, 4)
    assert end.trades[0].reason == "end" and end.trades[0].exit_at == T0 + timedelta(hours=3)


def test_entries_are_skipped_when_the_open_gapped_past_a_level_or_the_size_is_too_small() -> None:
    past = [FLAT, ("1.0940", "1.0945", "1.0930", "1.0940"), FLAT]
    run = en.simulate(bars_of(past), long_at(0, 3), PLAIN, SPREAD_ONLY, DEFAULT, 0, 3)
    assert run.trades == [] and run.skipped["gap"] == 1
    tiny = en.simulate(
        bars_of([FLAT] * 3), long_at(0, 3), PLAIN, SPREAD_ONLY, DEFAULT, 0, 3, initial=D(10)
    )
    assert tiny.trades == [] and tiny.skipped["too_small"] == 1


def test_shorts_mirror_longs_and_the_reward_multiple_sets_the_target() -> None:
    rows = [FLAT, FLAT, ("1.1000", "1.1060", "1.0990", "1.1050"), FLAT]
    short = [stg.Decision("short", D("1.1050"), D("1.0900"), "test"), None, None, None]
    (t,) = en.simulate(bars_of(rows), short, PLAIN, SPREAD_ONLY, DEFAULT, 0, 4).trades
    assert t.entry_price == D("1.09995") and t.reason == "stop" and t.exit_price == D("1.10505")
    wide = en.simulate(
        bars_of(rows), long_at(0, 4), PLAIN, SPREAD_ONLY, en.Params(reward_multiple=D(1)), 0, 4
    )
    assert wide.trades[0].target == D("1.1050") and wide.trades[0].reason == "target"


def test_one_position_at_a_time() -> None:
    decisions: list[stg.Decision | None] = [stg.Decision("long", D("1.0950"), D("1.1100"), "t")] * 6
    run = en.simulate(
        bars_of([FLAT] * 6), decisions, PLAIN, SPREAD_ONLY, en.Params(max_hold=2), 0, 6
    )
    spans = [(t.entry_at, t.exit_at) for t in run.trades]
    assert all(a[1] < b[0] for a, b in pairwise(spans))


def test_later_bars_never_change_an_earlier_trade() -> None:
    bars = synthetic(400)
    decisions = stg.rule_decisions(stg.setups_by_bar(bars, 199, 400), "breakout")
    run = en.simulate(bars, decisions, PLAIN, SPREAD_ONLY, DEFAULT, 199, 400)
    assert len(run.trades) >= 2
    first = run.trades[0]
    cut = bars.ts.index(first.exit_at)
    other = stg.altered_after(bars, cut)
    again = en.simulate(
        other,
        decisions[: cut + 1] + [None] * (400 - cut - 1),
        PLAIN,
        SPREAD_ONLY,
        DEFAULT,
        199,
        400,
    )
    assert again.trades[0] == first


def test_bad_parameters_and_ranges_are_refused() -> None:
    for bad in (
        {"max_hold": 0},
        {"reward_multiple": D(0)},
        {"risk_percent": D(0)},
        {"risk_percent": D(11)},
    ):
        with pytest.raises(ValueError):
            en.Params(**bad)
    with pytest.raises(ValueError):
        en.simulate(bars_of([FLAT]), [None], PLAIN, SPREAD_ONLY, DEFAULT, 0, 2)


def test_costs_come_from_the_specification_and_scale() -> None:
    spec = replace(PLAIN, slippage_pips=D("0.5"), commission_per_lot_side=D("3.5"))
    c = en.costs_for(spec, -4, D("1.2"))
    assert c == en.Costs(D("0.00012"), D("0.00005"), D("0.000035"))
    assert c.round_trip == D("0.00029")
    assert c.scaled(D(2), D(3)) == en.Costs(D("0.00024"), D("0.00015"), D("0.000070"))


# ---------------------------------------------------------------------------------- metrics
def trade(pnl: str, risk: str = "100") -> en.Trade:
    return en.Trade(
        "t", "long", T0, T0, T0, D(1), D(1), D(1), D(1), D(1), D(risk), D(pnl), D(1), 1, "time"
    )


def test_metrics_worked_by_hand() -> None:
    trades = [trade("100"), trade("-50"), trade("-50"), trade("200"), trade("-25")]
    equity = [D(1100), D(1050), D(1000), D(1200), D(1175)]
    m = mt.summarise(trades, D(1000), equity, 3, 5, "1H")
    assert m.trades == 5 and m.wins == 2 and m.win_rate == D("0.4")
    assert m.gross_profit == D(300) and m.gross_loss == D(125) and m.profit_factor == D("2.4")
    assert m.average_trade == D(35) and m.expectancy_r == D("0.35")
    assert m.longest_losing_streak == 2 and m.exposure == D("0.6")
    assert m.total_return == D("0.175") and m.costs == D(5)
    with localcontext() as ctx:
        ctx.prec = 50
        assert m.max_drawdown == (D(1100) - D(1000)) / D(1100)
    returns = [
        Fraction(1100, 1000) - 1,
        Fraction(1050, 1100) - 1,
        Fraction(1000, 1050) - 1,
        Fraction(1200, 1000) - 1,
        Fraction(1175, 1200) - 1,
    ]
    mean = sum(returns) / 5
    var = sum((r - mean) ** 2 for r in returns) / 4
    sharpe = float(mean) / float(var) ** 0.5 * 6240**0.5
    assert m.sharpe is not None and abs(float(m.sharpe) - sharpe) < 1e-9
    down = float(sum(min(r, Fraction(0)) ** 2 for r in returns) / 5) ** 0.5
    assert (
        m.sortino is not None
        and abs(float(m.sortino) - float(mean) / float(down) * 6240**0.5) < 1e-9
    )


def test_metrics_without_trades_or_losses() -> None:
    empty = mt.summarise([], D(1000), [D(1000)] * 3, 0, 3, "1D")
    assert empty.win_rate is None and empty.profit_factor is None and empty.sharpe is None
    assert empty.total_return == 0 and empty.max_drawdown == 0
    only_wins = mt.summarise([trade("10")], D(1000), [D(1000), D(1010)], 1, 2, "4H")
    assert only_wins.profit_factor is None and only_wins.sortino is None
    assert mt.max_drawdown([D(10), D(5), D(20), D(15)]) == D("0.5")
    assert (
        mt.longest_losing_streak([trade("0"), trade("-1"), trade("1")]) == 2
    )  # zero counts as a loss
    assert mt.bar_returns(D(100), [D(110), D(99)]) == [D("0.1"), D("-0.1")]
    assert mt.sharpe_sortino([D("0.01")], 260) == (None, None)


# --------------------------------------------------------------------- walk-forward and more
@pytest.fixture(scope="module")
def series() -> tuple[su.Bars, list[stg.Decision | None]]:
    bars = synthetic(700)
    return bars, stg.rule_decisions(stg.setups_by_bar(bars, 199, 700), "trend_continuation")


def test_walk_forward_windows_never_overlap_and_choose_in_sample(
    series: tuple[su.Bars, list[stg.Decision | None]],
) -> None:
    bars, decisions = series
    assert va.windows(199, 700, 4) == [(199, 299), (299, 399), (399, 499), (499, 599), (599, 700)]
    wf = va.walk_forward(bars, decisions, PLAIN, SPREAD_ONLY, 199, 700, 4, "1H")
    assert len(wf.folds) == 4 and wf.span == (299, 700)
    for f in wf.folds:
        assert f.in_sample[1] == f.out_of_sample[0]  # next window, never the same bars
        oos = f.out_of_sample
        for t in f.out_of_sample_run.trades:
            assert bars.ts[oos[0]] < t.entry_at and t.exit_at <= bars.ts[oos[1] - 1]
        best = max(
            mt.compute(
                en.simulate(bars, decisions, PLAIN, SPREAD_ONLY, p, *f.in_sample), "1H"
            ).total_return
            for p in va.GRID
        )
        assert f.in_sample_metrics.total_return == best
    with localcontext() as ctx:
        ctx.prec = 50
        compounded = D(1)
        for f in wf.folds:
            compounded *= f.out_of_sample_run.final / f.out_of_sample_run.initial
        expected = compounded - 1
    assert abs(wf.out_of_sample.total_return - expected) < D("1e-30")
    assert wf.stability is not None and 0 <= wf.stability <= 1
    with pytest.raises(ValueError):
        va.windows(0, 5, 4)
    with pytest.raises(ValueError):
        va.windows(0, 100, 0)


def test_benchmarks_and_sensitivity(series: tuple[su.Bars, list[stg.Decision | None]]) -> None:
    bars, decisions = series
    costs = en.Costs(D("0.00012"), D("0.00002"), D(0))
    wf = va.walk_forward(bars, decisions, PLAIN, costs, 199, 700, 4, "1H")
    b = va.benchmarks(bars, PLAIN, costs, wf, seed=7, runs=5)
    assert b.no_trade == 0 and b.random_runs == 5 and b.strategy_beat_share is not None
    start, end = wf.span
    against = D("0.00008")
    with localcontext() as ctx:
        ctx.prec = 50
        expected = (bars.close[end - 1] - against) / (bars.open[start] + against) - 1
    assert abs(b.buy_and_hold - expected) < D("1e-30")
    trades = sum(len(f.out_of_sample_run.trades) for f in wf.folds)
    same = va.random_entry(bars, PLAIN, costs, DEFAULT, start, end, trades, D("0.003"), 7, 3)
    assert same == va.random_entry(
        bars, PLAIN, costs, DEFAULT, start, end, trades, D("0.003"), 7, 3
    )
    assert same != va.random_entry(
        bars, PLAIN, costs, DEFAULT, start, end, trades, D("0.003"), 8, 3
    )
    scenarios = va.sensitivity(bars, decisions, PLAIN, costs, DEFAULT, 199, 700, "1H")
    assert scenarios[0].name == "base"
    assert all(
        s.spread_and_commission >= 1 and s.slippage >= 1 for s in scenarios
    )  # costs never removed
    base = mt.compute(en.simulate(bars, decisions, PLAIN, costs, DEFAULT, 199, 700), "1H")
    assert scenarios[0].metrics == base
    worst = scenarios[-1].metrics
    assert worst.total_return < base.total_return and worst.costs > 0


def test_no_out_of_sample_trades_means_no_random_benchmark() -> None:
    bars = synthetic(700)
    wf = va.walk_forward(bars, [None] * 700, PLAIN, SPREAD_ONLY, 199, 700, 4, "1H")
    b = va.benchmarks(bars, PLAIN, SPREAD_ONLY, wf, seed=7)
    assert b.random_runs == 0 and b.random_mean is None and "not run" in b.note


# ------------------------------------------------------------------------------ leakage audit
@dataclass(frozen=True)
class Peeker:
    """Deliberately leaky: built from the whole series, it looks at the next close."""

    future: su.Bars

    def decide(self, history: su.Bars) -> stg.Decision | None:
        i = (
            len(self.future.ts)
            if history.ts[-1] == self.future.ts[-1]
            else self.future.ts.index(history.ts[-1])
        )
        if i + 1 >= len(self.future.ts):
            return None
        c, nxt = history.close[-1], self.future.close[i + 1]
        if nxt > c:
            return stg.Decision("long", c - D("0.0050"), c + D("0.0010"), "peek")
        return stg.Decision("short", c + D("0.0050"), c - D("0.0010"), "peek")


def test_the_audit_fails_a_leaky_strategy_and_passes_the_real_one() -> None:
    bars = synthetic(330)
    leaky = stg.leakage_audit(lambda b: Peeker(b), bars, [260, 300], lookback=5)
    assert not leaky.passed and leaky.first_difference is not None
    real = stg.leakage_audit(lambda _: stg.RuleStrategy("breakout"), bars, [260, 300], lookback=5)
    assert real.passed and real.checked == 20 and real.first_difference is None
    # The leak would look like a fine strategy: the audit is what exposes it.
    peeking = stg.decisions(Peeker(bars), bars, 199, 330)
    run = en.simulate(bars, peeking, PLAIN, SPREAD_ONLY, en.Params(max_hold=1), 199, 330)
    assert mt.compute(run, "1H").win_rate is not None
    with pytest.raises(ValueError):
        stg.leakage_audit(lambda _: stg.RuleStrategy("breakout"), bars, [329])


def test_history_is_a_copy_of_the_closed_bars_only() -> None:
    bars = synthetic(250)
    h = stg.history(bars, 210)
    assert len(h) == 200 and h.ts[-1] == bars.ts[210] and h.ts[0] == bars.ts[11]
    assert stg.history(bars, 5).ts == list(bars.ts[:6])
    assert stg.RuleStrategy("breakout").decide(stg.history(bars, 30)) is None  # too few bars
    for how in stg.ALTERATIONS:
        altered = stg.altered_after(bars, 100, how)
        assert (
            altered.close[:101] == list(bars.close[:101]) and altered.close[101] != bars.close[101]
        )
        assert all(hi >= lo for hi, lo in zip(altered.high, altered.low, strict=True))
    up = bars.close[101] - bars.close[100]
    assert stg.altered_after(bars, 100, "mirror").close[101] - bars.close[100] == -up
    assert stg.altered_after(bars, 100, "stretch").close[101] - bars.close[100] == 2 * up


def test_the_shared_setups_equal_the_strategy_decisions() -> None:
    bars = synthetic(260)
    shared = stg.rule_decisions(stg.setups_by_bar(bars, 199, 260), "momentum")
    direct = stg.decisions(stg.RuleStrategy("momentum"), bars, 199, 260)
    assert shared == direct


# ------------------------------------------------------------------------------- the report
@pytest.fixture(scope="module")
def pair() -> runner.PairData:
    _, _, specs = load_file()
    return runner.PairData(
        "EUR_USD", "1H", synthetic(520), ["simulated"], -4, 5, "major", specs["EUR_USD"], 1, False
    )


def test_reports_are_reproducible_and_fully_described(pair: runner.PairData) -> None:
    settings = runner.Settings(random_runs=3, audit_cuts=1, audit_lookback=3)
    rules = ("trend_continuation", "breakout")
    first = runner.run_pair(pair, settings, datetime(2026, 10, 14, tzinfo=UTC), rules)
    again = runner.run_pair(pair, settings, datetime(2026, 10, 15, tzinfo=UTC), rules)
    assert [r["report_hash"] for r in first] == [r["report_hash"] for r in again]
    assert first[0]["generated_at"] != again[0]["generated_at"]
    assert rp.report_hash(first[0]) == first[0]["report_hash"]
    r = first[0]
    assert r["label"] == "backtested" and r["seed"] == 7 and r["code_version"]
    assert (
        r["data"]["snapshot_hash"] == rp.data_hash(pair.bars, 0, 520) and r["data"]["bars"] == 321
    )
    assert r["data"]["data_types"] == ["simulated"] and r["leakage_audit"]["passed"] is True
    assert (
        r["costs"]["contract_specification_review"] == "unreviewed"
        and r["costs"]["swaps"] == "not modelled"
    )
    assert len(r["walk_forward"]["windows"]) == 4 and len(r["cost_sensitivity"]) == 6
    assert guarantee_problems([r["notice"]], forecast_used=False) == []
    other_seed = runner.run_pair(
        pair, replace(settings, seed=8), datetime(2026, 10, 14, tzinfo=UTC), rules
    )
    assert other_seed[0]["report_hash"] != r["report_hash"]
    moved = replace(
        pair,
        bars=replace(pair.bars, close=[*pair.bars.close[:-1], pair.bars.close[-1] + D("0.0001")]),
    )
    changed = runner.run_pair(moved, settings, datetime(2026, 10, 14, tzinfo=UTC), rules)
    assert changed[0]["data"]["snapshot_hash"] != r["data"]["snapshot_hash"]
    assert changed[0]["report_hash"] != r["report_hash"]


def test_too_few_bars_are_refused(pair: runner.PairData) -> None:
    short = replace(pair, bars=stg.history(pair.bars, 400, window=401))
    with pytest.raises(ValueError, match="bars are needed"):
        runner.run_pair(short, runner.Settings(), datetime(2026, 10, 14, tzinfo=UTC))
