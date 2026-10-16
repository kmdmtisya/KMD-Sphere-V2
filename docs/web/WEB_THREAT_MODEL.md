# Web portal threat model

**Status:** updated for P14-T19 (2026-10-16). Scope: the Next.js portal and its Backend-for-Frontend (ADR-0018) as built in P14-T01 to T18 and T25. The API's own threat model and controls (ADR-0011 ownership, audit, rate limits) apply unchanged and are not repeated.

## What is protected

| Asset | Where it lives | Why it matters |
|---|---|---|
| The user's tokens (access, refresh) | Redis, sealed with AES-256-GCM, held by the BFF only | Whoever has them acts as the user |
| The session | `__Host-ws_session` cookie (HttpOnly, Secure, SameSite=Lax) pointing at the Redis record | A stolen cookie is a stolen session |
| Financial data | The API; the browser shows what the API returns for the signed-in user | Confidentiality between users |
| The CSRF token | `__Host-ws_csrf` cookie, double-submit with a request header and an Origin check | Prevents forged writes |
| Operator views | `/api/v1/operator/*` behind the `support` role | Must never expose account data |

## Trust boundaries

Browser ⇄ portal server (BFF) ⇄ API ⇄ database; browser ⇄ identity provider (sign-in pages only); browser ⇄ API WebSocket (live quotes, authorised by a single-use ticket). The browser is untrusted. The BFF holds no business logic and forwards only allow-listed `/api/v1/*` paths.

## Threats, controls and the tests that exercise them

| # | Threat | Control | Evidence |
|---|---|---|---|
| S1 | Session theft from the browser (XSS, storage) | Tokens never reach the browser; the session cookie is HttpOnly; nothing sensitive in local or session storage | `auth.spec` (no token visible), `settings.spec` (no JWT in storage), `security.spec` |
| S2 | Replay of a session cookie after sign-out | Sign-out deletes the server-side record; idle (30 min) and absolute (10 h) limits | `auth.spec`, `security.spec` (stolen cookie → 401) |
| S3 | Forged sign-in or open redirect | Authorization Code with PKCE and state checked by `openid-client`; fixed redirect URI from configuration | `auth.spec`, unit tests of the OIDC settings |
| T1 | Cross-site request forgery | Double-submit token plus Origin check on every state-changing proxy request; SameSite=Lax; `form-action` limited | `auth.spec`, `security.spec` (no token, wrong token, foreign Origin → 403) |
| T2 | Tampering with a record someone else changed | `ETag`/`If-Match` → 409, enforced inside the UPDATE | `test_concurrency_api`, `sync.spec` |
| T3 | Open relay through the proxy (SSRF, traversal) | Only `/api/v1/*`, plain path segments, fixed methods, the API host from configuration, bodies capped at 1 MB | allow-list unit tests, `security.spec` |
| R1 | An action that cannot be traced | Audit events for material changes, report generation, AI tool calls and operator access; channel recorded from the token | backend audit tests, `test_operator_api` |
| I1 | One user reading another's data | Ownership checked in the API on every resource; 404 for foreign ids; the web adds no second path to data | IDOR registry and sweep (backend), `security.spec` (13 routes through the portal), per-module cross-user e2e |
| I2 | Secrets in source or logs | Secrets from the environment only; the BFF never logs tokens; secret scanning in CI | `gitleaks` (no leaks across 389 commits), CI security gate |
| I3 | Sensitive data cached by browsers or proxies | `Cache-Control: no-store` on proxied responses and on report downloads | proxy code, `reports.spec` |
| I4 | Information leaked through the Referer | `Referrer-Policy: same-origin` | `security.spec` |
| D1 | Brute force or flooding | API rate limits per user; Keycloak brute-force protection; chat limit of 30 questions a day; WebSocket connection and message limits | backend tests; realm tests |
| E1 | A normal user reaching operator functions | Role read from the verified token on the server; 403; denied attempts audited; the menu entry is only a convenience | `test_operator_api`, `operator.spec` |
| E2 | Cross-site scripting | React output encoding; no HTML rendering of user, asset or assistant text (`react/no-danger` is an error, with one reviewed exception); enforced CSP | `security.spec` (hostile names run nothing), lint self-test, `ai.spec` (assistant text shown as text) |
| E3 | Clickjacking | `frame-ancestors 'none'` and `X-Frame-Options: DENY` | `security.spec` (the portal cannot be framed) |
| E4 | Data exfiltration by injected script | `connect-src` limited to this site and the configured quotes socket; `img-src`, `font-src`, `default-src` self; `form-action` self and the identity provider | `security.spec` (script, request, frame and form to another origin are blocked) |
| E5 | A WebSocket used without authentication | Single-use 30-second ticket, only a hash stored, the token's own expiry, never in a URL | `test_ws_ticket`, `forex.spec` |
| E6 | Spreadsheet formula injection in exports | Text starting with `=`, `+`, `-`, `@` is neutralised in CSV and XLSX; PDF text is escaped | `test_reports_render` |

## Content-Security-Policy

Enforced on every page and route by `src/proxy.ts`: `default-src 'self'`, `script-src 'self' 'unsafe-inline'` (no `unsafe-eval` in production), `style-src 'self' 'unsafe-inline'`, `connect-src 'self'` plus the quotes socket origin, `object-src 'none'`, `base-uri 'self'`, `form-action 'self'` plus the identity provider, `frame-ancestors 'none'`, and `upgrade-insecure-requests` in production over HTTPS. Origins come from the runtime configuration.

## Residual risks and decisions

1. **Inline scripts are allowed (`'unsafe-inline'`).** Next.js emits inline scripts for streaming and page data whose content differs per page and request, so they cannot be allow-listed by hash; a nonce would make every page dynamic, and Partial Prerendering (ADR-0018) cannot give a prerendered shell a nonce. The CSP therefore does not by itself stop an injected inline script. The compensating controls are E2 (no HTML rendering, lint rule) and E4 (an injected script still cannot send data to another origin or load code from one). **Medium residual risk, accepted for now; to be revisited if PPR is dropped (then a nonce-based policy is possible) or if Next.js supports hashing its inline scripts.** The theme boot script is the app's only inline script of its own and contains no input.
2. **Redis holds the sessions.** A Redis compromise exposes sealed tokens; the key (`WS_SESSION_KEY`) is separate. Network isolation and the key's custody are deployment items (P15).
3. **Mobile does not send `If-Match` yet**, so a web edit can still be overwritten by an older mobile edit (and the reverse is refused). Follow-up.
4. **The `support` role is granted outside the application** (an identity administrator). Who may grant it is an operating procedure to settle before production.
5. **Manual review is not replaced by these tests.** A penetration test of the deployed portal is a pre-production activity (P15/P17).

## Dependency and secret scanning

`npm audit --omit=dev` reports 0 vulnerabilities (TD-12 records the dev-only advisory in the lint toolchain's `braces`). The CI security gate runs dependency audits (pip-audit, npm audit, OSV), Trivy, CodeQL and gitleaks on every pull request; a local gitleaks scan of the full history found no leaks.
