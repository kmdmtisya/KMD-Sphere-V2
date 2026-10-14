# Forex signals and the Opportunity Ranking, as built (P13-T06)

How the setup rules, the opportunity score, the market condition and risk level, and the ranking API were built. The design is in [forex-technical-design.md](forex-technical-design.md) section 8. The formulas are in [financial-methods.md](../financial-methods.md) section 20, and the tests are rows O-01 to O-06 of the financial test matrix.

**Rules for what this module produces:**
- **Research candidates only.** Every item is a candidate, not advice, not a recommendation to buy or sell, and not a probability of profit.
- **Illustrative levels.** Levels come only from stored bars and the rule definitions, and carry the time of the bar they are based on. They are not orders.
- **No trade or guarantee wording.** Scenarios are "Bullish scenario" or "Bearish scenario". No text uses buy, sell, will or guarantee wording: a test runs the AI answer guard and a trade-word check over every string.
- **No language model** decides a setup, a score or a ranking.

## 1. Code

The code is in `backend/app/modules/forex/signals/`:

| File | Content |
|---|---|
| `setups.py` | Six versioned rules: trend continuation, breakout, reversal, range, momentum and mean reversion. Each has an invalidation level and a target; the thresholds are in the module docstring |
| `scoring.py` | The weights (setting `forex_signal_weights`, validated, version 1), the score, the market condition and the risk level |
| `ranking.py` | Candidates for a pair, with factors, adjustments, assumptions, risks, costs and freshness, and the ranking |
| `service.py` | Per pair: closed bars (provider candles of the timeframe, or aggregated minutes), the latest quote for the spread, event windows from the calendar, and the matching forecast (5m → 15m, 15m → 1h, 1H → 4h, 4H → 24h, 1D → 1w) |
| `api.py` | The ranking API (section 3) |

## 2. Score, condition and risk

The score is 100 × clip(Σ weight × component, 0, 1), over ten components. Macro-event risk is a negative weight (a penalty). Each item shows every factor with its value, weight, contribution and a plain explanation.

**Adjustments.** Each adjustment is stated in `adjustments`:

| When | Effect |
|---|---|
| A high-importance event window is open or about to open | Score × 0.5 |
| There is no fresh quote (the spread is unknown) | Score × 0.75 |
| The bars are stale (more than two periods old) | Excluded, and listed under `excluded` |

**Forecasts.** A forecast that requires calibration contributes nothing, and says so. A calibrated one counts only when it agrees with the setup.

**Strategy history.** It contributes 0 until out-of-sample backtests exist (P13-T08), and the factor says so.

**Market condition,** in priority order:
1. High volatility: ATR above 1.5 × its median.
2. Trending: ADX ≥ 25.
3. Momentum strengthening: ADX and the MACD histogram growing.
4. Consolidating: ADX < 20.
5. Otherwise, mixed.

**Risk level.** Points from volatility, the spread relative to ATR, and event windows give low, medium, medium-high or high.

## 3. API

Both endpoints need sign-in and the forex flag (404 when it is off). They serve reference data, the same for every user.

`GET /api/v1/forex/opportunities?timeframe=1H[&setup][&risk][&tier]` returns the best setup of each active pair, ranked.

**Each item carries:**
- `label` ("Research candidate"), market condition, opportunity type, scenario and risk;
- the score, levels and pips;
- every factor;
- adjustments, assumptions, risks and the rule's evidence;
- costs (spread only; swaps and slippage are not included);
- freshness (bar and quote age, data types);
- the forecast reference, with its calibration label;
- the rule and its version.

The response also publishes the weights and their version, and lists excluded items separately.

`GET /api/v1/forex/opportunities/setups?instrument=&timeframe=` returns every setup of one pair, best first.

The ranking is computed on request from stored data: about a second for 12 pairs. A cache or precomputation is a P13-T13 soak decision.

## 4. Open items

- **Strategy history** waits for P13-T08 backtests.
- **Costs** cover only the latest spread. Swap and commission models come with the risk engine (P13-T07).
- **With the simulated feed,** setups reflect the simulator's daily wave. Items carry the `simulated` data type and a risk line saying so.
