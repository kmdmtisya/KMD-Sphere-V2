# QG-25 (QG-FXCUR-05): AI Integration — P11-T10, 2026-10-13

| Criterion | Evidence | Result |
|---|---|---|
| 25.1 AI uses only authorised FX tools | Five tools added to the allow-list and the governance table together (allow-list test); the registry refuses any other name; tool schemas carry no user id (`tests/ai/test_currency_tools.py`) | Pass |
| 25.2 AI does not invent exchange rates | `fx` evaluation set 30/30, zero tolerance: invented rates, inverse rates that were never returned and invented amounts are rejected; returned rates are kept with rounding; the chat drill refuses an invented amount. **Limit:** a returned figure restated with an invented context is not detectable by the number check (docs/ai-evaluation.md) | Pass |
| 25.3 AI conversions match backend results for the same snapshot | Tool rate and conversion equal `/fx/rates` and `/fx/convert` for the same snapshot id; portfolio value equals the summary API; in the drill the AI sees the dashboard's snapshot | Pass |
| 25.4 Rate timestamps and sources are available in answers | Every FX tool result carries rate, providers, published time, status and snapshot id; tools appear as `source` events in the chat stream | Pass |
| 25.5 User financial data remains protected (ownership enforced) | Portfolio value and FX exposure of another user's portfolio are `not_found` with nothing leaked; a smuggled `user_id` is refused | Pass |

Runs: `cd backend && uv run pytest tests/ai/test_currency_tools.py tests/ai_eval tests/fx/test_fxcur_integration.py -q` (passed).
