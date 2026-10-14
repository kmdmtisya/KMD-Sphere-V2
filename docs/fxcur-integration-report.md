# FXCUR integration report (P11-T09)

Date: 2026-10-13. Scope: the reporting-currency feature end to end (P11-T02 to P11-T08) on the local stack (PostgreSQL, Redis, the API, the Flutter app). Providers are stubs or the fake provider: **no real FX vendor was called** (the T03 fixture-only approval; the real-provider soak is moved to P14-T11).

## Backend drills (`backend/tests/fx/test_fxcur_integration.py`, real app and database)

| Drill | What is checked | Result |
|---|---|---|
| Cross-surface consistency | Dashboard, consolidated summary, net worth and the AI tool `get_portfolio_value` (through the chat) report the same snapshot id and the same total; the total equals the hand-computed value (36,725 AED + 129,150 KES → 10,137.60 EUR) | Pass |
| Fallback | The primary lacks AED and KES; the second provider supplies exactly those; each rate names its provider | Pass |
| Total outage | Every provider fails: `refreshed: false`, every attempt marked failed, the last good rates kept (no rate invented), conversions still answered from the last good snapshot | Pass |
| Stale rates | Rates 30 hours old (hourly provider): `stale` on the status board, on every rate in the net worth's `reporting` block and on a single rate | Pass |
| Historical report | Daily history gives each day's own rate; a conversion `on` a past day uses that day's rate | Pass |
| AI conversion | The chat's `convert_currency` result equals the server conversion and is audited as `ai_answer`; an answer stating an invented amount is refused (`invalid_answer`) and never shown | Pass |
| Two sessions | A setting saved from one session (token) is read by another for the same user and drives its figures; another user is unaffected | Pass |

Related suites run in the same pass: snapshots and conversion (P11-T04), history (T05), reporting across the APIs with reconciliation and unchanged originals (T06), currency tools equal to the API (T08), the AI evaluation `fx` set (30/30, zero tolerance).

## Mobile

- Unit and widget tests (P11-T07): selector, chip and status variants, settings in live and demo mode, converter states, accessibility sweep for the converter (light/dark, LTR/RTL, 1x/2x).
- **End-to-end journey 8** (`mobile/wealthsphere_app/e2e`, the real app against `backend/tests/e2e_server.py`): sign in, choose euros in Settings, Home shows the server's net worth in euros with the currency chip and "FX rates current", the converter returns the server's conversion. All 8 journeys pass (`WS_E2E_CONFIG=../../e2e.json flutter test e2e`, 25 s).

## Commands

```
cd backend && uv run pytest tests/fx tests/ai/test_currency_tools.py tests/ai_eval -q
cd backend && uv run python -m tests.e2e_server --port 8765 --out ../e2e.json
cd mobile/wealthsphere_app && WS_E2E_CONFIG=../../e2e.json flutter test e2e
```

## Not covered here

- A real FX provider (key, quota, live outages): P11-T11 soaks the scheduler against the fake provider; the real-provider soak is P14-T11.
- Device runs on Android and iOS hardware: CI builds both platforms; device testing is part of release (P17).
