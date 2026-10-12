# QG-22 (QG-FXCUR-02): Portfolio Consistency — P11-T10, 2026-10-13

| Criterion | Evidence | Result |
|---|---|---|
| 22.1 Portfolio totals reconcile after currency conversion | `tests/fx/test_reporting_currency.py::test_figures_follow_the_preference_and_reconcile_under_one_snapshot` (total equals the sum of converted parts within cents; shares add up); consolidated summary tests in `tests/test_summary_api.py` | Pass |
| 22.2 Original transaction values remain unchanged | Same test: transaction, portfolio and goal rows identical before and after several currency switches; goal target currency unchanged; forecast inputs unchanged (`test_a_forecast_keeps_its_inputs_and_translates_only_its_end_values`) | Pass |
| 22.3 Multi-currency holdings aggregate correctly | USD + AED portfolios converted per part under one snapshot; AED + KES to EUR in the integration drill (10,137.60 EUR, computed by hand) | Pass |
| 22.4 Historical reporting uses the appropriate historical rates | `tests/fx/test_history.py` (each day its own rate, never today's; missing days flagged; a ledger posting uses its trade date's rate); conversion `on` a past day; analytics stay on posting-date rates (docs/design/reporting-currency.md) | Pass |
| 22.5 Dashboard and report totals agree for the same rate snapshot | `tests/fx/test_fxcur_integration.py::test_dashboard_summary_net_worth_and_ai_agree_for_one_snapshot` (same snapshot id and total on dashboard, summary, net worth and the AI tool) | Pass |

Run: `cd backend && uv run pytest tests/fx tests/test_summary_api.py -q` (passed).
