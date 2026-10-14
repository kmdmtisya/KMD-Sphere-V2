# ADR-0018: Web portal frontend architecture (DEC-30, DEC-31)

**Status:** Proposed (2026-10-14). Not accepted until the user approves it; until then no web application code is written.

**Context**

The user has asked for a web portal for desktop and laptop browsers. It must have full functional parity with the Android and iOS apps, use the same backend, identity and data, and be a desktop-grade workspace rather than an enlarged phone screen. Two frontend options were compared: Flutter Web, which extends the existing app, and a dedicated Next.js / React / TypeScript application. Option A was assessed against the repository as it is on 2026-10-14 (commit 23d0903), not against Flutter Web in general.

## Evidence from the repository

| Fact | Where | Bearing on the choice |
|---|---|---|
| The Flutter app has no web target (no `web/` folder; never built for the browser) | `mobile/wealthsphere_app` | Option A is also new work, not a switch to flip |
| Sign-in uses `flutter_appauth`, which has no web implementation | `pubspec.yaml`, `lib/core/auth/oidc_client.dart` | Option A has to rewrite the authentication layer either way |
| Tokens are kept in `flutter_secure_storage`; on the web this is browser storage (IndexedDB with a key held in the browser) | `lib/core/auth/token_store.dart` | The requirement is that no long-lived token sits in browser storage. Option A would still need a server-side session (BFF) |
| App lock uses `local_auth`, which has no web implementation | `lib/core/security` | Desktop needs a different app-lock design on either option |
| The encrypted offline cache uses `path_provider` and `dart:io` | `lib/core/offline/snapshot_cache.dart` | Not portable as is; the web would use no offline cache in v1 (see the architecture document) |
| About 27,000 lines of Dart: 8,700 in core and shared code (tokens, 27 components, 3 charts), the rest in 15 feature folders built around a 5-tab phone layout | `lib/` | The reusable part is the design system, DTOs and repositories. Layouts and navigation are phone-shaped and would be re-laid out for desktop on either option |
| Charts use `fl_chart`: line, donut and forecast charts. No candlestick chart and no data grid | `lib/shared/design_system/charts` | The desktop requirements (data grids with column resizing, saved views and keyboard navigation; candlestick charts) are new on either option |
| The backend authenticates bearer tokens only; CORS is off by default and allows explicit origins only; the Keycloak realm has a public mobile client and the API client | `app/core/auth.py`, `app/core/config.py`, `infra/keycloak/realm-export.json` | A web client needs a new Keycloak client. A BFF can call the API with bearer tokens unchanged, with no CORS opening |
| The API is OpenAPI 3.1, exported and Spectral-linted in CI (`backend/openapi.json`) | `scripts/export_openapi.py`, `.spectral.yaml` | A typed TypeScript client can be generated from it and checked in CI |
| Brand colours and measured-contrast shades live in Dart (`brand_palette.dart`, `wealth_colors.dart`), guarded by a style test | `lib/shared/design_system/tokens` | Tokens can be moved to one JSON source that generates both the Dart palette and CSS variables |

## Comparison

Each option is scored for this repository: ++ strong, + adequate, − weak.

| Criterion | A: Flutter Web | B: Next.js + TypeScript |
|---|---|---|
| Code reuse | + design system, DTOs, repositories and l10n reused; screens re-laid out | − UI rebuilt. Business logic is not duplicated, because it is on the backend; the API client is generated |
| Functional parity | + the same widgets, but desktop forms of every screen are needed | + built against the same API; a parity matrix and contract tests enforce it |
| Long-term maintenance | ++ one UI codebase | − two UI codebases (mitigated by shared tokens, the generated client and the parity matrix) |
| Desktop UX quality | − canvas rendering: browser find, text selection, copy from tables, right-click and middle-click behave unlike web pages | ++ native web: tables, links, selection, keyboard and browser features |
| Charts and financial visualisation | − `fl_chart` only; no maintained open candlestick or financial chart for Flutter | ++ mature libraries: Apache ECharts, and TradingView Lightweight Charts (Apache-2.0) for candlesticks |
| Data grids | − no mature open grid (the strongest one is a commercial licence) | ++ TanStack Table: headless, open, virtualised |
| Authentication | − rewrite plus a BFF anyway | ++ BFF in the same Next.js server; HttpOnly cookies; tokens never reach the browser |
| Accessibility (WCAG 2.2 AA target) | − the screen reader works through a separate semantics tree; harder to audit with standard tools | ++ semantic HTML; axe and Playwright audits in CI |
| Performance (Lighthouse at least 85, LCP at most 2.5 s) | − the CanvasKit and Wasm engine download is several MB before first paint; target unlikely on the first visit | ++ server rendering and route splitting; targets are realistic |
| Testing | + the same test style as mobile | ++ Vitest, Testing Library, Playwright across Chrome, Edge, Firefox and Safari engines |
| Hosting cost | + static files only, but still needs a BFF server for sessions | + one small Node container behind the same ingress as the API |
| Security | − token handling would have to be redone; CSP is harder because of the engine's runtime code loading | ++ strict CSP with nonces, CSRF tokens, SameSite cookies |
| Developer productivity | + one language | + the most common web stack; agents and developers are productive in it |

