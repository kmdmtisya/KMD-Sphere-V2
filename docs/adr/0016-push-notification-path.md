# ADR-0016: Push-notification path (DEC-08)

Status: Accepted (proposed in P09-T08, 2026-10-12; chosen by the user on 2026-10-12)

## Context
Alerts (P08-T07) fire on the server. Device push needs FCM (Android, and iOS through APNs), which needs a Firebase project and an APNs key from the user's Apple account. Those do not exist yet.

## Decision
1. Build the **provider-agnostic** parts now: a backend notification module (device registration, per-user preferences, payloads that carry no amounts or holdings), an in-app notification inbox fed by alert events, and deep-link routing that opens the right screen after sign-in.
2. **Delivery sits behind an interface** (`PushSender`). The default sender records nothing outward; the FCM/APNs sender is switched on when the Firebase project files and the APNs key are supplied (a later task; recorded as an open item).
3. Payloads contain an event type, an id and a route only; the app fetches the figures after authentication.

## Consequences
- Everything except the vendor hop is built and tested in P09; switching FCM on is configuration plus one adapter.
- Until then users see alerts in the app (inbox and badge), not as device notifications.
