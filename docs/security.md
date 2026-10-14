# Security Requirements and Controls

Derived from CLAUDE.md (Security Rules), `SOLUTION_INTENT.md` section 23 and the implementation guide section 12. The threat model is [threat-model.md](threat-model.md) and findings are tracked in [security-findings.md](security-findings.md) (P04-T09).

## Principles
- Cross-user portfolio access is a critical security failure.
- Authorization is enforced server-side on every protected resource; the client is never trusted.
- Security controls are never weakened to fix an error.

## Controls

| Area | Requirement | Planned in |
|---|---|---|
| Identity | Keycloak, OIDC Authorization Code + PKCE, MFA, email verification, password policy | P04-T01 |
| Tokens | Short-lived access tokens, refresh rotation; stored only in secure mobile storage (see "Mobile session tokens" below) | P04-T06 |
| App access | Biometric unlock, lock on background/timeout (see "App lock" below) | P04-T07 |
| Authorization | Ownership checks on every resource; IDOR tests per endpoint | P04-T03, P05-T09 |
| API protection | Rate limiting, brute-force controls, input limits, security headers (see "API protection" below) | P04-T05 |
| Audit | Append-only audit events for financial changes and AI/tool activity (see "Audit events" below) | P04-T04 |
| Secrets | Never in source control; `.env` is git-ignored; secret manager in cloud; CI uses OIDC, not long-lived keys | P01-T05, P15-T06 |
| Transport / storage | TLS 1.2+ (prefer 1.3); encryption at rest | P15 |
| Logging | No secrets or unnecessary financial payloads in logs; redaction filter with tests | P01-T12 |
| Supply chain | Secret scanning, dependency and container scanning, SAST, SBOM | P01-T11 |
| Backups | Encrypted backups, restore tests, documented RPO/RTO | P15-T10 |
| Privacy | Consent, retention, export and account deletion | P16-T05 |
| Reviews | OWASP API Security Top 10, OWASP MASVS, penetration test | P16 |

## Secrets handling (current)
- Local development values live in `.env` (ignored by git); only `.env.example` with placeholders is committed.
- Provider and LLM keys are read from the environment or a secret manager, never from code, and never logged.

## Data classification
| Class | Examples | Handling |
|---|---|---|
| Restricted | credentials, tokens, API keys | secret storage only; never logged |
| Confidential | holdings, balances, transactions, goals | authorised access only; minimal logging; encrypted at rest |
| Internal | aggregated non-identifying metrics | access controlled |
| Public | marketing content, published disclosures | none |

## Reporting
Security issues: see `SECURITY.md` (added in P01-T11).

## Authorization and IDOR tests (ADR-0011)

- Query user data only through `owned_by(Model, user.id)` from `app/core/authz.py`; repeat `user_id = :user` in every `UPDATE`/`DELETE`.
- A resource that is not the caller's answers **404**, identical to a missing one; **403** is only for a visible resource and a missing permission.
- Never accept an owner or `user_id` in a request body.
- For every route with an id in its path, write a cross-user test with `tests/authz_harness.py`:

```python
from tests.authz_harness import TwoUsers, assert_hidden_from, two_users  # noqa: F401

async def test_bob_cannot_read_alices_goal(http, two_users: TwoUsers) -> None:
    goal = await http.post("/api/v1/goals", headers=two_users.alice.headers, json={...})
    await assert_hidden_from(http, two_users.bob, "GET", f"/api/v1/goals/{goal.json()['id']}")
```

  then register it in `tests/idor_registry.py`. `tests/test_idor_coverage.py` fails CI for any id route without a registered test.

## Audit events (P04-T04)

Material financial changes, security-relevant changes and AI tool activity emit an audit event through `AuditWriter` in `app/core/audit.py`:

```python
await AuditWriter(session).record(
    "portfolio.transaction.created",          # <module>.<resource>.<verb>, lower-case
    Actor.user(user.id),                       # Actor.ai(user.id) for AI tool calls, Actor.system() for jobs
    resource_type="transaction",
    resource_id=tx.id,
    details={"changed": ["quantity"]},         # redacted before storage
)
await session.commit()                         # the change and its event commit together
```

