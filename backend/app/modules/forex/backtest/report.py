"""Reproducible backtest reports (P13-T08.6).

A report is plain JSON: every number is a rounded decimal string, every time ISO 8601. Its hash is
the SHA-256 of the canonical JSON (sorted keys, no spaces) of everything except `generated_at`
and the hash itself, so the same bars, parameters, seed and code give the same hash. The report
names the data snapshot hash (the bars), the code version, the parameters and the seed.

Backtested results are labelled `backtested` and are never added to paper or live results."""

import hashlib
import json
import os
from collections.abc import Sequence
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.core.money import format_decimal
from app.modules.forex.backtest import metrics as mt
from app.modules.forex.backtest.engine import ENGINE_VERSION, Params, Trade
from app.modules.forex.backtest.strategy import Audit
from app.modules.forex.backtest.validation import Benchmarks, Scenario, WalkForward
from app.modules.forex.signals import setups as su

LABEL = "backtested"
CODE_VERSION = "fx-backtest-1"
MAX_TRADES = 1000  # out-of-sample trades listed in a report
NOTICE = (
    "Backtested on stored bars with modelled spread, slippage and commission. A backtest is a "
    "study of how a published rule would have behaved, not a forecast: it does not show what "
    "will happen, and results on simulated data say nothing about real markets. Backtested, "
    "paper and live results are separate series and are never combined."
)


def code_version() -> str:
    return os.environ.get("GIT_SHA", CODE_VERSION)


def data_hash(bars: su.Bars, start: int, end: int) -> str:
    digest = hashlib.sha256()
    for i in range(start, end):
        digest.update(
            f"{bars.ts[i].isoformat()}|{bars.open[i]}|{bars.high[i]}|{bars.low[i]}|{bars.close[i]}\n".encode()
        )
    return digest.hexdigest()[:16]


def _q(value: Decimal | None, places: str) -> str | None:
    if value is None:
        return None
    return format_decimal(value.quantize(Decimal(places), rounding=ROUND_HALF_UP))


def metrics(m: mt.Metrics) -> dict[str, Any]:
    return {
        "trades": m.trades,
        "wins": m.wins,
        "win_rate": _q(m.win_rate, "0.000001"),
        "total_return": _q(m.total_return, "0.000001"),
        "max_drawdown": _q(m.max_drawdown, "0.000001"),
        "gross_profit": _q(m.gross_profit, "0.01"),
        "gross_loss": _q(m.gross_loss, "0.01"),
        "profit_factor": _q(m.profit_factor, "0.01"),
        "average_trade": _q(m.average_trade, "0.01"),
        "expectancy_r": _q(m.expectancy_r, "0.01"),
        "longest_losing_streak": m.longest_losing_streak,
        "exposure": _q(m.exposure, "0.000001"),
        "sharpe": _q(m.sharpe, "0.01"),
        "sortino": _q(m.sortino, "0.01"),
        "costs": _q(m.costs, "0.01"),
    }


def params(p: Params) -> dict[str, Any]:
    return {
        "max_hold": p.max_hold,
        "reward_multiple": None if p.reward_multiple is None else format_decimal(p.reward_multiple),
        "risk_percent": format_decimal(p.risk_percent),
    }


def trade(t: Trade, precision: int) -> dict[str, Any]:
    q = "1E-" + str(precision + 1)
    return {
        "side": t.side,
        "decided_at": t.decided_at.isoformat(),
        "entry_at": t.entry_at.isoformat(),
        "exit_at": t.exit_at.isoformat(),
        "entry_price": _q(t.entry_price, q),
        "exit_price": _q(t.exit_price, q),
        "stop": _q(t.stop, q),
        "target": _q(t.target, q),
        "units": format_decimal(t.units),
        "pnl": _q(t.pnl, "0.01"),
        "r_multiple": _q(t.r_multiple, "0.01"),
        "costs": _q(t.costs, "0.01"),
        "bars_held": t.bars_held,
        "reason": t.reason,
    }


