# Cross-platform feature parity matrix

**Status:** Proposed baseline (2026-10-14), built from repository evidence at commit 23d0903:
- the mobile live repositories under `mobile/wealthsphere_app/lib/features/*/data`;
- the mobile routes (`lib/app/app_routes.dart`);
- the API (`backend/openapi.json`).

Android and iOS share one Flutter codebase, so their columns match unless stated. "Web" is the task that delivers the capability; nothing on the web is implemented yet.

**Rules**
- **No false claims.** A capability that no platform has today is listed as a **planned dependency** (with its task), never as parity already reached.
- **New features record web status.** A new mobile capability is not done until this matrix records its web status, whether delivered or an exception with a reason. P14-T18 adds a CI check that every mobile route maps to a web route or a recorded exception.
- **Permissions.** "Owner" means the API returns only the signed-in user's own data and answers 404 for anyone else's (ADR-0011). "Reference" means the same answer for every signed-in user.
- **QG.** The gate whose evidence covers the row on the web: QG-26 to QG-34 (web) or QG-19 (forex web).

## 1. Capabilities in the apps today

| # | Capability | Android / iOS | Backend API | Permission | Web | Web tests | QG |
|---|---|---|---|---|---|---|---|
| 1 | Sign in (OIDC, PKCE), MFA (TOTP), sign out | Live (P04, P09) | Keycloak; `GET /me` | Signed in | P14-T05 (BFF, `wealthsphere-web` client) | e2e login and logout, expiry, MFA | QG-29 |
| 2 | Profile and preferences (theme, notifications) | Live | `GET /me`, `PATCH /me/preferences` | Owner | P14-T16 | component, e2e | QG-28 |
| 3 | Risk profile | Live | `GET/POST/PATCH /risk-profiles` | Owner | P14-T16 | API-contract, e2e | QG-28 |
| 4 | Home dashboard (wealth, net worth, income, goals) | Live (P09) | `GET /dashboard`, `/net-worth`, `/income/summary`, `/goals/summary` | Owner | **P14-T07 (priority)** | reconciliation with the API, e2e | QG-28, QG-30 |
| 5 | Portfolios: list, create, edit, archive; all-portfolio summary | Live | `GET/POST /portfolios`, `PATCH /portfolios/{id}`, `POST /…/archive`, `/portfolios/consolidated/summary`, `/portfolios/{id}/summary` | Owner | **P14-T08 (priority)** | CRUD e2e, IDOR via API | QG-28, QG-30 |
| 6 | Holdings | Live | `GET /portfolios/{id}/holdings` | Owner | **P14-T08** | grid, reconciliation | QG-28, QG-30 |
| 7 | Transactions: list, add (all types, multi-currency), reverse | Live | `GET/POST /portfolios/{id}/transactions`, `GET …/{tid}`, `POST …/{tid}/reversal` | Owner | **P14-T08** | e2e add and reverse, cross-channel sync | QG-28, QG-30, QG-33 |
| 8 | Manual valuations (assets without a market price) | Live | `/portfolios/{id}/valuations` (CRUD, `latest`) | Owner | **P14-T08** | CRUD e2e | QG-28 |
| 9 | Assets: classes, catalogue search, custom assets, detail and prices | Live | `/asset-classes`, `/assets/search`, `POST /assets`, `/assets/{id}`, `/assets/{id}/prices` | Reference, or owner for custom assets | **P14-T08** | component, e2e | QG-28 |
| 10 | Analytics: performance (TWR, XIRR, CAGR), allocation (class, currency, country), risk (volatility, drawdown) | Live | `/portfolios/{id}/performance`, `/allocation`, `/risk` | Owner | P14-T09 | reconciliation, chart a11y | QG-28, QG-30 |
| 11 | Compounding calculator | Live (backend-calculated) | `POST /forecasts/compound` | Signed in | P14-T10 | outputs equal the API | QG-30 |
| 12 | Wealth forecast scenarios | Live | `POST /forecasts/scenarios` | Signed in | P14-T10 | outputs equal the API | QG-30 |
| 13 | Goals: CRUD, progress, contribution estimate | Live | `/goals` (CRUD), `/goals/{id}/progress`, `/goals/summary`, `POST /forecasts/goal` | Owner | P14-T10 | CRUD e2e | QG-28 |
| 14 | Net worth and liabilities | Live | `/net-worth`, `/liabilities` (CRUD) | Owner | P14-T11 | reconciliation | QG-28, QG-30 |
| 15 | Passive income | Live | `/income/summary`, `/portfolios/{id}/income` | Owner | P14-T11 | reconciliation | QG-28, QG-30 |
| 16 | Reporting currency (global) and converter; FX status and refresh | Live (P11) | `/currencies`, `/me/currency-preferences`, `POST /fx/convert`, `/fx/status`, `POST /fx/refresh`, `/fx/rates`, `/fx/history` | Signed in, or owner for preferences | P14-T14 | currency switch e2e; equal to the API for the same snapshot | QG-28, QG-30 |
| 17 | AI Wealth Copilot: streamed chat, conversations, scopes | Live (P10) | `POST /ai/chat` (SSE), `/ai/conversations` (list, get, delete) | Owner; tools allow-listed and authorised server-side | **P14-T12 (priority)** | stream through the BFF; AI regression set reused; cross-user | QG-28, QG-29 |
| 18 | Portfolio Doctor | Live (P12) | `POST /ai/portfolio-doctor` | Owner | P14-T12 | e2e | QG-28 |
| 19 | Opportunities, runs, compare, simulate | Live (P12) | `POST /ai/opportunities`, `/ai/opportunities/runs`, `POST /ai/compare`, `POST /ai/simulate` | Owner | P14-T12 | e2e; notices shown | QG-28 |
| 20 | Investment universe, scores, compatibility, research | Live in the instrument screens (P12) | `/universe`, `/universe/scores`, `POST /universe/compatibility`, `/research` | Reference, or owner for compatibility | P14-T12 | component | QG-28 |
| 21 | Watchlist | Live | `/watchlist` (list, add, remove) | Owner | P14-T16 | e2e | QG-28 |
| 22 | Alerts, alert events, preferences | Live (P08, P09) | `/alerts` (CRUD), `/alerts/events`, `…/seen`, `/alert-preferences` | Owner | P14-T16 (notification centre) | e2e | QG-28 |
| 23 | Push notifications (device registration) | Live (FCM/APNs, P09) | `/devices` | Owner | **Exception:** no web push in v1; the notification centre shows the same events (row 22). Web push needs DEC-35 | — | — |
| 24 | App lock (biometrics) and encrypted offline snapshots | Live (ADR-0015) | — (client side) | — | **Exception:** replaced on the web by session idle and absolute timeouts and by no data at rest in the browser (architecture section 4) | timeout tests | QG-29 |
| 25 | Forex Intelligence (pairs, quotes, candles, stream, analysis, forecasts, Opportunity Ranking and scanner, risk calculator, calendar, backtests, paper trading and journal, Forex Copilot, notifications) | Built (P13-T11): More → Forex Intelligence, shown only when the section is available; DEMO fixtures and live API; the stream reconnects and pauses with the app | `/forex/quotes`, `/forex/candles`, `/forex/indicators`, `/forex/structure`, `/forex/forecasts`, `/forex/opportunities`, `/forex/calendar`, `/forex/risk/calculate`, `/forex/backtests`, `/forex/paper/...`, `WS /forex/stream`; Copilot forex tools (P13-T10) | Reference, or owner for paper trading; flag (DEC-23) | P14-T13 (entry and live markets) and **P14-T24** (advanced workspace, after P13 and the core web modules) | e2e with the simulated feed; paper-trading journey | QG-19 |

