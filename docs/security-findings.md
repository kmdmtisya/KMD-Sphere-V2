# Security Findings Register

Security-relevant issues found while building and testing WealthSphere, with status. Severities use the impact on users' data if exploited in a release build: Critical / High / Medium / Low / Info. Started at P04-T09 (2026-10-10); later phases append. The threat model is [threat-model.md](threat-model.md).

Status values: **Fixed** (fix merged and tested), **Open** (owner and phase set), **Decision** (needs a user decision), **Accepted** (risk accepted with a reason).

## Fixed

| ID | Severity | Finding | Found | Fix | Evidence |
|---|---|---|---|---|---|
| SF-01 | Medium | Android auto-backup was on (platform default), so the app's encrypted token storage could be backed up or moved to another device, where it cannot be decrypted, and app data could leave the device | P04-T06 review | `allowBackup=false`, `fullBackupContent=false`, data-extraction rules excluding all domains for cloud backup and device transfer | PR #36; manifest and `data_extraction_rules.xml` |
| SF-02 | Medium | `android:taskAffinity=""` on the main activity breaks the AppAuth redirect back into the app's task (sign-in could fail or land in the wrong task) | P04-T06 (plugin guidance) | Attribute removed | PR #36; emulator sign-in |
| SF-03 | Low | The main Android manifest had no `INTERNET` permission (only the debug manifest did), so release builds could not reach the API or identity provider | P04-T06 review | Permission added to the main manifest | PR #36 |
| SF-04 | Low | App lock: re-prompting on every resume would loop on iOS, where the Face ID sheet itself makes the app inactive and then resumed (users stuck in a prompt loop) | P04-T07 mutation testing | Prompt only when the lock engages; after a failure the user taps Unlock; regression test | PR #37; `app_lock_gate_test` |
| SF-05 | Low | App lock: a biometric result arriving after sign-out could put a lock screen over a signed-out app | P04-T07 mutation testing | Late results are ignored unless the prompt is still current; regression test | PR #37 |
| SF-06 | Low | Rate-limit tests shared Redis counters across test modules, so the failure-lockout path could pass or fail by accident rather than by design | P04-T05 | Tests use per-app counters; the Redis store has its own live test | PR #35 |
| SF-07 | Info | Mobile emulator could not complete sign-in against the API because the token issuer (`127.0.0.1`) differed from the emulator's host alias (`10.0.2.2`) | P04-T06 | Use `adb reverse` so both sides use `127.0.0.1`; documented | docs/dev-setup.md |

## Open

SF-10 is an accepted risk, kept here so it is revisited at P15.

| ID | Severity | Finding | Owner / phase | Notes |
|---|---|---|---|---|
| SF-10 | High | TOTP MFA is optional: a stolen password alone signs in to accounts without TOTP | Accepted for now (user decision, 2026-10-10: keep optional) | Revisit before P15 release readiness; options remain: require TOTP for all accounts, or before real financial data is linked |
| SF-11 | Medium | iOS Keychain storage and Face ID have not been exercised on an iPhone or simulator (no macOS in this environment); covered by unit tests and the CI iOS compile only | Deferred by the user on 2026-10-10 under waiver of QG-05.4 (expires 2026-12-31); must be verified on an iPhone or simulator before any iOS release (P16) | Needs a macOS machine or a cloud device run |
| SF-12 | Medium | Per-IP rate limits depend on correct client-IP attribution behind the load balancer | P14 | uvicorn `--proxy-headers --forwarded-allow-ips`; never trust `X-Forwarded-For` directly |
| SF-13 | Medium | The application database role owns `audit_events`, so it could disable the append-only triggers | P15 | Separate least-privilege runtime role without ownership or `TRIGGER` privilege |
| SF-14 | Low | No certificate pinning; no root/jailbreak or tamper signals | P15 (MASVS review) | Decide with the threat of compromised devices in mind |
| SF-15 | Low | Android 8 to 12 rely on the in-app privacy cover for the Recents snapshot (only 13+ disables the screenshot) | P15 | Consider `FLAG_SECURE` while locked or on sensitive screens |
| SF-16 | Info | The local gitleaks binary is missing on the development machine, so commits skip the local hook (`SKIP=gitleaks`); CI gitleaks runs on every PR over full history | Developer setup | Install gitleaks locally |
| SF-17 | Info | Development Keycloak and API run over HTTP | P14 | Release builds refuse non-HTTPS endpoints already |
| SF-18 | Medium | iOS keeps Keychain items after the app is deleted, so a reinstalled app could restore a previous session | Deferred with SF-11 (same waiver); verify with the delete-and-reinstall check | Verify on an iPhone/simulator; fix is to clear stored tokens on the first launch after an install |
