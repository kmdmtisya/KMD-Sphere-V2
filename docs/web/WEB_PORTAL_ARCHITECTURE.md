# WealthSphere Web Portal: architecture

**Status:** Approved. Phase P14 was approved on 2026-10-14 and [ADR-0018](../adr/0018-web-portal-architecture.md) was accepted on 2026-10-15 (P14-T02). Related documents:
- Appearance: [WEB_THEME_SYSTEM.md](WEB_THEME_SYSTEM.md)
- Design references: [WEB_DESIGN_REFERENCE_ANALYSIS.md](WEB_DESIGN_REFERENCE_ANALYSIS.md)
- UX: [WEB_UI_UX_SPECIFICATION.md](WEB_UI_UX_SPECIFICATION.md)
- Parity: [CROSS_PLATFORM_FEATURE_PARITY_MATRIX.md](CROSS_PLATFORM_FEATURE_PARITY_MATRIX.md)
- Deployment: [WEB_DEPLOYMENT_PLAN.md](WEB_DEPLOYMENT_PLAN.md)

## 1. One platform, three channels

```text
   Android app          iOS app            Web portal (browser)
   (Flutter)            (Flutter)          Next.js UI  ──►  Next.js BFF (server)
       │ bearer token        │ bearer token          session cookie │ bearer token
       └─────────────────────┴─────────────────────────────────────┤
                                                                    ▼
                         Keycloak (OIDC, PKCE, MFA)      WealthSphere API (FastAPI)
                         clients: mobile (public),       authorisation, ownership, audit,
                         web (confidential), api         financial engines, AI orchestrator,
                                                         market data, FX, forex
                                                                    │
                                                         PostgreSQL · Redis · workers
```

- **One backend.** Android, iOS and web call the same `/api/v1` endpoints, with the same schemas and the same server-side rules. The web adds no database, no business service and no second calculation path.
- **The BFF is a thin adapter.** It handles the OIDC code exchange, token custody, cookie sessions, CSRF and request forwarding. It never decides what a user may see; the API does that on every call, as it does for mobile.
- **The backend stays authoritative.** Valuation, XIRR, TWR, risk, FX conversion, forecasts, goals, scores and forex figures are computed only by the backend. The web formats decimal strings for display. It never parses money into floating point or does arithmetic on it; a lint rule and a test enforce this (QG-26.3).

## 2. Repository layout (proposed)

```text
web/                         Next.js app (new, P14-T04)
  app/                       routes (App Router): (auth), (portal)/home, portfolios, …
  app/api/                   BFF route handlers: auth/*, proxy/[...path], stream/*, ws-ticket
  src/client/                generated OpenAPI types + thin typed fetcher (no business logic)
  src/components/            design-system components (tables, cards, charts, AI, risk, states)
  src/features/<module>/     screens per module, mirroring mobile/lib/features
  src/tokens/                generated CSS variables (from design/tokens)
  tests/                     unit and component tests (Vitest), e2e (Playwright)
design/tokens/               wealthsphere.tokens.json, the single token source (P14-T03)
backend/                     unchanged; small additions only where the matrix says so
mobile/                      unchanged, apart from consuming the generated Dart palette
```

## 3. Sessions, tokens and security (DEC-31)

