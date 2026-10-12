# End-to-end journeys (P09-T10)

The real app, the live repositories and real HTTP, against a real backend and database.

## Run it
```
cd backend
uv run python -m tests.e2e_server --port 8765 --out ../e2e.json      # needs the compose Postgres (or CI service)
cd ../mobile/wealthsphere_app
WS_E2E_CONFIG=../../e2e.json flutter test e2e                         # skipped when the variable is unset
```
`backend/tests/e2e_server.py` creates a throwaway migrated database, seeds it through the public API (a user "Alice" with a portfolio, a deposit and a purchase, a stored market price, a goal, a registered device and a price alert that has fired), serves it, and drops the database on Ctrl+C. CI runs the same two commands in `.github/workflows/e2e.yml` (service Postgres, no mocks).

## Journeys (`mobile/wealthsphere_app/e2e/e2e_journeys_test.dart`)
1. **Sign in** from Settings: the account shows the server's account.
2. **View the portfolio**: greeting from the stored display name, net worth equal to a direct `GET /net-worth`, the holding priced from the stored market price (10 x 120).
3. **Add a transaction** (a deposit through the real form): the server books it (net worth up by exactly 500.00) and Home shows the server's new total.
4. **Forecast**: the calculator's projection equals a direct call to the forecast engine with the same inputs; no DEMO label.
5. **Goal progress**: the goal and the server's assumption notice.
6. **Notification deep link**: a notification tapped while signed out waits; after sign-in the Watchlist and alerts screen opens and shows the fired alert.

## What is and is not real
Real: HTTP, the API, authorization, the database, the services, the live repositories, the screens. Stood in for: the identity provider's browser login (a fake sign-in hands over a token signed with the test key the E2E backend trusts; the Keycloak login is covered by `backend/tests/test_identity_keycloak_live.py` and the device journeys), the device lock prompt, and FCM delivery (not configured, ADR-0016: journey 6 starts from the tap).
Not run here: an Android/iOS device or emulator run against this backend (the existing `integration_test` journeys cover the DEMO app on the emulator).
