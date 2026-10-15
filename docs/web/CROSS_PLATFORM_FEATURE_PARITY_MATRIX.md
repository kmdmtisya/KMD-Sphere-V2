# Cross-platform feature parity matrix

**Status:** Baseline (2026-10-14, commit 23d0903), re-verified for P14-T01 on 2026-10-15 at `main` 3b3c6b1 ([repository audit](WEB_REPOSITORY_AUDIT.md)). Built from:
- the mobile live repositories under `mobile/wealthsphere_app/lib/features/*/data`;
- the mobile routes (`lib/app/app_routes.dart`);
- the API (`backend/openapi.json`).

Android and iOS share one Flutter codebase, so their columns match unless stated. "Web" is the task that delivers the capability; nothing on the web is implemented yet.

**Navigation (P14-T06).** Every web route and the mobile destination it answers are defined in `web/src/lib/nav/nav.ts`, and a unit test checks that every mobile route maps to a web route or one of the recorded exceptions (`MOBILE_EXCEPTIONS`: welcome, sign-in, the More hub, the debug gallery). P14-T18 adds the CI check against the app's own route list.

**Rules**
- **No false claims.** A capability that no platform has today is listed as a **planned dependency** (with its task), never as parity already reached.
- **New features record web status.** A new mobile capability is not done until this matrix records its web status, whether delivered or an exception with a reason. P14-T18 adds a CI check that every mobile route maps to a web route or a recorded exception.
- **Permissions.** "Owner" means the API returns only the signed-in user's own data and answers 404 for anyone else's (ADR-0011). "Reference" means the same answer for every signed-in user.
- **QG.** The gate whose evidence covers the row on the web: QG-26 to QG-36 (web) or QG-19 (forex web).
- **"API only".** The backend has the capability, but no mobile screen uses it (P14-T01 audit). The web builds it as an **extension** on the existing API. It is not counted as parity, and it is not a backend gap.

## 1. Capabilities in the apps today