| Concern | Design |
|---|---|
| Sign-in | Authorization Code with PKCE from the BFF to Keycloak (`wealthsphere-web`, confidential, redirect URIs per environment). MFA (TOTP) is enforced by the realm as for mobile |
| Token custody | Access and refresh tokens stay server-side in Redis, encrypted with a key from the secret store, keyed by session ID. Nothing goes in localStorage or sessionStorage, and no token reaches browser JavaScript |
| Cookie | `__Host-ws_session`: HttpOnly, Secure, SameSite=Lax, path `/`, no domain. Rotated at sign-in and on privilege change |
| CSRF | Double-submit token: a readable cookie plus an `X-CSRF-Token` header on every non-GET call. Origin and Referer are checked. SameSite=Lax is a second layer |
| Forwarding | `/api/proxy/*` forwards to FastAPI with `Authorization: Bearer …`. Methods and paths are allow-listed to `/api/v1/*`, the body-size limit is kept, the correlation ID is passed through, and request bodies are never logged |
| Refresh and expiry | The BFF refreshes access tokens shortly before expiry. The idle timeout is 30 minutes and the absolute timeout 12 hours (to confirm against the realm). When either is reached, the session is removed and the user signs in again |
| Logout | The BFF session is deleted, the refresh token revoked, and Keycloak's RP-initiated logout ends the SSO session |
| Headers | Strict CSP with nonces, no inline script, `connect-src` limited to the BFF origin, `frame-ancestors 'none'`. HSTS in deployed environments. Plus the existing headers (nosniff, no-referrer, …) |
| Authorisation | Unchanged and server-side: ownership is checked on every resource (ADR-0011, 404 for another user's resource), and a role is checked for operator views (DEC-34). Hidden UI is never the control |
| Rate limits | The API's per-IP and per-account budgets apply as for mobile. The BFF also limits sign-in attempts per IP |
| Audit | Existing audit events (material financial changes, AI tool use) are written by the API and carry a `channel=web` attribute so channels can be told apart. Sign-in and logout are audited by Keycloak |
| Streams | AI chat (server-sent events) is proxied as a stream with backpressure. The forex WebSocket uses a single-use ticket valid for 30 s, minted by the BFF; the API exchanges it for a session (P14-T13) |

## 4. Data, caching and cross-platform consistency

- **The source of truth is the API.** The web keeps server state in TanStack Query with short stale times per kind of data, for example:
  - prices and quotes: as the API's freshness rules say;
  - analytics: the API's own cache (`analytics_cache_seconds`).
- **After a write**, the web invalidates the related queries, as mobile does, and the API invalidates its own per-user caches (`InvalidationMiddleware`). An investment added on Android therefore appears on the web at the next fetch or focus.
- **Refresh policy.**
  - Data is refetched on focus and reconnect.
  - Dashboards poll gently while visible (default 60 s; quotes faster where licensed).
  - No polling runs while the tab is hidden.
- **Concurrent edits.** Today the API is last-write-wins on PATCH (portfolios, goals, liabilities, valuations). Ledger transactions are append-only with reversals, so they cannot conflict. P14-T18 adds optimistic concurrency: `ETag`/`If-Match`, or a `version` field with 409 on conflict, for editable records used by both channels. The web shows a reload-and-compare prompt on 409. This is a backend change, listed in the matrix.
- **Preferences.** The reporting currency, theme and notification preferences are already server-side (`/me/preferences`, `/me/currency-preferences`) and shared across channels. Web-only layout preferences (sidebar, table views, dashboard layout) would need a small preferences extension (P14-T07, DEC-35). Until then they are kept per browser as conveniences.
- **Timestamps.** Every figure shows its as-of time from the API, rendered in the user's locale and time zone. Nothing is re-timestamped by the client.
- **Offline.** In v1 the web has no offline cache: financial data is not stored at rest in the browser. When offline, the portal shows an offline state and keeps nothing on disk. (Mobile keeps its encrypted snapshots, ADR-0015.)

## 5. Rendering and performance

- **Rendering split.** Server components render the shell and the first view of each page (data fetched server-side through the BFF with the user's session). Interactive panels (charts, grids, the copilot) are client components, loaded per route and lazily.
- **Responsive.** The same routes serve desktop (1280px and wider), laptop and tablet (768 to 1279px) and phone browsers (under 768px).
- **Large data.** Tables use server pagination where the API pages (transactions, events), and virtualisation for long client lists.
- **Charts.** Data is decimated; repaints are coalesced to at most about 4 per second while data streams.
- **Targets to approve (DEC-36).** Lighthouse performance at least 85 and accessibility at least 95 on the tested pages; LCP at most 2.5 s, INP at most 200 ms and CLS at most 0.1 at p75; dashboard API p95 at most 500 ms. All are measured in CI (Lighthouse CI) and in staging, and nothing is claimed without measurements (QG-31).

## 6. Observability

- **Front-end errors.** These go to the backend's telemetry through a BFF endpoint, with no personal data, no amounts and no tokens. The OpenTelemetry trace context runs from the browser to the BFF to the API, keeping the existing correlation ID.
- **BFF metrics.** Sign-in successes and failures, refreshes, proxy latency, upstream error rate and session count.
- **Real-user monitoring.** Web vitals are sampled in production and sent to the same metrics stack (P15).

## 7. Backend changes this workstream needs

Each change is small, and tested and documented like any other API change.

| Change | Task | Why |
|---|---|---|
| Keycloak client `wealthsphere-web` (confidential, PKCE, redirect URIs) and `OIDC_AUTHORIZED_PARTIES` adding `wealthsphere-web` | P14-T05 | Web sign-in |
| `channel` attribute on audit events (from a BFF header, validated) | P14-T05 | Telling channels apart in the audit trail |
| Optimistic concurrency on editable records (`ETag`/`If-Match` or `version`) | P14-T18 | Safe cross-channel edits |
| Report and export endpoints (PDF, CSV, XLSX) generated by the backend from the same engines | P14-T15 (DEC-33) | Exports must reconcile with the screens; none exist today on any channel |
| Net-worth history endpoint | P14-T11 | The web dashboard asks for a history series; today only the current net worth exists |
| Search endpoint across the user's own portfolios, assets, transactions and goals (owner-scoped) | P14-T07 | Global search; today only catalogue asset search exists |
| Operator endpoints behind the `support` role (read-only operational status) | P14-T17 (DEC-34) | No admin functions exist today; scope to be decided |
| Web-ticket exchange for the forex WebSocket | P14-T13 | Browser streaming without a token in the URL |
