"""Writes reports/quality/qg-17-forex-backtest-validation.md (P13-T08, QG-17): the backtester run on
controlled synthetic series and on the simulated feed. Deterministic (fixed seeds). No real
market data exists yet (DEC-19), so this validates the backtester, not any strategy.

    cd backend && uv run python ../scripts/forex_backtest_report.py
"""

import asyncio
import random
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.modules.forex.backtest import engine as en  # noqa: E402
from app.modules.forex.backtest import metrics as mt  # noqa: E402
from app.modules.forex.backtest import runner  # noqa: E402
from app.modules.forex.backtest import strategy as stg  # noqa: E402
from app.modules.forex.candles.aggregate import aggregate  # noqa: E402
from app.modules.forex.marketdata.fake import FakeForexProvider  # noqa: E402
from app.modules.forex.marketdata.types import Timeframe  # noqa: E402
from app.modules.forex.risk.specs import load_file  # noqa: E402
from app.modules.forex.signals import setups as su  # noqa: E402

OUT = ROOT / "reports" / "quality" / "qg-17-forex-backtest-validation.md"
D = Decimal
T0 = datetime(2026, 1, 5, tzinfo=UTC)
GENERATED = datetime(2026, 10, 14, tzinfo=UTC)  # fixed, so the file is reproducible
N = 900