def build(
    *,
    instrument: str,
    timeframe: str,
    rule: str,
    rule_version: int,
    bars: su.Bars,
    start: int,
    end: int,
    data_types: Sequence[str],
    precision: int,
    seed: int,
    folds: int,
    costs_assumption: dict[str, str],
    full_params: Params,
    full: mt.Metrics,
    scenarios: Sequence[Scenario],
    wf: WalkForward,
    bench: Benchmarks,
    audit: Audit,
    generated_at: datetime,
) -> dict[str, Any]:
    oos_trades = [t for f in wf.folds for t in f.out_of_sample_run.trades]
    body: dict[str, Any] = {
        "label": LABEL,
        "notice": NOTICE,
        "instrument": instrument,
        "timeframe": timeframe,
        "rule": rule,
        "rule_version": rule_version,
        "engine_version": ENGINE_VERSION,
        "code_version": code_version(),
        "seed": seed,
        "data": {
            "snapshot_hash": data_hash(bars, 0, end),
            "bars": end - start,
            "warm_up_bars": start,
            "start": bars.ts[start].isoformat(),
            "end": bars.ts[end - 1].isoformat(),
            "data_types": sorted(data_types),
        },
        "costs": costs_assumption,
        "full_period": {
            "label": "full period, rule defaults (not fitted)",
            "params": params(full_params),
            "metrics": metrics(full),
        },
        "cost_sensitivity": [
            {
                "scenario": s.name,
                "spread_and_commission_multiplier": format_decimal(s.spread_and_commission),
                "slippage_multiplier": format_decimal(s.slippage),
                "metrics": metrics(s.metrics),
            }
            for s in scenarios
        ],
        "walk_forward": {
            "folds": folds,
            "selection": "best in-sample net return over the parameter grid",
            "stability": _q(wf.stability, "0.01"),
            "windows": [
                {
                    "fold": f.index,
                    "in_sample": [
                        bars.ts[f.in_sample[0]].isoformat(),
                        bars.ts[f.in_sample[1] - 1].isoformat(),
                    ],
                    "out_of_sample": [
                        bars.ts[f.out_of_sample[0]].isoformat(),
                        bars.ts[f.out_of_sample[1] - 1].isoformat(),
                    ],
                    "chosen": params(f.chosen),
                    "in_sample_metrics": metrics(f.in_sample_metrics),
                    "out_of_sample_metrics": metrics(f.out_of_sample_metrics),
                }
                for f in wf.folds
            ],
            "out_of_sample": metrics(wf.out_of_sample),
        },
        "benchmarks": {
            "span": [bars.ts[wf.span[0]].isoformat(), bars.ts[wf.span[1] - 1].isoformat()],
            "strategy_out_of_sample_return": _q(wf.out_of_sample.total_return, "0.000001"),
            "no_trade_return": _q(bench.no_trade, "0.000001"),
            "buy_and_hold_return": _q(bench.buy_and_hold, "0.000001"),
            "random_entry_mean_return": _q(bench.random_mean, "0.000001"),
            "random_entry_median_return": _q(bench.random_median, "0.000001"),
            "random_entry_runs": bench.random_runs,
            "strategy_beat_share_of_random_runs": _q(bench.strategy_beat_share, "0.01"),
            "note": bench.note,
        },
        "leakage_audit": {
            "passed": audit.passed,
            "cuts": [bars.ts[c].isoformat() for c in audit.cuts],
            "decisions_compared": audit.checked,
            "first_difference": None
            if audit.first_difference is None
            else bars.ts[audit.first_difference].isoformat(),
        },
        "out_of_sample_trades": [trade(t, precision) for t in oos_trades[:MAX_TRADES]],
        "out_of_sample_trades_listed": min(len(oos_trades), MAX_TRADES),
    }
    body["report_hash"] = report_hash(body)
    body["generated_at"] = generated_at.isoformat()
    return body


def canonical(report: dict[str, Any]) -> str:
    content = {k: v for k, v in report.items() if k not in ("generated_at", "report_hash")}
    return json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def report_hash(report: dict[str, Any]) -> str:
    return hashlib.sha256(canonical(report).encode()).hexdigest()
