# Notifications and deep links (P09-T08, ADR-0016)

## Built now (everything except the vendor hop)
- **Backend** `devices` (migration 0013) and `POST/GET /api/v1/devices`, `DELETE /api/v1/devices/{id}`: a user registers a push token (max 10; re-registering refreshes it; the token is never returned in full; audited without the token; owner-scoped, IDOR-tested).
- **Payloads** (`notifications/push.py`): `type`, `alert_id`, `event_id`, `route` and nothing else. No amounts, prices, holdings or asset names (tested). The app fetches figures after sign-in.
- **Delivery** behind `PushSender`. The alert-evaluation job pushes each fired alert to the user's devices; a failing device does not stop the others and is logged by error type only. The only sender is `NullPushSender` until FCM/APNs is configured (`build_push_sender` is the one place to change).
- **Mobile**: `PushTokenSource` (no source yet), device registration at sign-in and removal at sign-out, `NotificationRoute` (an allow-list of in-app routes; URLs, other schemes and unknown routes are ignored), a pending deep link that waits through sign-in and is dropped at sign-out, and `DeepLinkHost` which opens the screen after authentication and then forgets the link.
- **Preferences**: the Watchlist and alerts screen has the three switches (all alerts, price alerts, allocation alerts), saved to `/alert-preferences`; off means those alerts are not checked.
- **In-app list**: every fired alert is on the Watchlist and alerts screen whether or not a device push happens.

## To switch device push on (open item for the user)
1. Create the Firebase project; add `google-services.json` and `GoogleService-Info.plist`; upload the APNs key to Firebase.
2. Add an FCM `PushSender` (backend) and a `PushTokenSource` backed by `firebase_messaging` plus the tap handler that calls `pendingDeepLinkProvider.received(payload)` (mobile).
3. Re-run the notification deep-link journey on a device.