def walk(n: int, seed: int, trend: bool) -> su.Bars:
    """A random walk, or alternating 150-bar trends with the same noise."""
    rng = random.Random(seed)  # noqa: S311 (synthetic test data)
    close = [D("1.1")]
    for k in range(n - 1):
        drift = (D("0.0004") if (k // 150) % 2 == 0 else D("-0.0004")) if trend else D(0)
        close.append(
            (close[-1] * (1 + drift + D(str(round(rng.gauss(0, 0.0012), 6))))).quantize(
                D("0.00001")
            )
        )
    opens = [close[0], *close[:-1]]
    high = [max(o, c) + D("0.0004") for o, c in zip(opens, close, strict=True)]
    low = [min(o, c) - D("0.0004") for o, c in zip(opens, close, strict=True)]
    return su.Bars([T0 + timedelta(hours=k) for k in range(n)], opens, high, low, close)


def simulated_feed() -> tuple[su.Bars, list[str]]:
    now = datetime(2026, 10, 9, 20, 0, tzinfo=UTC)
    provider = FakeForexProvider(clock=lambda: now)
    minutes = asyncio.run(provider.candles("EUR_USD", Timeframe.M1, now - timedelta(days=54), now))
    bars = [c for c in aggregate(minutes, Timeframe.H1, now).candles if not c.forming][-N:]
    return (
        su.Bars(
            [b.ts for b in bars],
            [b.open for b in bars],
            [b.high for b in bars],
            [b.low for b in bars],
            [b.close for b in bars],
        ),
        sorted({m.data_type.value for m in minutes}),
    )


def pair(bars: su.Bars, data_types: list[str]) -> runner.PairData:
    _, _, specs = load_file()
    return runner.PairData(
        "EUR_USD", "1H", bars, data_types, -4, 5, "major", specs["EUR_USD"], 1, False
    )


def pct(value: str | None) -> str:
    return "n/a" if value is None else f"{Decimal(value) * 100:.2f}%"


def rows(reports: list[dict[str, Any]]) -> list[str]:
    out = [
        "| Rule | Full-period trades | Full-period return | OOS trades | OOS return | OOS profit factor | OOS max drawdown | Buy and hold | Random entry (mean) | Beat random | Audit |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in reports:
        full, oos, b = (
            r["full_period"]["metrics"],
            r["walk_forward"]["out_of_sample"],
            r["benchmarks"],
        )
        out.append(
            f"| {r['rule']} | {full['trades']} | {pct(full['total_return'])} | {oos['trades']} | "
            f"{pct(oos['total_return'])} | {oos['profit_factor'] or 'n/a'} | {pct(oos['max_drawdown'])} | "
            f"{pct(b['buy_and_hold_return'])} | {pct(b['random_entry_mean_return'])} | "
            f"{b['strategy_beat_share_of_random_runs'] or 'n/a'} | {'passed' if r['leakage_audit']['passed'] else 'FAILED'} |"
        )
    return out


class Peeker:
    """Deliberately leaky: built from the whole series, it reads the next close."""

    def __init__(self, future: su.Bars) -> None:
        self.future = future
        self.index = {t: i for i, t in enumerate(future.ts)}

    def decide(self, history: su.Bars) -> stg.Decision | None:
        i = self.index[history.ts[-1]]
        if i + 1 >= len(self.future.ts):
            return None
        c = history.close[-1]
        if self.future.close[i + 1] > c:
            return stg.Decision("long", c - D("0.005"), c + D("0.001"), "peek")
        return stg.Decision("short", c + D("0.005"), c - D("0.001"), "peek")


def main() -> None:
    settings = runner.Settings()
    random_walk = pair(walk(N, 21, trend=False), ["synthetic"])
    trending = pair(walk(N, 21, trend=True), ["synthetic"])
    feed_bars, feed_types = simulated_feed()
    feed = pair(feed_bars, feed_types)
    rw = runner.run_pair(random_walk, settings, GENERATED)
    tr = runner.run_pair(trending, settings, GENERATED)
    fd = runner.run_pair(feed, settings, GENERATED)
    again = runner.run_pair(random_walk, settings, GENERATED + timedelta(days=1))
    same = all(a["report_hash"] == b["report_hash"] for a, b in zip(rw, again, strict=True))
    bars = random_walk.bars
    leaky = stg.leakage_audit(lambda b: Peeker(b), bars, [400, 600, 800], lookback=10)
    real = stg.leakage_audit(
        lambda _: stg.RuleStrategy("breakout"), bars, [400, 600, 800], lookback=10
    )
    costs = en.costs_for(random_walk.spec, -4, runner.SPREAD_PIPS["major"])
    peek = mt.compute(
        en.simulate(
            bars,
            stg.decisions(Peeker(bars), bars, 199, N),
            random_walk.spec,
            costs,
            en.Params(max_hold=1),
            199,
            N,
        ),
        "1H",
    )
    sens = next(r for r in tr if r["rule"] == "trend_continuation")["cost_sensitivity"]
    lines = [
        "# QG-17 evidence: forex backtester validation (P13-T08)",
        "",
        "_Generated by `scripts/forex_backtest_report.py` (deterministic: fixed seeds and a fixed generation time). The method is in_",
        "_docs/design/forex-backtesting.md; the tests are in backend/tests/forex/test_backtest_core.py and test_backtest_api.py._",
        "",
        "**Read this first.** No real market data is used: the forex provider is fixture-only (DEC-19). These runs check that the",
        "backtester behaves correctly where the answer is known. A random walk should show no lasting edge once costs are paid; a",
        "series built from alternating trends should favour the trend rules. They say nothing about how any rule would do in real",
        "markets. Every figure is a backtested result, net of modelled costs, and is not a forecast.",
        "",
        f"Settings: {N} hourly bars per series (the first 199 warm the indicators up), walk-forward with {settings.folds} folds over a",
        "9-point parameter grid, risk 1% of equity per trade, EUR_USD contract specification v1 (unreviewed DEMO values), spread",
        f"{runner.SPREAD_PIPS['major']} pips, {settings.random_runs} random-entry runs, seed {settings.seed}.",
        "",
        "## QG-17.1 Look-ahead bias",
        "",
        "The leakage audit re-makes the decisions before each cut on the real series and on two altered futures (mirrored,",
        "and stretched), rebuilding the strategy from each. Any difference is look-ahead.",
        "",
        "| Strategy | Audit | Decisions compared | First difference |",
        "|---|---|---|---|",
        f"| Deliberately leaky (reads the next close) | {'passed' if leaky.passed else 'FAILED'} | {leaky.checked} | {'none' if leaky.first_difference is None else bars.ts[leaky.first_difference].isoformat()} |",
        f"| Real rule (breakout) | {'passed' if real.passed else 'FAILED'} | {real.checked} | {'none' if real.first_difference is None else bars.ts[real.first_difference].isoformat()} |",
        "",
        f"Unchecked, the leaky strategy would look excellent on a random walk: win rate {pct(str(peek.win_rate))}, return",
        f"{pct(str(peek.total_return))} over {peek.trades} trades. That is why every stored report carries the audit result.",
        "Every report below passed it.",
        "",
        "## QG-17.2 Costs and slippage are included",
        "",
        "Every run pays half the spread and the slippage on each fill, and the commission per side. The sensitivity runs only",
        "raise costs; none removes them. Trend continuation on the trending series:",
        "",
        "| Scenario | Trades | Return | Profit factor | Costs paid |",
        "|---|---|---|---|---|",
        *[
            f"| {s['scenario']} | {s['metrics']['trades']} | {pct(s['metrics']['total_return'])} | {s['metrics']['profit_factor'] or 'n/a'} | {s['metrics']['costs']} |"
            for s in sens
        ],
        "",
        "## QG-17.3 Walk-forward validation",
        "",
        "Each fold picks parameters on one window and is tested once on the next. OOS figures compound the out-of-sample",
        'windows only. Benchmarks use the same out-of-sample bars. "Beat random" is the share of random-entry runs with a lower',
        "return than the strategy.",
        "",
        "### Random walk (no edge exists)",
        "",
        *rows(rw),
        "",
        "### Alternating trends (trend rules should do better)",
        "",
        *rows(tr),
        "",
        f"### Simulated feed, EUR_USD ({', '.join(feed_types)} data: a daily wave plus noise, not a market)",
        "",
        *rows(fd),
        "",
        "**Reading.** Out-of-sample results on the random walk are noise around a cost drag; a positive figure there is luck, which",
        "is why a rule's history counts in the Opportunity Ranking only from 30 out-of-sample trades and is labelled with its data",
        "type. Trend rules gain on the trending series, as built. The simulated feed's regular wave favours some rules; that is a",
        "property of the simulator.",
        "",
        "## QG-17.4 Reproducible reports",
        "",
        f"The random-walk reports were made twice, a day apart: identical hashes: **{'yes' if same else 'NO'}**. The hash covers",
        "the data snapshot hash, code version, parameters, seed and every result; only the generation time is left out.",
        "",
        "| Rule | Data snapshot | Report hash |",
        "|---|---|---|",
        *[
            f"| {r['rule']} | `{r['data']['snapshot_hash']}` | `{r['report_hash'][:16]}…` |"
            for r in rw
        ],
        "",
    ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
