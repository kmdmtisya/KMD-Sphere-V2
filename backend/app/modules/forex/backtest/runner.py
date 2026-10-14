"""One pair's backtests (no database): every setup rule over the same bars, with the full-period
run, cost sensitivity, walk-forward validation, benchmarks and the leakage audit, as reports.

The setups of every bar are computed once and shared by the six rules. The audit re-derives the
decisions through the strategy interface on the real and on an altered future, and the runner
checks that the shared decisions equal the audited ones, so the precomputation cannot hide
look-ahead."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from app.core.money import format_decimal
from app.modules.forex.backtest import metrics as mt
from app.modules.forex.backtest import report as rp
from app.modules.forex.backtest import validation as va
from app.modules.forex.backtest.engine import ONE_PERCENT, Params, costs_for, simulate
from app.modules.forex.backtest.strategy import (
    WINDOW,
    RuleStrategy,
    Strategy,
    decisions,
    leakage_audit,
    rule_decisions,
    setups_by_bar,
)
from app.modules.forex.risk.specs import SpecValues
from app.modules.forex.signals import setups as su

D = Decimal
RULES = ("trend_continuation", "breakout", "reversal", "range", "momentum", "mean_reversion")
# The spread assumed per fill when no historical spread is stored: the simulated feed's typical
# spread per liquidity tier, in pips (marketdata.fake.SPREAD_PIPS).
SPREAD_PIPS = {"major": D("1.2"), "minor": D("2.0"), "exotic": D("40")}
MIN_TRADABLE_BARS = 300


@dataclass(frozen=True)
class PairData:
    instrument: str
    timeframe: str
    bars: su.Bars
    data_types: Sequence[str]
    pip_location: int
    display_precision: int
    liquidity_tier: str
    spec: SpecValues
    spec_version: int
    spec_reviewed: bool


@dataclass(frozen=True)
class Settings:
    seed: int = 7
    folds: int = 4
    risk_percent: Decimal = ONE_PERCENT
    random_runs: int = 20
    audit_cuts: int = 2
    audit_lookback: int = 10


def run_pair(
    data: PairData, settings: Settings, generated_at: datetime, rules: Sequence[str] = RULES
) -> list[dict[str, Any]]:
    bars = data.bars
    start, end = WINDOW - 1, len(bars)
    if end - start < MIN_TRADABLE_BARS:
        raise ValueError(f"at least {WINDOW - 1 + MIN_TRADABLE_BARS} bars are needed")
    by_bar = setups_by_bar(bars, start, end)
    spread_pips = SPREAD_PIPS[data.liquidity_tier]
    costs = costs_for(data.spec, data.pip_location, spread_pips)
    assumption = {
        "spread_pips": format_decimal(spread_pips),
        "spread_source": "assumption: the simulated feed's typical spread for the tier",
        "slippage_pips_per_fill": format_decimal(data.spec.slippage_pips),
        "commission_per_lot_side": format_decimal(data.spec.commission_per_lot_side),
        "contract_specification_version": str(data.spec_version),
        "contract_specification_review": "reviewed" if data.spec_reviewed else "unreviewed",
        "swaps": "not modelled",
    }
    span = end - start
    cuts = [start + span * (k + 1) // (settings.audit_cuts + 1) for k in range(settings.audit_cuts)]
    defaults = Params(risk_percent=settings.risk_percent)
    reports = []
    for rule in rules:
        shared = rule_decisions(by_bar, rule)

        def factory(_: su.Bars, rule: str = rule) -> Strategy:
            return RuleStrategy(rule)

        audit = leakage_audit(factory, bars, cuts, settings.audit_lookback)
        lo = cuts[0] + 1 - settings.audit_lookback
        direct = decisions(RuleStrategy(rule), bars, lo, cuts[0] + 1)
        if direct[lo : cuts[0] + 1] != shared[lo : cuts[0] + 1]:
            raise RuntimeError("the shared decisions differ from the strategy's own")
        full = mt.compute(
            simulate(bars, shared, data.spec, costs, defaults, start, end), data.timeframe
        )
        scenarios = va.sensitivity(
            bars, shared, data.spec, costs, defaults, start, end, data.timeframe
        )
        wf = va.walk_forward(
            bars,
            shared,
            data.spec,
            costs,
            start,
            end,
            settings.folds,
            data.timeframe,
            settings.risk_percent,
        )
        bench = va.benchmarks(bars, data.spec, costs, wf, settings.seed, settings.random_runs)
        reports.append(
            rp.build(
                instrument=data.instrument,
                timeframe=data.timeframe,
                rule=rule,
                rule_version=su.RULE_VERSION,
                bars=bars,
                start=start,
                end=end,
                data_types=data.data_types,
                precision=data.display_precision,
                seed=settings.seed,
                folds=settings.folds,
                costs_assumption=assumption,
                full_params=defaults,
                full=full,
                scenarios=scenarios,
                wf=wf,
                bench=bench,
                audit=audit,
                generated_at=generated_at,
            )
        )
    return reports
