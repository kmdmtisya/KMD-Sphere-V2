# Forex technical analysis, as built (P13-T03)

How P13-T03 was built: the indicator library, the session calendar, timeframe aggregation, market structure, the price-action detectors and their API. The design is in [forex-technical-design.md](forex-technical-design.md) section 5. Formulas and conventions are in [financial-methods.md](../financial-methods.md) section 19, and the tests that prove them are rows T-01 to T-18 of the financial test matrix.

**Rules:**
- Every figure is computed by the backend in `Decimal`. No language model computes, edits or invents an indicator value, a level or a pattern (a test checks that the analysis packages import nothing from the AI layer).
- Results describe past prices. None of them is a forecast or a probability.

## 1. Code

The code is in `backend/app/modules/forex/`:

| File | Content |
|---|---|
| `analysis/indicators.py` | SMA, EMA, MACD, RSI, Stochastic, ROC, true range, ATR, ADX, Bollinger Bands |
| `analysis/structure.py` | Swing points (confirmed, no look-ahead), support and resistance levels, breakouts, trendlines, channels |
| `analysis/patterns.py` | Doji, marubozu, hammer, hanging man, shooting star, inverted hammer, engulfing, harami, inside bar, morning and evening star, three soldiers and crows, range consolidation, breakout-and-retest |
| `analysis/registry.py` | Indicator requests (`name` or `name:p1,p2`), with bounded parameters: periods 1 to 500, multipliers above 0 and at most 10, at most 12 indicators per request |
| `analysis/service.py`, `analysis/api.py` | Candle loading, and the API (section 3) |
| `candles/sessions.py` | The FX session calendar on New York rollover |
| `candles/aggregate.py` | Aggregation of one-minute candles into 5m to 1M |
| `candles/sync.py` | Stores the provider's one-minute candles; worker job `forex_candle_sync` every 5 minutes when forex is switched on |

## 2. How the results are checked (QG-14)

| Criterion | Evidence |
|---|---|
| QG-14.1: indicators match independently validated references | `tests/forex/indicator_oracle.py` recomputes every indicator in exact `Fraction` arithmetic with different algorithms (closed-form weighted sums instead of running updates). On seeded random series the library matches it within 1e-18. The published RSI(14) worked example is matched exactly (70.53, 66.32, 66.55, 69.41, …). Hand-checkable cases cover each indicator; there are warm-up, edge-case, range, scale and shift tests, and a no-look-ahead test |
| QG-14.2: timeframe aggregation is correct | Boundaries for every timeframe, including daylight-saving weeks and months that start on a weekend; OHLC and volume arithmetic; an hour equals the sum of its 5-minute periods; results do not depend on input order |
| QG-14.3: missing candles and irregular hours are handled | Missing minutes give a period marked `partial`. A period with no candle is absent. Candles stamped while the market is closed are ignored and counted. A forming period is marked and left out of the analysis. Tests: `test_candles_sessions.py` and the API tests on stored data with deleted minutes |

## 3. API

All three endpoints need sign-in and the forex flag (404 when it is off). They serve reference data, the same for every user. Each takes `instrument`, `start` and `end` (with time zones, at most 366 days apart), `timeframe` and `price_basis` (mid by default).

- `GET /api/v1/forex/indicators?indicator=rsi:14&indicator=macd:12,26,9…`: one value per bar for each output. A value is null during the warm-up or where it is undefined, and `first_defined_index` says where the values start.
- `GET /api/v1/forex/structure`: swings with their confirmation time, levels with their role and touches, breakouts, and trendlines with their channel.
- `GET /api/v1/forex/patterns`: rule-based hits, each with its rule, category, bias and the candles it used.

Every response also carries:
- **Data coverage:** the candles' data types (for example `simulated`), the number of bars, partial bars, forming periods left out, and `truncated`.
- **A notice:** "descriptive only: not a forecast, a probability or advice".

**Which candles are used:**
- Stored candles of the requested timeframe when the provider published them.
- Otherwise, the stored one-minute candles aggregated on the calendar. At most `forex_analysis_source_cap` (150,000) are aggregated; a larger request is refused, and the caller asks for a shorter range.
- At most `forex_analysis_max_bars` (2,000) bars are analysed per call.

## 4. Open items

- **Holidays, early closes and per-pair rollover.** Public holidays and early closes are not modelled. Quotes continue through them and nothing is invented, but a holiday period counts its usual expected minutes and so shows as partial. A per-pair rollover other than 17:00 New York is not modelled either.
- **The simulated provider's closed hours** are fixed at Friday 21:00 to Sunday 21:00 UTC. That matches the calendar in summer (EDT) but is one hour early in winter. Real providers follow the market.
- **Levels from a whole window.** Levels are computed from all swings in the requested window, which suits display and explanation. Backtests (P13-T08) must compute structure on each prefix; the functions support this, because swings are confirmation-based.
- **Higher-timeframe candles are not stored.** Aggregation runs per request. Storing them is a P13-T13 soak decision.