## Decision (proposed)

**Option B: a dedicated Next.js (App Router) / React / TypeScript web portal with a Backend-for-Frontend, in `web/` beside `backend/` and `mobile/`.** The reasons, in order:

1. **Desktop UX.** The requirements (data grids, candlestick and multi-panel charts, keyboard use, browser behaviour) are met by mature web libraries and not by Flutter on canvas.
2. **Measurable targets.** WCAG 2.2 AA and the performance targets are realistic on B and doubtful on A.
3. **Security.** Option A needs a BFF and a new authentication layer too, so it loses most of its reuse advantage exactly where risk is highest.

### What stays single-sourced (no drift)

- **Business logic and calculations:** only on the backend. The web, like the app, formats values and never computes financial truth. A lint rule and a test forbid arithmetic on money values in `web/`, mirroring the Flutter style guard.
- **API contract:** a typed client is generated from `backend/openapi.json` (`openapi-typescript`). CI fails if the generated client is out of date or a call does not type-check.
- **Design tokens:** brand and semantic tokens move to `design/tokens/wealthsphere.tokens.json`. It generates the Dart palette (checked by the existing contrast and style tests) and CSS variables for the web.
- **Copy and disclosures:** the server's notices (not advice, DEMO, simulated, stale) are shown as sent, never rewritten. The web's own strings sit in one message catalogue with a key-parity check against `app_en.arb`.
- **Parity:** `docs/web/CROSS_PLATFORM_FEATURE_PARITY_MATRIX.md` and an automated check that every mobile route has a web route or a recorded exception.

### Stack (to confirm in P15-T02)

| Area | Choice |
|---|---|
| Framework and language | Next.js (App Router), React, TypeScript in strict mode |
| Styling | Tailwind CSS on generated CSS-variable tokens |
| Components | Radix UI primitives (accessible, unstyled) |
| Data | TanStack Query for server state; TanStack Table for grids |
| Charts | Apache ECharts for portfolio charts; TradingView Lightweight Charts for candlesticks (attribution kept as its licence requires) |
| Decimal display | `decimal.js` for formatting decimal strings only, never for calculating |
| Tests | Vitest, Testing Library, Playwright, axe-core, Lighthouse CI |

Exact versions are pinned in P15-T04 after a licence and dependency audit (the `security gate` covers `npm audit`, licences and secret scanning).

### Session model (DEC-31): Backend-for-Frontend

- **Client.** The Next.js server is a confidential OIDC client (`wealthsphere-web`) using Authorization Code with PKCE. Its secret is in the secret store, never in the repository.
- **Tokens.** Access and refresh tokens are kept server-side in Redis, encrypted. The browser holds only an opaque session ID in an HttpOnly, Secure, SameSite=Lax, host-only (`__Host-`) cookie.
- **API calls.** The BFF forwards `/api/*` to FastAPI with the bearer token. The API stays the only authority: it verifies the token, its audience and the authorised party (`wealthsphere-web` is added to `OIDC_AUTHORIZED_PARTIES`), and enforces ownership on every call. The BFF holds no business rules.
- **CSRF and headers.** Every state-changing request needs a CSRF token header (double submit) on top of SameSite. CSP uses nonces, plus the existing security headers.
- **Session lifetime.** Idle and absolute session timeouts follow the realm. Logout ends the Keycloak session (RP-initiated logout). MFA is enforced by Keycloak as for mobile.
- **Streaming.** The chat stream (server-sent events) is proxied as a stream. The forex WebSocket gets a short-lived, single-use ticket minted by the BFF (P15-T13), because the browser cannot send the bearer token and the token must not go in a URL.

## Consequences

- **Benefits**
  - A desktop-native workspace that can meet the accessibility, performance and browser targets.
  - A session model where tokens never reach browser JavaScript.
  - An independent web deployment lifecycle.
  - No change to business rules or financial engines.
- **Costs**
  - A second UI codebase (TypeScript) to maintain beside Flutter.
  - A Node runtime to host.
  - Every new feature needs a web implementation, tracked in the parity matrix.
  - A small backend change: the web client in Keycloak and its authorised party; later, export and admin endpoints if approved.
- **Mitigation**
  - Generated client, generated tokens, catalogue-parity check and parity-matrix check in CI.
  - New mobile features are not "done" until the matrix records their web status.
- **Rejected alternative:** Flutter Web. Reconsider it only if the desktop requirements are relaxed to the phone layouts. It would still need the BFF.
- **Superseded parts of earlier documents:** `SOLUTION_INTENT.md` section 4 ("Future Web") and the phrase "shared Flutter design system". The design system is shared through tokens, not through Flutter widgets on the web.