- **Append-only.** The database rejects `UPDATE`, `DELETE` and `TRUNCATE` on `audit_events` (triggers in migration 0003); the ORM refuses to flush a change to or deletion of a loaded event; the writer has no update or delete method.
- **Same transaction.** Record the event before `commit()`; if the event cannot be written the change is rolled back too.
- **Correlation.** Each event stores the request's correlation ID (`X-Correlation-ID`), linking it to logs and traces.
- **Redaction.** `details` pass through `app.core.redaction.redact`: credentials, tokens and financial values (amounts, prices, balances and so on) are replaced with `[REDACTED]`; floats are never stored; details over 8 KiB are reduced to their key names. Store field names and resource ids, not amounts; the resource's own append-only history holds the values.
- **AI tool calls** store `hash_arguments(arguments)`, not the arguments (docs/ai-governance.md).
- **No foreign key to users**, so the trail outlives the rows it describes. Retention and account-deletion handling are defined in P16-T05 (privacy: export, deletion, retention). In deployed environments the application database role should not own `audit_events` (P16 hardening), so it cannot disable the triggers.

## API protection (P04-T05)

| Control | Setting (default) | Behaviour |
|---|---|---|
| Sign-in brute force | Keycloak realm: 5 failures, temporary lockout 1 to 15 minutes, never permanent | Wrong passwords and wrong TOTP codes count. Passwords never reach the API. |
| Auth routes (`/api/v1/auth/*`) | 10 requests / 60 s per client IP | Stricter than any other budget. |
| Failed authentication | 10 failures (401) / 300 s per client IP | Once spent, **every** request from that IP gets 429 until the window ends, so tokens cannot be guessed. |
| General API | 600 requests / 60 s per client IP | Flood ceiling; health and metrics probes are exempt. |
| Per account | 120 requests / 60 s per verified subject | Applied in `current_user` after the token is verified, before any database work. |
| Request body | 1 MiB | 413 by `Content-Length`, or while streaming a chunked body. A malformed length is refused. |
| CORS | Off | Only explicit https origins may be configured (`CORS_ALLOWED_ORIGINS`); no wildcard, no credentials. |

- Exceeding a budget returns **429** problem+json (`type .../rate-limited`) with `Retry-After` in whole seconds; mobile clients wait at least that long before retrying.
- Counters are fixed windows in Redis (`ws:rl:<budget>:<sha256>`; raw IPs and user ids are not stored). If Redis is unavailable, each process keeps its own counters and the outage is logged: limits stay on, they are never skipped.
- The client IP is the direct peer. Behind a proxy or load balancer, run uvicorn with `--proxy-headers --forwarded-allow-ips=<proxy>` (P15); `X-Forwarded-For` is never trusted directly.
- Every response carries `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Cross-Origin-Resource-Policy: same-origin`, `Permissions-Policy`, `Cache-Control: no-store` and a deny-all `Content-Security-Policy` (except Swagger UI, which is disabled in production). Staging and production add `Strict-Transport-Security`.

### Forex stream WebSocket (P13-T02)

The REST budgets above do not apply to WebSockets. `/api/v1/forex/stream` has its own controls (details in `docs/design/forex-market-data.md` section 5):

- **Authentication.** The first frame must authenticate, within 5 s, using the same OIDC access token as REST. The token is never accepted in the URL. A disabled account is refused. When the token expires, the socket is closed with code 4401.
- **Limits per verified subject.** At most 3 sockets, 20 pairs per socket and 60 client messages a minute. Frames are capped at 4 KiB.
- **Cross-site risk.** The stream carries only public reference prices, and no cookie authenticates it, so a cross-site page cannot ride a session.

## Analytics cache (P06-T09)

- Analytics answers are cached in Redis under keys that contain the requesting user's id, and only after the route has authorised the request. A cached answer is never read back for another user, and refused requests store nothing (tests: `tests/test_analytics_api.py`, `tests/test_cache.py`).
- Any successful write by a user invalidates their cached answers before the response is sent (a per-user generation counter). Entries also expire after `analytics_cache_seconds` (300).
- Cached answers hold financial figures, so Redis must stay internal and password-protected, with TLS in deployed environments (P15). If Redis is down, answers are computed without it.
- Design: docs/design/analytics-api.md.

## Mobile session tokens (P04-T06)