| # | Capability | Android / iOS | Backend API | Permission | Web | Web tests | QG |
|---|---|---|---|---|---|---|---|
| 1 | Sign in (OIDC, PKCE), MFA (TOTP), sign out | Live (P04, P09) | Keycloak; `GET /me` | Signed in | **Built (P14-T05):** BFF sign-in with the `wealthsphere-web` client, server-side sessions, CSRF, sign-out | e2e against Keycloak: login, no token in the browser, CSRF, cross-user 404, logout and cookie replay, TOTP enrolment; unit tests for idle, absolute expiry and refresh | QG-29 |
| 2 | Profile and preferences (theme, notifications) | Live | `GET /me`, `PATCH /me/preferences` | Owner | P14-T16; **Appearance built (P14-T25):** Light, Dark, System, saved to `theme_mode` and applied at sign-in on any browser (mobile saves it on the device only until P14-T18 adds the approved sync, DEC-40) | component, e2e | QG-28, QG-36 |
| 3 | Risk profile | API only (no mobile screen) | `GET/POST/PATCH /risk-profiles` | Owner | P14-T16 | API-contract, e2e | QG-28 |
| 4 | Home dashboard (wealth, net worth, income, goals) | Live (P09) | `GET /dashboard`, `/net-worth`, `/income/summary`, `/goals/summary` | Owner | **Built (P14-T07):** net worth, assets, liabilities, portfolio value, unrealised P/L, income, goals, allocation, recent activity, Portfolio Doctor insights | every headline figure compared with the API's response (e2e, real stack); states: loading, error, stale, empty, offline | QG-28, QG-30 |
| 5 | Portfolios: list, create, edit, archive; all-portfolio summary | Live (archive: API only) | `GET/POST /portfolios`, `PATCH /portfolios/{id}`, `POST /…/archive`, `/portfolios/consolidated/summary`, `/portfolios/{id}/summary` | Owner | **Built (P14-T08)** | CRUD e2e, IDOR via API | QG-28, QG-30 |
| 6 | Holdings | Live | `GET /portfolios/{id}/holdings` | Owner | **Built (P14-T08)** | grid, reconciliation | QG-28, QG-30 |
| 7 | Transactions: list, add (all types, multi-currency), reverse | Live | `GET/POST /portfolios/{id}/transactions`, `GET …/{tid}`, `POST …/{tid}/reversal` | Owner | **Built (P14-T08)** | e2e add and reverse, cross-channel sync | QG-28, QG-30, QG-33 |
| 8 | Manual valuations (assets without a market price) | API only (no mobile screen) | `/portfolios/{id}/valuations` (CRUD, `latest`) | Owner | **Built (P14-T08)** | CRUD e2e | QG-28 |
| 9 | Assets: classes, catalogue search, custom assets, detail and prices | Live (catalogue search and custom assets: API only) | `/asset-classes`, `/assets/search`, `POST /assets`, `/assets/{id}`, `/assets/{id}/prices` | Reference, or owner for custom assets | **Built (P14-T08)** | component, e2e | QG-28 |
| 10 | Analytics: performance (TWR, XIRR, CAGR), allocation (class, currency, country), risk (volatility, drawdown) | Live | `/portfolios/{id}/performance`, `/allocation`, `/risk` | Owner | **Built (P14-T09):** performance (return, XIRR, TWR, profit or loss), value over time with periods, risk (volatility, largest fall), allocation by class, currency, country and sector with drill-down, concentration, portfolio comparison | unit, e2e reconciliation with the API, cross-user 404, axe Light and Dark | QG-28, QG-30 |
| 11 | Compounding calculator | Live (backend-calculated) | `POST /forecasts/scenarios` (the app's calculator); `POST /forecasts/compound` is unused by the app | Signed in | **Built (P14-T10):** inputs, three scenarios, growth chart with table alternative, target planner (`POST /forecasts/goal`); projections labelled, never a promise | e2e: outputs equal the API; bad input; axe Light and Dark | QG-30 |
| 12 | Wealth forecast scenarios | Live | `POST /forecasts/scenarios` | Signed in | **Built (P14-T10):** cautious, base and optimistic rates, nominal and today's-money values, reporting-currency note | e2e: outputs equal the API | QG-30 |
| 13 | Goals: CRUD, progress, contribution estimate | Live (contribution estimate `POST /forecasts/goal`: API only) | `/goals` (CRUD), `/goals/{id}/progress`, `/goals/summary`, `POST /forecasts/goal` | Owner | **Built (P14-T10):** list with progress, create, edit, delete, estimated completion, required contribution, scenario outcomes | unit; e2e CRUD, progress equals API, cross-user 404, axe | QG-28 |
| 14 | Net worth and liabilities | Live (liabilities CRUD: API only) | `/net-worth`, `/liabilities` (CRUD) | Owner | **Built (P14-T11):** net worth, assets and liabilities, history chart, assets by class, liabilities add, edit and delete | unit; e2e: totals equal the API, CRUD, cross-user 404, axe Light and Dark | QG-28, QG-30 |
| 15 | Passive income | Live | `/income/summary`, `/portfolios/{id}/income` | Owner | **Built (P14-T11):** summary, per portfolio, last 12 months (gross, fees, taxes, net), by type and by asset, monthly chart | e2e: figures equal the API, axe Light and Dark | QG-28, QG-30 |
| 16 | Reporting currency (global) and converter; FX status and refresh | Live (P11; `/fx/rates` and `/fx/history`: API only) | `/currencies`, `/me/currency-preferences`, `POST /fx/convert`, `/fx/status`, `POST /fx/refresh`, `/fx/rates`, `/fx/history` | Signed in, or owner for preferences | P14-T14 | currency switch e2e; equal to the API for the same snapshot | QG-28, QG-30 |
| 17 | AI Wealth Copilot: streamed chat, conversations, scopes | Live (P10) | `POST /ai/chat` (SSE), `/ai/conversations` (list, get, delete) | Owner; tools allow-listed and authorised server-side | **Built (P14-T12):** streamed answers with checks, sources and the four parts apart; refusals; history; docked panel scoped to the portfolio in view. Doctor, opportunities, universe, research, compare and simulate pages | unit (SSE parser, turn), e2e (unavailable, streamed answer, refusal, no HTML rendering, cross-user 404, axe); Doctor equals the API | QG-28, QG-29 |
| 18 | Portfolio Doctor | Live (P12) | `POST /ai/portfolio-doctor` | Owner | **Built (P14-T12):** checks with severity, measured value, threshold and assumptions; what-if scenarios (not trades) | e2e: findings equal the API, cross-user 404, axe Light and Dark | QG-28 |
| 19 | Opportunities, runs, compare, simulate | Live (P12; simulate hands off to the calculator, `POST /ai/simulate`: API only) | `POST /ai/opportunities`, `/ai/opportunities/runs`, `POST /ai/compare`, `POST /ai/simulate` | Owner | **Built (P14-T12):** candidates with risks, assumptions and evidence, earlier searches, compare 2 to 5, simulate under your own returns (no default) | e2e: compare and simulate run only where the universe has 2 or more instruments | QG-28 |
| 20 | Investment universe, scores, compatibility, research | API only (the instrument screens use DEMO data) | `/universe`, `/universe/scores`, `POST /universe/compatibility`, `/research` | Reference, or owner for compatibility | **Built (P14-T12):** universe with eligibility, research library; DEMO labelled | e2e: universe and research load, axe Light and Dark | QG-28 |
| 21 | Watchlist | Live | `/watchlist` (list, add, remove) | Owner | P14-T16 | e2e | QG-28 |
| 22 | Alerts, alert events, preferences | Live (P08, P09) | `/alerts` (CRUD), `/alerts/events`, `…/seen`, `/alert-preferences` | Owner | P14-T16 (notification centre) | e2e | QG-28 |
| 23 | Push notifications (device registration) | Live (FCM/APNs, P09) | `/devices` | Owner | **Exception:** no web push in v1; the notification centre shows the same events (row 22). Web push needs DEC-35 | — | — |
| 24 | App lock (biometrics) and encrypted offline snapshots | Live (ADR-0015) | — (client side) | — | **Exception:** replaced on the web by session idle and absolute timeouts and by no data at rest in the browser (architecture section 4) | timeout tests | QG-29 |
| 25 | Forex Intelligence (pairs, quotes, candles, stream, analysis, forecasts, Opportunity Ranking and scanner, risk calculator, calendar, backtests, paper trading and journal, Forex Copilot, notifications) | Built (P13-T11): More → Forex Intelligence, shown only when the section is available; DEMO fixtures and live API; the stream reconnects and pauses with the app | `/forex/quotes`, `/forex/candles`, `/forex/indicators`, `/forex/structure`, `/forex/forecasts`, `/forex/opportunities`, `/forex/calendar`, `/forex/risk/calculate`, `/forex/backtests`, `/forex/paper/...`, `WS /forex/stream`; Copilot forex tools (P13-T10) | Reference, or owner for paper trading; flag (DEC-23) | **Code built (P14-T13, live-feed run still to do):** flag-aware entry, single-use WebSocket ticket (`POST /forex/stream-ticket`), Live markets page; and **P14-T24** (advanced workspace, after P13 and the core web modules) | e2e with the simulated feed; paper-trading journey | QG-19 |

## 2. Required by the web brief, on no platform today (planned dependencies)

These are new capabilities, not parity gaps. Each needs backend work first (or a decision) and is delivered to the web, and where useful to mobile, by the listed task.

| # | Capability | Status today | Needs | Task |
|---|---|---|---|---|
| 26 | Reports and exports (PDF, CSV, XLSX): portfolio, performance, net worth, income, FX exposure, goals, forecast; forex strategy reports after P13-T08 | No endpoint on any channel | Backend report service from the same engines, with as-of times and currency on every file (DEC-33) | P14-T15 |
| 27 | Global search across own portfolios, assets, transactions, goals, reports and watchlist | **Built (P14-T07):** `GET /api/v1/search`, owner-scoped: portfolios, goals, liabilities, and the assets you hold, watch or created; command palette (Ctrl/⌘+K) on the web | — | P14-T07 |
| 28 | Net-worth history chart | Current net worth only | **Built (P14-T11):** `GET /net-worth/history`, owner-scoped; assets rebuilt per date, liabilities from the date recorded | P14-T11 |
| 29 | Dashboard customisation (order, visibility, default dashboard) | **Built (P14-T07):** section order and visibility use the existing `dashboard_layout` preference, shared with the mobile Home (DEC-35) | — | P14-T07 |
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
