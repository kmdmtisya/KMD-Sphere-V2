# Developer environment

Verified on Windows 11 on 2026-10-09 (task P01-T01).

| Tool | Version | Notes |
|---|---|---|
| Flutter / Dart | 3.47.5 / 3.13.4 | `flutter doctor`: all sections OK |
| Android SDK | platform 36, build-tools 28.0.3 and 36.0.0 | licences accepted; installed with `sdkmanager` |
| Android emulators | `Pixel_8_Pro`, `Medium_Phone_API_36` | `flutter emulators --launch Pixel_8_Pro` |
| Python / uv | 3.14.5 / 0.12.20 | backend needs Python 3.13+ |
| Docker | 29.5.3 | Docker Desktop must be running (`docker info`) |
| Terraform | 1.16.5 | installed with winget; open a new shell to pick up PATH |
| Git / gh / Node / make | 2.56.0 / 2.101 / 24.16 / 4.4.1 | |

iOS cannot be built on Windows. CI compiles it on macOS (P01-T10); device QA needs a Mac or cloud device.

## Quick checks

```bash
flutter doctor          # all [√]
docker info             # server answers
terraform version
python --version && uv --version
flutter emulators --launch Pixel_8_Pro
```

## Local stack (P01-T05)

```bash
cp .env.example .env     # then replace every CHANGE_ME (dev values only; .env is git-ignored)
make up                  # docker compose up -d --wait
make ps | make logs | make down | make reset   # reset DESTROYS local data volumes
```

| Service | Host port (default) | Notes |
|---|---|---|
| PostgreSQL 17 + pgvector | 5433 | databases `wealthsphere` and `keycloak`; extensions `vector`, `pgcrypto` |
| Redis 7 | 6380 | password required |
| RabbitMQ 4 | 5673 (AMQP), 15673 (management UI) | |
| Keycloak 26.4 (start-dev) | 8081 (health on 9001) | realm and client are configured in P04-T01 |

Host ports differ from the usual defaults so the stack can run beside other local services. Override them in `.env`. All ports bind to 127.0.0.1 only.

## Mobile app

```bash
cd mobile/wealthsphere_app
flutter pub get && flutter gen-l10n
dart format --output=none --set-exit-if-changed . && flutter analyze && flutter test
flutter build apk --debug && flutter install -d emulator-5554
```
The first Android build also needs NDK 28.2.13676358 (`sdkmanager --install "ndk;28.2.13676358"`).

## Keycloak development realm

`docker compose up` imports `infra/keycloak/realm-export.json` (realm `wealthsphere`) on first start. Import skips a realm that already exists: after changing realm-level settings in the file, run `python scripts/keycloak_dev.py sync-realm` (applies policies, lifetimes and brute-force settings; not clients, roles or users). For other changes, remove the realm in the admin console (or recreate the Keycloak database) and restart the container.

- Mobile client `wealthsphere-mobile`: public, Authorization Code + PKCE (S256) only; implicit and password grants are off. Redirect URI `com.kmdmtisya.wealthsphere:/oauth2redirect`. Access tokens carry the audience `wealthsphere-api` and live 5 minutes; refresh tokens rotate.
- Password policy: 12+ characters with upper, lower, digit and symbol, not the username or email, last 5 not reusable. New accounts must verify their email. TOTP MFA is available; enforcing it for every account is decided before production (P04-GATE).
- Brute-force detection: 5 failed sign-ins (wrong password or TOTP code) lock the account temporarily, starting at 1 minute and growing to at most 15 minutes; never permanently, so nobody can disable someone else's account by guessing. Clear a dev lockout under Users > (user) or with the admin API.
- Test users `alice@example.test`, `bob@example.test` (two users for cross-user tests) and `mfa@example.test` (must enrol TOTP) are imported **without passwords**. Set `KEYCLOAK_TEST_USER_PASSWORD` in `.env`, then:

```
python scripts/keycloak_dev.py seed-users   # set passwords; reset the MFA user's enrolment
python scripts/keycloak_dev.py smoke        # PKCE, rejected grants, TOTP, brute-force lockout
```

## Backend authentication

The API verifies Keycloak access tokens (RS256, issuer, audience `wealthsphere-api`, expiry, authorised party `wealthsphere-mobile`) against the realm's JWKS. Set `OIDC_ISSUER` in `.env` to the realm URL exactly as it appears in the token's `iss` claim (locally `http://127.0.0.1:8081/realms/wealthsphere`). With no issuer configured every protected endpoint answers 401.

Rate limits use Redis (`RATE_LIMIT_*` settings in `app/core/config.py`; see docs/security.md "API protection"). Set `RATE_LIMIT_ENABLED=false` only for local load experiments.

A user row is created on the first valid request (`GET /api/v1/me`). `PATCH /api/v1/me/preferences` updates display name, base currency, locale, time zone and UI preferences.

## Mobile sign-in against the local stack

The app signs in with Authorization Code + PKCE in the system browser (Custom Tabs / ASWebAuthenticationSession) and calls the API with the resulting access token. Defaults target the local stack; override with `--dart-define=WS_API_BASE_URL=...` and `--dart-define=WS_OIDC_ISSUER=...` (release builds require https).

1. Start the stack and the API (`docker compose up -d`, then `cd backend && uv run uvicorn app.main:app --port 8000`), with `OIDC_ISSUER=http://127.0.0.1:8081/realms/wealthsphere` in `.env`.
2. Android emulator or USB device: forward the ports so `127.0.0.1` on the device is your machine and the token issuer matches the API's `OIDC_ISSUER`:
   ```
   adb reverse tcp:8000 tcp:8000
   adb reverse tcp:8081 tcp:8081
   ```
   The iOS simulator shares the host's network; nothing to forward.
3. Run the app, open **More > Account > Sign in**, and sign in as a seeded test user. The card shows the account as the API reports it (`GET /api/v1/me`).

App lock: a restored session opens locked. On an emulator without a screen lock the lock screen offers only Sign out; set one with `adb shell locksettings set-pin <pin>` (remove it with `adb shell locksettings clear --old <pin>`), or turn app lock off under More > Account.

Plain HTTP is allowed only to `127.0.0.1`, `localhost` and `10.0.2.2`, and only in debug builds (Android `src/debug` network security config; iOS `NSAllowsLocalNetworking`). A fresh emulator's Chrome shows its first-run screen on the first sign-in; dismiss it once.