- **Sign-in:** Authorization Code + PKCE (S256) through AppAuth in the system browser; public client, no secret on the device; no `offline_access` scope. iOS uses an ephemeral browser session, so no SSO cookie outlives sign-out.
- **Storage:** tokens live only in `flutter_secure_storage` (Android Keystore-encrypted storage; iOS Keychain `first_unlock_this_device`, not synced). Android backup and device transfer are disabled for the app. Shared preferences hold UI preferences only.
- **Refresh:** `TokenManager` refreshes 30 s before expiry, one refresh at a time, and persists the rotated refresh token immediately (Keycloak revokes the old one). On a 401 the API client refreshes once and retries once.
- **Session end:** a refused refresh (expired or revoked session) clears the tokens and signs out; so does the API refusing a freshly refreshed token (for example, a disabled account). A network failure during refresh fails the request but keeps the session for when the device is back online.
- **Sign-out:** tokens are deleted from the device first, then the Keycloak session is ended (`/protocol/openid-connect/logout` with the refresh token), best effort.
- **No leaks:** there is no HTTP logging interceptor; `TokenSet`, `AuthException` and `ApiException` print no token; UI state never holds tokens. Tests assert tokens never appear in printed output or errors.
- **Transport:** release builds require https; debug builds allow plain HTTP only to loopback development hosts.

## App lock (P04-T07)

- **When:** only while signed in, and on by default (users can turn it off after verifying themselves). The app locks when a stored session is restored at start-up, when it returns from the background after the chosen timeout (immediately, 1 minute or 5 minutes; immediately by default), and after 5 minutes without a touch. A fresh sign-in is not locked again. If the device clock moved backwards while away, the app locks.
- **Unlock:** `local_auth` with biometrics and the device PIN/pattern/passcode as the platform fallback. Only a successful check unlocks; a failed, cancelled or locked-out check leaves the app locked with a plain message. Without any device security, the lock screen offers only **Sign out** (sign in again with Keycloak). The prompt opens once when the lock engages; after a failure the user taps Unlock, so resume events never loop it.
- **While locked:** the app is offstage (not painted, not hit-testable, hidden from screen readers, animations paused) behind the lock screen; navigation state is kept.
- **Settings:** turning the lock off or changing the timeout needs a successful device check first. On a device that cannot verify anyone, the lock can only be turned off.
- **App switcher:** while the app is inactive a privacy cover replaces its content, so the Recents/app-switcher snapshot shows no financial data. Android 13+ also disables the Recents screenshot (`setRecentsScreenshotEnabled(false)`).
- **Platform:** Android `MainActivity` is a `FlutterFragmentActivity` with AppCompat themes and `USE_BIOMETRIC`; iOS declares `NSFaceIDUsageDescription`.

## Sign-in screens (P04-T08)

- **No credentials in the app.** Screen 2 collects at most an optional email to pre-fill the hosted page (`login_hint`, validated). Passwords, TOTP codes, registration (`prompt=create`) and password reset happen only on Keycloak's pages; two-step verification is set up there too (`kc_action=CONFIGURE_TOTP`, from More > Account). The reset link is built from configuration only.
- **Non-leaking errors.** Failures show one of a few fixed messages (cannot reach the sign-in service / sign-in did not complete / session ended); nothing names the account, provider error codes or tokens. Cancelling shows nothing.
- **Biometric offer.** After the first sign-in on a device, a one-time sheet offers the app lock: turning it on needs a successful device check; "Not now" turns it off (an explicit choice right after a full sign-in). Devices without a screen lock are told that returning will require signing in again.
- **DEMO mode.** "Explore with DEMO data" continues without an account; everything shown is labelled DEMO.

## Market data: key custody, terms and logs (P08-T09)

Reviewed 2026-10-12 against the code on `main` after P08-T08. Automated checks that keep these findings true: `backend/tests/market_data/test_security_review.py` and `TestKeysNeverLeak` in `test_adapters.py`. No real provider key exists yet (none was created); the checks run against stand-in values.

