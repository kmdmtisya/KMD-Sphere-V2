# Forex backtesting and strategy validation, as built (P13-T08)

This document covers the backtester: how it runs, how it is validated, and where its results go. The design is in [forex-technical-design.md](forex-technical-design.md) section 10. The formulas are in [financial-methods.md](../financial-methods.md) section 22, and the tests are rows B-01 to B-06 of the financial test matrix. The QG-17 evidence is [reports/quality/qg-17-forex-backtest-validation.md](../../reports/quality/qg-17-forex-backtest-validation.md).

**Rules for what this module produces:**
- **Labelled `backtested`.** Results are a separate series. They are never added to paper (P13-T09) or live results.
- **A study, not a forecast.** A backtest shows how a published rule would have behaved on stored bars. Every report says that results on simulated data say nothing about real markets.
- **Costs always included.** Spread, slippage and commission are paid on every fill. Swaps are not modelled, and every report says so.
- **No look-ahead.** Every stored report carries the result of a leakage audit.
- **No language model** takes part, and nothing is traded.

## 1. Code

The code is in `backend/app/modules/forex/backtest/`:

| File | Content |
|---|---|
| `strategy.py` | Decisions, the rule strategy (the live setup rules and 200-bar window), shared setups per bar, and the leakage audit |
| `engine.py` | The event-driven engine: clock, fills with costs, sizing through the risk engine (P13-T07), and exits |
| `metrics.py` | Return, drawdown, win rate, profit factor, average trade, expectancy, streaks, exposure, Sharpe, Sortino and costs |
| `validation.py` | Walk-forward folds, benchmarks (no trade, buy and hold, seeded random entry) and cost sensitivity |
| `report.py` | The JSON report and its SHA-256 hash |
| `runner.py` | One pair, all six rules, no database |
| `store.py` | `forex_backtest_reports` (migration 0024), stored once per hash |
| `service.py` | Bars and the contract specification from the database, then run and store |
| `api.py` | The read-only API (section 4) |

The daily `forex_backtest` job runs every rule on every active pair at `forex_backtest_timeframe` (1H by default) at 02:10 UTC. It runs only when forex is switched on. The job is idempotent per day, and a report with an existing hash is not stored again.

## 2. How a run works

1. **Load bars.** The newest `forex_backtest_max_bars` closed bars are loaded. These are provider candles, or one-minute candles aggregated, as in the ranking. The first 199 bars only warm the indicators up.
2. **Find setups.** The setups of every bar are computed once from that bar's 200-bar history and shared by the six rules. The runner checks that the shared decisions equal the rule strategy's own.
3. **Simulate.** The engine fills each decision at the next open and exits by the stated order (financial-methods section 22).
4. **Validate and report.** Each rule gets a full-period run with the rule defaults, six cost scenarios, four walk-forward folds over a 9-point grid, the benchmarks and the leakage audit. The result is one report per rule.

About 9 ms per bar goes on finding setups, so 2,000 bars take about 20 seconds per pair. That is why runs happen in the job and the API only reads stored reports.

## 3. The four controls (QG-17)

| Gate | Control | Test |
|---|---|---|
| QG-17.1 Look-ahead | The clock: fills at the next open, and decisions see copies of closed bars only. The leakage audit rebuilds the strategy on a mirrored and a stretched future and compares the decisions before each cut. A deliberately leaky strategy, which reads the next close, fails; the real rules pass | `test_the_audit_fails_a_leaky_strategy_and_passes_the_real_one`, `test_later_bars_never_change_an_earlier_trade` |
| QG-17.2 Costs | Every fill pays half the spread and the slippage, plus commission per side. The sensitivity runs only raise costs | `test_a_decision_fills_at_the_next_open_with_costs_and_stays_within_the_risk`, `test_benchmarks_and_sensitivity` |
| QG-17.3 Walk-forward | Parameters are chosen in-sample and tested once on the next window. Windows never overlap, and in-sample and out-of-sample results are reported separately | `test_walk_forward_windows_never_overlap_and_choose_in_sample` |
| QG-17.4 Reproducible | The report hash covers the data snapshot hash, code version, parameters, seed and results, but not the generation time. The same inputs give the same hash | `test_reports_are_reproducible_and_fully_described` |

## 4. API

Both endpoints need sign-in and the forex flag; when the flag is off they answer 404. Reports are reference data, the same for every user.

- `GET /api/v1/forex/backtests?instrument=&timeframe=&rule=&limit=` returns summaries, newest first. Each summary gives the out-of-sample trades, return and profit factor, the data types, and whether the leakage audit passed.
- `GET /api/v1/forex/backtests/{id}` returns the full typed report:
  - the data snapshot, the cost assumptions and the full-period run;
  - the cost sensitivity;
  - every walk-forward window, in-sample and out-of-sample;
  - the benchmarks and the audit;
  - up to 1,000 out-of-sample trades.

## 5. Strategy history in the Opportunity Ranking

P13-T06 left the `strategy_history` factor at 0 until backtests existed. It now reads the newest stored report of the candidate's rule on the same pair and timeframe:
- the value is clip(out-of-sample profit factor − 1, 0, 1), or 1 when there was no losing trade;
- with fewer than 30 out-of-sample trades, or no report, it is 0;
- the factor's detail names the trade count and the data type.

The weight is unchanged at 0.05.

## 6. Limits and open items

- **No historical spread** is stored. The spread is an assumption per tier, stated in every report. A stored spread history would replace it.
- **Swaps and financing** are not modelled.
- **Intrabar order.** The path inside a bar is unknown, so when a bar touches both levels the stop is assumed first. This is the conservative order.
- **The simulated feed** is a daily wave plus noise. On it, mean-reversion and reversal rules look strong (see the QG-17 report). That is a property of the simulator, and it reaches the ranking's strategy history as a small, labelled factor. Real backtests need licensed data (DEC-19).
- **Survivorship.** The universe is fixed (12 pairs, none removed), so survivorship does not arise yet. If pairs are retired, their reports and bars are kept, because instruments are deactivated, never deleted.
