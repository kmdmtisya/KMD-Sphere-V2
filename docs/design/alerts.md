# Watchlists and alerts (P08-T07)

Backend only. Push delivery is P09-T07; the Opportunities and notification screens consume these
endpoints later.

## API

| Method and path | Purpose |
|---|---|
| `POST /api/v1/watchlist` | Add an asset (idempotent: 201 new, 200 already there). Max 100. |
| `GET /api/v1/watchlist` | The list with each asset's latest stored price and its `stale` flag. |
| `DELETE /api/v1/watchlist/{asset_id}` | Remove. |
| `POST/GET /api/v1/alerts`, `GET/PATCH/DELETE /api/v1/alerts/{alert_id}` | Alerts. Max 50. |
| `GET /api/v1/alerts/events[?unseen=true]` | Alerts that fired, newest first (100). |
| `POST /api/v1/alerts/events/{event_id}/seen` | Mark one seen. |
| `GET/PUT /api/v1/alert-preferences` | Master switch plus price and allocation switches. |

Everything is the signed-in user's own. Another user's ids answer 404 (ADR-0011); the cross-user
tests are named in `tests/idor_registry.py`.

## Alert types

- `price_above` / `price_below`: a price in the asset's own currency (a different currency is
  rejected, no conversion is guessed).
- `allocation_above`: an asset class's share (0 to 100 %) of one of the user's portfolios, measured
  by the same allocation the analytics API publishes.

## Evaluation (`app.modules.alerts.evaluation`, job `evaluate_alerts`, every 15 minutes)

- Only **active** alerts. A user with alerts (or that kind) switched off is skipped: nothing is
  queued, the alerts stay as they are.
- A price alert needs a stored price that is **not stale**; with none, or an old one, it does not
  fire. An allocation alert needs a measurable share.
- Fire when price >= threshold (above), price <= threshold (below) or share >= threshold.
- Firing is **one-shot**: the alert becomes `triggered` and one `alert_events` row is written; the
  user re-arms it with `PATCH {"status": "active"}`. The event is unique per (alert, trigger key),
  the key being the price observation time or the day, so evaluating the same data again changes
  nothing, and two evaluators cannot both fire one alert.
- Audit: `alerts.alert.created/updated/deleted`, `alerts.watchlist.added/removed`,
  `alerts.preferences.updated` by the user; `alerts.alert.triggered` by the system. Details hold no
  amounts or thresholds.

## Not here

No notification is sent (P09-T07), no alert on an AI opportunity score, and an alert is not advice
or a prediction: it only reports that a stored figure crossed a threshold the user chose.