### Key custody (P08-T09.1)
- Keys (`COINGECKO_API_KEY`, `TWELVEDATA_API_KEY`) are `SecretStr` settings read from the environment. They are unwrapped in two places only: the adapters' header builders (`coingecko.py`, `twelvedata.py`) and `registry.py`, which merely tests whether one is set. A provider with no key is not built; one built without a key refuses to call (`ProviderAuthError`).
- Keys travel in request headers (`x-cg-demo-api-key` or `x-cg-pro-api-key`; `Authorization: apikey ...`), never in URLs or query strings, so they cannot appear in transport errors or access logs. The transport wrapper reduces any HTTP failure to its type name.
- Adapter `repr` shows no key; errors name the provider and the HTTP or body status code, never the response body. Tests feed responses that echo the key (401, 403, 500, error bodies, invalid JSON) and assert it appears in no exception, `repr` or captured log, for both CoinGecko and Twelve Data.
- `.env.example` documents both variables with empty values (tested). No compose file or source file assigns them. Deployed environments must inject them from a secret manager (P15); until then they live only in an untracked `.env`.
- Jobs take identifiers only (asset id, dates), never keys, so Celery task arguments, `job_runs` keys and `job_failures` rows hold no secret.
- Gaps: there is no custom gitleaks rule for these two key shapes (the default rules and the empty example file are the control). Add rules once real keys exist. Key rotation is not automated; rotation means changing the secret and restarting workers.

### Terms and redistribution (P08-T09.2)
The licence position is in ADR-0014 section 4 and `docs/market-data-providers.md`. Nothing here confirms a licence.

| Provider | Used for | Finding |
|---|---|---|
| ECB reference rates | FX conversion | Published "for information purposes only". The API now labels every rate `data_type: indicative_rate` (added in this review; previously only the docstring said so). The ECB copyright page was not read; reuse terms still need confirming. |
| CoinGecko | Crypto prices | Demo plan is attribution-required and not a commercial licence; "Data provided by CoinGecko" with a link is required on paid plans, and the app does not show it yet. Production needs a paid plan plus that attribution (open item for P09 and P12). |
| Twelve Data | Listed prices, FX gaps | Individual plans are personal, internal and non-commercial. **Not usable in production** without a commercial or display licence. |
| Fake | Development and tests | Synthetic, labelled DEMO. |

- Redistribution control: provider data reaches users only as per-user values with provenance (holdings and summary valuations, watchlist latest price, `GET /api/v1/fx-rates/{base}/{quote}`), all behind authentication. There is no bulk, search, history or public price endpoint, and a test fails if a route mentioning prices, quotes, rates or markets is added without updating the reviewed list, which forces a licence check first.
- Storage: prices and rates are stored with provider, as-of and ingestion times (needed for audit and valuation). Whether storing history is allowed depends on the unsigned licences.
- Forex (P13-T02): `GET /api/v1/forex/quotes`, `GET /api/v1/forex/candles` and the stream were reviewed and added to the list. They serve only the in-house simulated feed (DEC-19, fixture-only), so no third-party data is shown. A real forex feed is blocked by QG-20.1 until its streaming, display and redistribution licence is reviewed.
- **Result:** no provider term is known to be violated in the current code because no real provider is enabled. Production use stays blocked until the licences in ADR-0014 are confirmed in writing.

### Log review (P08-T09.3)
- Our log lines in `app/modules/market_data` and `app/worker`: the warning for partially failed ingestion (counts only), job failure lines (job name, task id, exception type), and failures to record or dead-letter a failure. None prints arguments, response bodies, URLs or messages from providers.
- Failure records (`job_failures`, `IngestFailure`) keep the error type and a truncated message of our own wording.
- Celery's own task logs include task arguments and exception text. Redaction only removes credential-shaped values. This is acceptable only because tasks never receive secrets or personal data; keep it that way (`docs/design/jobs.md`).
- Prometheus labels hold job names only.

### Residual risks and follow-ups
1. Licences unconfirmed for every real provider (blocks production, tracked in ADR-0014).
2. CoinGecko attribution not yet shown in the app.
3. ECB reuse terms not read.
4. Custom gitleaks rules for provider keys, and secret-manager injection (P15).
5. The synthetic CoinGecko and Twelve Data fixtures must be re-recorded against the real services once keys exist, and the key checks repeated with a real key.

## Offline cache (P09-T06, ADR-0015)
- Saved API answers are encrypted at rest (AES-256-GCM, random 256-bit key in Keychain / Android Keystore via `flutter_secure_storage`), stored per user under hashed folder and file names, and never hold tokens.
- Sign-out and session end wipe every saved file and the key; in-memory data is dropped at once (data epoch). Tests: `test/core/offline/offline_cache_test.dart` (no plaintext amounts, ids or paths on disk; one user cannot read another's; wipe removes files and key; a different key cannot decrypt).
- Saved data is served only when the device cannot reach the server; authorization and server errors are never masked.