## 2. Required by the web brief, on no platform today (planned dependencies)

These are new capabilities, not parity gaps. Each needs backend work first (or a decision) and is delivered to the web, and where useful to mobile, by the listed task.

| # | Capability | Status today | Needs | Task |
|---|---|---|---|---|
| 26 | Reports and exports (PDF, CSV, XLSX): portfolio, performance, net worth, income, FX exposure, goals, forecast; forex strategy reports after P13-T08 | No endpoint on any channel | Backend report service from the same engines, with as-of times and currency on every file (DEC-33) | P14-T15 |
| 27 | Global search across own portfolios, assets, transactions, goals, reports and watchlist | Catalogue asset search only | Owner-scoped search endpoint | P14-T07 |
| 28 | Net-worth history chart | Current net worth only | History endpoint, from valuations and snapshots | P14-T11 |
| 29 | Dashboard customisation (order, visibility, default dashboard) | None | A preference shape for layouts (DEC-35) | P14-T07 |
| 30 | Saved table views | None | The same preference store, or per-browser convenience only | P14-T08 |
| 31 | Active session management (list, sign out others) | None in the apps | Keycloak account console (linked), or an account API through the BFF | P14-T16 |
| 32 | Account deletion workflow | Planned (P16-T05) | P16-T05 | P14-T16 shows it when available |
| 33 | Administration and operator views | **None exist.** The `support` realm role exists but no endpoint uses it | Decide the scope (DEC-34); role-gated, read-only operator endpoints | P14-T17 |
| 34 | Optimistic concurrency for cross-channel edits | Last write wins on PATCH | `ETag`/`If-Match` or `version` with 409 | P14-T18 |
| 35 | Performance attribution | Not computed | Out of scope unless approved; listed for completeness | — |

## 3. How the matrix is kept honest

- **In each web task.** When a web task is completed, its rows are updated with the PR, the tests and the gate evidence.
- **Cross-channel test (P14-T18).** The same user adds an investment through the API, as the mobile app does, then reads and edits it through the web BFF and reads it back. Run against the real backend in CI.
- **Reconciliation (QG-30).** For a seeded book, every figure on the web's dashboard, portfolio and net-worth pages equals the API response for the same request and currency. The mobile apps are already tested against those responses.
