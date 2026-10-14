# QG-14 (QG-FX-02): Technical Indicator Accuracy — P13-T12, 2026-10-14

The method is in [docs/design/forex-analysis.md](../../docs/design/forex-analysis.md). The formulas are in financial-methods section 19, and the tests are rows T-01 to T-18 of the financial test matrix.

| Criterion | Evidence | Result |
|---|---|---|
| 14.1 Indicator calculations match independently validated reference cases | `tests/forex/test_indicators.py`: every indicator equals an independent oracle written separately with exact arithmetic (`tests/forex/indicator_oracle.py`): SMA, EMA, MACD, RSI, stochastic, ROC, ATR, ADX and Bollinger. Hand-worked values; RSI equals the published worked example (`test_rsi_matches_the_published_worked_example`); exact warm-ups; undefined ratios are None, not zero; scaling and shifting properties; no float in the indicator modules; `test_no_indicator_depends_on_later_bars`. API: `test_indicators_equal_the_library_applied_to_the_stored_candles` | Pass |
| 14.2 Timeframe aggregation is correct | `tests/forex/test_candles_sessions.py`: five-minute bars are first open, extremes and last close, with volume summed; `test_the_hour_equals_the_sum_of_its_five_minute_periods`; weeks run Sunday to Friday close; months follow trading days; aggregation is deterministic and independent of input order; forming periods are marked and excluded. API: `test_five_minute_indicators_come_from_aggregated_minutes_and_flag_partial_bars`, `test_provider_candles_of_the_requested_timeframe_are_used_as_they_are` | Pass |
| 14.3 Missing candles and irregular market hours are handled | `test_missing_minutes_stay_missing_and_mark_the_period_partial`, `test_a_period_with_no_candles_is_absent_not_filled`, `test_the_weekend_gap_produces_no_candles_and_closed_minutes_are_ignored`, `test_expected_candle_counts`, daylight-saving tests; `test_candles_are_served_with_gaps_left_absent_and_forming_ones_not_stored`, `test_a_provider_outage_leaves_a_gap_and_is_reported_not_filled`; structure and patterns with too little data are empty, not invented | Pass |

Run: `cd backend && uv run pytest tests/forex -q` (part of the 753-test run of 2026-10-14; all passed).
